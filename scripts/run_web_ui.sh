#!/usr/bin/env bash
# ==============================================================================
# Web UI Dashboard Launcher
# Topic 15: Build and Configure an MCP Server for Agentic AI in Linux
# Course: Linux & Open Source Software 2026 - VKU
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_ROOT}"

# Ensure binary exists
if [ ! -f "bin/vku_mcp_server" ]; then
    echo "[*] Binary not found. Compiling C++ MCP Server..."
    make all
fi

echo "======================================================================"
echo " [VKU OSS 2026] Starting Web Dashboard & Live Telemetry Server..."
echo " Open your browser at: http://localhost:8080"
echo " (Press Ctrl+C to stop the server)"
echo "======================================================================"

python3 client/web_ui.py
