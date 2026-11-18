#ifndef VKU_SECURITY_SANDBOX_HPP
#define VKU_SECURITY_SANDBOX_HPP

#include <string>
#include <vector>
#include <array>
#include <sstream>
#include <algorithm>
#include <cctype>
#include <nlohmann/json.hpp>

namespace vku::tools {

using json = nlohmann::json;

class SecuritySandbox {
public:
    // Audit active network listening sockets
    static json audit_network_ports() {
        json result;

#ifdef __linux__
        std::string cmd = "ss -tulpn 2>/dev/null | grep -E 'LISTEN|UNCONN' || netstat -tulpn 2>/dev/null";
        std::array<char, 256> buffer;
        std::string output;

        FILE* pipe = popen(cmd.c_str(), "r");
        if (pipe) {
            while (fgets(buffer.data(), buffer.size(), pipe) != nullptr) {
                output += buffer.data();
            }
            pclose(pipe);
        }

        result["status"] = "AUDITED";
        result["raw_sockets"] = output.empty() ? "(No open listening ports detected)" : output;
        result["recommendation"] = "Verify that only necessary ports (22, 80, 443) are exposed publicly.";

#else
        result = {
            {"status", "DEV_SIMULATION"},
            {"raw_sockets", "tcp LISTEN 0 128 0.0.0.0:22 (sshd)\ntcp LISTEN 0 511 0.0.0.0:80 (vku-nginx)"},
            {"recommendation", "Standard SSH and Web ports are active."}
        };
#endif

        return result;
    }

    // Execute arbitrary diagnostic commands with sandbox security guardrails
    static json execute_safe_command(const std::string& command) {
        json result;

        // 1. Blacklist check: Pattern matching for destructive payloads
        const std::vector<std::string> destructive_patterns = {
            "rm -rf", "mkfs", "dd if=", ":(){ :|:& };:", "chmod -R 777 /",
            "> /dev/sd", "reboot", "shutdown", "poweroff", "init 0", "passwd",
            "> /dev/null 2>&1 &", "nc -e", "/dev/tcp/"
        };

        std::string lower_cmd = command;
        std::transform(lower_cmd.begin(), lower_cmd.end(), lower_cmd.begin(), ::tolower);

        for (const auto& pattern : destructive_patterns) {
            if (lower_cmd.find(pattern) != std::string::npos) {
                result["allowed"] = false;
                result["violation"] = "BLOCKED_BY_SANDBOX";
                result["reason"] = "Detected forbidden destructive pattern: '" + pattern + "'";
                return result;
            }
        }

        // 2. Whitelist command prefix check
        const std::vector<std::string> allowed_prefixes = {
            "df", "free", "ps", "top", "uptime", "ls", "grep", "cat", "who", "w",
            "ip", "netstat", "ss", "systemctl", "journalctl", "find", "head", "tail",
            "curl", "ping", "id", "uname", "pwd", "date", "which", "tree", "awk", "sed"
        };

        // Extract first word
        std::istringstream iss(command);
        std::string first_word;
        iss >> first_word;

        bool prefix_allowed = false;
        for (const auto& prefix : allowed_prefixes) {
            if (first_word == prefix) {
                prefix_allowed = true;
                break;
            }
        }

        if (!prefix_allowed) {
            result["allowed"] = false;
            result["violation"] = "COMMAND_NOT_WHITELISTED";
            result["reason"] = "Command binary '" + first_word + "' is not permitted in the safe sandbox.";
            return result;
        }

        // 3. Safe Execution
#ifdef __linux__
        std::array<char, 512> buffer;
        std::string output;
        std::string safe_exec_cmd = command + " 2>&1";

        FILE* pipe = popen(safe_exec_cmd.c_str(), "r");
        if (!pipe) {
            result["allowed"] = true;
            result["success"] = false;
            result["error"] = "Failed to spawn process.";
            return result;
        }

        // Cap output at 64KB to avoid memory flooding
        size_t total_read = 0;
        const size_t MAX_OUTPUT = 65536;

        while (fgets(buffer.data(), buffer.size(), pipe) != nullptr) {
            total_read += buffer.size();
            output += buffer.data();
            if (total_read >= MAX_OUTPUT) {
                output += "\n[... Output truncated by VKU MCP Sandbox ...]";
                break;
            }
        }

        int status = pclose(pipe);
        int exit_code = WEXITSTATUS(status);

        result["allowed"] = true;
        result["command"] = command;
        result["exit_code"] = exit_code;
        result["output"] = output;
        result["success"] = (exit_code == 0);

#else
        result = {
            {"allowed", true},
            {"command", command},
            {"exit_code", 0},
            {"output", "Simulated output for: " + command},
            {"success", true}
        };
#endif

        return result;
    }
};

} // namespace vku::tools

#endif // VKU_SECURITY_SANDBOX_HPP
