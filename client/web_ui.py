#!/usr/bin/env python3
"""
==============================================================================
 VKU Agentic AI - Modern Web UI & Live Telemetry Dashboard
 Powered by: Native C++ Model Context Protocol (MCP) Server
 Author: VKU OSS Team
 Course: Linux & Open Source Software 2026 - VKU
==============================================================================
"""

import os
import sys
import json
import time
import subprocess
import threading
import re
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import urllib.parse
import urllib.request

# Import bridge and agent from agent_cli
sys.path.insert(0, os.path.dirname(__file__))
from agent_cli import MCPServerBridge, AgenticController, BIN_PATH

HOST = "0.0.0.0"
PORT = 8080
SERVER_BOOT_TIME = int(time.time() * 1000)

# Global bridge & agent instances
mcp_bridge = None
agent_instance = None
mcp_traffic_logs = []
MAX_TRAFFIC_LOGS = 50
watchdog_enabled = False
watchdog_alerts = []

def send_external_alert(message):
    # Gửi cảnh báo qua Telegram Bot hoặc Discord Webhook nếu được cấu hình biến môi trường
    tg_token = os.environ.get("VKU_TELEGRAM_BOT_TOKEN")
    tg_chat = os.environ.get("VKU_TELEGRAM_CHAT_ID")
    discord_hook = os.environ.get("VKU_DISCORD_WEBHOOK")
    try:
        if tg_token and tg_chat:
            url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
            data = json.dumps({"chat_id": tg_chat, "text": message}).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=4)
        if discord_hook:
            data = json.dumps({"content": message}).encode("utf-8")
            req = urllib.request.Request(discord_hook, data=data, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=4)
    except Exception:
        pass

def add_watchdog_alert(level, message):
    global watchdog_alerts
    entry = {"timestamp": time.strftime("%H:%M:%S"), "level": level, "message": message}
    watchdog_alerts.append(entry)
    if len(watchdog_alerts) > 20:
        watchdog_alerts.pop(0)
    send_external_alert(f"[VKU AI Watchdog - {level}] {message}")

def self_healing_watchdog():
    # Luồng chạy ngầm (Self-Healing): mỗi 20s tự kiểm tra RAM & dịch vụ nginx để tự phục hồi sự cố
    while True:
        time.sleep(20)
        if not watchdog_enabled or mcp_bridge is None:
            continue
        try:
            health_raw = mcp_bridge.call_tool("get_system_health")
            health = json.loads(health_raw)
            ram_pct = health.get("memory", {}).get("used_percentage", 0)
            if ram_pct >= 90:
                add_watchdog_alert("WARNING", f"Cảnh báo RAM cao ({ram_pct}%)! AI đang ghi nhận snapshot sự cố.")
                mcp_bridge.call_tool("collect_incident_snapshot", {"log_lines": 10})

            svc_raw = mcp_bridge.call_tool("manage_service", {"service_name": "nginx", "action": "is-active"})
            svc = json.loads(svc_raw)
            if svc.get("active_state") in ("inactive", "failed"):
                mcp_bridge.call_tool("inspect_logs", {"log_source": "nginx", "lines": 10})
                mcp_bridge.call_tool("manage_service", {"service_name": "nginx", "action": "restart"})
                mcp_bridge.call_tool("incident_memory", {
                    "action": "save",
                    "keyword": "nginx",
                    "solution": "Auto-restarted nginx by Self-Healing Watchdog"
                })
                add_watchdog_alert("HEALED", "Phát hiện NGINX ngừng hoạt động! AI đã đọc log, tự khởi động lại và lưu vào Incident Memory.")
        except Exception:
            pass

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

# Kế thừa MCPServerBridge để ghi lại toàn bộ gói tin JSON-RPC gửi/nhận hiển thị lên Live Inspector
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
        log_traffic("OUT (Client -> C++ MCP)", payload) # Lưu log chiều gửi đi để hiển thị lên bảng Live Inspector

        self.proc.stdin.write(req_str + "\n")
        self.proc.stdin.flush()

        resp_line = self.proc.stdout.readline()
        if not resp_line:
            raise RuntimeError("MCP Server terminated unexpectedly.")
        
        resp_json = json.loads(resp_line)
        log_traffic("IN (C++ MCP -> Client)", resp_json) # Lưu log chiều phản hồi từ C++ Server
        return resp_json

# Khởi tạo kết nối C++ MCP Server và AI Agent cho Web UI
def init_backend():
    global mcp_bridge, agent_instance
    if not os.path.exists(BIN_PATH):
        print(f"[!] Binary not found: {BIN_PATH}. Please compile first.")
    mcp_bridge = LoggedBridge(BIN_PATH)
    agent_instance = AgenticController(mcp_bridge)
    threading.Thread(target=self_healing_watchdog, daemon=True).start()
    print(f"[OK] C++ MCP Server connected. Initialized for Web UI on port {PORT}.")

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VKU Linux Agentic AI - C++ MCP Dashboard</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-base: #0b0f19;
            --bg-surface: #111827;
            --bg-card: #1a2234;
            --bg-hover: #232d42;
            --border: #2a3449;
            --primary: #38bdf8;
            --primary-glow: rgba(56, 189, 248, 0.18);
            --accent: #818cf8;
            --success: #34d399;
            --warning: #fbbf24;
            --danger: #f87171;
            --text-main: #f3f4f6;
            --text-muted: #94a3b8;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
            background-color: var(--bg-base);
            color: var(--text-main);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            overflow-x: hidden;
        }

        /* Thanh cuộn tinh gọn */
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #334155; border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: #475569; }

        /* Top Header */
        header {
            background: rgba(17, 24, 39, 0.88);
            backdrop-filter: blur(12px);
            border-bottom: 1px solid var(--border);
            padding: 12px 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: sticky;
            top: 0;
            z-index: 50;
            gap: 12px;
        }

        .brand { display: flex; align-items: center; gap: 12px; }
        .brand-badge {
            background: linear-gradient(135deg, #0284c7, #6366f1);
            color: white;
            font-weight: 700;
            font-size: 0.8rem;
            padding: 4px 10px;
            border-radius: 6px;
            letter-spacing: 0.4px;
        }
        .brand h1 { font-size: 1.08rem; font-weight: 700; letter-spacing: -0.3px; }
        .brand-sub { color: var(--text-muted); font-size: 0.78rem; }

        .header-actions { display: flex; align-items: center; gap: 10px; }
        .btn-toggle-inspector {
            background: var(--bg-card);
            border: 1px solid var(--border);
            color: var(--text-main);
            padding: 6px 12px;
            border-radius: 8px;
            font-size: 0.8rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .btn-toggle-inspector:hover { border-color: var(--primary); color: var(--primary); }

        .status-pill {
            display: flex;
            align-items: center;
            gap: 8px;
            background: rgba(52, 211, 153, 0.1);
            border: 1px solid rgba(52, 211, 153, 0.28);
            color: var(--success);
            padding: 6px 12px;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 600;
        }
        .pulse-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--success);
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0% { box-shadow: 0 0 0 0 rgba(52, 211, 153, 0.6); }
            70% { box-shadow: 0 0 0 6px rgba(52, 211, 153, 0); }
            100% { box-shadow: 0 0 0 0 rgba(52, 211, 153, 0); }
        }

        /* Telemetry Bar (4 cards nhỏ gọn) */
        .telemetry-bar {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 14px;
            padding: 16px 24px 0 24px;
        }
        .card {
            background: var(--bg-surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 14px 16px;
            display: flex;
            flex-direction: column;
            gap: 6px;
        }
        .card-title {
            display: flex;
            justify-content: space-between;
            font-size: 0.76rem;
            color: var(--text-muted);
            font-weight: 500;
        }
        .card-value {
            font-size: 1.15rem;
            font-weight: 700;
            font-family: 'JetBrains Mono', monospace;
        }
        .progress-bar-bg {
            width: 100%;
            height: 6px;
            background: #1e293b;
            border-radius: 999px;
            overflow: hidden;
            margin-top: 2px;
        }
        .progress-bar-fill {
            height: 100%;
            width: 0%;
            background: var(--success);
            border-radius: 999px;
            transition: width 0.4s ease, background-color 0.3s ease;
        }

        /* Workspace 3 Cột: Sidebar Tools | Chat | Inspector */
        .workspace {
            display: grid;
            grid-template-columns: 275px 1fr 370px;
            gap: 16px;
            padding: 16px 24px 20px 24px;
            flex: 1;
            min-height: 0;
            transition: grid-template-columns 0.25s ease;
        }
        .workspace.inspector-hidden {
            grid-template-columns: 275px 1fr 0px;
        }
        .workspace.inspector-hidden .inspector-panel {
            display: none;
        }

        /* Left Sidebar: Accordion Tools */
        .sidebar-panel {
            background: var(--bg-surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            display: flex;
            flex-direction: column;
            height: calc(100vh - 210px);
            overflow: hidden;
        }
        .sidebar-header {
            padding: 13px 16px;
            border-bottom: 1px solid var(--border);
            background: rgba(26, 34, 52, 0.5);
            font-weight: 600;
            font-size: 0.88rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .tool-count-badge {
            background: rgba(56, 189, 248, 0.15);
            color: var(--primary);
            padding: 2px 8px;
            border-radius: 999px;
            font-size: 0.72rem;
            font-weight: 700;
        }
        .sidebar-content {
            flex: 1;
            overflow-y: auto;
            padding: 10px;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        .acc-group {
            flex-shrink: 0;
            border: 1px solid var(--border);
            border-radius: 8px;
            background: rgba(15, 23, 42, 0.5);
            overflow: hidden;
        }
        .acc-header {
            width: 100%;
            background: transparent;
            border: none;
            color: var(--text-main);
            padding: 10px 12px;
            font-size: 0.82rem;
            font-weight: 600;
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: pointer;
            text-align: left;
        }
        .acc-header:hover { background: var(--bg-hover); }
        .acc-body {
            display: none;
            flex-direction: column;
            gap: 4px;
            padding: 4px 8px 8px 8px;
            border-top: 1px solid rgba(42, 52, 73, 0.6);
        }
        .acc-group.open .acc-body { display: flex; }
        .acc-arrow { font-size: 0.7rem; color: var(--text-muted); transition: transform 0.2s; }
        .acc-group.open .acc-arrow { transform: rotate(90deg); }

        .tool-item {
            background: var(--bg-card);
            border: 1px solid transparent;
            color: var(--text-main);
            padding: 7px 10px;
            border-radius: 6px;
            font-size: 0.78rem;
            cursor: pointer;
            text-align: left;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: all 0.15s;
        }
        .tool-item:hover { border-color: var(--primary); background: var(--bg-hover); }
        .tool-item.planned { opacity: 0.55; cursor: default; }
        .tool-item.planned:hover { border-color: transparent; background: var(--bg-card); }
        .tool-name { font-family: 'JetBrains Mono', monospace; font-size: 0.74rem; }
        .tag-live {
            font-size: 0.65rem;
            padding: 1px 6px;
            border-radius: 4px;
            background: rgba(52, 211, 153, 0.15);
            color: var(--success);
            font-weight: 600;
        }
        .tag-plan {
            font-size: 0.65rem;
            padding: 1px 6px;
            border-radius: 4px;
            background: rgba(148, 163, 184, 0.15);
            color: var(--text-muted);
        }

        /* Center: Chat Panel */
        .chat-panel {
            background: var(--bg-surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            display: flex;
            flex-direction: column;
            height: calc(100vh - 210px);
            overflow: hidden;
        }
        .chat-header {
            padding: 13px 18px;
            border-bottom: 1px solid var(--border);
            background: rgba(26, 34, 52, 0.5);
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-weight: 600;
            font-size: 0.9rem;
        }
        .btn-clear-chat {
            background: var(--bg-card);
            border: 1px solid var(--border);
            color: var(--text-muted);
            padding: 5px 10px;
            border-radius: 6px;
            font-size: 0.76rem;
            cursor: pointer;
            transition: all 0.2s;
        }
        .btn-clear-chat:hover { color: var(--text-main); border-color: var(--primary); }

        .chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 18px;
            display: flex;
            flex-direction: column;
            gap: 14px;
        }
        .msg {
            max-width: 88%;
            padding: 12px 16px;
            border-radius: 12px;
            font-size: 0.9rem;
            line-height: 1.55;
            word-wrap: break-word;
        }
        .msg-user {
            align-self: flex-end;
            background: linear-gradient(135deg, #0284c7, #2563eb);
            color: white;
            border-bottom-right-radius: 4px;
        }
        .msg-ai {
            align-self: flex-start;
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-bottom-left-radius: 4px;
        }
        .msg-ai pre {
            background: #090d16;
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 10px 12px;
            margin: 8px 0;
            overflow-x: auto;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.8rem;
            color: #e2e8f0;
        }
        .msg-ai code {
            font-family: 'JetBrains Mono', monospace;
            background: rgba(56, 189, 248, 0.12);
            color: var(--primary);
            padding: 1px 5px;
            border-radius: 4px;
            font-size: 0.82rem;
        }
        .msg-ai pre code { background: transparent; color: inherit; padding: 0; }
        .tool-badge {
            display: inline-block;
            background: rgba(129, 140, 248, 0.18);
            color: var(--accent);
            font-size: 0.75rem;
            font-weight: 600;
            padding: 2px 8px;
            border-radius: 6px;
            margin-right: 6px;
        }

        /* 4 Quick Actions gọn nhẹ */
        .quick-prompts {
            padding: 10px 16px;
            border-top: 1px solid var(--border);
            background: rgba(15, 23, 42, 0.45);
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }
        .btn-prompt {
            background: var(--bg-card);
            border: 1px solid var(--border);
            color: var(--text-main);
            padding: 5px 11px;
            border-radius: 999px;
            font-size: 0.76rem;
            cursor: pointer;
            transition: all 0.15s;
        }
        .btn-prompt:hover { border-color: var(--primary); color: var(--primary); background: var(--primary-glow); }

        .chat-input-box {
            padding: 12px 16px;
            border-top: 1px solid var(--border);
            display: flex;
            gap: 10px;
            background: var(--bg-surface);
        }
        .chat-input {
            flex: 1;
            background: #090d16;
            border: 1px solid var(--border);
            color: var(--text-main);
            padding: 10px 14px;
            border-radius: 8px;
            font-size: 0.9rem;
            outline: none;
        }
        .chat-input:focus { border-color: var(--primary); }
        .btn-send {
            background: linear-gradient(135deg, #0284c7, #4f46e5);
            color: white;
            border: none;
            padding: 0 20px;
            border-radius: 8px;
            font-weight: 600;
            font-size: 0.88rem;
            cursor: pointer;
        }
        .btn-send:hover { opacity: 0.92; }

        /* Right Panel: Live MCP Inspector */
        .inspector-panel {
            background: var(--bg-surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            display: flex;
            flex-direction: column;
            height: calc(100vh - 210px);
            overflow: hidden;
        }
        .inspector-header {
            padding: 12px 16px;
            border-bottom: 1px solid var(--border);
            background: rgba(26, 34, 52, 0.5);
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        .inspector-top {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .inspector-title {
            font-weight: 600;
            font-size: 0.88rem;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .filter-pills { display: flex; gap: 6px; }
        .filter-btn {
            background: var(--bg-card);
            border: 1px solid var(--border);
            color: var(--text-muted);
            padding: 3px 9px;
            border-radius: 6px;
            font-size: 0.72rem;
            cursor: pointer;
        }
        .filter-btn.active {
            background: var(--primary-glow);
            border-color: var(--primary);
            color: var(--primary);
            font-weight: 600;
        }

        .inspector-logs {
            flex: 1;
            overflow-y: auto;
            padding: 10px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.75rem;
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
        .log-blocked { border-left-color: var(--danger); background: rgba(248, 113, 113, 0.08); }
        .log-time { color: var(--text-muted); font-size: 0.68rem; margin-bottom: 4px; }
        .log-dir { font-weight: 700; color: #e2e8f0; }
        .log-body { white-space: pre-wrap; word-break: break-all; color: #94a3b8; max-height: 120px; overflow-y: auto; }

        @media (max-width: 1180px) {
            .telemetry-bar { grid-template-columns: repeat(2, 1fr); }
            .workspace, .workspace.inspector-hidden { grid-template-columns: 1fr; }
            .sidebar-panel { height: auto; max-height: 260px; }
            .chat-panel { height: 500px; }
            .inspector-panel { height: 360px; }
        }
    </style>
</head>
<body>

    <!-- Header -->
    <header>
        <div class="brand">
            <span class="brand-badge">VKU OSS 2026</span>
            <div>
                <h1>Agentic AI Linux MCP Controller</h1>
                <span class="brand-sub">Native C++17 POSIX Core • 14 Active Tools</span>
            </div>
        </div>
        <div class="header-actions">
            <button class="btn-toggle-inspector" onclick="toggleWatchdog()" id="toggle-wd-btn">
                🛡️ Watchdog: OFF
            </button>
            <button class="btn-toggle-inspector" onclick="toggleInspector()" id="toggle-insp-btn">
                ⚡ Ẩn Inspector
            </button>
            <div class="status-pill">
                <div class="pulse-dot"></div>
                <span>MCP Active (v2024-11-05)</span>
            </div>
        </div>
    </header>

    <!-- Thanh Telemetry 4 chỉ số -->
    <section class="telemetry-bar">
        <div class="card">
            <div class="card-title"><span>Memory (RAM)</span><span>/proc/meminfo</span></div>
            <div class="card-value" id="ram-val">-- MB</div>
            <div class="progress-bar-bg"><div class="progress-bar-fill" id="ram-fill"></div></div>
        </div>
        <div class="card">
            <div class="card-title"><span>Disk Storage (/)</span><span>POSIX statvfs</span></div>
            <div class="card-value" id="disk-val">-- GB</div>
            <div class="progress-bar-bg"><div class="progress-bar-fill" id="disk-fill"></div></div>
        </div>
        <div class="card">
            <div class="card-title"><span>CPU Load Average</span><span>/proc/loadavg</span></div>
            <div class="card-value" id="cpu-val">0.00</div>
            <div style="font-size: 0.72rem; color: var(--text-muted);">1m | 5m trung bình</div>
        </div>
        <div class="card">
            <div class="card-title"><span>System Uptime</span><span>Host Telemetry</span></div>
            <div class="card-value" id="uptime-val" style="font-size: 1.05rem;">--</div>
            <div style="font-size: 0.72rem; color: var(--success);">● Server đang hoạt động</div>
        </div>
    </section>

    <!-- Workspace 3 cột -->
    <main class="workspace" id="workspace-grid">

        <!-- Cột trái: Sidebar Accordion Tools -->
        <aside class="sidebar-panel">
            <div class="sidebar-header">
                <span>🧰 Danh mục MCP Tools</span>
                <span class="tool-count-badge">14 Live</span>
            </div>
            <div class="sidebar-content">
                <!-- Nhóm 1: Hệ thống & Dịch vụ -->
                <div class="acc-group open">
                    <button class="acc-header" onclick="toggleGroup(this)">
                        <span>🖥️ Hệ thống & Dịch vụ (3)</span>
                        <span class="acc-arrow">▶</span>
                    </button>
                    <div class="acc-body">
                        <button class="tool-item" onclick="sendPrompt('Kiểm tra sức khỏe hệ thống')">
                            <span class="tool-name">get_system_health</span><span class="tag-live">LIVE</span>
                        </button>
                        <button class="tool-item" onclick="sendPrompt('Kiểm tra trạng thái dịch vụ ssh')">
                            <span class="tool-name">manage_service</span><span class="tag-live">LIVE</span>
                        </button>
                        <button class="tool-item" onclick="sendPrompt('Xem 15 dòng log syslog gần nhất')">
                            <span class="tool-name">inspect_logs</span><span class="tag-live">LIVE</span>
                        </button>
                    </div>
                </div>

                <!-- Nhóm 2: Bảo mật & Tường lửa -->
                <div class="acc-group open">
                    <button class="acc-header" onclick="toggleGroup(this)">
                        <span>🛡️ Bảo mật & Tường lửa (5)</span>
                        <span class="acc-arrow">▶</span>
                    </button>
                    <div class="acc-body">
                        <button class="tool-item" onclick="sendPrompt('Rà soát các cổng mạng đang mở')">
                            <span class="tool-name">audit_network_ports</span><span class="tag-live">LIVE</span>
                        </button>
                        <button class="tool-item" onclick="sendPrompt('Chạy lệnh uname -a')">
                            <span class="tool-name">execute_safe_command</span><span class="tag-live">LIVE</span>
                        </button>
                        <button class="tool-item" onclick="sendPrompt('Kiểm tra trạng thái tường lửa ufw')">
                            <span class="tool-name">check_firewall_status</span><span class="tag-live">LIVE</span>
                        </button>
                        <button class="tool-item" onclick="sendPrompt('Mở port 8080 trên tường lửa ufw')">
                            <span class="tool-name">manage_firewall_rule</span><span class="tag-live">LIVE</span>
                        </button>
                        <button class="tool-item" onclick="sendPrompt('Kiểm tra các lần đăng nhập SSH thất bại')">
                            <span class="tool-name">check_failed_logins</span><span class="tag-live">LIVE</span>
                        </button>
                    </div>
                </div>

                <!-- Nhóm 3: Agentic AI & Tự hành -->
                <div class="acc-group open">
                    <button class="acc-header" onclick="toggleGroup(this)">
                        <span>🤖 Agentic AI & Tự hành (6)</span>
                        <span class="acc-arrow">▶</span>
                    </button>
                    <div class="acc-body">
                        <button class="tool-item" onclick="sendPrompt('Thu thập snapshot sự cố hệ thống hiện tại')">
                            <span class="tool-name">collect_incident_snapshot</span><span class="tag-live">LIVE</span>
                        </button>
                        <button class="tool-item" onclick="sendPrompt('Quét các IP đang brute-force SSH')">
                            <span class="tool-name">auto_mitigate_ssh_attack</span><span class="tag-live">LIVE</span>
                        </button>
                        <button class="tool-item" onclick="sendPrompt('Tra cứu bộ nhớ sự cố liên quan tới nginx')">
                            <span class="tool-name">incident_memory</span><span class="tag-live">LIVE</span>
                        </button>
                        <button class="tool-item" onclick="sendPrompt('Liệt kê các model Ollama đang cài')">
                            <span class="tool-name">manage_ollama_models</span><span class="tag-live">LIVE</span>
                        </button>
                        <button class="tool-item" onclick="sendPrompt('Kiểm tra phần cứng GPU và CPU cho AI')">
                            <span class="tool-name">check_ai_hardware</span><span class="tag-live">LIVE</span>
                        </button>
                        <button class="tool-item" onclick="sendPrompt('Gợi ý model Qwen phù hợp với RAM hiện tại')">
                            <span class="tool-name">ai_model_router</span><span class="tag-live">LIVE</span>
                        </button>
                    </div>
                </div>

                <!-- Nhóm 4: Mở rộng theo lộ trình -->
                <div class="acc-group">
                    <button class="acc-header" onclick="toggleGroup(this)">
                        <span>🚀 Lộ trình mở rộng (12)</span>
                        <span class="acc-arrow">▶</span>
                    </button>
                    <div class="acc-body">
                        <div class="tool-item planned"><span class="tool-name">list_top_processes</span><span class="tag-plan">Plan</span></div>
                        <div class="tool-item planned"><span class="tool-name">read_file_safe</span><span class="tag-plan">Plan</span></div>
                        <div class="tool-item planned"><span class="tool-name">ping_host</span><span class="tag-plan">Plan</span></div>
                        <div class="tool-item planned"><span class="tool-name">manage_docker_containers</span><span class="tag-plan">Plan</span></div>
                    </div>
                </div>
            </div>
        </aside>

        <!-- Cột giữa: Chat Interface -->
        <section class="chat-panel">
            <div class="chat-header">
                <span>🤖 AI Agent Terminal Interface</span>
                <button class="btn-clear-chat" onclick="clearChat()">🔄 Làm mới Chat</button>
            </div>

            <div class="chat-messages" id="chat-box">
                <div class="msg msg-ai">
                    Xin chào! Tôi là Trợ lý AI Quản trị Linux VKU kết nối trực tiếp với <strong>C++ MCP Server</strong>.<br><br>
                    Chọn nhanh một công cụ ở cột bên trái hoặc nhập câu hỏi bằng tiếng Việt ở bên dưới để bắt đầu!
                </div>
            </div>

            <!-- 4 Quick Actions hay dùng nhất -->
            <div class="quick-prompts">
                <button class="btn-prompt" onclick="sendPrompt('Kiểm tra sức khỏe hệ thống')">📊 Sức khỏe hệ thống</button>
                <button class="btn-prompt" onclick="sendPrompt('Rà soát các cổng mạng đang mở')">🛡️ Quét cổng mạng</button>
                <button class="btn-prompt" onclick="sendPrompt('Kiểm tra trạng thái tường lửa ufw')">🔥 Trạng thái Firewall</button>
                <button class="btn-prompt" onclick="sendPrompt('chạy lệnh rm -rf /tmp/data')">⚠️ Test Sandbox (rm -rf)</button>
            </div>

            <div class="chat-input-box">
                <input type="text" id="user-input" class="chat-input" placeholder="Nhập câu lệnh Tiếng Việt hoặc Tiếng Anh (Enter để gửi)..." onkeydown="if(event.key==='Enter') doSend();">
                <button class="btn-send" onclick="doSend()">Gửi Lệnh</button>
            </div>
        </section>

        <!-- Cột phải: Live JSON-RPC MCP Protocol Inspector -->
        <section class="inspector-panel">
            <div class="inspector-header">
                <div class="inspector-top">
                    <div class="inspector-title">
                        <span style="color: var(--primary);">⚡</span>
                        <span>Live MCP Inspector</span>
                    </div>
                    <span style="font-size: 0.7rem; color: var(--text-muted);">Stdio Stream</span>
                </div>
                <div class="filter-pills">
                    <button class="filter-btn active" onclick="setTrafficFilter('all', this)">Tất cả</button>
                    <button class="filter-btn" onclick="setTrafficFilter('ok', this)">Thành công</button>
                    <button class="filter-btn" onclick="setTrafficFilter('blocked', this)">Bị Sandbox chặn</button>
                </div>
            </div>
            <div class="inspector-logs" id="traffic-box"></div>
        </section>

    </main>

    <script>
        let currentTrafficFilter = 'all';
        let cachedLogs = [];

        function toggleGroup(btn) {
            btn.parentElement.classList.toggle('open');
        }

        function toggleInspector() {
            const ws = document.getElementById('workspace-grid');
            const btn = document.getElementById('toggle-insp-btn');
            ws.classList.toggle('inspector-hidden');
            btn.innerText = ws.classList.contains('inspector-hidden') ? '⚡ Hiện Inspector' : '⚡ Ẩn Inspector';
        }

        let lastAlertCount = 0;
        async function toggleWatchdog() {
            try {
                const res = await fetch('/api/watchdog', { method: 'POST' });
                const data = await res.json();
                const btn = document.getElementById('toggle-wd-btn');
                btn.innerText = data.enabled ? '🛡️ Watchdog: ON' : '🛡️ Watchdog: OFF';
                btn.style.borderColor = data.enabled ? 'var(--success)' : 'var(--border)';
                btn.style.color = data.enabled ? 'var(--success)' : 'var(--text-main)';
            } catch (e) {}
        }

        async function pollAlerts() {
            try {
                const res = await fetch('/api/alerts');
                const alerts = await res.json();
                if (alerts.length > lastAlertCount) {
                    for (let i = lastAlertCount; i < alerts.length; i++) {
                        appendMessage('ai', `🤖 **[Self-Healing Watchdog - ${alerts[i].timestamp}]**\n${alerts[i].message}`, true);
                    }
                    lastAlertCount = alerts.length;
                }
            } catch (e) {}
        }
        setInterval(pollAlerts, 4000);

        function setTrafficFilter(mode, btn) {
            currentTrafficFilter = mode;
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            renderTraffic();
        }

        function setBarColor(el, pct) {
            if (pct >= 85) el.style.backgroundColor = 'var(--danger)';
            else if (pct >= 70) el.style.backgroundColor = 'var(--warning)';
            else el.style.backgroundColor = 'var(--success)';
        }

        async function updateTelemetry() {
            try {
                const res = await fetch('/api/telemetry');
                const data = await res.json();
                if (data.memory) {
                    document.getElementById('ram-val').innerText = `${data.memory.used_mb} MB (${data.memory.used_percentage}%)`;
                    const ramFill = document.getElementById('ram-fill');
                    ramFill.style.width = `${data.memory.used_percentage}%`;
                    setBarColor(ramFill, data.memory.used_percentage);
                }
                if (data.disk_root) {
                    document.getElementById('disk-val').innerText = `${data.disk_root.used_gb} GB (${data.disk_root.used_percentage}%)`;
                    const diskFill = document.getElementById('disk-fill');
                    diskFill.style.width = `${data.disk_root.used_percentage}%`;
                    setBarColor(diskFill, data.disk_root.used_percentage);
                }
                if (data.cpu_load) {
                    document.getElementById('cpu-val').innerText = `${data.cpu_load.load_1min} | ${data.cpu_load.load_5min}`;
                }
                if (data.uptime) {
                    document.getElementById('uptime-val').innerText = data.uptime.formatted;
                }
            } catch (err) {}
        }

        function renderTraffic() {
            const box = document.getElementById('traffic-box');
            box.innerHTML = '';
            cachedLogs.slice().reverse().forEach(log => {
                const rawStr = JSON.stringify(log.data, null, 2);
                const isBlocked = rawStr.includes('BLOCKED_BY_SANDBOX') || rawStr.includes('COMMAND_NOT_WHITELISTED') || rawStr.includes('BLOCKED_BY_READONLY_MODE');

                if (currentTrafficFilter === 'blocked' && !isBlocked) return;
                if (currentTrafficFilter === 'ok' && isBlocked) return;

                const div = document.createElement('div');
                const cls = isBlocked ? 'log-blocked' : (log.direction.startsWith('OUT') ? 'log-out' : 'log-in');
                div.className = `log-entry ${cls}`;
                div.innerHTML = `
                    <div class="log-time">${log.timestamp} • <span class="log-dir">${log.direction}</span>${isBlocked ? ' <span style="color:var(--danger)">[BLOCKED]</span>' : ''}</div>
                    <div class="log-body">${escapeHtml(rawStr)}</div>
                `;
                box.appendChild(div);
            });
        }

        async function updateTraffic() {
            try {
                const res = await fetch('/api/traffic');
                cachedLogs = await res.json();
                renderTraffic();
            } catch (err) {}
        }

        function escapeHtml(str) {
            return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        }

        // Render Markdown đơn giản cho tin nhắn AI (code block, inline code, bold, xuống dòng)
        function formatMarkdown(text) {
            let safe = escapeHtml(text);
            safe = safe.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
            safe = safe.replace(/`([^`]+)`/g, '<code>$1</code>');
            safe = safe.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
            safe = safe.replace(/\\n|\n/g, '<br>');
            return safe;
        }

        function appendMessage(sender, text, isAi = false) {
            const chatBox = document.getElementById('chat-box');
            const div = document.createElement('div');
            div.className = `msg ${isAi ? 'msg-ai' : 'msg-user'}`;
            div.innerHTML = isAi ? formatMarkdown(text) : escapeHtml(text).replace(/\n/g, '<br>');
            chatBox.appendChild(div);
            chatBox.scrollTop = chatBox.scrollHeight;
        }

        function fillPrompt(text) {
            const input = document.getElementById('user-input');
            input.value = text;
            input.focus();
        }

        async function doSend() {
            const input = document.getElementById('user-input');
            const prompt = input.value.trim();
            if (!prompt) return;

            appendMessage('user', prompt, false);
            input.value = '';

            const thinkingDiv = document.createElement('div');
            thinkingDiv.className = 'msg msg-ai';
            thinkingDiv.id = 'thinking-temp';
            thinkingDiv.innerHTML = '<span class="tool-badge">🧠 AI Thinking...</span> Đang xử lý qua C++ MCP Server...';
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
                appendMessage('ai', `Lỗi kết nối: ${err.message}`, true);
            }
        }

        async function clearChat() {
            try {
                await fetch('/api/clear_chat', { method: 'POST' });
                document.getElementById('chat-box').innerHTML = `
                    <div class="msg msg-ai">
                        🔄 <em>Đã làm mới đoạn chat và giải phóng bộ nhớ context!</em><br><br>
                        Chọn công cụ bên trái hoặc nhập câu hỏi mới để tiếp tục.
                    </div>
                `;
            } catch (err) {}
        }

        function sendPrompt(text) {
            document.getElementById('user-input').value = text;
            doSend();
        }

        updateTelemetry();
        updateTraffic();
        setInterval(updateTelemetry, 3000);
        setInterval(updateTraffic, 1500);

        let currentBootTime = null;
        setInterval(async () => {
            try {
                const res = await fetch('/api/version');
                if (res.ok) {
                    const data = await res.json();
                    if (currentBootTime === null) currentBootTime = data.boot_time;
                    else if (currentBootTime !== data.boot_time) window.location.reload();
                }
            } catch (e) {}
        }, 1000);
    </script>
</body>
</html>
"""

# Bộ xử lý HTTP API cho Web Dashboard (/api/telemetry, /api/chat, /api/traffic...)
class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/" or parsed.path == "/index.html":
            # Trả về giao diện HTML Dashboard chính
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
        elif parsed.path == "/api/telemetry":
            # API lấy thông số RAM/CPU/Disk thời gian thực từ tool C++ get_system_health
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
        elif parsed.path == "/api/version":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"boot_time": SERVER_BOOT_TIME}).encode("utf-8"))
        elif parsed.path == "/api/alerts":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(watchdog_alerts).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/chat":
            # Nhận câu hỏi từ giao diện Web -> chuyển cho AI Agent xử lý -> xóa mã màu ANSI -> trả kết quả JSON
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len)
            req_data = json.loads(body.decode("utf-8"))
            prompt = req_data.get("prompt", "")

            response_text = agent_instance.process_query(prompt)
            # Xóa các ký tự mã màu terminal ANSI để hiển thị sạch sẽ trên trình duyệt
            clean_text = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', response_text)

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"response": clean_text}).encode("utf-8"))
        elif parsed.path == "/api/clear_chat":
            if agent_instance:
                agent_instance.clear_history()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode("utf-8"))
        elif parsed.path == "/api/watchdog":
            global watchdog_enabled
            watchdog_enabled = not watchdog_enabled
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"enabled": watchdog_enabled}).encode("utf-8"))
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
    print(f" -> Network Access : http://192.168.122.28:{PORT}")
    print("======================================================================")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping web server...")
        mcp_bridge.close()
        server.server_close()

if __name__ == "__main__":
    run_server()
