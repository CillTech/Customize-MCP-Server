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


# Chuẩn hóa chuỗi tiếng Việt (có dấu & không dấu) để nhận diện từ khóa lệnh chính xác hơn
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


# Cầu nối giao tiếp JSON-RPC 2.0 qua stdin/stdout với C++ MCP Server
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

        # Gửi payload JSON-RPC 2.0 qua stdin tới tiến trình C++ MCP Server và đọc 1 dòng phản hồi từ stdout
        req_line = json.dumps(payload) + "\n"
        self.proc.stdin.write(req_line)
        self.proc.stdin.flush() # Đẩy dữ liệu ngay lập tức qua pipe, tránh bị kẹt trong bộ đệm

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


# Bộ điều khiển AI Agent: kết nối LLM (Ollama Qwen / Gemini / Offline Reasoner) với các Tool MCP
class AgenticController:
    SYSTEM_INSTRUCTION = (
        "Bạn là Trợ lý AI Quản trị Hệ thống Linux thông minh, trò chuyện tự nhiên và súc tích bằng tiếng Việt.\n"
        "Khi có dữ liệu thực tế từ hệ thống, hãy nêu rõ các thông số hoặc trạng thái vừa ghi nhận, "
        "kèm 1–2 nhận xét kỹ thuật ngắn gọn và chốt bằng 1 dòng kết luận về tình trạng hiện tại.\n"
        "Khi người dùng hỏi tiếp nối hoặc trao đổi thêm, hãy dựa vào ngữ cảnh cuộc trò chuyện trước đó để trả lời liền mạch, tự nhiên như một đoạn chat.\n"
        "Đi thẳng vào trọng tâm, không dài dòng hướng dẫn từng bước và không hỏi ngược lại người dùng."
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

    SUPPORTED_SERVICES = ["nginx", "ssh", "docker", "mysql", "postgresql", "apache2", "cron"]

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

    @staticmethod
    def _strip_unsolicited_guides(text):
        """Cắt bỏ phần hướng dẫn từng bước hoặc danh sách lệnh terminal nếu model nhỏ tự sinh thêm khi phân tích hệ thống."""
        if not text:
            return text
        guide_marker = re.search(
            r"(?im)^\s*(?:"
            r"để\s+(?:kích hoạt|bật|tắt|cài đặt|kiểm tra|cấu hình|điều chỉnh|xử lý|khắc phục|sử dụng|thực hiện|bảo vệ)[^\n]*(?:bước sau|lệnh sau|:)"
            r"|bạn có thể (?:sử dụng|dùng|thực hiện) các (?:lệnh|bước) sau"
            r"|dưới đây là các (?:bước|lệnh)"
            r"|các bước thực hiện"
            r"|```"
            r")",
            text,
        )
        if guide_marker and guide_marker.start() > 40:
            cleaned = text[: guide_marker.start()].strip()
            if cleaned:
                return cleaned
        return text

    @staticmethod
    def _clean_cjk_leaks(text):
        """Loại bỏ các ký tự Hán/Trung vô tình lọt vào câu trả lời của model đa ngữ nhỏ."""
        if not text:
            return text
        cleaned = re.sub(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]+", "", text)
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
        cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
        return cleaned.strip()

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

    def format_tool_context(self, tool_name, args, raw_output):
        """Chuyển JSON thô từ C++ MCP Server thành ngữ cảnh tiếng Việt rõ ràng cho LLM nhỏ."""
        if tool_name == "get_system_health":
            return self.format_telemetry_for_ai(raw_output)

        data = self._safe_json(raw_output)
        if tool_name == "check_firewall_status":
            state = data.get("ufw_state", "unknown")
            state_vi = (
                "ĐANG TẮT (inactive - UFW chưa bật bảo vệ)"
                if state == "inactive"
                else (
                    "ĐANG BẬT (active - UFW đang hoạt động lọc gói tin)"
                    if state == "active"
                    else "CHƯA XÁC ĐỊNH"
                )
            )
            raw = (data.get("raw_output") or "").strip()
            note = data.get("note", "")
            meta_lines = []
            rule_lines = []
            for ln in raw.splitlines():
                s = ln.strip()
                if not s or s.startswith("--") or s.lower().startswith(("to ", "status:")):
                    continue
                if not s.lower().startswith("default:") and any(k in s.upper() for k in ("ALLOW", "DENY", "REJECT", "LIMIT")):
                    rule_lines.append("  " + re.sub(r"\s{2,}", " | ", s))
                else:
                    meta_lines.append(s)

            ctx = (
                f"Kết quả kiểm tra tường lửa UFW thực tế:\n"
                f"- Trạng thái: {state_vi}\n"
            )
            if meta_lines:
                ctx += "- Cấu hình chung: " + " ; ".join(meta_lines) + "\n"
            if rule_lines:
                ctx += "- Các rule/cổng đang cấu hình:\n" + "\n".join(rule_lines) + "\n"
            if note:
                ctx += f"- Ghi chú: {note}"
            return ctx.strip()

        if tool_name == "manage_firewall_rule":
            success = data.get("success", False)
            action = args.get("action")
            target = args.get("target", "ufw")
            status_vi = "THÀNH CÔNG" if success else "THẤT BẠI"
            out = (data.get("output") or data.get("error") or "").strip()
            note = data.get("note", "")
            if action == "disable":
                act_desc = "TẮT tường lửa UFW"
                state_desc = "Tường lửa UFW hiện ĐÃ TẮT (inactive)." if success else "Không thể tắt UFW."
            elif action == "enable":
                act_desc = "BẬT tường lửa UFW"
                state_desc = "Tường lửa UFW hiện ĐÃ BẬT (active)." if success else "Không thể bật UFW."
            else:
                act_desc = f"Cập nhật rule UFW ({action} {target})"
                state_desc = f"Đã áp dụng {action} {target}." if success else f"Không thể áp dụng {action} {target}."
            ctx = (
                f"Hành động: {act_desc} -> {status_vi}\n"
                f"- Trạng thái sau khi chạy: {state_desc}\n"
                f"- Chi tiết output:\n{out}"
            )
            if note:
                ctx += f"\n- Ghi chú: {note}"
            return ctx

        if tool_name == "manage_workspace":
            ok = data.get("success", False)
            action = args.get("action", "")
            path = data.get("path") or args.get("path", ".")
            if data.get("allowed") is False:
                return (
                    f"Thao tác Workspace ({action} trên '{path}') BỊ SANDBOX TỪ CHỐI.\n"
                    f"- Mã vi phạm: {data.get('violation', 'N/A')}\n"
                    f"- Lý do: {data.get('error', 'Vi phạm chính sách bảo mật Workspace/Nội dung')}"
                )
            lines = [f"Thao tác Workspace ({action}) trên 'Customize-MCP-Server/{path}': {'THÀNH CÔNG' if ok else 'THẤT BẠI'}"]
            if data.get("content_audit"):
                lines.append(f"- Kiểm duyệt nội dung Sandbox: {data.get('content_audit')}")
            if "entries" in data:
                items = [f"{e['name']} ({e['type']})" for e in data.get("entries", [])[:25]]
                lines.append(f"- Danh sách ({data.get('count', 0)} mục): {', '.join(items) if items else '(Thư mục trống)'}")
            if "content" in data:
                lines.append(f"- Nội dung file:\n{data.get('content', '')[:1200]}")
            if "output" in data:
                lines.append(f"- Kết quả chạy (exit_code={data.get('exit_code')}):\n{(data.get('output') or '').strip()}")
            if data.get("error"):
                lines.append(f"- Lỗi: {data.get('error')}")
            return "\n".join(lines)

        return f"Công cụ '{tool_name}' ({args}) đã chạy và trả về:\n{raw_output}"

    @staticmethod
    def _extract_workspace_path_and_content(user_input, prefixes):
        """Tách đường dẫn và nội dung (nếu có) từ câu lệnh tiếng Việt cho manage_workspace."""
        text = user_input.strip()
        lower = text.lower()
        body = text
        for p in sorted(prefixes, key=len, reverse=True):
            idx = lower.find(p)
            if idx != -1:
                body = text[idx + len(p):].strip()
                break

        content = ""
        m_content = re.search(
            r"\s+(?:với\s+nội\s+dung|voi\s+noi\s+dung|nội\s+dung|noi\s+dung|thành\s+nội\s+dung|thanh\s+noi\s+dung|thành|thanh|content)\s*[:=]?\s*(.+)$",
            body,
            re.IGNORECASE | re.DOTALL,
        )
        if m_content:
            content = m_content.group(1).strip()
            if len(content) >= 2 and content[0] == content[-1] and content[0] in ("'", '"'):
                content = content[1:-1]
            body = body[: m_content.start()].strip()

        match_loc = re.search(
            r"^(?:(.*?)\s+)?(?:trong|ở|tai|tại|in)\s+([^\s]+)$",
            body,
            re.IGNORECASE,
        )
        if match_loc:
            name = (match_loc.group(1) or "").strip(" '\"")
            parent = os.path.expanduser(match_loc.group(2).strip(" '\""))
            if parent.rstrip("/") in ("Customize-MCP-Server", "."):
                path = name or "."
            else:
                path = os.path.join(parent, name) if name else parent
        else:
            path = os.path.expanduser(body.strip(" '\":"))

        if path.rstrip("/") == "Customize-MCP-Server":
            path = "."
        return path or ".", content

    def _match_intent(self, user_input):
        """
        Bộ phân tích Intent dùng chung (DRY) hỗ trợ đủ 14 MCP Tools theo thứ tự ưu tiên:
        Help -> Agentic AI Tools -> Security & Firewall -> Logs -> Sandbox Command -> Ports -> Services -> Telemetry.
        """
        _, plain = normalize_vietnamese(user_input)

        def has_any(keywords):
            return any(normalize_vietnamese(kw)[1] in plain for kw in keywords)

        # 1. Help / Menu
        if has_any(["chức năng", "làm được gì", "tác dụng", "hỏi gì", "giúp", "help", "menu", "hướng dẫn"]):
            return "help", None, {}

        # 1.5 Hội thoại tiếp nối / hỏi tác động, lý do, đánh giá -> trả lời theo ngữ cảnh đoạn chat, KHÔNG chạy nhầm tool
        explicit_action_start = plain.startswith((
            "chạy ", "chay ", "tạo ", "tao ", "thêm ", "them ",
            "sửa ", "sua ", "xóa ", "xoa ", "đọc ", "doc ",
            "kiểm tra", "kiem tra", "xem ", "mở ", "mo ",
            "đóng ", "dong ", "chặn ", "chan ", "bật ", "bat ",
            "tắt ", "tat ", "quét ", "quet ", "rà soát", "ra soat",
            "liệt kê", "liet ke", "thu thập", "thu thap",
            "dừng ", "dung ", "giết ", "giet ", "tìm ", "tim ", "ping ",
        ))
        is_discussion = has_any([
            "ảnh hưởng gì", "ảnh hưởng như thế nào", "ảnh hưởng thế nào", "ảnh hưởng đến", "ảnh hưởng tới",
            "tác động gì", "tác động thế nào", "tác động đến", "tác động tới",
            "có sao không", "có nguy hiểm", "có rủi ro", "có nên", "có ổn không", "có vấn đề gì",
            "tại sao", "vì sao", "nguyên nhân gì", "nghĩa là gì", "là gì",
            "giải thích", "nói rõ hơn", "phân tích thêm", "cụ thể hơn", "nhớ không", "vừa rồi",
            "việc này", "việc đó", "điều này", "điều đó", "cái này", "cái đó", "vấn đề này",
        ])
        if is_discussion and not explicit_action_start and not has_any(["kiểm tra", "xem log", "quét", "rà soát", "chạy lệnh", "thu thập snapshot"]):
            return "discuss", None, {}

        # 2. Agentic AI & Tự hành (Nhóm 3 trên UI - đặt trước service/telemetry để tránh trùng 'nginx', 'ssh', 'cpu', 'ram', 'hệ thống')
        if has_any(["snapshot", "thu thập sự cố", "toàn cảnh sự cố", "gom thông số"]):
            num_match = re.search(r"\b(\d{1,2})\b", plain)
            lines = min(max(int(num_match.group(1)), 5), 50) if num_match else 15
            return "snapshot", "collect_incident_snapshot", {"log_lines": lines}

        if has_any(["brute-force", "brute force", "bruteforce", "tấn công ssh", "quét các ip", "quét ip ssh", "tự động chặn ip"]):
            auto_block = has_any(["tự động chặn", "chặn tự động", "auto block", "chặn luôn"])
            return "mitigate_ssh", "auto_mitigate_ssh_attack", {"threshold": 5, "auto_block": auto_block}

        if has_any(["bộ nhớ sự cố", "incident memory", "kinh nghiệm sự cố", "lịch sử sự cố", "tra cứu bộ nhớ", "lưu sự cố"]):
            mem_action = "save" if has_any(["lưu bộ nhớ", "lưu sự cố", "ghi nhớ sự cố"]) else "search"
            keyword = ""
            for kw_cand in ["nginx", "ssh", "ufw", "docker", "mysql", "ram", "cpu", "disk", "test_nginx"]:
                if kw_cand in plain:
                    keyword = kw_cand
                    break
            if not keyword:
                m_kw = re.search(r"(?:tới|toi|về|ve|từ khóa|keyword)\s+([a-z0-9_.-]+)$", plain)
                if m_kw:
                    keyword = m_kw.group(1)
            return "incident_memory", "incident_memory", {"action": mem_action, "keyword": keyword}

        if has_any(["ollama", "danh sách model", "các model", "liệt kê model", "model đang cài", "model đang chạy"]):
            ol_action = "ps" if has_any(["đang chạy", "running", "ps"]) else ("status" if has_any(["trạng thái", "status"]) else "list")
            return "ollama", "manage_ollama_models", {"action": ol_action}

        if has_any(["phần cứng gpu", "phần cứng ai", "phần cứng cpu", "cho ai", "gpu", "nvidia", "vram", "avx2", "avx512"]):
            return "ai_hardware", "check_ai_hardware", {}

        if has_any(["gợi ý model", "đề xuất model", "chọn model", "model router", "model qwen phù hợp", "phù hợp với ram"]):
            prefer_speed = has_any(["nhanh", "tốc độ", "speed"])
            return "model_router", "ai_model_router", {"prefer_speed": prefer_speed}

        # 3. Bảo mật & Tường lửa (Nhóm 2 trên UI - đặt trước Services & Network Ports)
        if has_any(["đăng nhập ssh thất bại", "đăng nhập thất bại", "failed login", "failed password", "sai mật khẩu", "lỗi đăng nhập", "lastb"]):
            num_match = re.search(r"\b(\d{1,3})\b", plain)
            limit = min(max(int(num_match.group(1)), 1), 100) if num_match else 20
            return "failed_logins", "check_failed_logins", {"limit": limit}

        ip_match = re.search(r"\b((?:\d{1,3}\.){3}\d{1,3})\b", plain)
        port_match = re.search(r"(?:port|cổng|cong)\s*(\d{1,5}(?:/tcp|/udp)?)\b", plain)
        is_fw_keyword = has_any(["tường lửa", "firewall", "ufw"])
        is_fw_rule_phrase = has_any(["mở port", "mở cổng", "đóng port", "đóng cổng", "chặn port", "chặn cổng", "chặn ip", "cấm ip", "allow port", "deny port", "allow ip", "deny ip"])

        if is_fw_keyword or (is_fw_rule_phrase and (ip_match or port_match)):
            is_check_query = (
                "?" in user_input
                or has_any([
                    "kiểm tra", "trạng thái", "status", "xem", "danh sách",
                    "rule", "luật", "bật hay tắt", "đang bật", "đang tắt",
                    "có bật", "có tắt", "bật chưa", "tắt chưa",
                ])
            )
            target = ip_match.group(1) if ip_match else (port_match.group(1) if port_match else "")

            if target and has_any(["chặn", "cấm", "đóng", "khóa", "deny", "block"]):
                return "firewall_rule", "manage_firewall_rule", {"action": "deny", "target": target}
            if target and has_any(["mở", "cho phép", "allow"]):
                return "firewall_rule", "manage_firewall_rule", {"action": "allow", "target": target}

            if not target and not is_check_query:
                if has_any(["bật", "enable", "kích hoạt", "mở", "start"]):
                    return "firewall_rule", "manage_firewall_rule", {"action": "enable", "target": "ufw"}
                if has_any(["tắt", "disable", "vô hiệu", "dừng", "ngắt", "đóng", "stop"]):
                    return "firewall_rule", "manage_firewall_rule", {"action": "disable", "target": "ufw"}

            return "firewall_status", "check_firewall_status", {}

        # 3.5 Tiến trình, Ổ đĩa, Tệp tin hệ thống, Mạng & DevOps (12 Tools mở rộng)
        if has_any(["dừng tiến trình", "giết tiến trình", "tắt tiến trình", "kill pid", "kill tiến trình"]):
            m_pid = re.search(r"\b(\d+)\b", plain)
            pid = int(m_pid.group(1)) if m_pid else 1
            sig = "SIGKILL" if has_any(["sigkill", "kill -9", "-9"]) else "SIGTERM"
            return "kill_proc", "kill_process", {"pid": pid, "signal": sig}

        if has_any(["top tiến trình", "tiến trình ăn cpu", "tiến trình tốn cpu", "tiến trình tốn ram", "tiến trình ăn ram", "danh sách tiến trình", "liệt kê tiến trình", "các tiến trình"]) or re.search(r"\btop\s+\d+\s+tiến trình", user_input.lower()):
            sort_by = "mem" if has_any(["ram", "bộ nhớ", "mem"]) else "cpu"
            m_lim = re.search(r"\b(\d{1,2})\b", plain)
            limit = min(max(int(m_lim.group(1)), 1), 30) if m_lim else 10
            return "top_proc", "list_top_processes", {"sort_by": sort_by, "limit": limit}

        if has_any(["phân vùng", "mountpoint", "partition", "các ổ đĩa"]):
            return "partitions", "get_disk_partitions", {}

        if has_any(["quyền file", "quyền thư mục", "chmod", "chown", "check_file_permissions", "quyền truy cập file"]):
            m_path = re.search(r"(/[^\s]+|[a-zA-Z0-9_./-]+)$", user_input.strip())
            fpath = m_path.group(1) if m_path else "/etc/passwd"
            return "file_perm", "check_file_permissions", {"path": fpath}

        if has_any(["tìm từ khóa", "tìm lỗi trong log", "tìm trong log", "search log", "search_in_logs"]) or (
            has_any(["tìm", "search"]) and has_any(["log", "syslog", "nhật ký"])
        ):
            lsrc = "syslog"
            if "nginx" in plain:
                lsrc = "nginx"
            elif "auth" in plain or "ssh" in plain:
                lsrc = "auth"
            elif "journal" in plain:
                lsrc = "journal"
            m_kw = re.search(
                r"(?:từ khóa|tu khoa)\s+[\"']?([^\s\"']+)[\"']?",
                user_input,
                re.IGNORECASE,
            ) or re.search(
                r"(?:tìm|tim)(?:\s+lỗi|\s+loi)?\s+[\"']?([^\s\"']+)[\"']?",
                user_input,
                re.IGNORECASE,
            )
            kw = m_kw.group(1) if m_kw and m_kw.group(1).lower() not in ("trong", "log") else "error"
            return "search_logs", "search_in_logs", {"keyword": kw, "log_source": lsrc, "limit": 30}

        if has_any(["đọc file hệ thống", "doc file he thong", "read_file_safe"]) or (
            has_any(["đọc file", "doc file", "xem file"])
            and re.search(r"\s(/(?:etc|var|proc|usr|tmp)/[^\s]+)", user_input)
        ):
            m_sys = re.search(r"(/(?:etc|var|proc|usr|tmp)/[^\s]+|[^\s]+)$", user_input.strip())
            fpath = m_sys.group(1) if m_sys else "/etc/os-release"
            return "read_sys_file", "read_file_safe", {"path": fpath, "max_lines": 50}

        if has_any(["ping tới", "ping thử", "ping_host"]) or plain.startswith("ping "):
            m_host = re.search(r"(?:ping(?:\s+thử|\s+thu)?(?:\s+tới|\s+toi|\s+đến|\s+den)?\s+)([a-zA-Z0-9.:-]+)", user_input, re.IGNORECASE)
            host = m_host.group(1) if m_host else "8.8.8.8"
            return "ping", "ping_host", {"host": host, "count": 3}

        if has_any(["phân giải tên miền", "kiểm tra dns", "tra cứu dns", "nslookup", "check_dns"]) or " dns " in f" {plain} ":
            m_dom = re.search(r"\b([a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+)\b", user_input)
            dom = m_dom.group(1) if m_dom else "google.com"
            return "dns", "check_dns_resolution", {"domain": dom}

        if has_any(["http endpoint", "kiểm tra http", "kiểm tra web", "check http", "check_http_endpoint"]) or re.search(r"https?://", user_input):
            m_url = re.search(r"(https?://[^\s]+)", user_input)
            url = m_url.group(1) if m_url else "http://127.0.0.1:8080"
            return "http_check", "check_http_endpoint", {"url": url}

        if has_any(["cron job", "tác vụ cron", "crontab", "tác vụ định kỳ", "list_cron_jobs"]):
            return "cron_jobs", "list_cron_jobs", {}

        if has_any(["user đang đăng nhập", "ai đang đăng nhập", "phiên đăng nhập", "người dùng đang đăng nhập", "get_user_sessions"]):
            return "user_sessions", "get_user_sessions", {}

        if has_any(["docker container", "các container", "docker ps", "log container", "restart container", "manage_docker"]):
            d_act = "ps"
            c_name = ""
            if has_any(["log", "nhật ký"]):
                d_act = "logs"
            elif has_any(["restart", "khởi động lại"]):
                d_act = "restart"
            if d_act != "ps":
                m_c = re.search(r"container\s+([a-zA-Z0-9_.-]+)", user_input, re.IGNORECASE)
                c_name = m_c.group(1) if m_c else ""
            return "docker", "manage_docker_containers", {"action": d_act, "container_name": c_name}

        # 4. Inspect Logs (đặt TRƯỚC service để 'xem log ssh/nginx' không bị nhầm sang manage_service)
        if has_any(["log", "nhật ký", "journal", "lỗi hệ thống", "dmesg"]):
            source = "syslog"
            if "nginx" in plain:
                source = "nginx"
            elif "auth" in plain or "ssh" in plain:
                source = "auth"
            elif "journal" in plain:
                source = "journal"
            elif "dmesg" in plain:
                source = "dmesg"

            num_match = re.search(r"\b(\d{1,3})\b", plain)
            lines = min(max(int(num_match.group(1)), 1), 100) if num_match else 10
            return "logs", "inspect_logs", {"log_source": source, "lines": lines}

        # 5. Sandboxed Command Execution (dùng regex cắt prefix an toàn)
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

        # 5.5 Workspace Operations (giới hạn duy nhất trong Customize-MCP-Server, duyệt nội dung qua Sandbox)
        ws_rules = [
            ("append_file", ["ghi thêm vào file", "ghi them vao file", "thêm nội dung vào file", "them noi dung vao file", "nối vào file"]),
            ("edit_file", ["sửa file", "sua file", "chỉnh sửa file", "chinh sua file", "cập nhật file", "cap nhat file", "sửa nội dung file"]),
            ("create_file", ["tạo file", "tao file", "thêm file", "them file", "viết file", "viet file", "tạo tập tin"]),
            ("create_dir", ["tạo thư mục", "tao thu muc", "tạo folder", "tao folder", "thêm thư mục", "them thu muc", "thêm folder"]),
            ("delete", ["xóa file", "xoa file", "xóa thư mục", "xoa thu muc", "xóa folder", "xoa folder"]),
            ("read_file", ["đọc file", "doc file", "xem nội dung file", "xem file"]),
            ("run_file", ["chạy file", "chay file", "chạy script", "chay script", "chạy thư mục", "chay thu muc", "chạy folder", "chay folder"]),
            ("list_dir", ["xem thư mục", "xem thu muc", "xem folder", "mở thư mục", "mo thu muc", "mở folder", "mo folder", "liệt kê file", "liet ke file", "liệt kê thư mục", "danh sách file"]),
        ]
        for ws_action, ws_prefixes in ws_rules:
            if has_any(ws_prefixes):
                path, content = self._extract_workspace_path_and_content(user_input, ws_prefixes)
                ws_args = {"action": ws_action, "path": path}
                if ws_action in ("create_file", "edit_file", "append_file"):
                    ws_args["content"] = content
                return "workspace", "manage_workspace", ws_args

        # 6. Network Ports Audit
        if has_any(["cổng", "port", "socket", "listening", "quét cổng", "rà soát"]):
            return "ports", "audit_network_ports", {}

        # 7. Service Management
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

        # 8. Telemetry (CPU / RAM / Disk / Uptime / General Health)
        if has_any(["cpu", "tải cpu", "load avg", "mức tải", "nhiệt độ", "temp"]):
            return "cpu", "get_system_health", {}
        if has_any(["ram", "bộ nhớ", "memory"]):
            return "ram", "get_system_health", {}
        if has_any(["ổ cứng", "disk", "dung lượng", "ổ đĩa", "storage", "hdd", "ssd"]):
            return "disk", "get_system_health", {}
        if has_any(["uptime", "chạy bao lâu", "bật bao lâu", "thời gian hoạt động"]):
            return "uptime", "get_system_health", {}
        if has_any([
            "sức khỏe", "tài nguyên", "tổng quan hệ thống", "tình trạng hệ thống",
            "tình trạng server", "tình trạng máy chủ", "kiểm tra hệ thống",
            "kiểm tra server", "kiểm tra máy chủ", "thông số hệ thống",
            "health", "system status", "server status",
        ]):
            return "health", "get_system_health", {}

        return "chat", None, {}

    def call_qwen_local_api(self, user_query, context_data=None, strip_guides=False, is_action=False):
        """
        Gọi Qwen Local qua Ollama (/api/chat - 100% Offline).
        Khi chạy tool thực tế, không đưa lịch sử tool cũ vào để model nhỏ không nhại lại trạng thái cũ.
        """
        current_user_content = user_query
        if context_data:
            if is_action:
                current_user_content = (
                    f"{user_query}\n\n"
                    f"[Kết quả từ hệ thống]:\n{context_data}\n\n"
                    f"Hãy phản hồi ngắn gọn, tự nhiên về kết quả thực thi, trạng thái mới và chốt lại bằng 1 dòng kết luận."
                )
            else:
                current_user_content = (
                    f"{user_query}\n\n"
                    f"[Dữ liệu thực tế từ hệ thống]:\n{context_data}\n\n"
                    f"Hãy trình bày lại trạng thái/số liệu trên một cách tự nhiên, ngắn gọn kèm 1–2 nhận xét kỹ thuật và kết thúc bằng 1 dòng kết luận."
                )

        # Chỉ dùng chat_history cho hội thoại thường; khi phân tích tool mới thì đọc đúng dữ liệu hiện tại
        history_msgs = [] if context_data else self.chat_history[-10:]
        messages = (
            [{"role": "system", "content": self.SYSTEM_INSTRUCTION}]
            + history_msgs
            + [{"role": "user", "content": current_user_content}]
        )

        payload = {
            "model": self.active_model,
            "messages": messages,
            "stream": False,
            "keep_alive": "60m",
            "options": {
                "num_predict": 600,
                "temperature": 0.25 if context_data else 0.35,
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
            if strip_guides:
                answer = self._strip_unsolicited_guides(answer)
            answer = self._clean_cjk_leaks(answer)

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

        if intent == "firewall_status":
            state = str(data.get("ufw_state", "unknown")).upper()
            raw_out = (data.get("raw_output") or "").strip()
            note = data.get("note", "")
            msg = (
                f"🔥 Trạng Thái Tường Lửa UFW:\n"
                f"  • Trạng thái: {state}\n"
                f"{raw_out}"
            )
            if note:
                msg += f"\n  • Ghi chú: {note}"
            return msg

        if intent == "firewall_rule":
            ok = data.get("success", False)
            out = (data.get("output") or data.get("error") or "").strip()
            note = data.get("note", "")
            msg = (
                f"🛡️ Thao Tác Tường Lửa UFW ({args.get('action')} {args.get('target', 'ufw')}):\n"
                f"  • Kết quả : {'THÀNH CÔNG' if ok else 'THẤT BẠI'}\n"
                f"  • Phản hồi: {out}"
            )
            if note:
                msg += f"\n  • Lưu ý   : {note}"
            return msg

        if intent == "failed_logins":
            return (
                f"🔐 Thống Kê Đăng Nhập SSH Thất Bại (Giới hạn {args.get('limit', 20)}):\n"
                f"{(data.get('entries') or '').strip()}"
            )

        if intent == "snapshot":
            return (
                f"📸 Snapshot Sự Cố Hệ Thống ({data.get('timestamp', 'N/A')}):\n"
                f"  • Tiến trình: {data.get('system_health', {}).get('process_count', 'N/A')}\n"
                f"  • RAM dùng  : {data.get('system_health', {}).get('memory', {}).get('used_percentage', 'N/A')}%\n"
                f"  • Cổng mạng : {(data.get('network_ports', {}).get('raw_sockets') or '').strip()}\n"
                f"  • SSH Failed: {(data.get('failed_ssh_logins', {}).get('entries') or '').strip()}"
            )

        if intent == "mitigate_ssh":
            attackers = data.get("attackers_detected", [])
            summary = "\n".join(
                f"  • IP {a.get('ip')}: {a.get('failed_attempts')} lần sai (blocked={a.get('blocked')})"
                for a in attackers
            ) or "  • Không phát hiện IP vượt ngưỡng tấn công brute-force."
            return f"🚨 Kết Quả Quét SSH Brute-force (Ngưỡng >= {args.get('threshold', 5)}):\n{summary}"

        if intent == "incident_memory":
            matches = data.get("matches", [])
            if matches:
                items = "\n".join(f"  • [{m.get('timestamp')}] {m.get('keyword')}: {m.get('solution')}" for m in matches)
            else:
                items = f"  • Không có bản ghi sự cố nào khớp từ khóa '{args.get('keyword', '')}'."
            return f"🧠 Bộ Nhớ Kinh Nghiệm Sự Cố:\n{items}"

        if intent == "ollama":
            return f"🤖 Trạng Thái Ollama ({args.get('action', 'list')}):\n{(data.get('output') or '').strip()}"

        if intent == "ai_hardware":
            return (
                f"🖥️ Phần Cứng Phục Vụ AI:\n"
                f"  • GPU NVIDIA: {data.get('gpu_info', 'N/A')}\n"
                f"  • Tập lệnh CPU: {(data.get('cpu_ai_extensions') or '').strip()}"
            )

        if intent == "model_router":
            return (
                f"🧭 Gợi Ý Model Qwen Tối Ưu:\n"
                f"  • RAM khả dụng: {data.get('available_ram_mb', 'N/A')} MB\n"
                f"  • Model đề xuất: {data.get('recommended_model', 'qwen2.5:1.5b')}\n"
                f"  • Lý do: {data.get('reason', '')}"
            )

        if intent == "workspace":
            if data.get("allowed") is False:
                return (
                    f"⛔ [SANDBOX WORKSPACE TỪ CHỐI]\n"
                    f"  • Thao tác : {args.get('action')} ({args.get('path')})\n"
                    f"  • Vi phạm  : {data.get('violation', 'N/A')}\n"
                    f"  • Lý do    : {data.get('error', 'Không được phép')}"
                )
            if not data.get("success", False):
                return f"⚠️ Lỗi Workspace ({args.get('action')}): {data.get('error', 'Thất bại')}"
            act = args.get("action")
            if act == "list_dir":
                entries = "\n".join(f"  • [{e['type']}] {e['name']}" for e in data.get("entries", [])[:30])
                return f"📁 Thư mục Customize-MCP-Server/{data.get('path', '.')} ({data.get('count', 0)} mục):\n{entries}"
            if act == "read_file":
                return f"📄 Nội dung {data.get('path')}:\n{data.get('content', '')}"
            if act == "run_file":
                return f"▶️ Chạy {data.get('path')} (exit={data.get('exit_code')}):\n{(data.get('output') or '').strip()}"
            return f"✅ Đã thực hiện {act} trong Customize-MCP-Server/{data.get('path')} (Sandbox Content: {data.get('content_audit', 'OK')})."

        if intent == "kill_proc":
            if data.get("allowed") is False:
                return f"⛔ [SANDBOX CHẶN]: {data.get('error', 'Không được phép dừng tiến trình lõi.')}"
            return f"⚙️ Kết quả kill PID {args.get('pid')}: {data.get('message') or data.get('error', '')}"

        if intent == "top_proc":
            return f"📈 Top {args.get('limit', 10)} tiến trình theo {args.get('sort_by', 'cpu').upper()}:\n{(data.get('processes') or '').strip()}"

        if intent == "partitions":
            rows = "\n".join(
                f"  • {p['mountpoint']} ({p['device']}, {p['fstype']}): {p['used_gb']}/{p['total_gb']} GB ({p['used_percentage']}%)"
                for p in data.get("partitions", [])
            )
            return f"💾 Các phân vùng ổ đĩa đang mount:\n{rows}"

        if intent == "file_perm":
            if not data.get("success", False):
                return f"⚠️ Lỗi kiểm tra quyền: {data.get('error', '')}"
            return (
                f"🔐 Quyền tệp {data.get('path')}:\n"
                f"  • Mode : {data.get('mode_symbolic')} ({data.get('mode_octal')})\n"
                f"  • Owner: {data.get('owner')}:{data.get('group')} | Size: {data.get('size_bytes')} bytes"
            )

        if intent == "search_logs":
            return f"🔎 Kết quả tìm '{args.get('keyword')}' trong {data.get('log_source')} ({data.get('match_count', 0)} dòng):\n{(data.get('matches') or '').strip()}"

        if intent == "read_sys_file":
            if data.get("allowed") is False:
                return f"⛔ [SANDBOX CHẶN]: {data.get('error', 'Không được phép đọc file nhạy cảm.')}"
            return f"📄 Nội dung {data.get('path')}:\n{(data.get('content') or data.get('error', '')).strip()}"

        if intent == "ping":
            return f"📡 Kết quả Ping {args.get('host')}:\n{(data.get('output') or data.get('error', '')).strip()}"

        if intent == "dns":
            recs = ", ".join(f"{r['type']}: {r['address']}" for r in data.get("records", []))
            return f"🌐 DNS {args.get('domain')}: {recs or data.get('error', 'Không phân giải được')}"

        if intent == "http_check":
            return f"🌍 Kiểm tra HTTP {args.get('url')}: {(data.get('output') or data.get('error', '')).strip()}"

        if intent == "cron_jobs":
            return f"⏱️ Cron Jobs:\n• User: {(data.get('user_crontab') or '').strip()}\n• /etc/cron.d: {data.get('system_cron_d', '')}"

        if intent == "user_sessions":
            return f"👥 Phiên đăng nhập:\n{(data.get('sessions') or '').strip()}"

        if intent == "docker":
            return f"🐳 Docker ({args.get('action')}):\n{(data.get('output') or data.get('error', '')).strip()}"

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
        # (Bỏ qua bước dịch lệnh nếu là câu hỏi trao đổi/tiếp nối 'discuss')
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
            context = self.format_tool_context(tool_name, args, raw_output)

        # 3. Đưa kết quả thực tế cho Qwen Local phân tích và trả lời ngay (100% Offline)
        qwen_err_msg = None
        strip_guides = bool(
            tool_name
            and tool_name
            not in ("execute_safe_command", "manage_workspace", "read_file_safe", "search_in_logs")
        )
        is_action = tool_name in {
            "manage_firewall_rule",
            "manage_service",
            "execute_safe_command",
            "auto_mitigate_ssh_attack",
            "incident_memory",
            "kill_process",
            "manage_docker_containers",
        } or (
            tool_name == "manage_workspace"
            and args.get("action") in ("create_dir", "create_file", "edit_file", "append_file", "delete", "run_file")
        )
        try:
            qwen_res, model_used = self.call_qwen_local_api(
                user_query, context, strip_guides=strip_guides, is_action=is_action
            )
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


# Vòng lặp giao diện dòng lệnh (CLI) cho phép chat trực tiếp với AI trên Terminal
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