# System Architecture & Technical Specifications
## Project: Native C++ Model Context Protocol (MCP) Server for Linux
**Course:** Linux & Open Source Software 2026 - VKU

---

## 1. High-Level Architectural Diagram

```
+---------------------------------------------------------------------------------+
|                                 USER INTERFACE                                  |
|   Conversational CLI Terminal / Claude Desktop / Custom Agentic AI Client       |
+---------------------------------------------------------------------------------+
                                       │
                                       │ User Prompt (Vietnamese / English)
                                       ▼
+---------------------------------------------------------------------------------+
|                               AI AGENT CONTROLLER                               |
|   - LLM Reasoning Engine (Google Gemini API / Autonomous Reasoner)             |
|   - Function Calling & Tool Selection Orchestrator                              |
+---------------------------------------------------------------------------------+
                                       │
                                       │ JSON-RPC 2.0 Request (Standard I/O)
                                       ▼
+---------------------------------------------------------------------------------+
|                         NATIVE C++ MCP SERVER (vku_mcp_server)                  |
|                                                                                 |
|  +---------------------------------------------------------------------------+  |
|  |                           MCP PROTOCOL ENGINE                             |  |
|  |   - JSON-RPC 2.0 Parser (nlohmann/json)                                   |  |
|  |   - Handshake: initialize (Protocol 2024-11-05)                           |  |
|  |   - Tool Discovery: tools/list (JSON Schema Draft-07)                     |  |
|  |   - Tool Execution Dispatcher: tools/call                                 |  |
|  +---------------------------------------------------------------------------+  |
|                                       │                                         |
|  +---------------------------------------------------------------------------+  |
|  |                         LINUX POSIX TOOL MODULES                          |  |
|  |                                                                           |  |
|  |  1. System Telemetry       2. Service Daemon      3. Log Diagnostics      |  |
|  |     sysinfo(), statvfs        systemctl (regex)      /var/log, journalctl |  |
|  |     /proc/loadavg             is-active, status      Bounded tail (5-200) |  |
|  |                                                                           |  |
|  |  4. Socket Auditing        5. Security Sandbox                            |  |
|  |     ss -tulpn, /proc/net      Pattern Blacklist (rm -rf, mkfs, fork bomb) |  |
|  |     Exposed port check        Binary Whitelist (df, free, ps, uname)      |  |
|  +---------------------------------------------------------------------------+  |
+---------------------------------------------------------------------------------+
                                       │
                                       │ Native System Calls & Subprocesses
                                       ▼
+---------------------------------------------------------------------------------+
|                              UBUNTU LINUX OS KERNEL                             |
|          Linux Kernel /proc, /sys | Systemd Init | Sockets | Filesystem         |
+---------------------------------------------------------------------------------+
```

---

## 2. Model Context Protocol (MCP) Message Formats

### 2.1 Initialization Handshake (`initialize`)
```json
// Client -> Server
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {}
}

// Server -> Client
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2024-11-05",
    "capabilities": {
      "tools": { "listChanged": false }
    },
    "serverInfo": {
      "name": "vku-linux-mcp-server",
      "version": "1.0.0",
      "description": "High-Performance Native C++ MCP Server for Linux Administration"
    }
  }
}
```

### 2.2 Tool Invocation (`tools/call`)
```json
// Client -> Server
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "get_system_health",
    "arguments": {}
  }
}

// Server -> Client
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\n  \"memory\": {\"total_mb\": 8192, \"used_mb\": 3540, \"used_percentage\": 43.2},\n  \"cpu_load\": {\"load_1min\": 0.45}\n}"
      }
    ],
    "isError": false
  }
}
```

---

## 3. Security Sandbox Design & Guardrails

To prevent prompt injection or rogue LLM tool calls from damaging the Ubuntu host, the C++ MCP Server incorporates an active sandbox:

1. **Destructive Pattern Filter (Blacklist)**:
   Scans incoming command strings for known dangerous signatures:
   `rm -rf`, `mkfs`, `dd if=`, `:(){ :|:& };:`, `chmod -R 777 /`, `> /dev/sd`, `reboot`, `shutdown`, `poweroff`, `passwd`.
2. **Binary Prefix Enforcement (Whitelist)**:
   Commands must initiate with an authorized system diagnostic utility:
   `df`, `free`, `ps`, `top`, `uptime`, `ls`, `grep`, `cat`, `who`, `w`, `ip`, `netstat`, `ss`, `systemctl`, `journalctl`, `find`, `head`, `tail`, `curl`, `ping`, `id`, `uname`, `pwd`.
3. **Execution Buffer Limit**:
   Command outputs are bounded at 64 KB to eliminate memory exhaustion attacks.
