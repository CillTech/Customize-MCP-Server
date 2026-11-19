# ==============================================================================
# Makefile for VKU Native C++ MCP Server (Linux OSS 2026)
# Author: VKU OSS Team
# ==============================================================================

CXX = g++
CXXFLAGS = -std=c++17 -O3 -Wall -Wextra -pedantic -Iinclude
TARGET_DIR = bin
TARGET = $(TARGET_DIR)/vku_mcp_server
SRC = src/main.cpp

.PHONY: all clean test install run help

all: $(TARGET)

$(TARGET): $(SRC) $(wildcard src/*.hpp)
	@mkdir -p $(TARGET_DIR)
	@echo "[*] Compiling Native C++ MCP Server (C++17 with -O3 optimization)..."
	$(CXX) $(CXXFLAGS) $(SRC) -o $(TARGET)
	@echo "[*] Stripping binary to minimize memory footprint..."
	@strip $(TARGET) 2>/dev/null || true
	@echo "[OK] Build complete: $(TARGET) (Size: $$(du -h $(TARGET) | cut -f1))"

clean:
	@echo "[*] Cleaning build artifacts..."
	@rm -rf $(TARGET_DIR)
	@echo "[OK] Cleaned."

test: $(TARGET)
	@echo "[*] Running MCP JSON-RPC protocol automated test suite..."
	@python3 client/test_mcp_direct.py

run: $(TARGET)
	@./$(TARGET)

install: $(TARGET)
	@echo "[*] Installing vku_mcp_server binary to /usr/local/bin..."
	@sudo cp $(TARGET) /usr/local/bin/
	@echo "[OK] Installed successfully. You can now invoke 'vku_mcp_server' globally."

help:
	@echo "VKU C++ MCP Server Build System"
	@echo "Targets:"
	@echo "  make all      - Compile and optimize C++ binary"
	@echo "  make clean    - Remove build artifacts"
	@echo "  make test     - Run automated JSON-RPC test suite"
	@echo "  make install  - Install binary to /usr/local/bin"
