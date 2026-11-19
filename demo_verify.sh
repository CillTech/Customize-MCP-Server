#!/usr/bin/env bash
# ==============================================================================
# Master Demonstration & Verification Portal
# Topic 15: Build and Configure an MCP Server for Agentic AI in Linux
# Course: Linux & Open Source Software 2026 - VKU
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

# 1. Run Automated Protocol Verification
echo "======================================================================"
echo " [PHASE 1/2] RUNNING AUTOMATED MCP PROTOCOL TEST SUITE"
echo "======================================================================"
python3 client/test_mcp_direct.py

echo ""
echo "======================================================================"
echo " [PHASE 2/2] CHOOSE PRESENTATION INTERFACE"
echo "======================================================================"
echo " 1) Live-Reload Dev Mode (⚡ Auto-build C++ & Live-reload browser on Save) [RECOMMENDED]"
echo " 2) Standard Web Dashboard UI (Static mode)"
echo " 3) Interactive Terminal CLI (Direct command-line chat session)"
echo " 4) Exit"
echo "----------------------------------------------------------------------"
read -rp "Select an option [1-4] (Default: 1): " choice
choice="${choice:-1}"

case "$choice" in
    1)
        echo "[*] Launching Live-Reload Dev Mode (Watching src/, include/, client/)..."
        python3 scripts/dev_watcher.py
        ;;
    2)
        echo "[*] Launching Standard Web Dashboard on port 8080..."
        python3 client/web_ui.py
        ;;
    3)
        echo "[*] Launching Interactive Terminal CLI..."
        python3 client/agent_cli.py
        ;;
    4)
        echo "Exiting."
        exit 0
        ;;
    *)
        echo "[*] Defaulting to Live-Reload Dev Mode..."
        python3 scripts/dev_watcher.py
        ;;
esac
