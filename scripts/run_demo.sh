#!/usr/bin/env bash
# ==============================================================================
# Live Demonstration Launcher
# Topic 15: Build and Configure an MCP Server for Agentic AI in Linux
# Course: Linux & Open Source Software 2026 - VKU
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_ROOT}"

# Ensure binary exists
if [ ! -f "bin/vku_mcp_server" ]; then
    echo "[*] Binary not found. Triggering automated build..."
    make all
fi

echo "[*] Launching Interactive Agentic AI Session..."
python3 client/agent_cli.py
