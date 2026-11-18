#!/usr/bin/env bash
# ==============================================================================
# Setup Environment for Native C++ MCP Server
# Topic 15: Build and Configure an MCP Server for Agentic AI in Linux
# Course: Linux & Open Source Software 2026 - VKU
# ==============================================================================

set -euo pipefail

echo "=========================================================="
echo " [VKU OSS 2026] Installing Toolchain & Dependencies..."
echo "=========================================================="

if [ "$EUID" -ne 0 ]; then
    echo "[!] Please run with sudo: sudo ./scripts/setup_env.sh"
    exit 1
fi

echo "[*] Updating APT package lists..."
apt-get update -y

echo "[*] Installing G++ compiler, Make, Python3 and Linux Utilities..."
apt-get install -y \
    build-essential \
    g++ \
    make \
    python3 \
    python3-pip \
    curl \
    net-tools \
    tree

echo "=========================================================="
echo " [OK] Environment is ready! Run './scripts/build.sh' to compile."
echo "=========================================================="
