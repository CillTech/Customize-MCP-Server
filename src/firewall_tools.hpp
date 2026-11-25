#ifndef VKU_FIREWALL_TOOLS_HPP
#define VKU_FIREWALL_TOOLS_HPP

#include <algorithm>
#include <array>
#include <cctype>
#include <cstdio>
#include <fstream>
#include <nlohmann/json.hpp>
#include <regex>
#include <string>

#ifdef __linux__
#include <sys/wait.h>
#include <unistd.h>
#endif

namespace vku::tools {

using json = nlohmann::json;

class FirewallTools {
private:
  // Hàm phụ trợ: chạy lệnh hệ thống qua pipe và giới hạn output tối đa 32KB
  static std::pair<int, std::string> run_cmd(const std::string &cmd) {
    std::array<char, 256> buffer;
    std::string output;
#ifdef _WIN32
    FILE *pipe = _popen(cmd.c_str(), "r");
#else
    FILE *pipe = popen(cmd.c_str(), "r");
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
    int raw_status = pclose(pipe);
    int exit_code =
        WIFEXITED(raw_status) ? WEXITSTATUS(raw_status) : raw_status;
#endif
    return {exit_code, output};
  }

  static bool is_root_user() {
#ifdef __linux__
    return geteuid() == 0;
#else
    return true;
#endif
  }

  static std::string ufw_cmd_prefix() {
    return is_root_user() ? "ufw " : "sudo -n ufw ";
  }

  static std::string to_lower_copy(std::string s) {
    std::transform(s.begin(), s.end(), s.begin(),
                   [](unsigned char c) { return std::tolower(c); });
    return s;
  }

  // Đọc trạng thái cấu hình từ /etc/ufw/ufw.conf (không cần root) làm fallback
  // khi chạy non-root chưa cấu hình sudoers NOPASSWD
  static std::string read_ufw_conf_enabled() {
    std::ifstream ifs("/etc/ufw/ufw.conf");
    if (!ifs.is_open()) {
      return "";
    }
    std::string line;
    while (std::getline(ifs, line)) {
      std::string trimmed;
      for (char c : line) {
        if (!std::isspace(static_cast<unsigned char>(c))) {
          trimmed.push_back(static_cast<char>(
              std::tolower(static_cast<unsigned char>(c))));
        }
      }
      if (trimmed == "enabled=yes") {
        return "yes";
      }
      if (trimmed == "enabled=no") {
        return "no";
      }
    }
    return "";
  }

public:
  // Tool 6: Kiểm tra trạng thái tường lửa UFW và các rule đang hoạt động
  static json check_firewall_status() {
    json result;
#ifdef __linux__
    auto [code, output] = run_cmd(ufw_cmd_prefix() + "status verbose 2>&1");
    std::string lower_out = to_lower_copy(output);
    result["tool"] = "ufw";

    if (code == 0) {
      result["success"] = true;
      result["raw_output"] = output;
      if (lower_out.find("status: inactive") != std::string::npos) {
        result["ufw_state"] = "inactive";
      } else if (lower_out.find("status: active") != std::string::npos) {
        result["ufw_state"] = "active";
      } else {
        result["ufw_state"] = "unknown";
      }
      return result;
    }

    // Nếu thiếu quyền sudo -n, đọc fallback từ /etc/ufw/ufw.conf để không báo
    // sai trạng thái bật/tắt của tường lửa
    std::string conf_enabled = read_ufw_conf_enabled();
    if (!conf_enabled.empty()) {
      std::string state = (conf_enabled == "yes") ? "active" : "inactive";
      result["success"] = true;
      result["ufw_state"] = state;
      result["config_fallback"] = true;
      result["config_source"] = "/etc/ufw/ufw.conf (ENABLED=" + conf_enabled + ")";
      result["raw_output"] =
          "Status: " + state +
          " (xác nhận từ /etc/ufw/ufw.conf; để xem đầy đủ danh sách rule cần "
          "cấp quyền sudo NOPASSWD cho /usr/sbin/ufw)\n[Command output]: " +
          output;
      result["note"] =
          "Chạy 'sudo visudo -f /etc/sudoers.d/vku_mcp' và thêm "
          "'<user> ALL=(ALL) NOPASSWD: /usr/sbin/ufw, /usr/bin/systemctl, "
          "/bin/systemctl' để MCP gọi trực tiếp 'ufw status verbose'.";
      return result;
    }

    result["success"] = false;
    result["ufw_state"] = "unknown";
    result["raw_output"] = output;
    result["note"] =
        "ufw requires root/sudo NOPASSWD privileges or is not installed.";
#else
    result["success"] = true;
    result["ufw_state"] = "active";
    result["tool"] = "ufw (simulated on non-Linux)";
    result["raw_output"] =
        "Status: active\nTo                         Action      From\n--       "
        "                  ------      ----\n22/tcp                     ALLOW "
        "IN    Anywhere\n8080/tcp                   ALLOW IN    Anywhere\n";
#endif
    return result;
  }

  // Tool 7: Quản lý tường lửa UFW (allow/deny Port/IPv4 hoặc enable/disable)
  static json manage_firewall_rule(const std::string &action,
                                   const std::string &target = "") {
    json result;

    // 1. Chỉ chấp nhận hành động hợp lệ
    if (action != "allow" && action != "deny" && action != "enable" &&
        action != "disable") {
      result["success"] = false;
      result["error"] =
          "Invalid action. Supported: 'allow', 'deny', 'enable', 'disable'.";
      return result;
    }

    if (action == "enable" || action == "disable") {
#ifdef __linux__
      bool protected_ports = false;
      if (action == "enable") {
        // Anti-Lockout: giữ mở SSH (22) và MCP Web UI (8080) trước khi bật UFW
        auto [c22, out22] =
            run_cmd(ufw_cmd_prefix() + "allow 22/tcp 2>&1");
        auto [c8080, out8080] =
            run_cmd(ufw_cmd_prefix() + "allow 8080/tcp 2>&1");
        (void)out22;
        (void)out8080;
        protected_ports = (c22 == 0 && c8080 == 0);
      }

      std::string cmd = (action == "enable")
                            ? (ufw_cmd_prefix() + "--force enable 2>&1")
                            : (ufw_cmd_prefix() + "disable 2>&1");
      auto [code, output] = run_cmd(cmd);
      result["success"] = (code == 0);
      result["action"] = action;
      result["target"] = "ufw";
      if (action == "enable" && code == 0 && protected_ports) {
        result["anti_lockout_ports"] = json::array({"22/tcp", "8080/tcp"});
        result["output"] =
            "[Anti-Lockout] Đã tự động giữ mở port 22/tcp (SSH) và 8080/tcp "
            "(Web UI).\n" +
            output;
      } else {
        result["output"] = output;
      }
      if (code != 0 && !is_root_user()) {
        result["note"] =
            "Thao tác bật/tắt UFW cần quyền root hoặc cấu hình sudo NOPASSWD "
            "cho /usr/sbin/ufw.";
      }
#else
      result["success"] = true;
      result["action"] = action;
      result["target"] = "ufw";
      result["output"] = "Simulated: ufw " + action + " applied.";
#endif
      return result;
    }

    // 2. Kiểm tra chặt chẽ tham số target bằng Regex (chỉ nhận Port hợp lệ hoặc
    // IPv4) để chống Command Injection
    std::regex port_regex("^([0-9]{1,5})(/tcp|/udp)?$");
    std::regex ipv4_regex("^([0-9]{1,3}\\.){3}[0-9]{1,3}$");

    bool is_port = std::regex_match(target, port_regex);
    bool is_ip = std::regex_match(target, ipv4_regex);

    if (!is_port && !is_ip) {
      result["success"] = false;
      result["error"] = "Security Violation: Invalid target. Must be a port "
                        "(e.g., 8080, 22/tcp) or IPv4 address.";
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
    // 4. Lắp ghép câu lệnh ufw an toàn (IP dùng "ufw allow/deny from <ip>",
    // Port dùng "ufw allow/deny <port>")
    std::string cmd;
    if (is_ip) {
      cmd = ufw_cmd_prefix() + action + " from " + target + " 2>&1";
    } else {
      cmd = ufw_cmd_prefix() + action + " " + target + " 2>&1";
    }
    auto [code, output] = run_cmd(cmd);
    result["success"] = (code == 0);
    result["action"] = action;
    result["target"] = target;
    result["output"] = output;
    if (code != 0 && !is_root_user()) {
      result["note"] =
          "Thay đổi rule UFW cần quyền root hoặc cấu hình sudo NOPASSWD cho "
          "/usr/sbin/ufw.";
    }
#else
    result["success"] = true;
    result["action"] = action;
    result["target"] = target;
    result["output"] = "Simulated: ufw " + action + " " + target + " applied.";
#endif
    return result;
  }

  // Tool 8: Thống kê các lần đăng nhập SSH thất bại (phát hiện tấn công
  // Brute-force)
  static json check_failed_logins(int limit = 20) {
    json result;
    limit = std::max(
        1, std::min(limit, 100)); // Giới hạn số dòng trả về từ 1 đến 100

#ifdef __linux__
    // Tìm các dòng "Failed password" hoặc "Invalid user" trong
    // /var/log/auth.log
    std::string cmd = "grep -E \"Failed password|Invalid user\" "
                      "/var/log/auth.log 2>/dev/null | tail -n " +
                      std::to_string(limit);
    auto [code, output] = run_cmd(cmd);
    if (output.empty()) {
      // Nếu auth.log trống hoặc không đọc được, thử đọc bằng lệnh lastb
      auto [code2, out2] =
          run_cmd("lastb -n " + std::to_string(limit) + " 2>&1");
      output = out2;
    }
    result["success"] = true;
    result["limit"] = limit;
    result["entries"] = output.empty()
                            ? "No failed login attempts found (or insufficient "
                              "permissions for /var/log/auth.log)."
                            : output;
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
