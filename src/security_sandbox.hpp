#ifndef VKU_SECURITY_SANDBOX_HPP
#define VKU_SECURITY_SANDBOX_HPP

#include <string>
#include <vector>
#include <array>
#include <sstream>
#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <ctime>
#include <fstream>
#include <filesystem>
#include <nlohmann/json.hpp>

#ifdef __linux__
#include <unistd.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <sys/resource.h>
#include <poll.h>
#include <signal.h>
#include <fcntl.h>
#endif

namespace vku::tools {

using json = nlohmann::json;

class SecuritySandbox {
private:
    // Chuẩn hóa khoảng trắng liên tiếp thành 1 dấu cách (chống lách luật kiểu "rm  -rf")
    static std::string normalize_whitespace(const std::string& input) {
        std::string out;
        out.reserve(input.size());
        bool in_space = true; // Bỏ qua khoảng trắng thừa ở đầu chuỗi
        for (char c : input) {
            if (std::isspace(static_cast<unsigned char>(c))) {
                if (!in_space) {
                    out.push_back(' ');
                    in_space = true;
                }
            } else {
                out.push_back(c);
                in_space = false;
            }
        }
        if (!out.empty() && out.back() == ' ') {
            out.pop_back();
        }
        return out;
    }

    // Tách tên file thực thi gốc (ví dụ "/bin/ls" -> "ls") để đối chiếu Whitelist
    static std::string extract_base_binary(const std::string& token) {
        size_t pos = token.find_last_of('/');
        if (pos != std::string::npos) {
            return token.substr(pos + 1);
        }
        return token;
    }

    // Tách chuỗi lệnh thành mảng tham số (giữ nguyên nội dung bên trong dấu ngoặc đơn/kép)
    static std::vector<std::string> split_args(const std::string& cmd) {
        std::vector<std::string> args;
        std::string current;
        bool in_single_quote = false;
        bool in_double_quote = false;

        for (char c : cmd) {
            if (c == '\'' && !in_double_quote) {
                in_single_quote = !in_single_quote;
            } else if (c == '"' && !in_single_quote) {
                in_double_quote = !in_double_quote;
            } else if (std::isspace(static_cast<unsigned char>(c)) && !in_single_quote && !in_double_quote) {
                if (!current.empty()) {
                    args.push_back(current);
                    current.clear();
                }
            } else {
                current.push_back(c);
            }
        }
        if (!current.empty()) {
            args.push_back(current);
        }
        return args;
    }

    // Ghi nhật ký kiểm toán bảo mật (Audit Log) vào logs/sandbox_audit.log
    static void write_audit_log(const std::string& status, const std::string& command, const std::string& detail) {
        try {
            std::filesystem::create_directories("logs");
            std::ofstream ofs("logs/sandbox_audit.log", std::ios::app);
            if (!ofs.is_open()) return;

            std::time_t now = std::time(nullptr);
            char time_buf[32];
            std::strftime(time_buf, sizeof(time_buf), "%Y-%m-%d %H:%M:%S", std::localtime(&now));

            ofs << "[" << time_buf << "] [" << status << "] cmd=\"" << command
                << "\" detail=\"" << detail << "\"\n";
        } catch (...) {
            // Không làm gián đoạn việc thực thi lệnh nếu không ghi được file log
        }
    }

public:
    // Tool 4: Quét các cổng mạng TCP/UDP đang mở ở trạng thái LISTEN trên máy chủ Linux
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

    // Tool 5: Thực thi lệnh chẩn đoán Linux an toàn qua Sandbox 5 lớp phòng thủ
    static json execute_safe_command(const std::string& raw_command) {
        json result;
        std::string command = normalize_whitespace(raw_command);

        if (command.empty()) {
            result["allowed"] = false;
            result["violation"] = "EMPTY_COMMAND";
            result["reason"] = "Command cannot be empty.";
            return result;
        }

        std::string lower_cmd = command;
        std::transform(lower_cmd.begin(), lower_cmd.end(), lower_cmd.begin(), ::tolower);

        // Lớp 1: Chặn các toán tử nối lệnh / chuyển hướng shell (chống Command Chaining & Injection)
        const std::vector<std::string> forbidden_operators = {
            ";", "&&", "||", "`", "$(", "${", ">", "<", "|", "\n", "\r"
        };
        for (const auto& op : forbidden_operators) {
            if (command.find(op) != std::string::npos) {
                std::string reason = "Shell chaining/redirection operator '" + op + "' is forbidden.";
                write_audit_log("BLOCKED_CHAINING", command, reason);
                result["allowed"] = false;
                result["violation"] = "BLOCKED_BY_SANDBOX";
                result["reason"] = reason;
                return result;
            }
        }

        // Lớp 2: Bảo vệ đường dẫn nhạy cảm (chặn đọc file mật khẩu, SSH key, biến môi trường)
        const std::vector<std::string> sensitive_paths = {
            "/etc/shadow", "/etc/gshadow", "/etc/sudoers",
            "id_rsa", "id_ed25519", ".env", "/dev/sd", "/dev/nvme", "/environ"
        };
        for (const auto& sp : sensitive_paths) {
            if (lower_cmd.find(sp) != std::string::npos) {
                std::string reason = "Access to sensitive path/resource '" + sp + "' is forbidden.";
                write_audit_log("BLOCKED_SENSITIVE_PATH", command, reason);
                result["allowed"] = false;
                result["violation"] = "BLOCKED_BY_SANDBOX";
                result["reason"] = reason;
                return result;
            }
        }

        // Lớp 3: Bộ lọc Blacklist chặn các mẫu lệnh phá hoại hệ thống (sau khi chuẩn hóa khoảng trắng)
        const std::vector<std::string> destructive_patterns = {
            "rm -rf", "rm -fr", "rm -r", "mkfs", "dd if=", ":(){ :|:& };:",
            "chmod -r 777", "chmod 777 /", "reboot", "shutdown", "poweroff",
            "init 0", "passwd", "nc -e", "/dev/tcp/"
        };
        for (const auto& pattern : destructive_patterns) {
            if (lower_cmd.find(pattern) != std::string::npos) {
                std::string reason = "Detected forbidden destructive pattern: '" + pattern + "'";
                write_audit_log("BLOCKED_BLACKLIST", command, reason);
                result["allowed"] = false;
                result["violation"] = "BLOCKED_BY_SANDBOX";
                result["reason"] = reason;
                return result;
            }
        }

        // Lớp 4: Kiểm tra Whitelist tên lệnh gốc (đã tách bỏ đường dẫn kiểu /bin/ls -> ls)
        std::vector<std::string> args = split_args(command);
        if (args.empty()) {
            result["allowed"] = false;
            result["violation"] = "EMPTY_COMMAND";
            result["reason"] = "Unable to parse command.";
            return result;
        }

        std::string base_bin = extract_base_binary(args[0]);
        args[0] = base_bin;

        const std::vector<std::string> allowed_prefixes = {
            "df", "free", "ps", "top", "uptime", "ls", "grep", "cat", "who", "w",
            "ip", "netstat", "ss", "systemctl", "journalctl", "find", "head", "tail",
            "curl", "ping", "id", "uname", "pwd", "date", "which", "tree", "awk", "sed",
            "mkdir", "touch", "echo", "cp"
        };

        bool prefix_allowed = std::find(allowed_prefixes.begin(), allowed_prefixes.end(), base_bin) != allowed_prefixes.end();
        if (!prefix_allowed) {
            std::string reason = "Command binary '" + base_bin + "' is not permitted in the safe sandbox.";
            write_audit_log("BLOCKED_WHITELIST", command, reason);
            result["allowed"] = false;
            result["violation"] = "COMMAND_NOT_WHITELISTED";
            result["reason"] = reason;
            return result;
        }

        // Lớp 4.5: Kiểm tra chế độ chỉ-đọc (bật bằng biến môi trường VKU_READONLY_MODE=1 khi demo)
        const char* ro_env = std::getenv("VKU_READONLY_MODE");
        if (ro_env && std::string(ro_env) == "1") {
            if (base_bin == "mkdir" || base_bin == "touch" || base_bin == "cp") {
                std::string reason = "Write command '" + base_bin + "' is disabled in VKU_READONLY_MODE.";
                write_audit_log("BLOCKED_READONLY", command, reason);
                result["allowed"] = false;
                result["violation"] = "BLOCKED_BY_READONLY_MODE";
                result["reason"] = reason;
                return result;
            }
        }

        // Lớp 5: Thực thi cô lập bằng fork() + execvp() (không qua /bin/sh -c), kèm Timeout 8s và giới hạn 64KB
#ifdef __linux__
        int pipefd[2]; // pipefd[0] để tiến trình cha đọc, pipefd[1] để tiến trình con ghi output
        if (pipe(pipefd) != 0) {
            result["allowed"] = true;
            result["success"] = false;
            result["error"] = "Failed to create pipe.";
            return result;
        }

        pid_t pid = fork(); // Nhân bản tiến trình để chạy lệnh trong tiến trình con riêng biệt
        if (pid < 0) {
            close(pipefd[0]);
            close(pipefd[1]);
            result["allowed"] = true;
            result["success"] = false;
            result["error"] = "Failed to fork process.";
            return result;
        }

        if (pid == 0) {
            // --- TIẾN TRÌNH CON (CHILD PROCESS) ---
            close(pipefd[0]);               // Đóng đầu đọc không dùng tới
            dup2(pipefd[1], STDOUT_FILENO); // Chuyển hướng stdout của lệnh vào đường ống pipe
            dup2(pipefd[1], STDERR_FILENO); // Chuyển hướng stderr vào chung đường ống pipe
            close(pipefd[1]);

            // Giới hạn tối đa 10 giây CPU cho tiến trình con tránh treo hệ thống
            struct rlimit cpu_limit{10, 10};
            setrlimit(RLIMIT_CPU, &cpu_limit);

            // Chuyển vector<string> thành mảng char* kết thúc bằng nullptr để truyền cho execvp()
            std::vector<char*> c_args;
            c_args.reserve(args.size() + 1);
            for (auto& s : args) {
                c_args.push_back(const_cast<char*>(s.c_str()));
            }
            c_args.push_back(nullptr);

            execvp(c_args[0], c_args.data()); // Thực thi trực tiếp file nhị phân (không gọi shell -> miễn nhiễm Shell Injection)
            _exit(127); // Nếu execvp thất bại (không tìm thấy lệnh) thì thoát ngay tiến trình con
        }

        // --- TIẾN TRÌNH CHA (PARENT PROCESS) ---
        // Đọc kết quả từ pipe ở chế độ non-blocking, kiểm soát Timeout 8s và cắt output tối đa 64KB
        close(pipefd[1]);
        fcntl(pipefd[0], F_SETFL, O_NONBLOCK); // Bật non-blocking để không bị treo khi đọc

        std::string output;
        const size_t MAX_OUTPUT = 65536; // Giới hạn output 64KB chống tràn RAM
        const int TIMEOUT_MS = 8000;     // Timeout 8 giây
        auto start_time = std::time(nullptr);
        bool timed_out = false;

        struct pollfd pfd{pipefd[0], POLLIN, 0};
        char buffer[512];

        while (true) {
            int elapsed_ms = static_cast<int>(std::difftime(std::time(nullptr), start_time) * 1000);
            int remaining_ms = TIMEOUT_MS - elapsed_ms;
            if (remaining_ms <= 0) {
                timed_out = true; // Quá 8 giây -> đánh dấu timeout để kill tiến trình con
                break;
            }

            int ret = poll(&pfd, 1, std::min(remaining_ms, 500)); // Chờ dữ liệu từ pipe tối đa 500ms mỗi nhịp
            if (ret > 0 && (pfd.revents & POLLIN)) {
                ssize_t n = read(pipefd[0], buffer, sizeof(buffer));
                if (n > 0) {
                    if (output.size() + static_cast<size_t>(n) > MAX_OUTPUT) {
                        output.append(buffer, MAX_OUTPUT - output.size());
                        output += "\n[... Output truncated at 64KB by VKU MCP Sandbox ...]";
                        break;
                    }
                    output.append(buffer, static_cast<size_t>(n));
                } else if (n == 0) {
                    break; // EOF
                }
            } else if (ret > 0 && (pfd.revents & (POLLHUP | POLLERR))) {
                // Drain remaining bytes
                ssize_t n;
                while ((n = read(pipefd[0], buffer, sizeof(buffer))) > 0) {
                    if (output.size() + static_cast<size_t>(n) > MAX_OUTPUT) break;
                    output.append(buffer, static_cast<size_t>(n));
                }
                break;
            }
        }

        close(pipefd[0]);

        int status = 0;
        if (timed_out) {
            kill(pid, SIGKILL);
            waitpid(pid, &status, 0);
            write_audit_log("TIMEOUT", command, "Exceeded 8s execution timeout");
            result["allowed"] = true;
            result["success"] = false;
            result["command"] = command;
            result["error"] = "SANDBOX_TIMEOUT: Command exceeded 8 seconds limit and was terminated.";
            result["output"] = output;
            return result;
        }

        waitpid(pid, &status, 0);
        int exit_code = WIFEXITED(status) ? WEXITSTATUS(status) : -1;

        write_audit_log("ALLOWED", command, "exit_code=" + std::to_string(exit_code));
        result["allowed"] = true;
        result["command"] = command;
        result["exit_code"] = exit_code;
        result["output"] = output;
        result["success"] = (exit_code == 0);
#else
        write_audit_log("ALLOWED_SIM", command, "Simulated on non-Linux");
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
