#ifndef VKU_MCP_SERVER_HPP
#define VKU_MCP_SERVER_HPP

#include <iostream>
#include <memory>
#include <nlohmann/json.hpp>
#include <string>
#include <vector>


#include "ai_tools.hpp"
#include "firewall_tools.hpp"
#include "log_tools.hpp"
#include "security_sandbox.hpp"
#include "service_tools.hpp"
#include "system_tools.hpp"


namespace vku::mcp {

using json = nlohmann::json;

class MCPServer {
private:
  // Thông tin định danh và phiên bản giao thức Model Context Protocol (MCP)
  const std::string PROTOCOL_VERSION = "2024-11-05";
  const std::string SERVER_NAME = "vku-linux-mcp-server";
  const std::string SERVER_VERSION = "1.0.0";

  // Khai báo danh sách 8 Tools kèm JSON Schema để AI hiểu cách truyền tham số
  json get_tool_definitions() {
    return json::array(
        {{{"name", "get_system_health"},
          {"description",
           "Retrieve real-time hardware telemetry and health metrics from the "
           "Linux host (RAM, CPU Load Average, Root Disk storage, System "
           "Uptime, and Kernel Release) using native POSIX sysinfo and statvfs "
           "system calls."},
          {"inputSchema",
           {{"type", "object"},
            {"properties", json::object()},
            {"required", json::array()}}}},
         {{"name", "manage_service"},
          {"description",
           "Inspect status or manage the lifecycle of Linux Systemd services "
           "(e.g., nginx, ssh, ufw, docker) with parameters validation."},
          {"inputSchema",
           {{"type", "object"},
            {"properties",
             {{"service_name",
               {{"type", "string"},
                {"description",
                 "Target service name (e.g., 'nginx', 'ssh', 'ufw')"}}},
              {"action",
               {{"type", "string"},
                {"enum",
                 {"status", "start", "stop", "restart", "reload", "is-active"}},
                {"description",
                 "Lifecycle action to perform on the service"}}}}},
            {"required", {"service_name", "action"}}}}},
         {{"name", "inspect_logs"},
          {"description", "Read and inspect recent system or daemon log "
                          "entries from systemd journald or /var/log to "
                          "diagnose errors, anomalies, and server events."},
          {"inputSchema",
           {{"type", "object"},
            {"properties",
             {{"log_source",
               {{"type", "string"},
                {"enum", {"syslog", "journal", "auth", "nginx", "dmesg"}},
                {"description", "Log source stream to inspect"}}},
              {"lines",
               {{"type", "integer"},
                {"description",
                 "Number of trailing lines to return (5 - 200, default 20)"},
                {"default", 20}}}}},
            {"required", {"log_source"}}}}},
         {{"name", "audit_network_ports"},
          {"description", "Perform a security audit of all open listening "
                          "TCP/UDP sockets and network services on the Linux "
                          "host to detect exposed or unauthorized ports."},
          {"inputSchema",
           {{"type", "object"},
            {"properties", json::object()},
            {"required", json::array()}}}},
         {{"name", "execute_safe_command"},
          {"description",
           "Execute an approved diagnostic Linux shell command inside an "
           "integrated security sandbox with automatic command blacklisting "
           "and output bounds checking."},
          {"inputSchema",
           {{"type", "object"},
            {"properties",
             {{"command",
               {{"type", "string"},
                {"description",
                 "Linux command to execute (must start with an approved prefix "
                 "like 'df', 'free', 'ps', 'uname', 'cat')"}}}}},
            {"required", {"command"}}}}},
         {{"name", "check_firewall_status"},
          {"description",
           "Check UFW firewall status and active rules on the Linux host."},
          {"inputSchema",
           {{"type", "object"},
            {"properties", json::object()},
            {"required", json::array()}}}},
         {{"name", "manage_firewall_rule"},
          {"description", "Allow or deny a port or IPv4 address in UFW "
                          "firewall with strict input validation."},
          {"inputSchema",
           {{"type", "object"},
            {"properties",
             {{"action",
               {{"type", "string"},
                {"enum", {"allow", "deny"}},
                {"description", "Firewall rule action"}}},
              {"target",
               {{"type", "string"},
                {"description",
                 "Target port (e.g., '8080', '22/tcp') or IPv4 address"}}}}},
            {"required", {"action", "target"}}}}},
         {{"name", "check_failed_logins"},
          {"description", "Check recent failed SSH login attempts from "
                          "auth.log or lastb to detect brute-force attacks."},
          {"inputSchema",
           {{"type", "object"},
            {"properties",
             {{"limit",
               {{"type", "integer"},
                {"description",
                 "Number of recent entries to return (1-100, default 20)"},
                {"default", 20}}}}},
            {"required", json::array()}}}},
         {{"name", "collect_incident_snapshot"},
          {"description", "Collect RAM, CPU, network ports, syslog, and failed SSH logins in a single snapshot."},
          {"inputSchema",
           {{"type", "object"},
            {"properties",
             {{"log_lines",
               {{"type", "integer"},
                {"description", "Number of syslog lines (5-50, default 15)"},
                {"default", 15}}}}},
            {"required", json::array()}}}},
         {{"name", "auto_mitigate_ssh_attack"},
          {"description", "Scan auth.log for SSH brute-force IPs and optionally block them via UFW firewall."},
          {"inputSchema",
           {{"type", "object"},
            {"properties",
             {{"threshold",
               {{"type", "integer"},
                {"description", "Failed attempts threshold (default 5)"},
                {"default", 5}}},
              {"auto_block",
               {{"type", "boolean"},
                {"description", "Automatically block offending IPs in UFW"},
                {"default", false}}}}},
            {"required", json::array()}}}},
         {{"name", "incident_memory"},
          {"description", "Search or save past Linux incident solutions in AI incident memory."},
          {"inputSchema",
           {{"type", "object"},
            {"properties",
             {{"action",
               {{"type", "string"},
                {"enum", {"search", "save"}},
                {"description", "Action: search or save"}}},
              {"keyword",
               {{"type", "string"},
                {"description", "Incident keyword (e.g., nginx, ram, ssh)"}}},
              {"solution",
               {{"type", "string"},
                {"description", "Fix applied (required for save)"}}}}},
            {"required", {"action"}}}}},
         {{"name", "manage_ollama_models"},
          {"description", "List local Ollama AI models, running models, or service status."},
          {"inputSchema",
           {{"type", "object"},
            {"properties",
             {{"action",
               {{"type", "string"},
                {"enum", {"list", "ps", "status"}},
                {"description", "Ollama action"}}}}},
            {"required", json::array()}}}},
         {{"name", "check_ai_hardware"},
          {"description", "Check NVIDIA GPU VRAM/temperature and CPU AI extensions (AVX2/AVX512)."},
          {"inputSchema",
           {{"type", "object"},
            {"properties", json::object()},
            {"required", json::array()}}}},
         {{"name", "ai_model_router"},
          {"description", "Recommend optimal local Qwen model based on available RAM."},
          {"inputSchema",
           {{"type", "object"},
            {"properties",
             {{"prefer_speed",
               {{"type", "boolean"},
                {"description", "Prioritize speed over reasoning depth"},
                {"default", false}}}}},
            {"required", json::array()}}}}});
  }

public:
  json handle_request(const json &request) {
    // Validate JSON-RPC 2.0 structure
    if (!request.contains("jsonrpc") || request["jsonrpc"] != "2.0") {
      return make_error(nullptr, -32600,
                        "Invalid Request: Must be JSON-RPC 2.0");
    }

    auto id = request.contains("id") ? request["id"] : nullptr;
    std::string method = request.value("method", "");

    // 1. Bước bắt tay khởi tạo kết nối MCP (Handshake)
    if (method == "initialize") {
      json result = {{"protocolVersion", PROTOCOL_VERSION},
                     {"capabilities", {{"tools", {{"listChanged", false}}}}},
                     {"serverInfo",
                      {{"name", SERVER_NAME},
                       {"version", SERVER_VERSION},
                       {"description", "High-Performance Native C++ MCP Server "
                                       "for Linux Administration"}}}};
      return make_response(id, result);
    }

    // 2. Notification: initialized
    if (method == "notifications/initialized") {
      // Notifications do not require a response in JSON-RPC
      return json::object();
    }

    // 3. Ping
    if (method == "ping") {
      return make_response(id, json::object());
    }

    // 4. Trả về danh sách toàn bộ Tools cho AI Client (tools/list)
    if (method == "tools/list") {
      json result = {{"tools", get_tool_definitions()}};
      return make_response(id, result);
    }

    // 5. Điều phối thực thi Tool tương ứng khi AI gọi (tools/call)
    if (method == "tools/call") {
      if (!request.contains("params") || !request["params"].contains("name")) {
        return make_error(id, -32602, "Invalid params: Missing tool 'name'");
      }

      std::string tool_name = request["params"]["name"];
      json args = request["params"].value("arguments", json::object());
      json execution_result;

      if (tool_name == "get_system_health") {
        execution_result = vku::tools::SystemTools::get_system_health();
      } else if (tool_name == "manage_service") {
        std::string s_name = args.value("service_name", "");
        std::string s_action = args.value("action", "status");
        execution_result =
            vku::tools::ServiceTools::manage_service(s_name, s_action);
      } else if (tool_name == "inspect_logs") {
        std::string l_source = args.value("log_source", "syslog");
        int l_lines = args.value("lines", 20);
        execution_result =
            vku::tools::LogTools::inspect_logs(l_source, l_lines);
      } else if (tool_name == "audit_network_ports") {
        execution_result = vku::tools::SecuritySandbox::audit_network_ports();
      } else if (tool_name == "execute_safe_command") {
        std::string cmd = args.value("command", "");
        execution_result =
            vku::tools::SecuritySandbox::execute_safe_command(cmd);
      } else if (tool_name == "check_firewall_status") {
        execution_result = vku::tools::FirewallTools::check_firewall_status();
      } else if (tool_name == "manage_firewall_rule") {
        std::string fw_action = args.value("action", "");
        std::string fw_target = args.value("target", "");
        execution_result = vku::tools::FirewallTools::manage_firewall_rule(
            fw_action, fw_target);
      } else if (tool_name == "check_failed_logins") {
        int l_limit = args.value("limit", 20);
        execution_result =
            vku::tools::FirewallTools::check_failed_logins(l_limit);
      } else if (tool_name == "collect_incident_snapshot") {
        int l_lines = args.value("log_lines", 15);
        execution_result =
            vku::tools::AITools::collect_incident_snapshot(l_lines);
      } else if (tool_name == "auto_mitigate_ssh_attack") {
        int threshold = args.value("threshold", 5);
        bool auto_block = args.value("auto_block", false);
        execution_result =
            vku::tools::AITools::auto_mitigate_ssh_attack(threshold, auto_block);
      } else if (tool_name == "incident_memory") {
        std::string mem_action = args.value("action", "search");
        std::string kw = args.value("keyword", "");
        std::string sol = args.value("solution", "");
        execution_result =
            vku::tools::AITools::incident_memory(mem_action, kw, sol);
      } else if (tool_name == "manage_ollama_models") {
        std::string ol_action = args.value("action", "list");
        execution_result =
            vku::tools::AITools::manage_ollama_models(ol_action);
      } else if (tool_name == "check_ai_hardware") {
        execution_result = vku::tools::AITools::check_ai_hardware();
      } else if (tool_name == "ai_model_router") {
        bool prefer_speed = args.value("prefer_speed", false);
        execution_result =
            vku::tools::AITools::ai_model_router(prefer_speed);
      } else {
        return make_error(id, -32601, "Method/Tool not found: " + tool_name);
      }

      // Đóng gói kết quả trả về theo đúng chuẩn MCP: content là mảng text JSON, kèm cờ isError
      json tool_response = {
          {"content", json::array({{{"type", "text"},
                                    {"text", execution_result.dump(2)}}})},
          {"isError", execution_result.value("success", true) == false &&
                          execution_result.contains("error")}};

      return make_response(id, tool_response);
    }

    // Trả về mã lỗi -32601 nếu client gọi method không tồn tại
    return make_error(id, -32601, "Method not implemented: " + method);
  }

private:
  // Hàm tạo gói tin phản hồi thành công chuẩn JSON-RPC 2.0
  json make_response(const json &id, const json &result) {
    json resp = {{"jsonrpc", "2.0"}, {"result", result}};
    if (!id.is_null()) {
      resp["id"] = id;
    }
    return resp;
  }

  // Hàm tạo gói tin báo lỗi chuẩn JSON-RPC 2.0
  json make_error(const json &id, int code, const std::string &message) {
    json resp = {{"jsonrpc", "2.0"},
                 {"error", {{"code", code}, {"message", message}}}};
    if (!id.is_null()) {
      resp["id"] = id;
    }
    return resp;
  }
};

} // namespace vku::mcp

#endif // VKU_MCP_SERVER_HPP
