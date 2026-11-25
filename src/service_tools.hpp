#ifndef VKU_SERVICE_TOOLS_HPP
#define VKU_SERVICE_TOOLS_HPP

#include <array>
#include <memory>
#include <nlohmann/json.hpp>
#include <regex>
#include <sstream>
#include <string>

#ifdef __linux__
#include <sys/wait.h>
#include <unistd.h>
#endif

namespace vku::tools {

using json = nlohmann::json;

class ServiceTools {
public:
  // Tool 2: Kiểm tra và điều khiển dịch vụ Systemd (nginx, ssh, docker...)
  static json manage_service(const std::string &service_name,
                             const std::string &action) {
    json result;

    // 1. Kiểm tra tên dịch vụ bằng Regex để chống tấn công Command Injection
    std::regex valid_name_regex("^[a-zA-Z0-9_\\-\\.]+$");
    if (!std::regex_match(service_name, valid_name_regex)) {
      result["success"] = false;
      result["error"] =
          "Security Violation: Invalid service name characters detected.";
      return result;
    }

    // 2. Chỉ cho phép các hành động hợp lệ trong danh sách (Whitelist)
    const std::vector<std::string> allowed_actions = {
        "status", "start",  "stop",    "restart",
        "reload", "enable", "disable", "is-active"};
    bool valid_action = false;
    for (const auto &a : allowed_actions) {
      if (action == a) {
        valid_action = true;
        break;
      }
    }

    if (!valid_action) {
      result["success"] = false;
      result["error"] = "Invalid action. Supported: status, start, stop, "
                        "restart, reload, is-active.";
      return result;
    }

#ifdef __linux__
    bool needs_priv = (action != "status" && action != "is-active");
    std::string prefix =
        (needs_priv && geteuid() != 0) ? "sudo -n systemctl " : "systemctl ";
    std::string cmd = prefix + action + " " + service_name + " 2>&1";
    std::array<char, 256> buffer;
    std::string output;

    FILE *pipe = popen(cmd.c_str(), "r");
    if (!pipe) {
      result["success"] = false;
      result["error"] = "Failed to spawn systemctl process.";
      return result;
    }

    while (fgets(buffer.data(), buffer.size(), pipe) != nullptr) {
      output += buffer.data();
    }

    int status = pclose(pipe);
    int exit_code = WIFEXITED(status)
                        ? WEXITSTATUS(status)
                        : status; // Tách mã thoát thực tế của lệnh systemctl
                                  // (0 = thành công, 3 = service đang tắt)

    // Kiểm tra thêm trạng thái hoạt động hiện tại (active / inactive / failed)
    // của dịch vụ
    std::string check_cmd =
        "systemctl is-active " + service_name + " 2>/dev/null";
    FILE *check_pipe = popen(check_cmd.c_str(), "r");
    std::string active_state = "unknown";
    if (check_pipe) {
      char state_buf[64];
      if (fgets(state_buf, sizeof(state_buf), check_pipe) != nullptr) {
        active_state = state_buf;
        // trim newline
        while (!active_state.empty() &&
               (active_state.back() == '\n' || active_state.back() == '\r')) {
          active_state.pop_back();
        }
      }
      pclose(check_pipe);
    }

    result["service"] = service_name;
    result["action"] = action;
    result["exit_code"] = exit_code;
    result["output"] = output.empty()
                           ? "(No output returned - action executed cleanly)"
                           : output;
    result["active_state"] = active_state;
    result["success"] =
        (exit_code == 0 || (action == "status" && exit_code == 3));
    if (service_name == "ufw") {
      result["note"] =
          "ufw.service la systemd oneshot unit; hay dung check_firewall_status "
          "de xem trang thai bat/tat loc goi tin thuc te.";
    } else if (needs_priv && exit_code != 0 && geteuid() != 0) {
      result["note"] =
          "Thao tac start/stop/restart systemd can quyen root hoac sudo "
          "NOPASSWD.";
    }

#else
    result = {{"service", service_name},
              {"action", action},
              {"exit_code", 0},
              {"output", "Simulated systemctl action executed."},
              {"active_state", action == "stop" ? "inactive" : "active"},
              {"success", true}};
#endif

    return result;
  }
};

} // namespace vku::tools

#endif // VKU_SERVICE_TOOLS_HPP
