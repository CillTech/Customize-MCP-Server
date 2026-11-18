#!/usr/bin/env python3
"""
==============================================================================
 VKU Agentic AI - Modern Web UI & Live Telemetry Dashboard
 Powered by: Native C++ Model Context Protocol (MCP) Server
 Author: Tran Duy Duc Anh (24IT009) & VKU Team
 Course: Linux & Open Source Software 2026 - VKU
==============================================================================
"""

import os
import sys
import json
import time
import subprocess
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import urllib.parse

# Import bridge and agent from agent_cli
sys.path.insert(0, os.path.dirname(__file__))
from agent_cli import MCPServerBridge, AgenticController, BIN_PATH

HOST = "0.0.0.0"
PORT = 8080

# Global bridge & agent instances
mcp_bridge = None
agent_instance = None
mcp_traffic_logs = []
MAX_TRAFFIC_LOGS = 50

def log_traffic(direction, data):
    global mcp_traffic_logs
    timestamp = time.strftime("%H:%M:%S")
    entry = {
        "timestamp": timestamp,
        "direction": direction,
        "data": data
    }
    mcp_traffic_logs.append(entry)
    if len(mcp_traffic_logs) > MAX_TRAFFIC_LOGS:
        mcp_traffic_logs.pop(0)

class LoggedBridge(MCPServerBridge):
    def _send_rpc(self, method, params=None):
        self.request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method
        }
        if params is not None:
            payload["params"] = params

        req_str = json.dumps(payload)
        log_traffic("OUT (Client -> C++ MCP)", payload)

        self.proc.stdin.write(req_str + "\n")
        self.proc.stdin.flush()

        resp_line = self.proc.stdout.readline()
        if not resp_line:
            raise RuntimeError("MCP Server terminated unexpectedly.")
        
        resp_json = json.loads(resp_line)
        log_traffic("IN (C++ MCP -> Client)", resp_json)
        return resp_json

def init_backend():
    global mcp_bridge, agent_instance
    if not os.path.exists(BIN_PATH):
        print(f"[!] Binary not found: {BIN_PATH}. Please compile first.")
    mcp_bridge = LoggedBridge(BIN_PATH)
    agent_instance = AgenticController(mcp_bridge)
    print(f"[OK] C++ MCP Server connected. Initialized for Web UI on port {PORT}.")

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VKU Linux Agentic AI - C++ MCP Dashboard</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-base: #090d16;
            --bg-surface: #111827;
            --bg-card: #1f2937;
            --border: #374151;
            --primary: #38bdf8;
            --primary-glow: rgba(56, 189, 248, 0.25);
            --accent: #818cf8;
            --success: #34d399;
            --warning: #fbbf24;
            --danger: #f87171;
            --text-main: #f9fafb;
            --text-muted: #9ca3af;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Plus Jakarta Sans', sans-serif;
            background-color: var(--bg-base);
            color: var(--text-main);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            overflow-x: hidden;
        }

        /* Top Header */
        header {
            background: rgba(17, 24, 39, 0.85);
            backdrop-filter: blur(12px);
            border-bottom: 1px solid var(--border);
            padding: 14px 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: sticky;
            top: 0;
            z-index: 50;
        }

        .brand {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .brand-badge {
            background: linear-gradient(135deg, #0284c7, #6366f1);
            color: white;
            font-weight: 700;
            font-size: 0.85rem;
            padding: 4px 10px;
            border-radius: 6px;
            letter-spacing: 0.5px;
        }

        .brand h1 {
            font-size: 1.15rem;
            font-weight: 700;
            letter-spacing: -0.3px;
        }

        .brand-sub {
            color: var(--text-muted);
            font-size: 0.8rem;
            margin-left: 6px;
        }

        .status-pill {
            display: flex;
            align-items: center;
            gap: 8px;
            background: rgba(52, 211, 153, 0.12);
            color: var(--success);
            border: 1px solid rgba(52, 211, 153, 0.3);
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 600;
        }

        .pulse-dot {
            width: 8px;
            height: 8px;
            background: var(--success);
            border-radius: 50%;
            box-shadow: 0 0 10px var(--success);
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0% { transform: scale(0.95); opacity: 0.8; }
            50% { transform: scale(1.2); opacity: 1; }
            100% { transform: scale(0.95); opacity: 0.8; }
        }

        /* Telemetry Cards Grid */
        .telemetry-bar {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
            gap: 16px;
            padding: 20px 24px;
            background: rgba(17, 24, 39, 0.4);
            border-bottom: 1px solid rgba(55, 65, 81, 0.5);
        }

        .card {
            background: var(--bg-surface);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 8px;
            transition: transform 0.2s, border-color 0.2s;
        }

        .card:hover {
            transform: translateY(-2px);
            border-color: var(--primary);
        }

        .card-title {
            color: var(--text-muted);
            font-size: 0.78rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.6px;
            display: flex;
            justify-content: space-between;
        }

        .card-value {
            font-size: 1.55rem;
            font-weight: 700;
            font-family: 'JetBrains Mono', monospace;
            color: var(--text-main);
        }

        .progress-bar-bg {
            background: #374151;
            height: 6px;
            border-radius: 3px;
            overflow: hidden;
            margin-top: 4px;
        }

        .progress-bar-fill {
            background: linear-gradient(90deg, #38bdf8, #818cf8);
            height: 100%;
            width: 0%;
            transition: width 0.5s ease;
        }

        /* Main Workspace Split */
        .workspace {
            display: grid;
            grid-template-columns: 1fr 420px;
            gap: 20px;
            padding: 20px 24px;
            flex: 1;
        }

        /* Left: Chat Container */
        .chat-panel {
            background: var(--bg-surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            height: calc(100vh - 250px);
        }

        .chat-header {
            padding: 14px 18px;
            border-bottom: 1px solid var(--border);
            background: rgba(31, 41, 55, 0.5);
            font-weight: 600;
            font-size: 0.95rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .msg {
            max-width: 82%;
            padding: 12px 16px;
            border-radius: 10px;
            font-size: 0.92rem;
            line-height: 1.55;
            word-break: break-word;
        }

        .msg-user {
            align-self: flex-end;
            background: linear-gradient(135deg, #0284c7, #2563eb);
            color: white;
            border-bottom-right-radius: 2px;
        }

        .msg-ai {
            align-self: flex-start;
            background: var(--bg-card);
            border: 1px solid var(--border);
            color: var(--text-main);
            border-bottom-left-radius: 2px;
        }

        .msg-ai pre {
            background: #0b0f19;
            padding: 10px 14px;
            border-radius: 6px;
            margin: 8px 0;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85rem;
            overflow-x: auto;
            border: 1px solid #2d3748;
        }

        .tool-badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(251, 191, 36, 0.15);
            color: #fbbf24;
            border: 1px solid rgba(251, 191, 36, 0.3);
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 0.75rem;
            font-family: 'JetBrains Mono', monospace;
            margin-bottom: 6px;
        }

        /* Quick Prompts Bar */
        .quick-prompts {
            padding: 8px 18px;
            display: flex;
            gap: 8px;
            overflow-x: auto;
            background: rgba(17, 24, 39, 0.7);
            border-top: 1px solid var(--border);
        }

        .btn-prompt {
            background: rgba(55, 65, 81, 0.6);
            color: #e2e8f0;
            border: 1px solid #4b5563;
            padding: 5px 12px;
            border-radius: 16px;
            font-size: 0.78rem;
            cursor: pointer;
            white-space: nowrap;
            transition: all 0.2s;
        }

        .btn-prompt:hover {
            background: var(--primary);
            color: #0f172a;
            font-weight: 600;
        }

        .chat-input-box {
            padding: 14px 18px;
            background: var(--bg-surface);
            border-top: 1px solid var(--border);
            display: flex;
            gap: 10px;
        }

        .chat-input {
            flex: 1;
            background: var(--bg-base);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 12px 16px;
            color: white;
            font-size: 0.92rem;
            outline: none;
            transition: border-color 0.2s;
        }

        .chat-input:focus {
            border-color: var(--primary);
            box-shadow: 0 0 0 2px var(--primary-glow);
        }

        .btn-send {
            background: linear-gradient(135deg, #0284c7, #6366f1);
            color: white;
            border: none;
            border-radius: 8px;
            padding: 0 22px;
            font-weight: 600;
            font-size: 0.92rem;
            cursor: pointer;
            transition: opacity 0.2s;
        }

        .btn-send:hover { opacity: 0.9; }

        /* Right: MCP Traffic Inspector */
        .inspector-panel {
            background: var(--bg-surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            display: flex;
            flex-direction: column;
            height: calc(100vh - 250px);
            overflow: hidden;
        }

        .inspector-header {
            padding: 14px 18px;
            border-bottom: 1px solid var(--border);
            background: rgba(31, 41, 55, 0.5);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .inspector-title {
            font-weight: 600;
            font-size: 0.92rem;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .inspector-logs {
            flex: 1;
            overflow-y: auto;
            padding: 12px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.78rem;
            display: flex;
            flex-direction: column;
            gap: 8px;
            background: #090d16;
        }

        .log-entry {
            background: #111827;
            border-radius: 6px;
            padding: 8px 10px;
            border-left: 3px solid #6b7280;
        }

        .log-out { border-left-color: var(--primary); }
        .log-in { border-left-color: var(--success); }

        .log-time { color: var(--text-muted); font-size: 0.7rem; margin-bottom: 4px; }
        .log-dir { font-weight: 700; color: #cbd5e1; }
        .log-body { white-space: pre-wrap; word-break: break-all; color: #94a3b8; max-height: 120px; overflow-y: auto; }

        @media (max-width: 1024px) {
            .workspace { grid-template-columns: 1fr; }
            .chat-panel { height: 500px; }
            .inspector-panel { height: 400px; }
        }
    </style>
</head>
<body>

    <!-- Header -->
    <header>
        <div class="brand">
            <span class="brand-badge">VKU OSS 2026</span>
            <h1>Agentic AI Linux MCP Controller</h1>
            <span class="brand-sub">Native C++17 POSIX Core</span>
        </div>
        <div class="status-pill">
            <div class="pulse-dot"></div>
            <span>MCP Protocol Active (v2024-11-05)</span>
        </div>
    </header>

    <!-- Real-time Hardware Telemetry Bar -->
    <section class="telemetry-bar">
        <div class="card">
            <div class="card-title">
                <span>Memory (RAM)</span>
                <span>POSIX sysinfo</span>
            </div>
            <div class="card-value" id="ram-val">-- MB</div>
            <div class="progress-bar-bg">
                <div class="progress-bar-fill" id="ram-fill"></div>
            </div>
        </div>

        <div class="card">
            <div class="card-title">
                <span>Disk Storage (/)</span>
                <span>POSIX statvfs</span>
            </div>
            <div class="card-value" id="disk-val">-- GB</div>
            <div class="progress-bar-bg">
                <div class="progress-bar-fill" id="disk-fill"></div>
            </div>
        </div>

        <div class="card">
            <div class="card-title">
                <span>CPU Load Average</span>
                <span>/proc/loadavg</span>
            </div>
            <div class="card-value" id="cpu-val">0.00</div>
            <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 4px;">1m | 5m | 15m averages</div>
        </div>

        <div class="card">
            <div class="card-title">
                <span>System Uptime</span>
                <span>Host Telemetry</span>
            </div>
            <div class="card-value" id="uptime-val" style="font-size: 1.15rem;">--</div>
            <div style="font-size: 0.75rem; color: var(--success); margin-top: 4px;">● Server Operating Normally</div>
        </div>
    </section>

    <!-- Workspace -->
    <main class="workspace">
        
        <!-- Left Panel: Chat Interface -->
        <section class="chat-panel">
            <div class="chat-header">
                <span>🤖 AI Agent Terminal Interface</span>
                <span style="font-size: 0.8rem; color: var(--text-muted);">Tran Duy Duc Anh (24IT009)</span>
            </div>

            <div class="chat-messages" id="chat-box">
                <div class="msg msg-ai">
                    Xin chào! Tôi là Trợ lý AI Quản trị Linux VKU được kết nối trực tiếp với <strong>C++ MCP Server</strong> trên nhân Linux.<br><br>
                    Tôi có thể tự động kiểm tra tài nguyên hệ thống, bật/tắt dịch vụ NGINX, đọc nhật ký lỗi, rà soát cổng mạng, hoặc thực thi lệnh an toàn qua Sandbox. Hãy nhập câu hỏi bên dưới hoặc chọn các thao tác nhanh!
                </div>
            </div>

            <!-- Quick Action Prompts -->
            <div class="quick-prompts">
                <button class="btn-prompt" onclick="sendPrompt('Kiểm tra nhiệt độ CPU')">🌡️ Nhiệt độ CPU</button>
                <button class="btn-prompt" onclick="sendPrompt('Kiểm tra sức khỏe hệ thống')">📊 Sức khỏe hệ thống</button>
                <button class="btn-prompt" onclick="sendPrompt('Kiểm tra xem NGINX có đang chạy không')">⚙️ Trạng thái NGINX</button>
                <button class="btn-prompt" onclick="sendPrompt('Khởi động lại dịch vụ NGINX')">🔄 Restart NGINX</button>
                <button class="btn-prompt" onclick="sendPrompt('Rà soát các cổng mạng đang mở')">🛡️ Quét cổng mạng</button>
                <button class="btn-prompt" onclick="sendPrompt('Xem 10 dòng log mới nhất')">📜 Đọc System Logs</button>
                <button class="btn-prompt" onclick="sendPrompt('chạy lệnh rm -rf /tmp/data')">⚠️ Thử nghiệm Sandbox (rm -rf)</button>
            </div>

            <div class="chat-input-box">
                <input type="text" id="user-input" class="chat-input" placeholder="Nhập câu lệnh bằng Tiếng Việt hoặc Tiếng Anh (Enter để gửi)..." onkeydown="if(event.key==='Enter') doSend();">
                <button class="btn-send" onclick="doSend()">Gửi Lệnh</button>
            </div>
        </section>

        <!-- Right Panel: Live JSON-RPC MCP Protocol Inspector -->
        <section class="inspector-panel">
            <div class="inspector-header">
                <div class="inspector-title">
                    <span style="color: var(--primary);">⚡</span>
                    <span>Live MCP JSON-RPC Inspector</span>
                </div>
                <span style="font-size: 0.75rem; color: var(--text-muted);">Real-time Stdio Stream</span>
            </div>
            <div class="inspector-logs" id="traffic-box">
                <!-- Streamed traffic logs -->
            </div>
        </section>

    </main>

    <script>
        // Poll telemetry every 3 seconds
        async function updateTelemetry() {
            try {
                const res = await fetch('/api/telemetry');
                const data = await res.json();
                
                if (data.memory) {
                    document.getElementById('ram-val').innerText = `${data.memory.used_mb} MB (${data.memory.used_percentage}%)`;
                    document.getElementById('ram-fill').style.width = `${data.memory.used_percentage}%`;
                }
                if (data.disk_root) {
                    document.getElementById('disk-val').innerText = `${data.disk_root.used_gb} GB (${data.disk_root.used_percentage}%)`;
                    document.getElementById('disk-fill').style.width = `${data.disk_root.used_percentage}%`;
                }
                if (data.cpu_load) {
                    document.getElementById('cpu-val').innerText = `${data.cpu_load.load_1min} | ${data.cpu_load.load_5min}`;
                }
                if (data.uptime) {
                    document.getElementById('uptime-val').innerText = data.uptime.formatted;
                }
            } catch (err) {
                console.error("Telemetry fetch error:", err);
            }
        }

        // Poll traffic logs every 1.5 seconds
        async function updateTraffic() {
            try {
                const res = await fetch('/api/traffic');
                const logs = await res.json();
                const box = document.getElementById('traffic-box');
                box.innerHTML = '';
                
                logs.slice().reverse().forEach(log => {
                    const div = document.createElement('div');
                    div.className = `log-entry ${log.direction.startsWith('OUT') ? 'log-out' : 'log-in'}`;
                    div.innerHTML = `
                        <div class="log-time">${log.timestamp} • <span class="log-dir">${log.direction}</span></div>
                        <div class="log-body">${escapeHtml(JSON.stringify(log.data, null, 2))}</div>
                    `;
                    box.appendChild(div);
                });
            } catch (err) {
                console.error("Traffic fetch error:", err);
            }
        }

        function escapeHtml(str) {
            return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        }

        function appendMessage(sender, text, isAi = false) {
            const chatBox = document.getElementById('chat-box');
            const div = document.createElement('div');
            div.className = `msg ${isAi ? 'msg-ai' : 'msg-user'}`;
            div.innerHTML = text.replace(/\\n/g, '<br>');
            chatBox.appendChild(div);
            chatBox.scrollTop = chatBox.scrollHeight;
        }

        async function doSend() {
            const input = document.getElementById('user-input');
            const prompt = input.value.trim();
            if (!prompt) return;

            appendMessage('user', prompt, false);
            input.value = '';

            // Show thinking
            const thinkingDiv = document.createElement('div');
            thinkingDiv.className = 'msg msg-ai';
            thinkingDiv.id = 'thinking-temp';
            thinkingDiv.innerHTML = '<span class="tool-badge">🧠 AI Thinking...</span> Đang kích hoạt MCP C++ Engine...';
            document.getElementById('chat-box').appendChild(thinkingDiv);
            document.getElementById('chat-box').scrollTop = document.getElementById('chat-box').scrollHeight;

            try {
                const res = await fetch('/api/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ prompt: prompt })
                });
                const data = await res.json();
                
                const temp = document.getElementById('thinking-temp');
                if (temp) temp.remove();

                appendMessage('ai', data.response, true);
                updateTelemetry();
                updateTraffic();
            } catch (err) {
                const temp = document.getElementById('thinking-temp');
                if (temp) temp.remove();
                appendMessage('ai', `<span style="color:var(--danger)">Lỗi kết nối: ${err.message}</span>`, true);
            }
        }

        function sendPrompt(text) {
            document.getElementById('user-input').value = text;
            doSend();
        }

        // Initialize polling intervals
        updateTelemetry();
        updateTraffic();
        setInterval(updateTelemetry, 3000);
        setInterval(updateTraffic, 1500);
    </script>
</body>
</html>
"""

class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/" or parsed.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
        elif parsed.path == "/api/telemetry":
            try:
                raw = mcp_bridge.call_tool("get_system_health")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(raw.encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
        elif parsed.path == "/api/traffic":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(mcp_traffic_logs).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/chat":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len)
            req_data = json.loads(body.decode("utf-8"))
            prompt = req_data.get("prompt", "")

            response_text = agent_instance.process_query(prompt)

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"response": response_text}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Silence standard HTTP access logging to keep console clean
        return

def run_server():
    init_backend()
    server = ThreadingHTTPServer((HOST, PORT), RequestHandler)
    print("======================================================================")
    print(f" [VKU OSS 2026] Web UI & Live Telemetry Dashboard is ONLINE!")
    print(f" -> Local Access   : http://localhost:{PORT}")
    print(f" -> Network Access : http://0.0.0.0:{PORT}")
    print("======================================================================")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping web server...")
        mcp_bridge.close()
        server.server_close()

if __name__ == "__main__":
    run_server()
