#include <iostream>
#include <string>
#include <nlohmann/json.hpp>
#include "mcp_server.hpp"

using json = nlohmann::json;

void print_banner() {
    std::cerr << "==========================================================\n"
              << " [VKU OSS 2026] Native C++ MCP Server for Agentic AI\n"
              << " Author: Tran Duy Duc Anh (Student ID: 24IT009)\n"
              << " Protocol: Model Context Protocol (JSON-RPC 2.0 / stdio)\n"
              << " Target: Ubuntu Linux System Administration\n"
              << "==========================================================\n"
              << std::flush;
}

int main(int argc, char* argv[]) {
    // Check CLI argument flags
    if (argc > 1) {
        std::string arg = argv[1];
        if (arg == "--version" || arg == "-v") {
            std::cout << "vku-linux-mcp-server v1.0.0 (C++17 Native POSIX)\n";
            return 0;
        }
        if (arg == "--help" || arg == "-h") {
            std::cout << "Usage: vku_mcp_server\n"
                      << "Communicates via JSON-RPC 2.0 over standard I/O (stdio).\n"
                      << "Integrated with Agentic AI systems (Claude Desktop, Gemini, Antigravity, Custom Agents).\n";
            return 0;
        }
    }

    print_banner();

    vku::mcp::MCPServer server;
    std::string line;

    // Main event loop: process incoming JSON-RPC lines from stdin
    while (std::getline(std::cin, line)) {
        if (line.empty()) {
            continue;
        }

        try {
            json request = json::parse(line);
            json response = server.handle_request(request);

            if (!response.empty()) {
                std::cout << response.dump() << "\n" << std::flush;
            }
        } catch (const json::parse_error& e) {
            json err_response = {
                {"jsonrpc", "2.0"},
                {"id", nullptr},
                {"error", {
                    {"code", -32700},
                    {"message", std::string("Parse error: ") + e.what()}
                }}
            };
            std::cout << err_response.dump() << "\n" << std::flush;
        } catch (const std::exception& e) {
            json err_response = {
                {"jsonrpc", "2.0"},
                {"id", nullptr},
                {"error", {
                    {"code", -32603},
                    {"message", std::string("Internal error: ") + e.what()}
                }}
            };
            std::cout << err_response.dump() << "\n" << std::flush;
        }
    }

    return 0;
}
