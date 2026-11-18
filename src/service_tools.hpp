#ifndef VKU_SERVICE_TOOLS_HPP
#define VKU_SERVICE_TOOLS_HPP

#include <string>
#include <regex>
#include <array>
#include <memory>
#include <sstream>
#include <nlohmann/json.hpp>

namespace vku::tools {

using json = nlohmann::json;

class ServiceTools {
public:
    static json manage_service(const std::string& service_name, const std::string& action) {
        json result;

        // 1. Validation: Prevent Shell Injection in service name
        std::regex valid_name_regex("^[a-zA-Z0-9_\\-\\.]+$");
        if (!std::regex_match(service_name, valid_name_regex)) {
            result["success"] = false;
            result["error"] = "Security Violation: Invalid service name characters detected.";
            return result;
        }

        // 2. Validation: Restrict to permitted actions
        const std::vector<std::string> allowed_actions = {
            "status", "start", "stop", "restart", "reload", "enable", "disable", "is-active"
        };
        bool valid_action = false;
        for (const auto& a : allowed_actions) {
            if (action == a) {
                valid_action = true;
                break;
            }
        }

        if (!valid_action) {
            result["success"] = false;
            result["error"] = "Invalid action. Supported: status, start, stop, restart, reload, is-active.";
            return result;
        }

#ifdef __linux__
        std::string cmd = "systemctl " + action + " " + service_name + " 2>&1";
        std::array<char, 256> buffer;
        std::string output;

        FILE* pipe = popen(cmd.c_str(), "r");
        if (!pipe) {
            result["success"] = false;
            result["error"] = "Failed to spawn systemctl process.";
            return result;
        }

        while (fgets(buffer.data(), buffer.size(), pipe) != nullptr) {
            output += buffer.data();
        }

        int status = pclose(pipe);
        int exit_code = WEXITSTATUS(status);

        // Check if active
        std::string check_cmd = "systemctl is-active " + service_name + " 2>/dev/null";
        FILE* check_pipe = popen(check_cmd.c_str(), "r");
        std::string active_state = "unknown";
        if (check_pipe) {
            char state_buf[64];
            if (fgets(state_buf, sizeof(state_buf), check_pipe) != nullptr) {
                active_state = state_buf;
                // trim newline
                while (!active_state.empty() && (active_state.back() == '\n' || active_state.back() == '\r')) {
                    active_state.pop_back();
                }
            }
            pclose(check_pipe);
        }

        result["service"] = service_name;
        result["action"] = action;
        result["exit_code"] = exit_code;
        result["output"] = output.empty() ? "(No output returned - action executed cleanly)" : output;
        result["active_state"] = active_state;
        result["success"] = (exit_code == 0 || (action == "status" && exit_code == 3));

#else
        result = {
            {"service", service_name},
            {"action", action},
            {"exit_code", 0},
            {"output", "Simulated systemctl action executed."},
            {"active_state", action == "stop" ? "inactive" : "active"},
            {"success", true}
        };
#endif

        return result;
    }
};

} // namespace vku::tools

#endif // VKU_SERVICE_TOOLS_HPP
