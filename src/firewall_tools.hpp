#ifndef VKU_FIREWALL_TOOLS_HPP
#define VKU_FIREWALL_TOOLS_HPP

#include <string>
#include <regex>
#include <array>
#include <cstdio>
#include <algorithm>
#include <nlohmann/json.hpp>

namespace vku::tools {

using json = nlohmann::json;

class FirewallTools {
private:
    // Hàm phụ trợ: chạy lệnh hệ thống qua pipe và giới hạn output tối đa 32KB
    static std::pair<int, std::string> run_cmd(const std::string& cmd) {
        std::array<char, 256> buffer;
        std::string output;
#ifdef _WIN32
        FILE* pipe = _popen(cmd.c_str(), "r");
#else
        FILE* pipe = popen(cmd.c_str(), "r");
#endif
        if (!pipe) {
            return {-1, "Failed to spawn process."};
        }
        while (fgets(buffer.data(), buffer.size(), pipe) != nullptr) {
            output += buffer.data();
            if (output.size() > 32768) {
                output += "\n...[Output truncated at 32KB]";
                break;
            }
        }
#ifdef _WIN32
        int exit_code = _pclose(pipe);
#else
        int exit_code = pclose(pipe);
#endif
        return {exit_code, output};
    }

public:
    // Tool 6: Kiểm tra trạng thái tường lửa UFW và các rule đang hoạt động
    static json check_firewall_status() {
        json result;
#ifdef __linux__
        auto [code, output] = run_cmd("ufw status verbose 2>&1");
        result["success"] = (code == 0);
        result["raw_output"] = output;
        result["tool"] = "ufw";
        if (code != 0) {
            result["note"] = "ufw may require root/sudo privileges or is not installed.";
        }
#else
        result["success"] = true;
        result["tool"] = "ufw (simulated on non-Linux)";
        result["raw_output"] = "Status: active\nTo                         Action      From\n--                         ------      ----\n22/tcp                     ALLOW IN    Anywhere\n8080/tcp                   ALLOW IN    Anywhere\n";
#endif
        return result;
    }

    // Tool 7: Thêm rule cho phép (allow) hoặc chặn (deny) theo Port hoặc IPv4
    static json manage_firewall_rule(const std::string& action, const std::string& target) {
        json result;

        // 1. Chỉ chấp nhận hành động "allow" hoặc "deny"
        if (action != "allow" && action != "deny") {
            result["success"] = false;
            result["error"] = "Invalid action. Supported: 'allow', 'deny'.";
            return result;
        }

        // 2. Kiểm tra chặt chẽ tham số target bằng Regex (chỉ nhận Port hợp lệ hoặc IPv4) để chống Command Injection
        std::regex port_regex("^([0-9]{1,5})(/tcp|/udp)?$");
        std::regex ipv4_regex("^([0-9]{1,3}\\.){3}[0-9]{1,3}$");

        bool is_port = std::regex_match(target, port_regex);
        bool is_ip = std::regex_match(target, ipv4_regex);

        if (!is_port && !is_ip) {
            result["success"] = false;
            result["error"] = "Security Violation: Invalid target. Must be a port (e.g., 8080, 22/tcp) or IPv4 address.";
            return result;
        }

        // 3. Nếu là Port thì kiểm tra dải cổng hợp lệ của TCP/UDP (1 - 65535)
        if (is_port) {
            int port_num = std::stoi(target.substr(0, target.find('/')));
            if (port_num < 1 || port_num > 65535) {
                result["success"] = false;
                result["error"] = "Invalid port range (1-65535).";
                return result;
            }
        }

#ifdef __linux__
        // 4. Lắp ghép câu lệnh ufw an toàn (IP dùng "ufw allow/deny from <ip>", Port dùng "ufw allow/deny <port>")
        std::string cmd;
        if (is_ip) {
            cmd = "ufw " + action + " from " + target + " 2>&1";
        } else {
            cmd = "ufw " + action + " " + target + " 2>&1";
        }
        auto [code, output] = run_cmd(cmd);
        result["success"] = (code == 0);
        result["action"] = action;
        result["target"] = target;
        result["output"] = output;
#else
        result["success"] = true;
        result["action"] = action;
        result["target"] = target;
        result["output"] = "Simulated: ufw " + action + " " + target + " applied.";
#endif
        return result;
    }

    // Tool 8: Thống kê các lần đăng nhập SSH thất bại (phát hiện tấn công Brute-force)
    static json check_failed_logins(int limit = 20) {
        json result;
        limit = std::max(1, std::min(limit, 100)); // Giới hạn số dòng trả về từ 1 đến 100

#ifdef __linux__
        // Tìm các dòng "Failed password" hoặc "Invalid user" trong /var/log/auth.log
        std::string cmd = "grep -E \"Failed password|Invalid user\" /var/log/auth.log 2>/dev/null | tail -n " + std::to_string(limit);
        auto [code, output] = run_cmd(cmd);
        if (output.empty()) {
            // Nếu auth.log trống hoặc không đọc được, thử đọc bằng lệnh lastb
            auto [code2, out2] = run_cmd("lastb -n " + std::to_string(limit) + " 2>&1");
            output = out2;
        }
        result["success"] = true;
        result["limit"] = limit;
        result["entries"] = output.empty() ? "No failed login attempts found (or insufficient permissions for /var/log/auth.log)." : output;
#else
        result["success"] = true;
        result["limit"] = limit;
        result["entries"] = "[Simulated] No failed SSH login attempts detected.";
#endif
        return result;
    }
};

} // namespace vku::tools

#endif // VKU_FIREWALL_TOOLS_HPP
