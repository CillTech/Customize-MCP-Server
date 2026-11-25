#ifndef VKU_PROCESS_TOOLS_HPP
#define VKU_PROCESS_TOOLS_HPP

#include <algorithm>
#include <cerrno>
#include <cstring>
#include <nlohmann/json.hpp>
#include <sstream>
#include <string>
#include <vector>

#ifdef __linux__
#include <mntent.h>
#include <signal.h>
#include <sys/statvfs.h>
#include <unistd.h>
#endif

#include "security_sandbox.hpp"

namespace vku::tools {

using json = nlohmann::json;

class ProcessTools {
public:
  // Tool 16: Liệt kê top N tiến trình tiêu thụ CPU hoặc RAM nhiều nhất
  static json list_top_processes(const std::string &sort_by = "cpu",
                                 int limit = 10) {
    if (sort_by != "cpu" && sort_by != "mem") {
      return {{"success", false},
              {"error", "Invalid sort_by. Supported: 'cpu', 'mem'."}};
    }
    limit = std::max(1, std::min(limit, 30));

#ifdef __linux__
    std::string sort_flag =
        (sort_by == "mem") ? "--sort=-%mem" : "--sort=-%cpu";
    json exec_res = SecuritySandbox::run_exec_args(
        {"ps", "-eo", "pid,ppid,user,%cpu,%mem,stat,comm", sort_flag},
        "list_top_processes");
    if (!exec_res.value("success", false)) {
      return exec_res;
    }

    std::istringstream iss(exec_res.value("output", ""));
    std::string line;
    std::string trimmed_out;
    int count = 0;
    while (std::getline(iss, line)) {
      trimmed_out += line + "\n";
      if (count >= limit) {
        break; // dòng 0 là header + tối đa 'limit' tiến trình
      }
      count++;
    }

    return {{"success", true},
            {"sort_by", sort_by},
            {"limit", limit},
            {"processes", trimmed_out}};
#else
    return {{"success", true},
            {"sort_by", sort_by},
            {"limit", limit},
            {"processes",
             "  PID  PPID USER     %CPU %MEM STAT COMMAND\n"
             " 1024     1 root      4.2  2.1 Ssl  ollama\n"
             " 1102   980 cill      1.1  0.4 S    vku_mcp_server\n"}};
#endif
  }

  // Tool 17: Dừng tiến trình bị treo theo PID (chặn kill tiến trình lõi PID <=
  // 100 và chính tiến trình MCP)
  static json kill_process(int pid, const std::string &signal_name = "SIGTERM") {
    if (signal_name != "SIGTERM" && signal_name != "SIGKILL") {
      return {{"success", false},
              {"allowed", false},
              {"error", "Invalid signal. Supported: 'SIGTERM', 'SIGKILL'."}};
    }

    if (pid <= 100) {
      SecuritySandbox::write_audit_log(
          "BLOCKED_KILL_PID", "pid=" + std::to_string(pid),
          "Protected core OS PID <= 100");
      return {{"success", false},
              {"allowed", false},
              {"violation", "BLOCKED_BY_SANDBOX"},
              {"error",
               "Security Violation: Refusing to terminate core system process "
               "(PID <= 100)."}};
    }

#ifdef __linux__
    if (pid == static_cast<int>(getpid()) ||
        pid == static_cast<int>(getppid())) {
      SecuritySandbox::write_audit_log(
          "BLOCKED_KILL_SELF", "pid=" + std::to_string(pid),
          "Cannot terminate active MCP server or parent UI");
      return {{"success", false},
              {"allowed", false},
              {"violation", "BLOCKED_BY_SANDBOX"},
              {"error",
               "Security Violation: Cannot kill active MCP Server or its "
               "parent process."}};
    }

    int sig = (signal_name == "SIGKILL") ? SIGKILL : SIGTERM;
    if (kill(static_cast<pid_t>(pid), sig) != 0) {
      int err = errno;
      SecuritySandbox::write_audit_log("KILL_FAILED",
                                       "pid=" + std::to_string(pid),
                                       std::strerror(err));
      return {{"success", false},
              {"allowed", true},
              {"pid", pid},
              {"signal", signal_name},
              {"error", std::string("kill() failed: ") + std::strerror(err)}};
    }

    SecuritySandbox::write_audit_log("KILL_PROCESS",
                                     "pid=" + std::to_string(pid),
                                     "signal=" + signal_name);
    return {{"success", true},
            {"allowed", true},
            {"pid", pid},
            {"signal", signal_name},
            {"message", "Signal " + signal_name + " sent to PID " +
                            std::to_string(pid)}};
#else
    return {{"success", true},
            {"allowed", true},
            {"pid", pid},
            {"signal", signal_name},
            {"message", "Simulated signal sent on non-Linux."}};
#endif
  }

  // Tool 18: Liệt kê chi tiết các phân vùng đĩa qua POSIX getmntent() +
  // statvfs()
  static json get_disk_partitions() {
    json partitions = json::array();
#ifdef __linux__
    FILE *mnt_file = setmntent("/proc/mounts", "r");
    if (!mnt_file) {
      return {{"success", false}, {"error", "Failed to open /proc/mounts."}};
    }

    struct mntent *ent;
    while ((ent = getmntent(mnt_file)) != nullptr) {
      std::string fsname = ent->mnt_fsname ? ent->mnt_fsname : "";
      std::string dir = ent->mnt_dir ? ent->mnt_dir : "";
      std::string type = ent->mnt_type ? ent->mnt_type : "";

      // Lọc các pseudo-filesystem ảo để giữ các phân vùng vật lý & mount chính
      bool is_real_dev = (fsname.rfind("/dev/", 0) == 0);
      if (!is_real_dev && dir != "/") {
        continue;
      }
      if (type == "squashfs" || type == "devtmpfs" || type == "tmpfs") {
        continue;
      }

      struct statvfs vfs;
      if (statvfs(dir.c_str(), &vfs) == 0 && vfs.f_blocks > 0) {
        double total_gb =
            static_cast<double>(vfs.f_blocks) * vfs.f_frsize /
            (1024.0 * 1024.0 * 1024.0);
        double avail_gb =
            static_cast<double>(vfs.f_bavail) * vfs.f_frsize /
            (1024.0 * 1024.0 * 1024.0);
        double free_gb =
            static_cast<double>(vfs.f_bfree) * vfs.f_frsize /
            (1024.0 * 1024.0 * 1024.0);
        double used_gb = total_gb - free_gb;
        double used_pct = (total_gb > 0) ? (used_gb / total_gb * 100.0) : 0.0;

        auto round2 = [](double v) {
          return static_cast<double>(static_cast<long long>(v * 100.0 + 0.5)) /
                 100.0;
        };

        partitions.push_back({{"device", fsname},
                              {"mountpoint", dir},
                              {"fstype", type},
                              {"total_gb", round2(total_gb)},
                              {"used_gb", round2(used_gb)},
                              {"available_gb", round2(avail_gb)},
                              {"used_percentage", round2(used_pct)}});
      }
    }
    endmntent(mnt_file);

    return {{"success", true},
            {"count", partitions.size()},
            {"partitions", partitions}};
#else
    partitions.push_back({{"device", "/dev/sda1"},
                          {"mountpoint", "/"},
                          {"fstype", "ext4"},
                          {"total_gb", 24.0},
                          {"used_gb", 18.2},
                          {"available_gb", 4.5},
                          {"used_percentage", 75.8}});
    return {{"success", true}, {"count", 1}, {"partitions", partitions}};
#endif
  }
};

} // namespace vku::tools

#endif // VKU_PROCESS_TOOLS_HPP

