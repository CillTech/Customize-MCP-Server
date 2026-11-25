#include "mcp_server.hpp"
#include <iostream>
#include <nlohmann/json.hpp>
#include <string>

using json = nlohmann::json;

// In banner giới thiệu server ra stderr (không làm nhiễu luồng JSON-RPC trên
// stdout)
void print_banner() {
  std::cerr << "==========================================================\n"
            << " [VKU OSS 2026] Native C++ MCP Server for Agentic AI\n"
            << " Protocol: Model Context Protocol (JSON-RPC 2.0 / stdio)\n"
            << " Target: Ubuntu Linux System Administration\n"
            << "==========================================================\n"
            << std::flush;
}

int main(int argc, char *argv[]) {
  // 1. Xử lý các cờ dòng lệnh (--version, --help)
  if (argc > 1) {
    std::string arg = argv[1];
    if (arg == "--version" || arg == "-v") {
      std::cout << "vku-linux-mcp-server v1.0.0 (C++17 Native POSIX)\n";
      return 0;
    }
    if (arg == "--help" || arg == "-h") {
      std::cout << "Usage: vku_mcp_server\n"
                << "Communicates via JSON-RPC 2.0 over standard I/O (stdio).\n"
                << "Integrated with Agentic AI systems (Claude Desktop, "
                   "Gemini, Antigravity, Custom Agents).\n";
      return 0;
    }
  }

  print_banner();

  // 2. Khởi tạo bộ xử lý MCP Server và lắng nghe từng dòng JSON từ stdin
  vku::mcp::MCPServer server;
  std::string line;

  // Vòng lặp sự kiện chính (Event Loop): đọc yêu cầu JSON-RPC -> xử lý -> trả
  // kết quả ra stdout
  while (std::getline(std::cin, line)) {
    if (line.empty()) {
      continue;
    }

    try {
      json request = json::parse(line);
      json response = server.handle_request(request);

      // Chỉ in phản hồi nếu không phải notification (request không có id)
      if (!response.empty()) {
        std::cout << response.dump() << "\n" << std::flush;
      }
    } catch (const json::parse_error &e) {
      // Lỗi cú pháp JSON (-32700: Parse error theo chuẩn JSON-RPC 2.0)
      json err_response = {
          {"jsonrpc", "2.0"},
          {"id", nullptr},
          {"error",
           {{"code", -32700},
            {"message", std::string("Parse error: ") + e.what()}}}};
      std::cout << err_response.dump() << "\n" << std::flush;
    } catch (const std::exception &e) {
      // Lỗi nội bộ server (-32603: Internal error)
      json err_response = {
          {"jsonrpc", "2.0"},
          {"id", nullptr},
          {"error",
           {{"code", -32603},
            {"message", std::string("Internal error: ") + e.what()}}}};
      std::cout << err_response.dump() << "\n" << std::flush;
    }
  }

  return 0;
}
