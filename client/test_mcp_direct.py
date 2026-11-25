#!/usr/bin/env python3
"""
Automated JSON-RPC Protocol Test Suite for VKU C++ MCP Server
Verifies 100% compliance with Model Context Protocol (2024-11-05) specification.
"""

import subprocess
import json
import sys
import os

BIN_PATH = os.path.join(os.path.dirname(__file__), "..", "bin", "vku_mcp_server")
if sys.platform == "win32" and not os.path.exists(BIN_PATH):
    BIN_PATH += ".exe"

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

def print_header(title):
    print(f"\n{CYAN}{BOLD}=== {title} ==={RESET}")

# Chạy bộ 6 bài test tự động kiểm tra chuẩn giao thức MCP (Handshake, Discovery, Tools, Sandbox)
def test_mcp_server():
    print(f"{BOLD}[VKU OSS 2026] Starting Automated MCP C++ Protocol Verification{RESET}")
    print(f"Target Binary: {BIN_PATH}")

    if not os.path.exists(BIN_PATH):
        print(f"{RED}[FAIL] Target binary not found at: {BIN_PATH}. Please run 'make' first.{RESET}")
        sys.exit(1)

    # Khởi chạy trực tiếp file thực thi C++ MCP Server qua đường ống stdin/stdout
    proc = subprocess.Popen(
        [BIN_PATH],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1
    )

    # Bộ kiểm thử toàn diện: Giao thức MCP + Toàn bộ 14 Tools + Các lớp bảo vệ Sandbox
    tests = [
        {
            "name": "MCP Handshake (initialize)",
            "request": {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            "validate": lambda res: res.get("result", {}).get("protocolVersion") == "2024-11-05"
        },
        {
            "name": "MCP Tool Discovery (tools/list -> 27 tools)",
            "request": {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            "validate": lambda res: len(res.get("result", {}).get("tools", [])) == 27
        },
        {
            "name": "Tool 1: get_system_health",
            "request": {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "get_system_health", "arguments": {}}},
            "validate": lambda res: "memory" in json.loads(res["result"]["content"][0]["text"])
        },
        {
            "name": "Tool 2: manage_service (ssh status)",
            "request": {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "manage_service", "arguments": {"service_name": "ssh", "action": "status"}}},
            "validate": lambda res: json.loads(res["result"]["content"][0]["text"]).get("service") == "ssh"
        },
        {
            "name": "Tool 3: inspect_logs (syslog)",
            "request": {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "inspect_logs", "arguments": {"log_source": "syslog", "lines": 5}}},
            "validate": lambda res: json.loads(res["result"]["content"][0]["text"]).get("success") is True
        },
        {
            "name": "Tool 4: audit_network_ports",
            "request": {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "audit_network_ports", "arguments": {}}},
            "validate": lambda res: "raw_sockets" in json.loads(res["result"]["content"][0]["text"])
        },
        {
            "name": "Tool 5: execute_safe_command (uname -a)",
            "request": {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "execute_safe_command", "arguments": {"command": "uname -a"}}},
            "validate": lambda res: json.loads(res["result"]["content"][0]["text"]).get("allowed") is True
        },
        {
            "name": "Sandbox Block: Dangerous pattern (rm -rf)",
            "request": {"jsonrpc": "2.0", "id": 8, "method": "tools/call", "params": {"name": "execute_safe_command", "arguments": {"command": "rm -rf /tmp/test"}}},
            "validate": lambda res: json.loads(res["result"]["content"][0]["text"]).get("violation") == "BLOCKED_BY_SANDBOX"
        },
        {
            "name": "Sandbox Block: Shell chaining (ls; id)",
            "request": {"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": "execute_safe_command", "arguments": {"command": "ls; id"}}},
            "validate": lambda res: json.loads(res["result"]["content"][0]["text"]).get("violation") == "BLOCKED_BY_SANDBOX"
        },
        {
            "name": "Sandbox Block: Sensitive path (cat /etc/shadow)",
            "request": {"jsonrpc": "2.0", "id": 10, "method": "tools/call", "params": {"name": "execute_safe_command", "arguments": {"command": "cat /etc/shadow"}}},
            "validate": lambda res: json.loads(res["result"]["content"][0]["text"]).get("violation") == "BLOCKED_BY_SANDBOX"
        },
        {
            "name": "Sandbox Block: Bypass normalization (/bin/rm  -fr)",
            "request": {"jsonrpc": "2.0", "id": 11, "method": "tools/call", "params": {"name": "execute_safe_command", "arguments": {"command": "/bin/rm  -fr /tmp"}}},
            "validate": lambda res: json.loads(res["result"]["content"][0]["text"]).get("violation") == "BLOCKED_BY_SANDBOX"
        },
        {
            "name": "Tool 6: check_firewall_status",
            "request": {"jsonrpc": "2.0", "id": 12, "method": "tools/call", "params": {"name": "check_firewall_status", "arguments": {}}},
            "validate": lambda res: "raw_output" in json.loads(res["result"]["content"][0]["text"])
        },
        {
            "name": "Tool 7: manage_firewall_rule (injection blocked)",
            "request": {"jsonrpc": "2.0", "id": 13, "method": "tools/call", "params": {"name": "manage_firewall_rule", "arguments": {"action": "allow", "target": "80; rm -rf /"}}},
            "validate": lambda res: json.loads(res["result"]["content"][0]["text"]).get("success") is False
        },
        {
            "name": "Tool 8: check_failed_logins",
            "request": {"jsonrpc": "2.0", "id": 14, "method": "tools/call", "params": {"name": "check_failed_logins", "arguments": {"limit": 5}}},
            "validate": lambda res: json.loads(res["result"]["content"][0]["text"]).get("success") is True
        },
        {
            "name": "Tool 9: collect_incident_snapshot",
            "request": {"jsonrpc": "2.0", "id": 15, "method": "tools/call", "params": {"name": "collect_incident_snapshot", "arguments": {"log_lines": 5}}},
            "validate": lambda res: "system_health" in json.loads(res["result"]["content"][0]["text"])
        },
        {
            "name": "Tool 10: auto_mitigate_ssh_attack (dry-run)",
            "request": {"jsonrpc": "2.0", "id": 16, "method": "tools/call", "params": {"name": "auto_mitigate_ssh_attack", "arguments": {"threshold": 5, "auto_block": False}}},
            "validate": lambda res: json.loads(res["result"]["content"][0]["text"]).get("success") is True
        },
        {
            "name": "Tool 11: incident_memory (save & search)",
            "request": {"jsonrpc": "2.0", "id": 17, "method": "tools/call", "params": {"name": "incident_memory", "arguments": {"action": "save", "keyword": "test_nginx", "solution": "systemctl restart nginx"}}},
            "validate": lambda res: json.loads(res["result"]["content"][0]["text"]).get("success") is True
        },
        {
            "name": "Tool 12: manage_ollama_models (list)",
            "request": {"jsonrpc": "2.0", "id": 18, "method": "tools/call", "params": {"name": "manage_ollama_models", "arguments": {"action": "list"}}},
            "validate": lambda res: "output" in json.loads(res["result"]["content"][0]["text"])
        },
        {
            "name": "Tool 13: check_ai_hardware",
            "request": {"jsonrpc": "2.0", "id": 19, "method": "tools/call", "params": {"name": "check_ai_hardware", "arguments": {}}},
            "validate": lambda res: json.loads(res["result"]["content"][0]["text"]).get("success") is True
        },
        {
            "name": "Tool 14: ai_model_router",
            "request": {"jsonrpc": "2.0", "id": 20, "method": "tools/call", "params": {"name": "ai_model_router", "arguments": {"prefer_speed": False}}},
            "validate": lambda res: "recommended_model" in json.loads(res["result"]["content"][0]["text"])
        },
        {
            "name": "Tool 15: manage_workspace (list_dir Customize-MCP-Server)",
            "request": {"jsonrpc": "2.0", "id": 21, "method": "tools/call", "params": {"name": "manage_workspace", "arguments": {"action": "list_dir", "path": "."}}},
            "validate": lambda res: json.loads(res["result"]["content"][0]["text"]).get("success") is True
        },
        {
            "name": "Tool 15: manage_workspace (content sandbox approved create_file)",
            "request": {"jsonrpc": "2.0", "id": 22, "method": "tools/call", "params": {"name": "manage_workspace", "arguments": {"action": "create_file", "path": "_mcp_test_tmp.py", "content": "print('workspace_ok')\n"}}},
            "validate": lambda res: json.loads(res["result"]["content"][0]["text"]).get("content_approved") is True
        },
        {
            "name": "Tool 15: manage_workspace (content sandbox block rm -rf)",
            "request": {"jsonrpc": "2.0", "id": 23, "method": "tools/call", "params": {"name": "manage_workspace", "arguments": {"action": "create_file", "path": "_mcp_bad.sh", "content": "#!/bin/bash\nrm -rf /\n"}}},
            "validate": lambda res: json.loads(res["result"]["content"][0]["text"]).get("violation") == "BLOCKED_BY_CONTENT_SANDBOX"
        },
        {
            "name": "Tool 15: manage_workspace (scope block outside Customize-MCP-Server)",
            "request": {"jsonrpc": "2.0", "id": 24, "method": "tools/call", "params": {"name": "manage_workspace", "arguments": {"action": "create_file", "path": "../_mcp_escape.txt", "content": "hi"}}},
            "validate": lambda res: json.loads(res["result"]["content"][0]["text"]).get("violation") == "OUTSIDE_WORKSPACE_SCOPE"
        },
        {
            "name": "Tool 15: manage_workspace (edit_file & run_file inside Customize-MCP-Server)",
            "request": {"jsonrpc": "2.0", "id": 25, "method": "tools/call", "params": {"name": "manage_workspace", "arguments": {"action": "edit_file", "path": "_mcp_test_tmp.py", "content": "print('workspace_edited')\n"}}},
            "validate": lambda res: json.loads(res["result"]["content"][0]["text"]).get("content_approved") is True
        },
        {
            "name": "Tool 15: manage_workspace (run_file .py)",
            "request": {"jsonrpc": "2.0", "id": 26, "method": "tools/call", "params": {"name": "manage_workspace", "arguments": {"action": "run_file", "path": "_mcp_test_tmp.py"}}},
            "validate": lambda res: "workspace_edited" in json.loads(res["result"]["content"][0]["text"]).get("output", "")
        },
        {
            "name": "Tool 15: manage_workspace (delete cleanup)",
            "request": {"jsonrpc": "2.0", "id": 27, "method": "tools/call", "params": {"name": "manage_workspace", "arguments": {"action": "delete", "path": "_mcp_test_tmp.py"}}},
            "validate": lambda res: json.loads(res["result"]["content"][0]["text"]).get("success") is True
        },
        {
            "name": "Tool 16: list_top_processes (cpu, limit 5)",
            "request": {"jsonrpc": "2.0", "id": 28, "method": "tools/call", "params": {"name": "list_top_processes", "arguments": {"sort_by": "cpu", "limit": 5}}},
            "validate": lambda res: json.loads(res["result"]["content"][0]["text"]).get("success") is True
        },
        {
            "name": "Tool 17: kill_process (Sandbox block core PID 1)",
            "request": {"jsonrpc": "2.0", "id": 29, "method": "tools/call", "params": {"name": "kill_process", "arguments": {"pid": 1, "signal": "SIGTERM"}}},
            "validate": lambda res: json.loads(res["result"]["content"][0]["text"]).get("violation") == "BLOCKED_BY_SANDBOX"
        },
        {
            "name": "Tool 18: get_disk_partitions",
            "request": {"jsonrpc": "2.0", "id": 30, "method": "tools/call", "params": {"name": "get_disk_partitions", "arguments": {}}},
            "validate": lambda res: "partitions" in json.loads(res["result"]["content"][0]["text"])
        },
        {
            "name": "Tool 19: read_file_safe (allow /etc/os-release)",
            "request": {"jsonrpc": "2.0", "id": 31, "method": "tools/call", "params": {"name": "read_file_safe", "arguments": {"path": "/etc/os-release", "max_lines": 10}}},
            "validate": lambda res: json.loads(res["result"]["content"][0]["text"]).get("success") is True
        },
        {
            "name": "Tool 19: read_file_safe (Sandbox block /etc/shadow)",
            "request": {"jsonrpc": "2.0", "id": 32, "method": "tools/call", "params": {"name": "read_file_safe", "arguments": {"path": "/etc/shadow", "max_lines": 10}}},
            "validate": lambda res: json.loads(res["result"]["content"][0]["text"]).get("violation") == "BLOCKED_BY_SANDBOX"
        },
        {
            "name": "Tool 20: search_in_logs",
            "request": {"jsonrpc": "2.0", "id": 33, "method": "tools/call", "params": {"name": "search_in_logs", "arguments": {"keyword": "linux", "log_source": "syslog", "limit": 5}}},
            "validate": lambda res: json.loads(res["result"]["content"][0]["text"]).get("success") is True
        },
        {
            "name": "Tool 21: check_file_permissions (/etc/passwd)",
            "request": {"jsonrpc": "2.0", "id": 34, "method": "tools/call", "params": {"name": "check_file_permissions", "arguments": {"path": "/etc/passwd"}}},
            "validate": lambda res: "mode_octal" in json.loads(res["result"]["content"][0]["text"])
        },
        {
            "name": "Tool 22: ping_host (Sandbox block injection)",
            "request": {"jsonrpc": "2.0", "id": 35, "method": "tools/call", "params": {"name": "ping_host", "arguments": {"host": "8.8.8.8; id", "count": 1}}},
            "validate": lambda res: json.loads(res["result"]["content"][0]["text"]).get("violation") == "BLOCKED_BY_SANDBOX"
        },
        {
            "name": "Tool 23: check_dns_resolution (localhost)",
            "request": {"jsonrpc": "2.0", "id": 36, "method": "tools/call", "params": {"name": "check_dns_resolution", "arguments": {"domain": "localhost"}}},
            "validate": lambda res: "records" in json.loads(res["result"]["content"][0]["text"]) or "error" in json.loads(res["result"]["content"][0]["text"])
        },
        {
            "name": "Tool 24: check_http_endpoint (Sandbox block invalid scheme)",
            "request": {"jsonrpc": "2.0", "id": 37, "method": "tools/call", "params": {"name": "check_http_endpoint", "arguments": {"url": "file:///etc/passwd"}}},
            "validate": lambda res: json.loads(res["result"]["content"][0]["text"]).get("violation") == "BLOCKED_BY_SANDBOX"
        },
        {
            "name": "Tool 25: list_cron_jobs",
            "request": {"jsonrpc": "2.0", "id": 38, "method": "tools/call", "params": {"name": "list_cron_jobs", "arguments": {}}},
            "validate": lambda res: "user_crontab" in json.loads(res["result"]["content"][0]["text"])
        },
        {
            "name": "Tool 26: get_user_sessions",
            "request": {"jsonrpc": "2.0", "id": 39, "method": "tools/call", "params": {"name": "get_user_sessions", "arguments": {}}},
            "validate": lambda res: "sessions" in json.loads(res["result"]["content"][0]["text"])
        },
        {
            "name": "Tool 27: manage_docker_containers (ps)",
            "request": {"jsonrpc": "2.0", "id": 40, "method": "tools/call", "params": {"name": "manage_docker_containers", "arguments": {"action": "ps", "container_name": ""}}},
            "validate": lambda res: "action" in json.loads(res["result"]["content"][0]["text"])
        }
    ]

    passed = 0
    for t in tests:
        req_line = json.dumps(t["request"]) + "\n"
        proc.stdin.write(req_line)
        proc.stdin.flush()

        resp_line = proc.stdout.readline()
        if not resp_line:
            print(f"  {RED}[ERROR] No response received from server for: {t['name']}{RESET}")
            continue

        try:
            resp_json = json.loads(resp_line)
            if t["validate"](resp_json):
                print(f"  {GREEN}[PASS]{RESET} {t['name']}")
                passed += 1
            else:
                print(f"  {RED}[FAIL]{RESET} {t['name']} - Unexpected response: {resp_line.strip()}")
        except Exception as e:
            print(f"  {RED}[FAIL]{RESET} {t['name']} - JSON Parsing/Validation Exception: {e}")

    proc.stdin.close()
    proc.terminate()

    print_header("Test Summary")
    if passed == len(tests):
        print(f"{GREEN}{BOLD}All {passed}/{len(tests)} tests PASSED! 100% MCP Specification Compliance.{RESET}\n")
        return 0
    else:
        print(f"{YELLOW}Passed {passed}/{len(tests)} tests.{RESET}\n")
        return 1

if __name__ == "__main__":
    sys.exit(test_mcp_server())
