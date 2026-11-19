#ifndef VKU_MCP_SERVER_HPP
#define VKU_MCP_SERVER_HPP

#include <iostream>
#include <string>
#include <vector>
#include <memory>
#include <nlohmann/json.hpp>

#include "system_tools.hpp"
#include "service_tools.hpp"
#include "log_tools.hpp"
#include "security_sandbox.hpp"

namespace vku::mcp {

using json = nlohmann::json;

class MCPServer {
private:
    const std::string PROTOCOL_VERSION = "2024-11-05";
    const std::string SERVER_NAME = "vku-linux-mcp-server";
    const std::string SERVER_VERSION = "1.0.0";

    json get_tool_definitions() {
        return json::array({
            {
                {"name", "get_system_health"},
                {"description", "Retrieve real-time hardware telemetry and health metrics from the Linux host (RAM, CPU Load Average, Root Disk storage, System Uptime, and Kernel Release) using native POSIX sysinfo and statvfs system calls."},
                {"inputSchema", {
                    {"type", "object"},
                    {"properties", json::object()},
                    {"required", json::array()}
                }}
            },
            {
                {"name", "manage_service"},
                {"description", "Inspect status or manage the lifecycle of Linux Systemd services (e.g., nginx, ssh, ufw, docker) with parameters validation."},
                {"inputSchema", {
                    {"type", "object"},
                    {"properties", {
                        {"service_name", {
                            {"type", "string"},
                            {"description", "Target service name (e.g., 'nginx', 'ssh', 'ufw')"}
                        }},
                        {"action", {
                            {"type", "string"},
                            {"enum", {"status", "start", "stop", "restart", "reload", "is-active"}},
                            {"description", "Lifecycle action to perform on the service"}
                        }}
                    }},
                    {"required", {"service_name", "action"}}
                }}
            },
            {
                {"name", "inspect_logs"},
                {"description", "Read and inspect recent system or daemon log entries from systemd journald or /var/log to diagnose errors, anomalies, and server events."},
                {"inputSchema", {
                    {"type", "object"},
                    {"properties", {
                        {"log_source", {
                            {"type", "string"},
                            {"enum", {"syslog", "journal", "auth", "nginx", "dmesg"}},
                            {"description", "Log source stream to inspect"}
                        }},
                        {"lines", {
                            {"type", "integer"},
                            {"description", "Number of trailing lines to return (5 - 200, default 20)"},
                            {"default", 20}
                        }}
                    }},
                    {"required", {"log_source"}}
                }}
            },
            {
                {"name", "audit_network_ports"},
                {"description", "Perform a security audit of all open listening TCP/UDP sockets and network services on the Linux host to detect exposed or unauthorized ports."},
                {"inputSchema", {
                    {"type", "object"},
                    {"properties", json::object()},
                    {"required", json::array()}
                }}
            },
            {
                {"name", "execute_safe_command"},
                {"description", "Execute an approved diagnostic Linux shell command inside an integrated security sandbox with automatic command blacklisting and output bounds checking."},
                {"inputSchema", {
                    {"type", "object"},
                    {"properties", {
                        {"command", {
                            {"type", "string"},
                            {"description", "Linux command to execute (must start with an approved prefix like 'df', 'free', 'ps', 'uname', 'cat')"}
                        }}
                    }},
                    {"required", {"command"}}
                }}
            }
        });
    }

public:
    json handle_request(const json& request) {
        // Validate JSON-RPC 2.0 structure
        if (!request.contains("jsonrpc") || request["jsonrpc"] != "2.0") {
            return make_error(nullptr, -32600, "Invalid Request: Must be JSON-RPC 2.0");
        }

        auto id = request.contains("id") ? request["id"] : nullptr;
        std::string method = request.value("method", "");

        // 1. MCP Initialization Handshake
        if (method == "initialize") {
            json result = {
                {"protocolVersion", PROTOCOL_VERSION},
                {"capabilities", {
                    {"tools", {
                        {"listChanged", false}
                    }}
                }},
                {"serverInfo", {
                    {"name", SERVER_NAME},
                    {"version", SERVER_VERSION},
                    {"description", "High-Performance Native C++ MCP Server for Linux Administration"}
                }}
            };
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

        // 4. MCP Tools List
        if (method == "tools/list") {
            json result = {
                {"tools", get_tool_definitions()}
            };
            return make_response(id, result);
        }

        // 5. MCP Tool Execution (tools/call)
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
                execution_result = vku::tools::ServiceTools::manage_service(s_name, s_action);
            } else if (tool_name == "inspect_logs") {
                std::string l_source = args.value("log_source", "syslog");
                int l_lines = args.value("lines", 20);
                execution_result = vku::tools::LogTools::inspect_logs(l_source, l_lines);
            } else if (tool_name == "audit_network_ports") {
                execution_result = vku::tools::SecuritySandbox::audit_network_ports();
            } else if (tool_name == "execute_safe_command") {
                std::string cmd = args.value("command", "");
                execution_result = vku::tools::SecuritySandbox::execute_safe_command(cmd);
            } else {
                return make_error(id, -32601, "Method/Tool not found: " + tool_name);
            }

            // Wrap in standard MCP tool response format
            json tool_response = {
                {"content", json::array({
                    {
                        {"type", "text"},
                        {"text", execution_result.dump(2)}
                    }
                })},
                {"isError", execution_result.value("success", true) == false && execution_result.contains("error")}
            };

            return make_response(id, tool_response);
        }

        return make_error(id, -32601, "Method not implemented: " + method);
    }

private:
    json make_response(const json& id, const json& result) {
        json resp = {
            {"jsonrpc", "2.0"},
            {"result", result}
        };
        if (!id.is_null()) {
            resp["id"] = id;
        }
        return resp;
    }

    json make_error(const json& id, int code, const std::string& message) {
        json resp = {
            {"jsonrpc", "2.0"},
            {"error", {
                {"code", code},
                {"message", message}
            }}
        };
        if (!id.is_null()) {
            resp["id"] = id;
        }
        return resp;
    }
};

} // namespace vku::mcp

#endif // VKU_MCP_SERVER_HPP
