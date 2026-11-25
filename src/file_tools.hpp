#ifndef VKU_FILE_TOOLS_HPP
#define VKU_FILE_TOOLS_HPP

#include <algorithm>
#include <cctype>
#include <cerrno>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <nlohmann/json.hpp>
#include <sstream>
#include <string>
#include <vector>

#ifdef __linux__
#include <grp.h>
#include <pwd.h>
#include <sys/stat.h>
#endif

#include "security_sandbox.hpp"

namespace vku::tools {

namespace fs = std::filesystem;
using json = nlohmann::json;

class FileTools {
private:
  static std::string to_lower_copy(std::string s) {
    std::transform(s.begin(), s.end(), s.begin(),
                   [](unsigned char c) { return std::tolower(c); });
    return s;
  }

  static bool contains_sensitive_pattern(const std::string &canon_path) {
    std::string lower = to_lower_copy(canon_path);
    const std::vector<std::string> forbidden = {
        "/etc/shadow", "/etc/gshadow", "/etc/sudoers", "id_rsa",
        "id_ed25519",  ".env",         "/environ",     ".ssh/"};
    for (const auto &f : forbidden) {
      if (lower.find(f) != std::string::npos) {
        return true;
      }
    }
    return false;
  }

  static bool is_whitelisted_read_path(const std::string &canon_path) {
    const std::vector<std::string> allowed_prefixes = {
        "/etc/nginx/", "/etc/ufw/", "/var/log/", "/etc/systemd/system/"};
    for (const auto &p : allowed_prefixes) {
      if (canon_path.rfind(p, 0) == 0) {
        return true;
      }
    }

    const std::vector<std::string> allowed_exact = {
        "/etc/os-release",
        "/usr/lib/os-release",
        "/etc/hosts",
        "/etc/hostname",
        "/etc/resolv.conf",
        "/run/systemd/resolve/stub-resolv.conf",
        "/run/systemd/resolve/resolv.conf",
        "/etc/fstab",
        "/proc/cpuinfo",
        "/proc/meminfo",
        "/proc/version",
        "/proc/uptime",
        "/proc/loadavg"};
    if (std::find(allowed_exact.begin(), allowed_exact.end(), canon_path) !=
        allowed_exact.end()) {
      return true;
    }

    // Cho phép đọc các file bên trong thư mục dự án Customize-MCP-Server
    std::error_code ec;
    fs::path cwd = fs::weakly_canonical(fs::current_path(ec), ec);
    if (!ec && canon_path.rfind(cwd.string() + "/", 0) == 0) {
      return true;
    }
    return false;
  }

public:
  // Tool 19: Đọc an toàn file cấu hình/log hệ thống (chặn file mật khẩu & SSH
  // key)
  static json read_file_safe(const std::string &path, int max_lines = 50) {
    if (path.empty()) {
      return {{"success", false}, {"error", "File path cannot be empty."}};
    }
    max_lines = std::max(1, std::min(max_lines, 200));

    // Kiểm tra sớm các đường dẫn nhạy cảm trước khi canonicalize
    if (contains_sensitive_pattern(path)) {
      SecuritySandbox::write_audit_log("BLOCKED_READ_SENSITIVE", path,
                                       "Forbidden sensitive path");
      return {{"success", false},
              {"allowed", false},
              {"violation", "BLOCKED_BY_SANDBOX"},
              {"error",
               "Security Violation: Reading sensitive credential or secret "
               "files is forbidden: " +
                   path}};
    }

    std::error_code ec;
    fs::path raw_p(path);
    if (!raw_p.is_absolute()) {
      raw_p = fs::current_path(ec) / raw_p;
    }
    fs::path canon = fs::weakly_canonical(raw_p, ec);
    if (ec) {
      return {{"success", false},
              {"error", "Invalid path or unable to resolve: " + path}};
    }
    std::string canon_str = canon.string();

    if (contains_sensitive_pattern(canon_str)) {
      SecuritySandbox::write_audit_log("BLOCKED_READ_SENSITIVE", canon_str,
                                       "Resolved to sensitive path");
      return {{"success", false},
              {"allowed", false},
              {"violation", "BLOCKED_BY_SANDBOX"},
              {"error", "Access to sensitive path is blocked: " + canon_str}};
    }

    if (!is_whitelisted_read_path(canon_str)) {
      SecuritySandbox::write_audit_log("BLOCKED_READ_WHITELIST", canon_str,
                                       "Outside safe read whitelist");
      return {{"success", false},
              {"allowed", false},
              {"violation", "OUTSIDE_READ_WHITELIST"},
              {"error",
               "Path is outside safe read whitelist (/etc/nginx, /etc/ufw, "
               "/var/log, /etc/os-release, /proc/..., or workspace): " +
                   canon_str}};
    }

    if (!fs::exists(canon, ec) || fs::is_directory(canon, ec)) {
      return {{"success", false},
              {"allowed", true},
              {"error", "File does not exist or is a directory: " + canon_str}};
    }

    std::ifstream ifs(canon_str);
    if (!ifs.is_open()) {
      return {{"success", false},
              {"allowed", true},
              {"error",
               "Permission denied or unable to open file: " + canon_str}};
    }

    std::string line;
    std::string out;
    int read_lines = 0;
    const size_t MAX_BYTES = 32768;
    while (read_lines < max_lines && std::getline(ifs, line)) {
      if (out.size() + line.size() + 1 > MAX_BYTES) {
        out += "\n...[Truncated at 32KB]";
        break;
      }
      out += line + "\n";
      read_lines++;
    }

    SecuritySandbox::write_audit_log("SAFE_READ", canon_str,
                                     "lines=" + std::to_string(read_lines));
    return {{"success", true},
            {"allowed", true},
            {"path", canon_str},
            {"lines_returned", read_lines},
            {"content", out}};
  }

  // Tool 20: Tìm kiếm từ khóa trong log hệ thống hoàn toàn bằng C++ (không gọi
  // shell)
  static json search_in_logs(const std::string &keyword,
                             const std::string &log_source = "syslog",
                             int limit = 30) {
    if (keyword.empty() || keyword.size() > 64) {
      return {{"success", false},
              {"error", "Keyword must be between 1 and 64 characters."}};
    }
    for (unsigned char c : keyword) {
      if (c < 32 || c == 127) {
        return {{"success", false},
                {"allowed", false},
                {"violation", "BLOCKED_BY_SANDBOX"},
                {"error", "Keyword contains invalid control characters."}};
      }
    }

    limit = std::max(1, std::min(limit, 100));
    std::string lower_kw = to_lower_copy(keyword);
    std::string target_file;

    if (log_source == "syslog") {
      target_file = "/var/log/syslog";
    } else if (log_source == "auth") {
      target_file = "/var/log/auth.log";
    } else if (log_source == "nginx") {
      target_file = "/var/log/nginx/error.log";
    } else if (log_source != "journal") {
      return {{"success", false},
              {"error",
               "Invalid log_source. Supported: syslog, auth, nginx, journal."}};
    }

#ifdef __linux__
    std::vector<std::string> matched_lines;
    std::string source_used = log_source;

    if (!target_file.empty()) {
      std::ifstream ifs(target_file);
      if (ifs.is_open()) {
        std::string line;
        while (std::getline(ifs, line)) {
          if (to_lower_copy(line).find(lower_kw) != std::string::npos) {
            matched_lines.push_back(line);
            if (matched_lines.size() > static_cast<size_t>(limit)) {
              matched_lines.erase(matched_lines.begin());
            }
          }
        }
      }
    }

    // Fallback sang journalctl nếu dùng source='journal' hoặc file log không mở
    // được
    if (log_source == "journal" ||
        (matched_lines.empty() && !std::ifstream(target_file).is_open())) {
      json j_res = SecuritySandbox::run_exec_args(
          {"journalctl", "-n", "300", "--no-pager"}, "search_in_logs_journal");
      if (j_res.value("success", false)) {
        source_used = "journalctl";
        std::istringstream iss(j_res.value("output", ""));
        std::string line;
        while (std::getline(iss, line)) {
          if (to_lower_copy(line).find(lower_kw) != std::string::npos) {
            matched_lines.push_back(line);
            if (matched_lines.size() > static_cast<size_t>(limit)) {
              matched_lines.erase(matched_lines.begin());
            }
          }
        }
      }
    }

    std::string joined;
    for (const auto &l : matched_lines) {
      joined += l + "\n";
    }

    return {{"success", true},
            {"keyword", keyword},
            {"log_source", source_used},
            {"match_count", matched_lines.size()},
            {"matches",
             joined.empty() ? "(No matching log entries found)" : joined}};
#else
    return {{"success", true},
            {"keyword", keyword},
            {"log_source", log_source},
            {"match_count", 1},
            {"matches", "[Simulated] 2026-11-26 mock log matching: " + keyword}};
#endif
  }

  // Tool 21: Kiểm tra quyền chmod / chown của file hoặc thư mục qua POSIX
  // stat()
  static json check_file_permissions(const std::string &path) {
    if (path.empty()) {
      return {{"success", false}, {"error", "Path cannot be empty."}};
    }

#ifdef __linux__
    struct stat st;
    if (stat(path.c_str(), &st) != 0) {
      return {{"success", false},
              {"path", path},
              {"error", std::string("stat() failed: ") + std::strerror(errno)}};
    }

    mode_t m = st.st_mode;
    std::ostringstream oct;
    oct << "0" << std::oct << (m & 07777);

    std::string sym;
    sym += S_ISDIR(m) ? 'd' : (S_ISLNK(m) ? 'l' : '-');
    sym += (m & S_IRUSR) ? 'r' : '-';
    sym += (m & S_IWUSR) ? 'w' : '-';
    sym += (m & S_IXUSR) ? 'x' : '-';
    sym += (m & S_IRGRP) ? 'r' : '-';
    sym += (m & S_IWGRP) ? 'w' : '-';
    sym += (m & S_IXGRP) ? 'x' : '-';
    sym += (m & S_IROTH) ? 'r' : '-';
    sym += (m & S_IWOTH) ? 'w' : '-';
    sym += (m & S_IXOTH) ? 'x' : '-';

    struct passwd *pw = getpwuid(st.st_uid);
    struct group *gr = getgrgid(st.st_gid);

    return {{"success", true},
            {"path", path},
            {"type", S_ISDIR(m) ? "directory" : "file"},
            {"mode_octal", oct.str()},
            {"mode_symbolic", sym},
            {"owner", pw ? std::string(pw->pw_name) : std::to_string(st.st_uid)},
            {"group", gr ? std::string(gr->gr_name) : std::to_string(st.st_gid)},
            {"size_bytes", static_cast<unsigned long long>(st.st_size)}};
#else
    return {{"success", true},
            {"path", path},
            {"type", "file"},
            {"mode_octal", "0644"},
            {"mode_symbolic", "-rw-r--r--"},
            {"owner", "root"},
            {"group", "root"},
            {"size_bytes", 0}};
#endif
  }
};

} // namespace vku::tools

#endif // VKU_FILE_TOOLS_HPP

