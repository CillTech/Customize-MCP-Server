#!/usr/bin/env bash
# ==============================================================================
# All-In-One: Setup Toolchain & Build Native C++ MCP Server
# Topic 15: Build and Configure an MCP Server for Agentic AI in Linux
# Course: Linux & Open Source Software 2026 - VKU
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=========================================================="
echo " [VKU OSS 2026] Step 1/2: Preparing Toolchain..."
echo "=========================================================="
if [ "$EUID" -ne 0 ]; then
    sudo bash "${SCRIPT_DIR}/scripts/setup_env.sh"
else
    bash "${SCRIPT_DIR}/scripts/setup_env.sh"
fi

echo ""
echo "=========================================================="
echo " [VKU OSS 2026] Step 2/2: Compiling C++ MCP Server..."
echo "=========================================================="
bash "${SCRIPT_DIR}/scripts/build.sh"

echo ""
echo "=========================================================="
echo " [SUCCESS] Setup and compilation completed!"
echo " Run './demo_verify.sh' to test protocol & launch AI session."
echo "=========================================================="
