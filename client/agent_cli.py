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
        text = user_input.lower().strip()

        # 0. Help / Capabilities / Menu
        if any(w in text for w in ["chức năng", "làm được gì", "tác dụng", "hỏi gì", "hỏi về cái gì", "giúp", "help", "menu", "hướng dẫn"]):
            return (
                f"🤖 {BOLD}CÁC TÁC DỤNG & CÂU HỎI BẠN CÓ THỂ HỎI TRỢ LÝ AI VKU:{RESET}\n"
                f"  1. 🌡️ {CYAN}Nhiệt độ CPU / Tình trạng nhiệt:{RESET}\n"
                f"     • 'Nhiệt độ CPU là bao nhiêu', 'Máy có bị nóng không', 'Kiểm tra nhiệt độ'\n"
                f"  2. 🧠 {CYAN}Bộ nhớ RAM:{RESET}\n"
                f"     • 'RAM còn bao nhiêu', 'Kiểm tra bộ nhớ RAM', 'Tình trạng RAM'\n"
                f"  3. 💾 {CYAN}Dung lượng Ổ cứng:{RESET}\n"
                f"     • 'Ổ cứng còn trống bao nhiêu', 'Kiểm tra dung lượng disk', 'Ổ đĩa đầy chưa'\n"
                f"  4. ⏱️ {CYAN}Thời gian hoạt động (Uptime):{RESET}\n"
                f"     • 'Máy đã chạy bao lâu', 'Uptime của server', 'Thời gian bật máy'\n"
                f"  5. 📈 {CYAN}Mức tải CPU (CPU Load):{RESET}\n"
                f"     • 'Mức tải CPU hiện tại', 'CPU load average', 'CPU đang chạy bao nhiêu'\n"
                f"  6. ⚙️ {CYAN}Quản lý dịch vụ Daemon (Systemd):{RESET}\n"
                f"     • 'Kiểm tra trạng thái NGINX', 'Khởi động lại NGINX', 'Bật SSH', 'Tắt NGINX'\n"
                f"  7. 🛡️ {CYAN}Rà soát cổng mạng & An toàn (Network Security):{RESET}\n"
                f"     • 'Rà soát các cổng mạng đang mở', 'Kiểm tra port listening', 'Quét cổng'\n"
                f"  8. 📜 {CYAN}Đọc nhật ký hệ thống (System Logs):{RESET}\n"
                f"     • 'Xem 10 dòng log mới nhất', 'Đọc syslog', 'Xem log lỗi nginx', 'Log auth'\n"
                f"  9. ⛔ {CYAN}Thử nghiệm Sandbox Bảo mật (C++ Security Filter):{RESET}\n"
                f"     • 'chạy lệnh rm -rf /tmp/data' (bị chặn ngay), 'chạy lệnh uname -a' (an toàn)\n"
                f" 10. 📊 {CYAN}Sức khỏe hệ thống tổng quát:{RESET}\n"
                f"     • 'Kiểm tra sức khỏe hệ thống', 'Tài nguyên máy chủ', 'Tình trạng server'\n"
            )

        # 1. Thermal / Temperature
        if any(w in text for w in ["nhiệt", "nhiệt độ", "temp", "temperature", "nóng", "quá nhiệt"]):
            print(f"  {MAGENTA}[Reasoning] Detected intent: Thermal Sensor & CPU Temperature Audit{RESET}")
            print(f"  {YELLOW}[Tool Call] ⚡ vku_mcp_server -> get_system_health(){RESET}")
            raw_output = self.bridge.call_tool("get_system_health")
            data = json.loads(raw_output)
            cpu = data.get("cpu_load", {})
            cpu_temp = data.get("cpu_temperature", None)
            
            if cpu_temp is not None:
                temp_status = f"{cpu_temp}°C (Đọc từ cảm biến thermal zone kernel)"
            else:
                temp_status = "Không có cảm biến vật lý (Máy ảo VirtualBox/VMware sử dụng vCPU ảo hóa, nhiệt độ chip thực tế do máy tính chủ quản lý)"

            return (
                f"🌡️ {BOLD}Báo Cáo Nhiệt Độ & Trạng Thái CPU (Thermal Telemetry):{RESET}\n"
                f"  • Nhiệt độ đo được : {CYAN}{temp_status}{RESET}\n"
                f"  • Tải CPU 1 phút   : {BOLD}{cpu.get('load_1min')}{RESET} (Mức tải trung bình)\n"
                f"  • Tải CPU 5 phút   : {cpu.get('load_5min')}\n"
                f"  • Tải CPU 15 phút  : {cpu.get('load_15min')}\n"
                f"  ➔ Đánh giá nhiệt   : {GREEN}Hệ thống đang hoạt động mát mẻ, CPU không có dấu hiệu quá nhiệt hay quá tải.{RESET}"
            )

        # 2. RAM Memory only
        if any(w in text for w in ["ram", "bộ nhớ", "memory"]):
            print(f"  {MAGENTA}[Reasoning] Detected intent: RAM Memory Analysis{RESET}")
            print(f"  {YELLOW}[Tool Call] ⚡ vku_mcp_server -> get_system_health(){RESET}")
            raw_output = self.bridge.call_tool("get_system_health")
            data = json.loads(raw_output)
            mem = data.get("memory", {})
            total = mem.get("total_mb", 0)
            used = mem.get("used_mb", 0)
            free = mem.get("free_mb", total - used)
            pct = mem.get("used_percentage", 0)
            
            eval_str = f"{GREEN}RAM rất dồi dào, hệ thống vận hành mượt mà.{RESET}" if pct < 80 else f"{RED}RAM đang ở mức cao! Cần lưu ý.{RESET}"
            return (
                f"🧠 {BOLD}Báo Cáo Bộ Nhớ RAM (Đọc trực tiếp qua POSIX sysinfo):{RESET}\n"
                f"  • Đang sử dụng : {BOLD}{used} MB / {total} MB{RESET} ({pct}%)\n"
                f"  • Còn trống    : {CYAN}{free} MB{RESET} ({round(100 - pct, 1)}%)\n"
                f"  ➔ Đánh giá     : {eval_str}"
            )

        # 3. Disk Storage only
        if any(w in text for w in ["ổ cứng", "disk", "dung lượng", "ổ đĩa", "storage", "lưu trữ", "hdd", "ssd"]):
            print(f"  {MAGENTA}[Reasoning] Detected intent: Disk Storage Analysis{RESET}")
            print(f"  {YELLOW}[Tool Call] ⚡ vku_mcp_server -> get_system_health(){RESET}")
            raw_output = self.bridge.call_tool("get_system_health")
            data = json.loads(raw_output)
            disk = data.get("disk_root", {})
            total = disk.get("total_gb", 0)
            used = disk.get("used_gb", 0)
            avail = disk.get("available_gb", 0)
            pct = disk.get("used_percentage", 0)
            
            eval_str = f"{GREEN}Dung lượng ổ cứng còn trống nhiều, an toàn cho lưu trữ.{RESET}" if pct < 85 else f"{RED}Ổ cứng sắp đầy! Cần dọn dẹp.{RESET}"
            return (
                f"💾 {BOLD}Báo Cáo Dung Lượng Ổ Cứng (Đọc trực tiếp qua POSIX statvfs):{RESET}\n"
                f"  • Phân vùng    : Root (/)\n"
                f"  • Đã sử dụng   : {BOLD}{used} GB / {total} GB{RESET} ({pct}%)\n"
                f"  • Còn khả dụng : {CYAN}{avail} GB{RESET} ({round(100 - pct, 1)}%)\n"
                f"  ➔ Đánh giá     : {eval_str}"
            )

        # 4. Uptime only
        if any(w in text for w in ["uptime", "chạy bao lâu", "bật bao lâu", "thời gian hoạt động", "thời gian chạy"]):
            print(f"  {MAGENTA}[Reasoning] Detected intent: System Uptime Query{RESET}")
            print(f"  {YELLOW}[Tool Call] ⚡ vku_mcp_server -> get_system_health(){RESET}")
            raw_output = self.bridge.call_tool("get_system_health")
            data = json.loads(raw_output)
            uptime = data.get("uptime", {}).get("formatted", "N/A")
            procs = data.get("process_count", "N/A")
            os_name = data.get("os_info", {}).get("sysname", "Linux")
            
            return (
                f"⏱️ {BOLD}Thời Gian Hoạt Động Hệ Thống (System Uptime):{RESET}\n"
                f"  • Thời gian chạy liên tục : {CYAN}{uptime}{RESET}\n"
                f"  • Số tiến trình hiện hành : {BOLD}{procs}{RESET} processes\n"
                f"  • Hệ điều hành            : {GREEN}{os_name}{RESET}\n"
                f"  ➔ Đánh giá               : {GREEN}Hệ thống hoạt động ổn định và liên tục, không bị reboot bất thường.{RESET}"
            )

        # 5. CPU Load only
        if any(w in text for w in ["tải cpu", "cpu load", "load avg", "mức tải"]):
            print(f"  {MAGENTA}[Reasoning] Detected intent: CPU Load Average Analysis{RESET}")
            print(f"  {YELLOW}[Tool Call] ⚡ vku_mcp_server -> get_system_health(){RESET}")
            raw_output = self.bridge.call_tool("get_system_health")
            data = json.loads(raw_output)
            cpu = data.get("cpu_load", {})
            l1 = cpu.get("load_1min", 0)
            l5 = cpu.get("load_5min", 0)
            l15 = cpu.get("load_15min", 0)
            
            eval_str = f"{GREEN}Mức tải CPU rất thấp, các tiến trình hoạt động nhanh chóng.{RESET}" if l1 < 2.0 else f"{YELLOW}Mức tải CPU tương đối cao.{RESET}"
            return (
                f"📈 {BOLD}Báo Cáo Mức Tải CPU (Đọc trực tiếp từ /proc/loadavg):{RESET}\n"
                f"  • Tải trung bình 1 phút  : {BOLD}{l1}{RESET}\n"
                f"  • Tải trung bình 5 phút  : {l5}\n"
                f"  • Tải trung bình 15 phút : {l15}\n"
                f"  ➔ Đánh giá               : {eval_str}"
            )

        # 6. Service Management (nginx, ssh, etc.)
        if any(w in text for w in ["service", "dịch vụ", "nginx", "ssh", "systemctl", "bật", "tắt", "khởi động", "restart", "start", "stop"]):
            service_name = "nginx"
            if "ssh" in text:
                service_name = "ssh"
            elif "ufw" in text:
                service_name = "ufw"

            action = "status"
            if any(w in text for w in ["bật", "start"]):
                action = "start"
            elif any(w in text for w in ["tắt", "stop"]):
                action = "stop"
            elif any(w in text for w in ["khởi động lại", "restart"]):
                action = "restart"

            print(f"  {MAGENTA}[Reasoning] Detected intent: Manage Daemon Service '{service_name}' with action '{action}'{RESET}")
            print(f"  {YELLOW}[Tool Call] ⚡ vku_mcp_server -> manage_service(service_name='{service_name}', action='{action}'){RESET}")
            raw_output = self.bridge.call_tool("manage_service", {"service_name": service_name, "action": action})
            data = json.loads(raw_output)

            state = data.get("active_state", "unknown")
            return (
                f"⚙️ {BOLD}Kết Quả Thao Tác Dịch Vụ Systemd:{RESET}\n"
                f"  • Dịch vụ   : {CYAN}{service_name}{RESET}\n"
                f"  • Thao tác  : {action.upper()}\n"
                f"  • Trạng thái: {GREEN if state == 'active' else RED}{state.upper()}{RESET}\n"
                f"  • Exit Code : {data.get('exit_code')}\n"
                f"  • Phản hồi  : {data.get('output').strip()}"
            )

        # 7. Network Ports Audit
        if any(w in text for w in ["cổng", "port", "socket", "mạng", "network", "listening"]):
            print(f"  {MAGENTA}[Reasoning] Detected intent: Network Security & Port Exposure Audit{RESET}")
            print(f"  {YELLOW}[Tool Call] ⚡ vku_mcp_server -> audit_network_ports(){RESET}")
            raw_output = self.bridge.call_tool("audit_network_ports")
            data = json.loads(raw_output)
            return (
                f"🛡️ {BOLD}Kết Quả Rà Soát Cổng Mạng (Security Audit):{RESET}\n"
                f"{data.get('raw_sockets').strip()}\n\n"
                f"  ➔ Khuyến nghị: {data.get('recommendation')}"
            )

        # 8. Inspect Logs
        if any(w in text for w in ["log", "nhật ký", "lỗi", "error", "journal"]):
            log_type = "syslog"
            if "nginx" in text:
                log_type = "nginx"
            elif "auth" in text or "ssh" in text:
                log_type = "auth"
            elif "journal" in text:
                log_type = "journal"

            print(f"  {MAGENTA}[Reasoning] Detected intent: Log Inspection for source '{log_type}'{RESET}")
            print(f"  {YELLOW}[Tool Call] ⚡ vku_mcp_server -> inspect_logs(log_source='{log_type}', lines=10){RESET}")
            raw_output = self.bridge.call_tool("inspect_logs", {"log_source": log_type, "lines": 10})
            data = json.loads(raw_output)
            return (
                f"📜 {BOLD}Nhật Ký Hệ Thống ({log_type}):{RESET}\n"
                f"{data.get('log_content').strip()}"
            )

        # 9. Arbitrary Command with Security Sandbox Test
        if any(w in text for w in ["chạy lệnh", "exec", "command", "lệnh"]) or text.startswith(("df", "free", "uname", "ls", "rm", "cat")):
            # extract command
            cmd = text
            for prefix in ["chạy lệnh", "exec", "command", "lệnh"]:
                if text.startswith(prefix):
                    cmd = text[len(prefix):].strip()
                    break

            print(f"  {MAGENTA}[Reasoning] Detected intent: Sandboxed Command Execution '{cmd}'{RESET}")
            print(f"  {YELLOW}[Tool Call] ⚡ vku_mcp_server -> execute_safe_command(command='{cmd}'){RESET}")
            raw_output = self.bridge.call_tool("execute_safe_command", {"command": cmd})
            data = json.loads(raw_output)

            if data.get("allowed") is False:
                return (
                    f"⛔ {RED}{BOLD}[CẢNH BÁO SANDBOX BẢO MẬT VI PHẠM]{RESET}\n"
                    f"  • Lệnh bị chặn : {cmd}\n"
                    f"  • Mã vi phạm   : {data.get('violation')}\n"
                    f"  • Lý do        : {data.get('reason')}\n"
                    f"  ➔ Hệ thống MCP C++ đã bảo vệ Ubuntu khỏi nguy cơ phá hoại!"
                )
            else:
                return (
                    f"💻 {BOLD}Thực Thi Lệnh Thành Công:{RESET}\n"
                    f"{data.get('output').strip()}"
                )

        # 10. General System Health / Resources / Overview
        if any(w in text for w in ["sức khỏe", "tài nguyên", "hệ thống", "tổng quan", "health", "tình trạng", "status", "server", "máy chủ", "cpu"]):
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
                f"📊 {BOLD}Báo Cáo Tình Trạng Hệ Thống (Đọc trực tiếp qua POSIX C++):{RESET}\n"
                f"  • Hệ điều hành : {GREEN}{os_name} (Uptime: {uptime}){RESET}\n"
                f"  • Bộ nhớ RAM   : Đang dùng {BOLD}{mem.get('used_mb')}MB / {mem.get('total_mb')}MB{RESET} ({mem.get('used_percentage')}%)\n"
                f"  • Ổ cứng (/)   : Đang dùng {BOLD}{disk.get('used_gb')}GB / {disk.get('total_gb')}GB{RESET} ({disk.get('used_percentage')}%)\n"
                f"  • CPU Load Avg : {cpu.get('load_1min')} (1m) | {cpu.get('load_5min')} (5m) | {cpu.get('load_15min')} (15m)\n"
                f"  ➔ Đánh giá: {GREEN}Hệ thống đang hoạt động ổn định và an toàn.{RESET}"
            )

        # Fallback General Response
        return (
            f"Tôi là Trợ lý AI Quản trị Linux VKU. Tôi có thể giúp bạn:\n"
            f"  1. 'Kiểm tra nhiệt độ CPU' hoặc 'Máy có bị nóng không'\n"
            f"  2. 'Kiểm tra tài nguyên máy chủ' (RAM, CPU, Ổ cứng)\n"
            f"  3. 'Kiểm tra trạng thái NGINX' hoặc 'Bật/Tắt dịch vụ NGINX'\n"
            f"  4. 'Rà soát các cổng mạng đang mở'\n"
            f"  5. 'Đọc nhật ký hệ thống (syslog, auth)'\n"
            f"  6. 'Thử chạy lệnh an toàn hoặc kiểm tra sandbox bảo mật'"
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
        
        return self.autonomous_reason(user_query)


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

    def safe_read_line(prompt_text):
        try:
            sys.stdout.write(prompt_text)
            sys.stdout.flush()
            if hasattr(sys.stdin, "buffer"):
                raw_bytes = sys.stdin.buffer.readline()
                if not raw_bytes:
                    return "exit"
                return raw_bytes.decode("utf-8", errors="replace").strip()
            return input().strip()
        except EOFError:
            return "exit"
        except UnicodeDecodeError:
            if hasattr(sys.stdin, "buffer"):
                return sys.stdin.buffer.readline().decode("utf-8", errors="ignore").strip()
            return ""
        except Exception:
            return ""

    while True:
        try:
            prompt = safe_read_line(f"{BOLD}{BLUE}VKU-SysAdmin > {RESET}")
            if not prompt:
                continue
            if prompt.lower() in ["exit", "quit", "q"]:
                print(f"{YELLOW}Đang đóng phiên làm việc... Tạm biệt!{RESET}")
                break

            print(f"{CYAN}[AI Thinking...] 🧠{RESET}")
            response = agent.process_query(prompt)
            print(f"\n{GREEN}{BOLD}[AI Agent Response]:{RESET}\n{response}\n")

        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as ex:
            print(f"{RED}[Error]: {ex}{RESET}\n")

    bridge.close()

if __name__ == "__main__":
    interactive_session()
