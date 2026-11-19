#!/usr/bin/env python3
"""
==============================================================================
 VKU Agentic AI Controller (Linux OSS 2026)
 Connects LLMs (Ollama Local Hybrid Tool Execution + Dynamic Command Inference /
 Gemini API / Autonomous Reasoner) with Native C++ MCP Server
 Author: VKU OSS Team
==============================================================================
"""

import sys
import os
import json
import subprocess
import urllib.request
import urllib.error
import re
import unicodedata


def normalize_vietnamese(text):
    if not text:
        return "", ""
    nfc = unicodedata.normalize("NFC", text).lower().strip()
    nfd = unicodedata.normalize("NFD", nfc)
    unaccented = (
        "".join(c for c in nfd if unicodedata.category(c) != "Mn")
        .replace("đ", "d")
        .replace("Đ", "d")
    )
    return nfc, unaccented


# ANSI Color formatting
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
MAGENTA = "\033[95m"
BLUE = "\033[94m"
RESET = "\033[0m"

BIN_PATH = os.path.join(os.path.dirname(__file__), "..", "bin", "vku_mcp_server")
if sys.platform == "win32" and not os.path.exists(BIN_PATH):
    BIN_PATH += ".exe"

# Force UTF-8 encoding with replacement to prevent crashes from Vietnamese Unikey/IME glitches in SSH terminals
if hasattr(sys.stdin, "reconfigure"):
    try:
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


class MCPServerBridge:
    def __init__(self, binary_path):
        if not os.path.exists(binary_path):
            raise FileNotFoundError(
                f"Binary not found: {binary_path}. Please compile with 'make'."
            )

        # Đẩy stderr sang DEVNULL để tránh deadlock khi C++ ghi log vượt 64KB pipe buffer
        self.proc = subprocess.Popen(
            [binary_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self.request_id = 0
        self.server_info = {}
        self._initialize()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _send_rpc(self, method, params=None):
        if self.proc.poll() is not None:
            raise RuntimeError("MCP Server process is not running.")

        self.request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
        }
        if params is not None:
            payload["params"] = params

        req_line = json.dumps(payload) + "\n"
        self.proc.stdin.write(req_line)
        self.proc.stdin.flush()

        resp_line = self.proc.stdout.readline()
        if not resp_line:
            raise RuntimeError("MCP Server terminated unexpectedly.")

        resp = json.loads(resp_line)
        if resp.get("id") != self.request_id:
            raise RuntimeError(
                f"JSON-RPC ID mismatch: expected {self.request_id}, got {resp.get('id')}"
            )
        if "error" in resp:
            err = resp["error"]
            raise RuntimeError(
                f"MCP RPC Error ({err.get('code')}): {err.get('message')}"
            )
        return resp

    def _initialize(self):
        resp = self._send_rpc("initialize", {})
        self.server_info = resp.get("result", {}).get("serverInfo", {})

    def list_tools(self):
        resp = self._send_rpc("tools/list", {})
        return resp.get("result", {}).get("tools", [])

    def call_tool(self, name, arguments=None):
        params = {"name": name, "arguments": arguments or {}}
        resp = self._send_rpc("tools/call", params)
        content = resp.get("result", {}).get("content", [])
        if content and isinstance(content[0], dict) and "text" in content[0]:
            return content[0]["text"]
        return json.dumps(resp.get("result", {}), ensure_ascii=False)

    def close(self):
        if not self.proc:
            return
        try:
            if self.proc.stdin and not self.proc.stdin.closed:
                self.proc.stdin.close()
            if self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    self.proc.wait()
        except Exception:
            pass


class AgenticController:
    SYSTEM_INSTRUCTION = (
        "Bạn là công cụ báo cáo kỹ thuật Linux (không phải chatbot trò chuyện).\n"
        "Nhiệm vụ: Đọc [Dữ liệu thực tế từ C++ MCP Server] và xuất báo cáo ngắn gọn, đầy đủ bằng tiếng Việt theo dạng gạch đầu dòng.\n"
        "Kết thúc bằng một câu nhận xét khẳng định. Cấm dùng dấu hỏi chấm (?) và cấm đặt câu hỏi cho người dùng."
    )

    COMMAND_INFER_PROMPT = (
        "You are a Linux command translator. "
        "If the user asks for live information from the current Linux server (e.g., IP address, top processes, kernel/OS version, logged-in users, hostname, network interfaces, files, environment), "
        "reply with ONLY ONE short read-only Linux shell command (no explanation, no markdown, no backticks). "
        "Examples:\n"
        "- 'IP của máy là gì?' -> ip -br a\n"
        "- 'Tiến trình nào tốn CPU nhất?' -> ps aux --sort=-%cpu | head -n 6\n"
        "- 'Ai đang đăng nhập?' -> who\n"
        "- 'Phiên bản Ubuntu là gì?' -> lsb_release -a\n"
        "If the user is just greeting, chatting, or asking a general theory question, reply with exactly: NONE"
    )

    SUPPORTED_SERVICES = ["nginx", "ssh", "ufw", "docker", "mysql", "postgresql", "apache2", "cron"]

    def __init__(self, bridge, api_key=None):
        self.bridge = bridge
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.qwen_host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
        self.default_model = os.environ.get("QWEN_MODEL", "qwen2.5:1.5b")

        self.tools = self.bridge.list_tools()
        # Cache model 1 lần khi khởi tạo
        self.active_model = self._detect_ollama_model()
        # Lịch sử hội thoại sạch (không chứa dữ liệu telemetry thừa)
        self.chat_history = []

    def clear_history(self):
        """Xóa toàn bộ lịch sử hội thoại để giải phóng bộ nhớ context và bắt đầu phiên mới"""
        self.chat_history.clear()
        print(
            f"  {CYAN}[Session] Đã xóa toàn bộ lịch sử hội thoại (Context Reset to 0).{RESET}"
        )

    def _detect_ollama_model(self):
        try:
            req = urllib.request.Request(f"{self.qwen_host}/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name", "") for m in data.get("models", [])]
                if not models:
                    return self.default_model
                for target in ["1.5b", "0.5b", "qwen"]:
                    for m in models:
                        if target in m.lower():
                            return m
                return models[0]
        except Exception:
            return self.default_model

    @staticmethod
    def _safe_json(raw_str):
        try:
            return json.loads(raw_str)
        except Exception:
            return {"raw": raw_str}

    @staticmethod
    def _strip_trailing_questions(text):
        """Loại bỏ triệt để các câu hỏi ngược / câu hỏi gợi ý thừa ở cuối câu trả lời của model nhỏ."""
        if not text:
            return text
        lines = text.strip().splitlines()
        while lines and lines[-1].strip().endswith("?"):
            parts = re.split(r"(?<=[.!])\s+", lines[-1].strip())
            kept = [p for p in parts if not p.strip().endswith("?")]
            if kept:
                lines[-1] = " ".join(kept)
                break
            lines.pop()
        return "\n".join(lines).strip()

    def _infer_linux_command(self, user_query):
        """
        Dùng Qwen Local dịch câu hỏi hệ thống ngoài intent sang 1 lệnh Linux duy nhất.
        Trả về chuỗi lệnh hoặc None nếu chỉ là trò chuyện bình thường.
        """
        payload = {
            "model": self.active_model,
            "messages": [
                {"role": "system", "content": self.COMMAND_INFER_PROMPT},
                {"role": "user", "content": user_query},
            ],
            "stream": False,
            "keep_alive": "60m",
            "options": {
                "num_predict": 40,
                "temperature": 0.0,
            },
        }
        try:
            req = urllib.request.Request(
                f"{self.qwen_host}/api/chat",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                raw = (
                    res_data.get("message", {}).get("content")
                    or res_data.get("response")
                    or ""
                ).strip()
        except Exception:
            return None

        # Làm sạch markdown / backtick nếu model lỡ bọc
        cmd = raw.splitlines()[0].strip().strip("`\"' ")
        if cmd.startswith("$ "):
            cmd = cmd[2:].strip()

        # Bỏ qua nếu là NONE, rỗng, quá dài, hoặc chứa ký tự không phải ASCII (câu trả lời tiếng Việt)
        if not cmd or cmd.upper() == "NONE" or len(cmd) > 120 or not cmd.isascii():
            return None
        return cmd

    def format_telemetry_for_ai(self, raw_json_str):
        """Chuyển đổi JSON thô của get_system_health thành bản tóm tắt dễ đọc cho model 1.5B."""
        data = self._safe_json(raw_json_str)
        if "memory" not in data:
            return raw_json_str

        mem = data.get("memory", {})
        cpu = data.get("cpu_load", {})
        disk = data.get("disk_root", {})
        proc_cnt = data.get("process_count", "N/A")
        uptime = data.get("uptime", {}).get("formatted", "N/A")

        return (
            f"- RAM: Đang dùng {mem.get('used_mb')} MB / {mem.get('total_mb')} MB ({mem.get('used_percentage')}%), "
            f"Còn trống {mem.get('free_mb')} MB, Khả dụng {mem.get('available_mb')} MB, Buff/Cache {mem.get('buff_cache_mb')} MB.\n"
            f"- CPU Load Average: 1m={cpu.get('load_1min')}, 5m={cpu.get('load_5min')}, 15m={cpu.get('load_15min')}.\n"
            f"- Ổ cứng (/): Đã dùng {disk.get('used_gb')} GB / {disk.get('total_gb')} GB ({disk.get('used_percentage')}%), "
            f"Còn khả dụng {disk.get('available_gb')} GB.\n"
            f"- Tiến trình: {proc_cnt} tiến trình | Uptime: {uptime}."
        )

    def _match_intent(self, user_input):
        """
        Bộ phân tích Intent dùng chung (DRY) theo thứ tự ưu tiên chuẩn:
        Help -> Logs -> Sandbox Command -> Network Ports -> Systemd Services -> Telemetry.
        """
        _, plain = normalize_vietnamese(user_input)

        def has_any(keywords):
            return any(normalize_vietnamese(kw)[1] in plain for kw in keywords)

        # 1. Help / Menu
        if has_any(["chức năng", "làm được gì", "tác dụng", "hỏi gì", "giúp", "help", "menu", "hướng dẫn"]):
            return "help", None, {}

        # 2. Inspect Logs (đặt TRƯỚC service để 'xem log ssh/nginx' không bị nhầm sang manage_service)
        if has_any(["log", "nhật ký", "journal", "lỗi hệ thống"]):
            source = "syslog"
            if "nginx" in plain:
                source = "nginx"
            elif "auth" in plain or "ssh" in plain:
                source = "auth"
            elif "journal" in plain:
                source = "journal"

            num_match = re.search(r"\b(\d{1,3})\b", plain)
            lines = min(max(int(num_match.group(1)), 1), 100) if num_match else 10
            return "logs", "inspect_logs", {"log_source": source, "lines": lines}

        # 3. Sandboxed Command Execution (dùng regex cắt prefix an toàn)
        cmd_match = re.match(
            r"^(?:chạy lệnh|chay lenh|exec|command|lệnh|lenh)\s+(.+)$",
            user_input.strip(),
            re.IGNORECASE,
        )
        if cmd_match or plain.startswith(("df ", "free", "uname", "ls", "rm ", "cat ", "whoami", "mkdir ", "touch ", "pwd", "tree ", "echo ")):
            cmd = cmd_match.group(1).strip() if cmd_match else user_input.strip()
            if "~" in cmd:
                cmd = " ".join(os.path.expanduser(p) for p in cmd.split())
            return "exec", "execute_safe_command", {"command": cmd}

        if has_any(["tạo thư mục", "tao thu muc", "tạo folder", "tao folder"]):
            raw_target = user_input.strip()
            for p in ["tạo thư mục", "tao thu muc", "tạo folder", "tao folder"]:
                idx = user_input.lower().find(p)
                if idx != -1:
                    raw_target = user_input[idx + len(p):].strip()
                    break

            # Bóc tách cú pháp: "<tên> trong/ở/tại <thư mục>" (ví dụ: 'demo trong /home/cill')
            match_loc = re.search(r"^(.*?)\s+(?:trong|ở|tai|tại|in)\s+(/[^\s]+|~[^\s]*|[^\s]+)$", raw_target, re.IGNORECASE)
            if match_loc:
                name = match_loc.group(1).strip()
                parent_dir = match_loc.group(2).strip()
                full_path = os.path.join(parent_dir, name)
            else:
                full_path = raw_target.strip()

            full_path = os.path.expanduser(full_path.strip("'\""))
            cmd = f"mkdir -p '{full_path}'"
            return "exec", "execute_safe_command", {"command": cmd}

        if has_any(["tạo file", "tao file"]):
            raw_target = user_input.strip()
            for p in ["tạo file", "tao file"]:
                idx = user_input.lower().find(p)
                if idx != -1:
                    raw_target = user_input[idx + len(p):].strip()
                    break

            match_loc = re.search(r"^(.*?)\s+(?:trong|ở|tai|tại|in)\s+(/[^\s]+|~[^\s]*|[^\s]+)$", raw_target, re.IGNORECASE)
            if match_loc:
                name = match_loc.group(1).strip()
                parent_dir = match_loc.group(2).strip()
                full_path = os.path.join(parent_dir, name)
            else:
                full_path = raw_target.strip()

            full_path = os.path.expanduser(full_path.strip("'\""))
            cmd = f"touch '{full_path}'"
            return "exec", "execute_safe_command", {"command": cmd}

        # 4. Network Ports Audit
        if has_any(["cổng", "port", "socket", "listening", "quét cổng", "rà soát"]):
            return "ports", "audit_network_ports", {}

        # 5. Service Management
        if has_any(self.SUPPORTED_SERVICES + ["dịch vụ", "service", "systemctl"]):
            service = "nginx"
            for svc in self.SUPPORTED_SERVICES:
                if svc in plain:
                    service = svc
                    break

            action = "status"
            if has_any(["khởi động lại", "restart", "reload"]):
                action = "restart"
            elif has_any(["bật", "start", "khởi chạy"]):
                action = "start"
            elif has_any(["tắt", "stop", "dừng"]):
                action = "stop"
            return "service", "manage_service", {"service_name": service, "action": action}

        # 6. Telemetry (CPU / RAM / Disk / Uptime / General Health)
        if has_any(["cpu", "tải cpu", "load avg", "mức tải", "nhiệt độ", "temp"]):
            return "cpu", "get_system_health", {}
        if has_any(["ram", "bộ nhớ", "memory"]):
            return "ram", "get_system_health", {}
        if has_any(["ổ cứng", "disk", "dung lượng", "ổ đĩa", "storage", "hdd", "ssd"]):
            return "disk", "get_system_health", {}
        if has_any(["uptime", "chạy bao lâu", "bật bao lâu", "thời gian hoạt động"]):
            return "uptime", "get_system_health", {}
        if has_any(["sức khỏe", "tài nguyên", "hệ thống", "tổng quan", "health", "tình trạng", "status", "server", "máy chủ"]):
            return "health", "get_system_health", {}

        return "chat", None, {}

    def call_qwen_local_api(self, user_query, context_data=None):
        """
        Gọi Qwen Local qua Ollama (/api/chat - 100% Offline).
        Dữ liệu tool chỉ đính kèm cho lượt hiện tại, KHÔNG nhồi vào lịch sử chat dài hạn.
        """
        current_user_content = user_query
        if context_data:
            current_user_content = (
                f"Yêu cầu: {user_query}\n\n"
                f"[Dữ liệu thực tế từ C++ MCP Server]:\n{context_data}\n\n"
                f"Hãy tóm tắt đầy đủ kết quả trên và kết thúc ngay, không hỏi thêm."
            )

        messages = (
            [{"role": "system", "content": self.SYSTEM_INSTRUCTION}]
            + self.chat_history[-10:]
            + [{"role": "user", "content": current_user_content}]
        )

        payload = {
            "model": self.active_model,
            "messages": messages,
            "stream": False,
            "keep_alive": "60m",
            "options": {
                "num_predict": 350,
                "temperature": 0.2,
            },
        }

        req = urllib.request.Request(
            f"{self.qwen_host}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        with urllib.request.urlopen(req, timeout=120) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            raw_answer = (
                res_data.get("message", {}).get("content")
                or res_data.get("response")
                or ""
            ).strip()

            answer = self._strip_trailing_questions(raw_answer)

            if answer:
                self.chat_history.append({"role": "user", "content": user_query})
                self.chat_history.append({"role": "assistant", "content": answer})

            return answer, self.active_model

    def call_gemini_api(self, prompt, context_data=None):
        """[NOTE DỰ PHÒNG] Calls Google Gemini Cloud API qua HTTP Header."""
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
        full_prompt = prompt
        if context_data:
            full_prompt += f"\n\n[Real-time Linux Telemetry from C++ MCP Server]:\n{context_data}"

        payload = {
            "contents": [{"parts": [{"text": full_prompt}]}],
            "systemInstruction": {"parts": [{"text": self.SYSTEM_INSTRUCTION}]},
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
        )

        with urllib.request.urlopen(req, timeout=15) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            return res_data["candidates"][0]["content"]["parts"][0]["text"]

    def autonomous_reason(self, user_input, pre_executed=None):
        """
        Built-in Intelligent Reasoner (Fallback): Chạy offline dưới 1ms.
        Tái sử dụng kết quả tool nếu đã gọi trước đó để không gọi C++ MCP 2 lần.
        """
        if pre_executed:
            intent, tool_name, args, raw_output = pre_executed
        else:
            intent, tool_name, args = self._match_intent(user_input)
            raw_output = self.bridge.call_tool(tool_name, args) if tool_name else None

        if intent == "help":
            return (
                "🤖 CÁC TÁC DỤNG & CÂU HỎI BẠN CÓ THỂ HỎI TRỢ LÝ AI VKU:\n"
                "  1. 📈 Hiệu suất & Tải CPU: 'Kiểm tra CPU', 'CPU load average'\n"
                "  2. 🧠 Bộ nhớ RAM: 'RAM còn bao nhiêu', 'Phân tích RAM'\n"
                "  3. 💾 Dung lượng Ổ cứng: 'Ổ cứng còn trống bao nhiêu', 'Kiểm tra disk'\n"
                "  4. ⏱️ Thời gian hoạt động: 'Máy đã chạy bao lâu', 'Uptime'\n"
                "  5. ⚙️ Quản lý dịch vụ: 'Trạng thái NGINX', 'Restart NGINX', 'Bật SSH'\n"
                "  6. 🛡️ Rà soát cổng mạng: 'Quét cổng mạng', 'Kiểm tra port listening'\n"
                "  7. 📜 Đọc nhật ký hệ thống: 'Đọc syslog', 'Xem 20 dòng log nginx', 'Log ssh'\n"
                "  8. ⛔ Thử nghiệm Sandbox: 'chạy lệnh rm -rf /tmp/data', 'chạy lệnh uname -a'\n"
                "  9. 📊 Sức khỏe tổng quát: 'Kiểm tra sức khỏe hệ thống', 'Tình trạng server'"
            )

        if not tool_name:
            return (
                "Tôi là Trợ lý AI Quản trị Linux VKU. Các yêu cầu hỗ trợ:\n"
                "  • 'Phân tích RAM', 'Kiểm tra CPU', 'Kiểm tra ổ cứng'\n"
                "  • 'Kiểm tra trạng thái NGINX', 'Quét cổng mạng', 'Đọc System Logs'\n"
                "  • 'chạy lệnh uname -a' hoặc hỏi trực tiếp thông tin hệ thống."
            )

        data = self._safe_json(raw_output)

        if intent == "exec":
            if data.get("allowed") is False:
                return (
                    f"⛔ [CẢNH BÁO SANDBOX BẢO MẬT VI PHẠM]\n"
                    f"  • Lệnh bị chặn : {args['command']}\n"
                    f"  • Mã vi phạm   : {data.get('violation', 'N/A')}\n"
                    f"  • Lý do        : {data.get('reason', 'Không được phép')}\n"
                    f"  ➔ Hệ thống MCP C++ đã bảo vệ Ubuntu khỏi nguy cơ phá hoại!"
                )
            out = (data.get("output") or "").strip()
            if not out:
                out = "✓ Lệnh đã được thực thi thành công (Exit code: 0)."
            return f"💻 Thực Thi Lệnh Thành Công ({args['command']}):\n{out}"

        if intent == "service":
            return (
                f"⚙️ Kết Quả Thao Tác Dịch Vụ Systemd:\n"
                f"  • Dịch vụ   : {args['service_name']}\n"
                f"  • Thao tác  : {args['action'].upper()}\n"
                f"  • Trạng thái: {str(data.get('active_state', 'unknown')).upper()}\n"
                f"  • Exit Code : {data.get('exit_code', 'N/A')}\n"
                f"  • Phản hồi  : {(data.get('output') or '').strip()}"
            )

        if intent == "ports":
            return (
                f"🛡️ Kết Quả Rà Soát Cổng Mạng (Security Audit):\n"
                f"{(data.get('raw_sockets') or '').strip()}\n\n"
                f"  ➔ Khuyến nghị: {data.get('recommendation', 'N/A')}"
            )

        if intent == "logs":
            return (
                f"📜 Nhật Ký Hệ Thống ({args['log_source']} - {args['lines']} dòng):\n"
                f"{(data.get('log_content') or '').strip()}"
            )

        mem = data.get("memory", {})
        disk = data.get("disk_root", {})
        cpu = data.get("cpu_load", {})
        uptime = data.get("uptime", {}).get("formatted", "N/A")
        os_name = data.get("os_info", {}).get("sysname", "Linux")

        if intent == "cpu":
            l1 = cpu.get("load_1min", 0)
            eval_str = "Mức tải CPU rất thấp, hệ thống phản hồi mượt mà." if l1 < 2.0 else "Mức tải CPU tương đối cao."
            return (
                f"📈 Báo Cáo Hiệu Suất CPU (/proc/loadavg):\n"
                f"  • 1 phút: {l1} | 5 phút: {cpu.get('load_5min', 0)} | 15 phút: {cpu.get('load_15min', 0)}\n"
                f"  ➔ Đánh giá: {eval_str}"
            )

        if intent == "ram":
            pct = mem.get("used_percentage", 0)
            eval_str = "RAM ổn định, hệ thống vận hành mượt mà." if pct < 80 else "RAM đang ở mức cao! Cần lưu ý."
            return (
                f"🧠 Báo Cáo Bộ Nhớ RAM:\n"
                f"  • Đang sử dụng : {mem.get('used_mb', 0)} MB / {mem.get('total_mb', 0)} MB ({pct}%)\n"
                f"  • Còn trống    : {mem.get('free_mb', 0)} MB | Khả dụng: {mem.get('available_mb', 0)} MB\n"
                f"  • Buff/Cache   : {mem.get('buff_cache_mb', 0)} MB\n"
                f"  ➔ Đánh giá     : {eval_str}"
            )

        if intent == "disk":
            pct = disk.get("used_percentage", 0)
            eval_str = "Dung lượng ổ cứng còn an toàn." if pct < 85 else "Ổ cứng sắp đầy! Cần dọn dẹp."
            return (
                f"💾 Báo Cáo Dung Lượng Ổ Cứng (/):\n"
                f"  • Đã sử dụng   : {disk.get('used_gb', 0)} GB / {disk.get('total_gb', 0)} GB ({pct}%)\n"
                f"  • Còn khả dụng : {disk.get('available_gb', 0)} GB\n"
                f"  ➔ Đánh giá     : {eval_str}"
            )

        if intent == "uptime":
            return (
                f"⏱️ Thời Gian Hoạt Động Hệ Thống:\n"
                f"  • Uptime: {uptime} | Tiến trình: {data.get('process_count', 'N/A')} | OS: {os_name}"
            )

        return (
            f"📊 Báo Cáo Tình Trạng Hệ Thống ({os_name} - Uptime: {uptime}):\n"
            f"  • RAM  : {mem.get('used_mb')}MB / {mem.get('total_mb')}MB ({mem.get('used_percentage')}%)\n"
            f"  • Disk : {disk.get('used_gb')}GB / {disk.get('total_gb')}GB ({disk.get('used_percentage')}%)\n"
            f"  • CPU  : {cpu.get('load_1min')} (1m) | {cpu.get('load_5min')} (5m) | {cpu.get('load_15min')} (15m)"
        )

    def process_query(self, user_query):
        # 1. Phân tích ý định cố định (nhanh, chính xác 100%)
        intent, tool_name, args = self._match_intent(user_query)

        # 2. Nếu ngoài intent cố định -> nhờ Qwen tự dịch sang lệnh Linux an toàn để chạy qua Sandbox
        if not tool_name and intent == "chat":
            inferred_cmd = self._infer_linux_command(user_query)
            if inferred_cmd:
                print(f"  {MAGENTA}[AI Command Inference] -> '{inferred_cmd}'{RESET}")
                intent = "exec"
                tool_name = "execute_safe_command"
                args = {"command": inferred_cmd}

        raw_output = None
        context = None

        if tool_name:
            print(f"  {YELLOW}[Tool Call] ⚡ vku_mcp_server -> {tool_name}({args}){RESET}")
            raw_output = self.bridge.call_tool(tool_name, args)
            if tool_name == "get_system_health":
                context = self.format_telemetry_for_ai(raw_output)
            else:
                context = f"Công cụ '{tool_name}' ({args}) đã chạy và trả về:\n{raw_output}"

        # 3. Đưa kết quả thực tế cho Qwen Local phân tích và trả lời ngay (100% Offline)
        qwen_err_msg = None
        try:
            qwen_res, model_used = self.call_qwen_local_api(user_query, context)
            if qwen_res:
                print(f"  {GREEN}[AI Engine] -> Processed by Qwen Local ({model_used}){RESET}")
                return f"{qwen_res}\n\n🤖 [Model: {model_used} Local | 100% Offline]"
        except Exception as e:
            qwen_err_msg = str(e)
            print(f"  {YELLOW}[Notice] Qwen Local chưa gọi được ({e}). Tự động dùng VKU Reasoner dự phòng.{RESET}")

        # 4. Fallback: VKU Autonomous Reasoner (tái sử dụng raw_output đã gọi)
        print(f"  {YELLOW}[AI Engine] -> Processed by VKU Autonomous Reasoner (Sub-ms Engine){RESET}")
        res = self.autonomous_reason(user_query, pre_executed=(intent, tool_name, args, raw_output))
        clean_res = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", res)
        err_note = f" (Chi tiết lỗi Qwen: {qwen_err_msg})" if qwen_err_msg else ""
        return f"{clean_res}\n\n⚡ [Engine: VKU Autonomous Reasoner | Sub-millisecond{err_note}]"


def interactive_session():
    print(f"\n{CYAN}{BOLD}======================================================================{RESET}")
    print(f"{CYAN}{BOLD}   [VKU OSS 2026] AGENTIC AI LINUX ADMINISTRATION INTERFACE{RESET}")
    print(f"{CYAN}{BOLD}   Topic 15: Build & Configure MCP Server for Agentic AI in Linux{RESET}")
    print(f"{CYAN}{BOLD}   Core Engine: C++17 POSIX (Native Linux Integration){RESET}")
    print(f"{CYAN}{BOLD}======================================================================{RESET}")

    EXIT_COMMANDS = {"exit", "quit", "q", "thoát", "thoat", "tạm biệt", "tam biet"}
    CLEAR_COMMANDS = {"clear", "/clear", "reset", "/reset", "cls", "xóa", "xoa"}

    def clean_terminal_input(raw_str):
        cleaned = re.sub(r"\x1b\[[0-9;?]*[a-zA-Z~]", "", raw_str)
        chars = []
        for c in cleaned:
            if c in ("\b", "\x08", "\x7f"):
                if chars:
                    chars.pop()
            else:
                chars.append(c)
        return unicodedata.normalize("NFC", "".join(chars).strip())

    def safe_read_line(prompt_text):
        try:
            sys.stdout.write(prompt_text)
            sys.stdout.flush()
            if hasattr(sys.stdin, "buffer"):
                raw_bytes = sys.stdin.buffer.readline()
                if not raw_bytes:
                    return "exit"
                decoded = raw_bytes.decode("utf-8", errors="replace")
                return clean_terminal_input(decoded)
            return clean_terminal_input(input())
        except (EOFError, KeyboardInterrupt):
            return "exit"
        except Exception:
            return ""

    try:
        with MCPServerBridge(BIN_PATH) as bridge:
            agent = AgenticController(bridge)
            print(f"{GREEN}[OK] Native C++ MCP Server connected successfully! Protocol: 2024-11-05{RESET}")
            print(f"Available Tools: {len(agent.tools)} active C++ tools registered.")
            print(f"Active Local Model: {agent.active_model}\n")
            print("Gõ câu hỏi bằng Tiếng Việt hoặc Tiếng Anh (Gõ 'clear' để làm mới chat, 'exit' để thoát).\n")

            while True:
                try:
                    prompt = safe_read_line(f"{BOLD}{BLUE}VKU-SysAdmin > {RESET}")
                    if not prompt:
                        continue

                    clean_p = prompt.strip().lower()

                    if clean_p in EXIT_COMMANDS:
                        print(f"{YELLOW}Đang đóng phiên làm việc... Tạm biệt!{RESET}")
                        break

                    if clean_p in CLEAR_COMMANDS:
                        agent.clear_history()
                        print(f"{CYAN}Đã xóa lịch sử hội thoại thành công! Bắt đầu phiên chat mới.{RESET}\n")
                        continue

                    print(f"{CYAN}[AI Thinking...] 🧠{RESET}")
                    response = agent.process_query(prompt)
                    print(f"\n{GREEN}{BOLD}[AI Agent Response]:{RESET}\n{response}\n")

                except KeyboardInterrupt:
                    print(f"\n{YELLOW}Đang đóng phiên làm việc... Tạm biệt!{RESET}")
                    break
                except Exception as ex:
                    print(f"{RED}[Error]: {ex}{RESET}\n")

    except Exception as e:
        print(f"{RED}[ERROR] Failed to start C++ MCP Server: {e}{RESET}")
        sys.exit(1)


if __name__ == "__main__":
    interactive_session()