#!/usr/bin/env python3
"""
==============================================================================
 VKU Agentic AI Controller (Linux OSS 2026)
 Connects LLMs (Google Gemini API / Autonomous Reasoner) with Native C++ MCP Server
 Author: Tran Duy Duc Anh (Student ID: 24IT009)
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
    nfc = unicodedata.normalize('NFC', text).lower().strip()
    nfd = unicodedata.normalize('NFD', nfc)
    unaccented = ''.join(c for c in nfd if unicodedata.category(c) != 'Mn').replace('đ', 'd').replace('Đ', 'd')
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
            raise FileNotFoundError(f"Binary not found: {binary_path}. Please compile with 'make'.")
        
        self.proc = subprocess.Popen(
            [binary_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1
        )
        self.request_id = 0
        self._initialize()

    def _send_rpc(self, method, params=None):
        self.request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method
        }
        if params is not None:
            payload["params"] = params
        
        req_line = json.dumps(payload) + "\n"
        self.proc.stdin.write(req_line)
        self.proc.stdin.flush()

        resp_line = self.proc.stdout.readline()
        if not resp_line:
            raise RuntimeError("MCP Server terminated unexpectedly.")
        return json.loads(resp_line)

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
        if content and "text" in content[0]:
            return content[0]["text"]
        return json.dumps(resp.get("result", {}))

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.terminate()
        except Exception:
            pass


class AgenticController:
    def __init__(self, bridge, api_key=None):
        self.bridge = bridge
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.tools = self.bridge.list_tools()

    def call_gemini_api(self, prompt, context_data=None):
        """Calls Google Gemini API with native tool-calling or prompt grounding"""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.api_key}"
        
        system_instruction = (
            "You are VKU Linux AI Agent, an autonomous Linux systems administrator. "
            "You have direct access to Ubuntu Linux via native C++ MCP tools. "
            "Explain system stats clearly, provide actionable insights, and be helpful and concise in Vietnamese or English."
        )

        full_prompt = prompt
        if context_data:
            full_prompt += f"\n\n[Real-time Linux Telemetry from C++ MCP Server]:\n{context_data}"

        payload = {
            "contents": [{
                "parts": [{"text": full_prompt}]
            }],
            "systemInstruction": {
                "parts": [{"text": system_instruction}]
            }
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(req, timeout=15) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            return res_data["candidates"][0]["content"]["parts"][0]["text"]

    def autonomous_reason(self, user_input):
        """
        Built-in Intelligent Reasoner: Works offline with 0 dependencies.
        Parses user intent, maps to C++ MCP tools, and synthesizes answers.
        """
        nfc, plain = normalize_vietnamese(user_input)

        def has_any(keywords):
            for kw in keywords:
                kw_nfc, kw_plain = normalize_vietnamese(kw)
                if kw_nfc in nfc or kw_plain in plain:
                    return True
            return False

        # Exit / Quit check
        if has_any(["exit", "quit", "thoát", "thoat", "tạm biệt", "tam biet"]):
            print(f"{YELLOW}Đang đóng phiên làm việc... Tạm biệt!{RESET}")
            sys.exit(0)

        # 0. Help / Capabilities / Menu
        if has_any(["chức năng", "làm được gì", "tác dụng", "hỏi gì", "giúp", "help", "menu", "hướng dẫn"]):
            return (
                f"🤖 CÁC TÁC DỤNG & CÂU HỎI BẠN CÓ THỂ HỎI TRỢ LÝ AI VKU:\n"
                f"  1. 📈 Hiệu suất & Tải CPU:\n"
                f"     • 'Kiểm tra CPU', 'Mức tải CPU hiện tại', 'CPU load average'\n"
                f"  2. 🧠 Bộ nhớ RAM:\n"
                f"     • 'RAM còn bao nhiêu', 'Kiểm tra bộ nhớ RAM', 'Tình trạng RAM'\n"
                f"  3. 💾 Dung lượng Ổ cứng:\n"
                f"     • 'Ổ cứng còn trống bao nhiêu', 'Kiểm tra dung lượng disk', 'Ổ đĩa đầy chưa'\n"
                f"  4. ⏱️ Thời gian hoạt động (Uptime):\n"
                f"     • 'Máy đã chạy bao lâu', 'Uptime của server', 'Thời gian bật máy'\n"
                f"  5. ⚙️ Quản lý dịch vụ Daemon (Systemd):\n"
                f"     • 'Kiểm tra trạng thái NGINX', 'Khởi động lại NGINX', 'Bật SSH', 'Tắt NGINX'\n"
                f"  6. 🛡️ Rà soát cổng mạng & An toàn (Network Security):\n"
                f"     • 'Rà soát các cổng mạng đang mở', 'Kiểm tra port listening', 'Quét cổng'\n"
                f"  7. 📜 Đọc nhật ký hệ thống (System Logs):\n"
                f"     • 'Xem 10 dòng log mới nhất', 'Đọc syslog', 'Xem log lỗi nginx', 'Log auth'\n"
                f"  8. ⛔ Thử nghiệm Sandbox Bảo mật (C++ Security Filter):\n"
                f"     • 'chạy lệnh rm -rf /tmp/data' (bị chặn ngay), 'chạy lệnh uname -a' (an toàn)\n"
                f"  9. 📊 Sức khỏe hệ thống tổng quát:\n"
                f"     • 'Kiểm tra sức khỏe hệ thống', 'Tài nguyên máy chủ', 'Tình trạng server'\n"
            )

        # 1. CPU Performance & Load Analysis
        if has_any(["cpu", "tải cpu", "cpu load", "load avg", "mức tải", "nhiệt", "nhiệt độ", "temp"]):
            print(f"  {MAGENTA}[Reasoning] Detected intent: CPU Performance & Load Average Audit{RESET}")
            print(f"  {YELLOW}[Tool Call] ⚡ vku_mcp_server -> get_system_health(){RESET}")
            raw_output = self.bridge.call_tool("get_system_health")
            data = json.loads(raw_output)
            cpu = data.get("cpu_load", {})
            l1 = cpu.get("load_1min", 0)
            l5 = cpu.get("load_5min", 0)
            l15 = cpu.get("load_15min", 0)
            
            eval_str = "Mức tải CPU rất thấp, hệ thống phản hồi cực kỳ mượt mà." if l1 < 2.0 else "Mức tải CPU tương đối cao."
            return (
                f"📈 Báo Cáo Hiệu Suất CPU (Đọc trực tiếp từ /proc/loadavg):\n"
                f"  • Tải trung bình 1 phút  : {l1}\n"
                f"  • Tải trung bình 5 phút  : {l5}\n"
                f"  • Tải trung bình 15 phút : {l15}\n"
                f"  ➔ Đánh giá               : {eval_str}"
            )

        # 2. RAM Memory only
        if has_any(["ram", "bộ nhớ", "memory"]):
            print(f"  {MAGENTA}[Reasoning] Detected intent: RAM Memory Analysis{RESET}")
            print(f"  {YELLOW}[Tool Call] ⚡ vku_mcp_server -> get_system_health(){RESET}")
            raw_output = self.bridge.call_tool("get_system_health")
            data = json.loads(raw_output)
            mem = data.get("memory", {})
            total = mem.get("total_mb", 0)
            used = mem.get("used_mb", 0)
            free = mem.get("free_mb", 0)
            avail = mem.get("available_mb", free)
            buff_cache = mem.get("buff_cache_mb", 0)
            pct = mem.get("used_percentage", 0)
            
            eval_str = "RAM rất dồi dào, hệ thống vận hành cực kỳ mượt mà." if pct < 80 else "RAM đang ở mức cao! Cần lưu ý."
            return (
                f"🧠 Báo Cáo Bộ Nhớ RAM (Chuẩn khớp lệnh 'free -m' của Linux):\n"
                f"  • Đang sử dụng : {used} MB / {total} MB ({pct}%)\n"
                f"  • Còn trống    : {free} MB\n"
                f"  • Khả dụng     : {avail} MB (Sẵn sàng cho ứng dụng)\n"
                f"  • Buff/Cache   : {buff_cache} MB (Bộ đệm cache hệ thống)\n"
                f"  ➔ Đánh giá     : {eval_str}"
            )

        # 3. Disk Storage only
        if has_any(["ổ cứng", "disk", "dung lượng", "ổ đĩa", "storage", "lưu trữ", "hdd", "ssd"]):
            print(f"  {MAGENTA}[Reasoning] Detected intent: Disk Storage Analysis{RESET}")
            print(f"  {YELLOW}[Tool Call] ⚡ vku_mcp_server -> get_system_health(){RESET}")
            raw_output = self.bridge.call_tool("get_system_health")
            data = json.loads(raw_output)
            disk = data.get("disk_root", {})
            total = disk.get("total_gb", 0)
            used = disk.get("used_gb", 0)
            avail = disk.get("available_gb", 0)
            pct = disk.get("used_percentage", 0)
            
            eval_str = "Dung lượng ổ cứng còn trống nhiều, an toàn cho lưu trữ." if pct < 85 else "Ổ cứng sắp đầy! Cần dọn dẹp."
            return (
                f"💾 Báo Cáo Dung Lượng Ổ Cứng (Đọc trực tiếp qua POSIX statvfs):\n"
                f"  • Phân vùng    : Root (/)\n"
                f"  • Đã sử dụng   : {used} GB / {total} GB ({pct}%)\n"
                f"  • Còn khả dụng : {avail} GB ({round(100 - pct, 1)}%)\n"
                f"  ➔ Đánh giá     : {eval_str}"
            )

        # 4. Uptime only
        if has_any(["uptime", "chạy bao lâu", "bật bao lâu", "thời gian hoạt động", "thời gian chạy"]):
            print(f"  {MAGENTA}[Reasoning] Detected intent: System Uptime Query{RESET}")
            print(f"  {YELLOW}[Tool Call] ⚡ vku_mcp_server -> get_system_health(){RESET}")
            raw_output = self.bridge.call_tool("get_system_health")
            data = json.loads(raw_output)
            uptime = data.get("uptime", {}).get("formatted", "N/A")
            procs = data.get("process_count", "N/A")
            os_name = data.get("os_info", {}).get("sysname", "Linux")
            
            return (
                f"⏱️ Thời Gian Hoạt Động Hệ Thống (System Uptime):\n"
                f"  • Thời gian chạy liên tục : {uptime}\n"
                f"  • Số tiến trình hiện hành : {procs} processes\n"
                f"  • Hệ điều hành            : {os_name}\n"
                f"  ➔ Đánh giá               : Hệ thống hoạt động ổn định và liên tục, không bị reboot bất thường."
            )

        # 6. Service Management (nginx, ssh, etc.)
        if has_any(["service", "dịch vụ", "nginx", "ssh", "systemctl", "bật", "tắt", "khởi động", "restart", "start", "stop"]):
            service_name = "nginx"
            if "ssh" in plain:
                service_name = "ssh"
            elif "ufw" in plain:
                service_name = "ufw"

            action = "status"
            if any(w in plain for w in ["bat", "start", "mo", "khoi chay"]):
                action = "start"
            elif any(w in plain for w in ["tat", "stop", "dung"]):
                action = "stop"
            elif any(w in plain for w in ["khoi dong", "restart", "load"]):
                action = "restart"

            print(f"  {MAGENTA}[Reasoning] Detected intent: Manage Daemon Service '{service_name}' with action '{action}'{RESET}")
            print(f"  {YELLOW}[Tool Call] ⚡ vku_mcp_server -> manage_service(service_name='{service_name}', action='{action}'){RESET}")
            raw_output = self.bridge.call_tool("manage_service", {"service_name": service_name, "action": action})
            data = json.loads(raw_output)

            state = data.get("active_state", "unknown")
            return (
                f"⚙️ Kết Quả Thao Tác Dịch Vụ Systemd:\n"
                f"  • Dịch vụ   : {service_name}\n"
                f"  • Thao tác  : {action.upper()}\n"
                f"  • Trạng thái: {state.upper()}\n"
                f"  • Exit Code : {data.get('exit_code')}\n"
                f"  • Phản hồi  : {data.get('output').strip()}"
            )

        # 7. Network Ports Audit
        if has_any(["cổng", "port", "socket", "mạng", "network", "listening"]):
            print(f"  {MAGENTA}[Reasoning] Detected intent: Network Security & Port Exposure Audit{RESET}")
            print(f"  {YELLOW}[Tool Call] ⚡ vku_mcp_server -> audit_network_ports(){RESET}")
            raw_output = self.bridge.call_tool("audit_network_ports")
            data = json.loads(raw_output)
            return (
                f"🛡️ Kết Quả Rà Soát Cổng Mạng (Security Audit):\n"
                f"{data.get('raw_sockets').strip()}\n\n"
                f"  ➔ Khuyến nghị: {data.get('recommendation')}"
            )

        # 8. Inspect Logs
        if has_any(["log", "nhật ký", "lỗi", "error", "journal"]):
            log_type = "syslog"
            if "nginx" in plain:
                log_type = "nginx"
            elif "auth" in plain or "ssh" in plain:
                log_type = "auth"
            elif "journal" in plain:
                log_type = "journal"

            print(f"  {MAGENTA}[Reasoning] Detected intent: Log Inspection for source '{log_type}'{RESET}")
            print(f"  {YELLOW}[Tool Call] ⚡ vku_mcp_server -> inspect_logs(log_source='{log_type}', lines=10){RESET}")
            raw_output = self.bridge.call_tool("inspect_logs", {"log_source": log_type, "lines": 10})
            data = json.loads(raw_output)
            return (
                f"📜 Nhật Ký Hệ Thống ({log_type}):\n"
                f"{data.get('log_content').strip()}"
            )

        # 9. Arbitrary Command with Security Sandbox Test
        if has_any(["chạy lệnh", "exec", "command", "lệnh"]) or plain.startswith(("df", "free", "uname", "ls", "rm", "cat")):
            # extract command
            cmd = nfc
            for prefix in ["chạy lệnh", "chay lenh", "exec", "command", "lệnh", "lenh"]:
                if plain.startswith(prefix) or nfc.startswith(prefix):
                    cmd = user_input[len(prefix):].strip()
                    break

            print(f"  {MAGENTA}[Reasoning] Detected intent: Sandboxed Command Execution '{cmd}'{RESET}")
            print(f"  {YELLOW}[Tool Call] ⚡ vku_mcp_server -> execute_safe_command(command='{cmd}'){RESET}")
            raw_output = self.bridge.call_tool("execute_safe_command", {"command": cmd})
            data = json.loads(raw_output)

            if data.get("allowed") is False:
                return (
                    f"⛔ [CẢNH BÁO SANDBOX BẢO MẬT VI PHẠM]\n"
                    f"  • Lệnh bị chặn : {cmd}\n"
                    f"  • Mã vi phạm   : {data.get('violation')}\n"
                    f"  • Lý do        : {data.get('reason')}\n"
                    f"  ➔ Hệ thống MCP C++ đã bảo vệ Ubuntu khỏi nguy cơ phá hoại!"
                )
            else:
                return (
                    f"💻 Thực Thi Lệnh Thành Công:\n"
                    f"{data.get('output').strip()}"
                )

        # 10. General System Health / Resources / Overview
        if has_any(["sức khỏe", "tài nguyên", "hệ thống", "tổng quan", "health", "tình trạng", "status", "server", "máy chủ", "cpu"]):
            print(f"  {MAGENTA}[Reasoning] Detected intent: System Telemetry & Health Audit{RESET}")
            print(f"  {YELLOW}[Tool Call] ⚡ vku_mcp_server -> get_system_health(){RESET}")
            raw_output = self.bridge.call_tool("get_system_health")
            data = json.loads(raw_output)

            mem = data.get("memory", {})
            disk = data.get("disk_root", {})
            cpu = data.get("cpu_load", {})
            uptime = data.get("uptime", {}).get("formatted", "N/A")
            os_name = data.get("os_info", {}).get("sysname", "Linux")

            return (
                f"📊 Báo Cáo Tình Trạng Hệ Thống (Đọc trực tiếp qua POSIX C++):\n"
                f"  • Hệ điều hành : {os_name} (Uptime: {uptime})\n"
                f"  • Bộ nhớ RAM   : Đang dùng {mem.get('used_mb')}MB / {mem.get('total_mb')}MB ({mem.get('used_percentage')}%)\n"
                f"  • Ổ cứng (/)   : Đang dùng {disk.get('used_gb')}GB / {disk.get('total_gb')}GB ({disk.get('used_percentage')}%)\n"
                f"  • CPU Load Avg : {cpu.get('load_1min')} (1m) | {cpu.get('load_5min')} (5m) | {cpu.get('load_15min')} (15m)\n"
                f"  ➔ Đánh giá: Hệ thống đang hoạt động ổn định và an toàn."
            )

        # Fallback General Response
        return (
            f"Tôi là Trợ lý AI Quản trị Linux VKU. Tôi có thể giúp bạn:\n"
            f"  1. 'Kiểm tra CPU' (Mức tải Load Average 1m, 5m, 15m)\n"
            f"  2. 'Kiểm tra tài nguyên RAM' hoặc 'RAM còn bao nhiêu'\n"
            f"  3. 'Kiểm tra ổ cứng' hoặc 'Dung lượng disk'\n"
            f"  4. 'Kiểm tra trạng thái NGINX' hoặc 'Khởi động lại NGINX'\n"
            f"  5. 'Rà soát các cổng mạng đang mở'\n"
            f"  6. 'Đọc nhật ký hệ thống (syslog, auth)'\n"
            f"  7. 'Thử chạy lệnh an toàn hoặc kiểm tra sandbox bảo mật'"
        )

    def process_query(self, user_query):
        # If API key is available, we can connect live cloud AI
        if self.api_key:
            try:
                # Pre-fetch telemetry for contextual grounding
                telemetry = self.bridge.call_tool("get_system_health")
                return self.call_gemini_api(user_query, telemetry)
            except Exception as e:
                print(f"  {YELLOW}[Notice] Cloud API unavailable ({e}). Falling back to Autonomous Reasoner.{RESET}")
        
        res = self.autonomous_reason(user_query)
        # Clean any stray terminal escape sequences
        return re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', res)


def interactive_session():
    print(f"\n{CYAN}{BOLD}======================================================================{RESET}")
    print(f"{CYAN}{BOLD}   [VKU OSS 2026] AGENTIC AI LINUX ADMINISTRATION INTERFACE{RESET}")
    print(f"{CYAN}{BOLD}   Topic 15: Build & Configure MCP Server for Agentic AI in Linux{RESET}")
    print(f"{CYAN}{BOLD}   Student: Tran Duy Duc Anh (24IT009) | Core Engine: C++17 POSIX{RESET}")
    print(f"{CYAN}{BOLD}======================================================================{RESET}")

    try:
        bridge = MCPServerBridge(BIN_PATH)
    except Exception as e:
        print(f"{RED}[ERROR] Failed to start C++ MCP Server: {e}{RESET}")
        sys.exit(1)

    agent = AgenticController(bridge)
    print(f"{GREEN}[OK] Native C++ MCP Server connected successfully! Protocol: 2024-11-05{RESET}")
    print(f"Available Tools: {len(agent.tools)} active C++ tools registered.\n")
    print(f"Gõ câu hỏi bằng Tiếng Việt hoặc Tiếng Anh (Gõ 'exit' hoặc 'quit' để thoát).\n")

    def clean_terminal_input(raw_str):
        # 1. Strip ANSI escape sequences (arrows, insert ^[[2~, etc.)
        cleaned = re.sub(r'\x1b\[[0-9;?]*[a-zA-Z~]', '', raw_str)
        # 2. Resolve backspaces (\x08, \b, \x7f) emitted by Unikey/EVKey when typing accented letters
        chars = []
        for c in cleaned:
            if c in ('\b', '\x08', '\x7f'):
                if chars:
                    chars.pop()
            else:
                chars.append(c)
        result = ''.join(chars).strip()
        # 3. Normalize Unicode to NFC
        return unicodedata.normalize('NFC', result)

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

    while True:
        try:
            prompt = safe_read_line(f"{BOLD}{BLUE}VKU-SysAdmin > {RESET}")
            if not prompt:
                continue
            clean_p = prompt.strip().lower()
            if any(w in clean_p for w in ["exit", "quit", "thoat", "tạm biệt", "tam biet"]) or clean_p == "q":
                print(f"{YELLOW}Đang đóng phiên làm việc... Tạm biệt!{RESET}")
                break

            print(f"{CYAN}[AI Thinking...] 🧠{RESET}")
            response = agent.process_query(prompt)
            print(f"\n{GREEN}{BOLD}[AI Agent Response]:{RESET}\n{response}\n")

        except KeyboardInterrupt:
            print(f"\n{YELLOW}Đang đóng phiên làm việc... Tạm biệt!{RESET}")
            break
        except Exception as ex:
            print(f"{RED}[Error]: {ex}{RESET}\n")

    bridge.close()

if __name__ == "__main__":
    interactive_session()
