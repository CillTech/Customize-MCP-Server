#!/usr/bin/env bash
# ==============================================================================
# 1-Click Build Script for Native C++ MCP Server
# Topic 15: Build and Configure an MCP Server for Agentic AI in Linux
# Course: Linux & Open Source Software 2026 - VKU
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_ROOT}"

echo "=========================================================="
echo " [VKU OSS 2026] Compiling C++ MCP Server..."
echo " Project Root : ${PROJECT_ROOT}"
echo "=========================================================="

# Run Makefile
make all

echo ""
echo "=========================================================="
echo " [OK] Build Succeeded! Binary located at: bin/vku_mcp_server"
echo "=========================================================="
./bin/vku_mcp_server --version
echo "=========================================================="
