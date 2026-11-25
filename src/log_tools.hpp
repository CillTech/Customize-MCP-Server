#ifndef VKU_LOG_TOOLS_HPP
#define VKU_LOG_TOOLS_HPP

#include <string>
#include <algorithm>
#include <vector>
#include <array>
#include <memory>
#include <nlohmann/json.hpp>

namespace vku::tools {

using json = nlohmann::json;

class LogTools {
public:
    // Tool 3: Đọc nhật ký hệ thống (journalctl, auth.log, nginx, dmesg, syslog)
    static json inspect_logs(const std::string& log_source, int lines) {
        json result;

        // 1. Giới hạn số dòng đọc (5 - 200) để tránh tràn bộ nhớ đệm khi AI yêu cầu quá lớn
        int safe_lines = std::clamp(lines, 5, 200);

        // 2. Chọn lệnh đọc log phù hợp theo nguồn log_source
        std::string cmd;
        if (log_source == "journal" || log_source == "systemd") {
            cmd = "journalctl -n " + std::to_string(safe_lines) + " --no-pager 2>&1";
        } else if (log_source == "auth") {
            cmd = "tail -n " + std::to_string(safe_lines) + " /var/log/auth.log 2>/dev/null || journalctl -u ssh -n " + std::to_string(safe_lines) + " --no-pager 2>&1";
        } else if (log_source == "nginx") {
            cmd = "tail -n " + std::to_string(safe_lines) + " /var/log/nginx/error.log 2>/dev/null || journalctl -u nginx -n " + std::to_string(safe_lines) + " --no-pager 2>&1";
        } else if (log_source == "dmesg" || log_source == "kernel") {
            cmd = "dmesg | tail -n " + std::to_string(safe_lines) + " 2>&1";
        } else {
            // Mặc định đọc syslog
            cmd = "tail -n " + std::to_string(safe_lines) + " /var/log/syslog 2>/dev/null || journalctl -n " + std::to_string(safe_lines) + " --no-pager 2>&1";
        }

#ifdef __linux__
        // 3. Thực thi lệnh qua pipe trên Linux và thu thập nội dung log
        std::array<char, 512> buffer;
        std::string output;
        FILE* pipe = popen(cmd.c_str(), "r");
        if (!pipe) {
            result["success"] = false;
            result["error"] = "Failed to open log pipeline.";
            return result;
        }

        while (fgets(buffer.data(), buffer.size(), pipe) != nullptr) {
            output += buffer.data();
        }
        pclose(pipe);

        result["source"] = log_source;
        result["requested_lines"] = safe_lines;
        result["log_content"] = output.empty() ? "(No log entries found or permission restricted)" : output;
        result["success"] = true;

#else
        result = {
            {"source", log_source},
            {"requested_lines", safe_lines},
            {"log_content", "Nov 17 22:00:00 ubuntu systemd[1]: Started VKU Linux MCP Agent Server.\nNov 17 22:01:00 ubuntu kernel: [Linux-OSS] System operating normally."},
            {"success", true}
        };
#endif

        return result;
    }
};

} // namespace vku::tools

#endif // VKU_LOG_TOOLS_HPP
