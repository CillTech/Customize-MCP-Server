#ifndef VKU_AI_TOOLS_HPP
#define VKU_AI_TOOLS_HPP

#include <string>
#include <vector>
#include <map>
#include <regex>
#include <array>
#include <fstream>
#include <filesystem>
#include <algorithm>
#include <ctime>
#include <nlohmann/json.hpp>

#include "system_tools.hpp"
#include "log_tools.hpp"
#include "security_sandbox.hpp"
#include "firewall_tools.hpp"

namespace vku::tools {

using json = nlohmann::json;

class AITools {
private:
    // Hàm phụ trợ: chạy lệnh hệ thống qua pipe và giới hạn output 32KB
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

    static std::string current_timestamp() {
        std::time_t now = std::time(nullptr);
        char buf[32];
        std::strftime(buf, sizeof(buf), "%Y-%m-%d %H:%M:%S", std::localtime(&now));
        return std::string(buf);
    }

public:
    // Tool 9 (Nhóm 6): Gom toàn bộ thông số sức khỏe + cổng mạng + log lỗi + SSH thất bại trong 1 lần gọi
    static json collect_incident_snapshot(int log_lines = 15) {
        int safe_lines = std::clamp(log_lines, 5, 50);
        json snapshot;
        snapshot["timestamp"] = current_timestamp();
        snapshot["system_health"] = SystemTools::get_system_health();
        snapshot["network_ports"] = SecuritySandbox::audit_network_ports();
        snapshot["recent_syslog"] = LogTools::inspect_logs("syslog", safe_lines);
        snapshot["failed_ssh_logins"] = FirewallTools::check_failed_logins(10);
        snapshot["success"] = true;
        return snapshot;
    }

    // Tool 10 (Nhóm 6): Quét log SSH brute-force và tự động chặn IP tấn công qua UFW (kết hợp Nhóm 3)
    static json auto_mitigate_ssh_attack(int threshold = 5, bool auto_block = false) {
        json result;
        threshold = std::max(2, std::min(threshold, 100));
        std::map<std::string, int> ip_counts;
        std::regex ip_regex("([0-9]{1,3}\\.[0-9]{1,3}\\.[0-9]{1,3}\\.[0-9]{1,3})");

#ifdef __linux__
        // Đọc các dòng đăng nhập SSH thất bại từ /var/log/auth.log
        std::ifstream auth_file("/var/log/auth.log");
        std::string line;
        if (auth_file.is_open()) {
            while (std::getline(auth_file, line)) {
                if (line.find("Failed password") != std::string::npos ||
                    line.find("Invalid user") != std::string::npos) {
                    std::smatch match;
                    if (std::regex_search(line, match, ip_regex)) {
                        std::string ip = match[1].str();
                        // Không bao giờ tự chặn localhost
                        if (ip != "127.0.0.1" && ip != "0.0.0.0") {
                            ip_counts[ip]++;
                        }
                    }
                }
            }
        }
#else
        // Dữ liệu mô phỏng khi chạy test trên Windows
        ip_counts["192.168.1.99"] = 6;
#endif

        json attackers = json::array();
        json blocked_ips = json::array();

        for (const auto& [ip, count] : ip_counts) {
            if (count >= threshold) {
                json entry = {{"ip", ip}, {"failed_attempts", count}};
                if (auto_block) {
                    // Gọi trực tiếp Tool Nhóm 3 để chặn IP trên tường lửa UFW
                    json fw_res = FirewallTools::manage_firewall_rule("deny", ip);
                    entry["blocked"] = fw_res.value("success", false);
                    entry["firewall_output"] = fw_res.value("output", fw_res.value("error", ""));
                    blocked_ips.push_back(ip);
                } else {
                    entry["blocked"] = false;
                }
                attackers.push_back(entry);
            }
        }

        result["success"] = true;
        result["threshold"] = threshold;
        result["auto_block"] = auto_block;
        result["attackers_detected"] = attackers;
        result["blocked_count"] = blocked_ips.size();
        return result;
    }

    // Tool 11 (Nhóm 6): Bộ nhớ kinh nghiệm sự cố AI (lưu & tra cứu từ logs/incident_memory.json)
    static json incident_memory(const std::string& action, const std::string& keyword = "", const std::string& solution = "") {
        json result;
        const std::string mem_path = "logs/incident_memory.json";

        try {
            std::filesystem::create_directories("logs");
            json memory_arr = json::array();

            if (std::filesystem::exists(mem_path)) {
                std::ifstream ifs(mem_path);
                if (ifs.is_open()) {
                    try {
                        ifs >> memory_arr;
                        if (!memory_arr.is_array()) memory_arr = json::array();
                    } catch (...) {
                        memory_arr = json::array();
                    }
                }
            }

            if (action == "save") {
                if (keyword.empty() || solution.empty()) {
                    return {{"success", false}, {"error", "Both 'keyword' and 'solution' are required for 'save'."}};
                }
                json new_entry = {
                    {"timestamp", current_timestamp()},
                    {"keyword", keyword},
                    {"solution", solution}
                };
                memory_arr.push_back(new_entry);

                std::ofstream ofs(mem_path);
                ofs << memory_arr.dump(2);

                result["success"] = true;
                result["action"] = "save";
                result["saved_entry"] = new_entry;
                result["total_records"] = memory_arr.size();
                return result;
            }

            // Mặc định: tìm kiếm kinh nghiệm cũ theo từ khóa (không phân biệt hoa thường)
            std::string lower_kw = keyword;
            std::transform(lower_kw.begin(), lower_kw.end(), lower_kw.begin(), ::tolower);

            json matches = json::array();
            for (const auto& item : memory_arr) {
                std::string k = item.value("keyword", "");
                std::string s = item.value("solution", "");
                std::string lk = k, ls = s;
                std::transform(lk.begin(), lk.end(), lk.begin(), ::tolower);
                std::transform(ls.begin(), ls.end(), ls.begin(), ::tolower);

                if (lower_kw.empty() || lk.find(lower_kw) != std::string::npos || ls.find(lower_kw) != std::string::npos) {
                    matches.push_back(item);
                }
            }

            result["success"] = true;
            result["action"] = "search";
            result["keyword"] = keyword;
            result["matches"] = matches;
            result["total_records"] = memory_arr.size();
        } catch (const std::exception& e) {
            result["success"] = false;
            result["error"] = std::string("Incident memory error: ") + e.what();
        }

        return result;
    }

    // Tool 12 (Nhóm 6): Quản lý các mô hình AI cục bộ Ollama (list, ps, status)
    static json manage_ollama_models(const std::string& action = "list") {
        json result;
        if (action != "list" && action != "ps" && action != "status") {
            return {{"success", false}, {"error", "Invalid action. Supported: 'list', 'ps', 'status'."}};
        }

#ifdef __linux__
        std::string cmd;
        if (action == "list") cmd = "ollama list 2>&1";
        else if (action == "ps") cmd = "ollama ps 2>&1";
        else cmd = "systemctl is-active ollama 2>&1";

        auto [code, output] = run_cmd(cmd);
        result["success"] = (code == 0);
        result["action"] = action;
        result["output"] = output;
#else
        result["success"] = true;
        result["action"] = action;
        result["output"] = (action == "status") ? "active (simulated)" : "NAME\t\tSIZE\nqwen2.5:1.5b\t986 MB\n";
#endif
        return result;
    }

    // Tool 13 (Nhóm 6): Kiểm tra phần cứng phục vụ AI (GPU NVIDIA VRAM/nhiệt độ & tập lệnh CPU AVX2)
    static json check_ai_hardware() {
        json result;
#ifdef __linux__
        auto [gpu_code, gpu_out] = run_cmd("nvidia-smi --query-gpu=name,memory.total,memory.free,temperature.gpu,utilization.gpu --format=csv,noheader 2>&1");
        bool has_gpu = (gpu_code == 0 && gpu_out.find("not found") == std::string::npos && gpu_out.find("failed") == std::string::npos);

        auto [avx_code, avx_out] = run_cmd("grep -oE 'avx2|avx512' /proc/cpuinfo 2>/dev/null | sort -u");
        result["success"] = true;
        result["has_nvidia_gpu"] = has_gpu;
        result["gpu_info"] = has_gpu ? gpu_out : "No NVIDIA GPU detected (Running on CPU mode)";
        result["cpu_ai_extensions"] = avx_out.empty() ? "Standard x86_64" : avx_out;
#else
        result["success"] = true;
        result["has_nvidia_gpu"] = false;
        result["gpu_info"] = "Simulated AI Hardware Check (non-Linux)";
        result["cpu_ai_extensions"] = "avx2";
#endif
        return result;
    }

    // Tool 14 (Nhóm 6): Tự động đánh giá RAM trống để định tuyến & gợi ý model Qwen tối ưu nhất
    static json ai_model_router(bool prefer_speed = false) {
        json health = SystemTools::get_system_health();
        unsigned long long avail_mb = 2048;
        if (health.contains("memory") && health["memory"].contains("available_mb")) {
            avail_mb = health["memory"]["available_mb"].get<unsigned long long>();
        }

        std::string recommended_model;
        std::string reason;

        if (prefer_speed || avail_mb < 1500) {
            recommended_model = "qwen2.5:0.5b";
            reason = "RAM khả dụng thấp hoặc ưu tiên tốc độ phản hồi siêu nhanh (~400MB RAM).";
        } else if (avail_mb >= 6000) {
            recommended_model = "qwen2.5:7b";
            reason = "RAM khả dụng dồi dào (>= 6GB), đủ sức chạy model 7B suy luận sâu.";
        } else {
            recommended_model = "qwen2.5:1.5b";
            reason = "Cân bằng tối ưu giữa độ thông minh tiếng Việt và tài nguyên RAM (~1.5GB).";
        }

        return {
            {"success", true},
            {"available_ram_mb", avail_mb},
            {"prefer_speed", prefer_speed},
            {"recommended_model", recommended_model},
            {"reason", reason}
        };
    }
};

} // namespace vku::tools

#endif // VKU_AI_TOOLS_HPP
