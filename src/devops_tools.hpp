#ifndef VKU_DEVOPS_TOOLS_HPP
#define VKU_DEVOPS_TOOLS_HPP

#include <filesystem>
#include <fstream>
#include <nlohmann/json.hpp>
#include <regex>
#include <string>

#include "security_sandbox.hpp"

namespace vku::tools {

namespace fs = std::filesystem;
using json = nlohmann::json;

class DevopsTools {
public:
  // Tool 25: Liệt kê các tác vụ định kỳ Cron của user và hệ thống (/etc/cron.d)
  static json list_cron_jobs() {
#ifdef __linux__
    json res = SecuritySandbox::run_exec_args({"crontab", "-l"}, "list_cron_jobs");
    std::string user_cron = res.value("output", "");
    int code = res.value("exit_code", -1);
    bool no_user_cron =
        (code != 0 && user_cron.find("no crontab") != std::string::npos);

    std::string sys_cron_files;
    std::error_code ec;
    if (fs::exists("/etc/cron.d", ec) && fs::is_directory("/etc/cron.d", ec)) {
      for (const auto &entry : fs::directory_iterator("/etc/cron.d", ec)) {
        sys_cron_files += entry.path().filename().string() + " ";
      }
    }

    return {{"success", (code == 0 || no_user_cron)},
            {"user_crontab",
             no_user_cron ? "(No personal crontab entries for current user)"
                          : user_cron},
            {"system_cron_d",
             sys_cron_files.empty() ? "(None)" : sys_cron_files}};
#else
    return {{"success", true},
            {"user_crontab", "(Simulated empty crontab)"},
            {"system_cron_d", "e2scrub_all sysstat"}};
#endif
  }

  // Tool 26: Liệt kê các phiên người dùng đang đăng nhập trên Linux
  static json get_user_sessions() {
#ifdef __linux__
    json res =
        SecuritySandbox::run_exec_args({"who", "-H"}, "get_user_sessions");
    std::string out = res.value("output", "");
    if (!res.value("success", false) || out.empty()) {
      res = SecuritySandbox::run_exec_args({"w"}, "get_user_sessions_w");
      out = res.value("output", "");
    }
    return {{"success", res.value("success", false)},
            {"sessions", out.empty() ? "(No active interactive TTY sessions)" : out}};
#else
    return {{"success", true},
            {"sessions", "NAME     LINE     TIME             COMMENT\ncill     pts/0    2026-11-26 02:30 (192.168.122.1)"}};
#endif
  }

  // Tool 27: Quản lý Docker containers (ps, logs, restart) kèm Regex chống
  // Injection
  static json manage_docker_containers(const std::string &action = "ps",
                                       const std::string &container_name = "") {
    if (action != "ps" && action != "logs" && action != "restart") {
      return {{"success", false},
              {"error", "Invalid action. Supported: 'ps', 'logs', 'restart'."}};
    }

    if (action != "ps") {
      std::regex valid_name("^[a-zA-Z0-9][a-zA-Z0-9_.\\-]{0,127}$");
      if (container_name.empty() ||
          !std::regex_match(container_name, valid_name)) {
        return {{"success", false},
                {"allowed", false},
                {"violation", "BLOCKED_BY_SANDBOX"},
                {"error",
                 "Security Violation: Invalid Docker container name format."}};
      }
    }

#ifdef __linux__
    json res;
    if (action == "ps") {
      res = SecuritySandbox::run_exec_args(
          {"docker", "ps", "-a", "--format",
           "table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Ports}}"},
          "docker_ps");
    } else if (action == "logs") {
      res = SecuritySandbox::run_exec_args(
          {"docker", "logs", "--tail", "30", container_name},
          "docker_logs:" + container_name);
    } else {
      res = SecuritySandbox::run_exec_args(
          {"docker", "restart", container_name},
          "docker_restart:" + container_name);
    }

    int code = res.value("exit_code", -1);
    std::string out = res.value("output", "");
    if (code == 127) {
      return {{"success", false},
              {"action", action},
              {"docker_installed", false},
              {"error",
               "Docker CLI ('docker') is not installed on this Linux host."}};
    }
    res["action"] = action;
    res["container_name"] = container_name;
    if (out.find("permission denied") != std::string::npos) {
      res["note"] =
          "Current user may need membership in the 'docker' group (sudo "
          "usermod -aG docker cill).";
    }
    return res;
#else
    return {{"success", true},
            {"action", action},
            {"container_name", container_name},
            {"output", "Simulated docker " + action + " output."}};
#endif
  }
};

} // namespace vku::tools

#endif // VKU_DEVOPS_TOOLS_HPP

