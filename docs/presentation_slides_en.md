# PRESENTATION SLIDES OUTLINE
## Topic 15: High-Performance Native C++ MCP Server for Agentic AI in Linux
**Course:** Linux & Open Source Software 2026 - VKU  
**Team:** Topic 15 Research Team (VKU Linux OSS 2026)

---

### Slide 1: Title & Team Introduction
- **Title:** High-Performance Native C++ MCP Server for Agentic AI in Linux
- **Subtitle:** Model Context Protocol & System Administration Automation
- **Institution:** Vietnam - Korea University of Information and Communication Technology (VKU)
- **Presenter:** Topic 15 Research Team

### Slide 2: The Rise of Agentic AI in System Administration
- What is Agentic AI? An AI with the ability to reason, plan, and autonomously take action.
- The Core Problem: How can an AI model interact with Linux servers safely, reliably, and efficiently?
- The Dangerous Alternative: Giving an AI raw bash access (`rm -rf /` risk, hallucinations, prompt injections).

### Slide 3: What is the Model Context Protocol (MCP)?
- Open standard protocol (pioneered by Anthropic, adopted across AI industry).
- Standardizes bidirectional communication between AI Agents and local/remote tools via JSON-RPC 2.0.
- Why most MCP servers use Python/Node.js: Easy to write, but high RAM footprint (70MB+) and slow execution.

### Slide 4: Our Innovation: Native C++17 MCP Server
- Why rewrite an MCP Server in C++ on Linux?
  1. Direct POSIX system calls (`sysinfo`, `statvfs`, `/proc`).
  2. Sub-millisecond execution latency (16x faster than Python).
  3. Ultra-low RAM footprint (< 3MB RAM vs 70MB in Python).
  4. True systems programming aligned with VKU Linux OSS curriculum!

### Slide 5: System Architecture Overview
- Complete pipeline diagram:
  - User Prompt -> AI Agent Brain (Gemini / Claude / Autonomous Reasoner)
  - -> JSON-RPC 2.0 over standard I/O (stdio)
  - -> Native C++ Server (`vku_mcp_server`)
  - -> POSIX APIs & Systemd (`systemctl`)
  - -> Formatted JSON observations returned to AI.

### Slide 6: C++ Protocol Dispatcher Engine
- File: `src/mcp_server.hpp` & `src/main.cpp`.
- Parses JSON-RPC messages line-by-line using `nlohmann/json`.
- Dispatches: `initialize`, `tools/list`, and `tools/call`.
- Full compliance with MCP Specification `2024-11-05`.

### Slide 7: Tool 1 - Real-time Hardware Telemetry (`get_system_health`)
- C++ POSIX implementation:
  - `<sys/sysinfo.h>` -> Total RAM, Free RAM, Buffers, Uptime, Process count.
  - `<sys/statvfs.h>` -> Storage capacity and percentage of `/`.
  - `/proc/loadavg` -> 1m, 5m, 15m CPU Load.
- Zero external runtime needed.

### Slide 8: Tool 2 - Systemd Daemon Manager (`manage_service`)
- Intercepts and executes `systemctl` actions (`status`, `start`, `stop`, `restart`).
- Regex input sanitization (`^[a-zA-Z0-9_\-\.]+$`) prevents command injection attacks.
- Returns status, active state, exit code, and stdout/stderr.

### Slide 9: Tool 3 - Log Diagnostic Engine (`inspect_logs`)
- Reads trailing log buffers from `/var/log/syslog`, `/var/log/auth.log`, `nginx/error.log` or `journalctl`.
- Enforces strict line bounding (5 to 200 lines) to avoid memory flooding.
- Allows AI to synthesize root causes of server failures.

### Slide 10: Tool 4 - Security Sandboxing & Guardrails (`execute_safe_command`)
- Dual-tier protection:
  1. Destructive Pattern Blacklist: Blocks `rm -rf`, `mkfs`, fork bombs, `chmod 777`.
  2. Binary Prefix Whitelist: Permitted diagnostics (`df`, `free`, `ps`, `uname`, `grep`).
- Output buffer capped at 64KB.

### Slide 11: Tool 5 - Network Socket Auditor (`audit_network_ports`)
- Queries active listening TCP/UDP sockets (`ss -tulpn` / `/proc/net/tcp`).
- Enables AI to detect unauthorized open ports and exposed attack surfaces.

### Slide 12: Dual-Mode Agentic AI Controller (`client/agent_cli.py`)
- **Mode 1 (Online)**: Google Gemini API integration for live LLM reasoning.
- **Mode 2 (Offline)**: Built-in VKU Autonomous Heuristic Reasoner (zero internet required, guarantees 100% demo success in the classroom).

### Slide 13: Live Demonstration Scenarios
- Scenario A: "Kiểm tra tình trạng tài nguyên máy chủ" -> Reads live memory and CPU.
- Scenario B: "Khởi động lại dịch vụ NGINX" -> Systemd state transition.
- Scenario C: "Chạy lệnh 'rm -rf /'" -> Demonstrates Security Sandbox block in real time!

### Slide 14: Experimental Benchmarks
- Benchmark comparison table:
  - RAM Footprint: 2.6 MB (C++) vs 68.4 MB (Python) -> 96% reduction!
  - Cold Start Latency: 3.2 ms vs 380 ms -> 118x faster!
  - 100% test pass rate across 6 automated protocol verification test cases.

### Slide 15: Conclusion & Future Work
- Project Deliverables: Compiled C++ binary, 5 native Linux tools, Security Sandbox, CLI Agent, 100% pass test suite.
- Academic impact: Demonstrates deep operating systems knowledge combined with 2026 Agentic AI technology.
- Q&A Session.
