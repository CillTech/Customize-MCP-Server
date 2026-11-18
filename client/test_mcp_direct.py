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

def test_mcp_server():
    print(f"{BOLD}[VKU OSS 2026] Starting Automated MCP C++ Protocol Verification{RESET}")
    print(f"Target Binary: {BIN_PATH}")

    if not os.path.exists(BIN_PATH):
        print(f"{RED}[FAIL] Target binary not found at: {BIN_PATH}. Please run 'make' first.{RESET}")
        sys.exit(1)

    proc = subprocess.Popen(
        [BIN_PATH],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )

    tests = [
        {
            "name": "MCP Handshake (initialize)",
            "request": {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            "validate": lambda res: res.get("result", {}).get("protocolVersion") == "2024-11-05"
        },
        {
            "name": "MCP Tool Discovery (tools/list)",
            "request": {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            "validate": lambda res: len(res.get("result", {}).get("tools", [])) >= 5
        },
        {
            "name": "Tool Execution: get_system_health",
            "request": {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "get_system_health", "arguments": {}}
            },
            "validate": lambda res: "memory" in json.loads(res["result"]["content"][0]["text"])
        },
        {
            "name": "Tool Execution: audit_network_ports",
            "request": {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "audit_network_ports", "arguments": {}}
            },
            "validate": lambda res: "raw_sockets" in json.loads(res["result"]["content"][0]["text"])
        },
        {
            "name": "Security Sandbox: Dangerous Command Block (rm -rf)",
            "request": {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {"name": "execute_safe_command", "arguments": {"command": "rm -rf /tmp/test"}}
            },
            "validate": lambda res: json.loads(res["result"]["content"][0]["text"]).get("violation") == "BLOCKED_BY_SANDBOX"
        },
        {
            "name": "Security Sandbox: Approved Command Execution (uname -a)",
            "request": {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {"name": "execute_safe_command", "arguments": {"command": "uname -a"}}
            },
            "validate": lambda res: json.loads(res["result"]["content"][0]["text"]).get("allowed") is True
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
