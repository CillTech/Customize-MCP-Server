#ifndef VKU_SYSTEM_TOOLS_HPP
#define VKU_SYSTEM_TOOLS_HPP

#include <string>
#include <fstream>
#include <sstream>
#include <vector>
#include <chrono>
#include <thread>
#include <iomanip>
#include <nlohmann/json.hpp>

#ifdef __linux__
#include <sys/sysinfo.h>
#include <sys/statvfs.h>
#include <sys/utsname.h>
#include <unistd.h>
#endif

namespace vku::tools {

using json = nlohmann::json;

class SystemTools {
public:
    static json get_system_health() {
        json result;

#ifdef __linux__
        // 1. Host and Kernel Information (uname)
        struct utsname u_info;
        if (uname(&u_info) == 0) {
            result["os_info"] = {
                {"sysname", u_info.sysname},
                {"nodename", u_info.nodename},
                {"release", u_info.release},
                {"version", u_info.version},
                {"machine", u_info.machine}
            };
        }

        // 2. Memory & Process Information (sysinfo POSIX call)
        struct sysinfo s_info;
        if (sysinfo(&s_info) == 0) {
            unsigned long long total_ram = (unsigned long long)s_info.totalram * s_info.mem_unit;
            unsigned long long free_ram = (unsigned long long)s_info.freeram * s_info.mem_unit;
            unsigned long long buffer_ram = (unsigned long long)s_info.bufferram * s_info.mem_unit;
            unsigned long long used_ram = total_ram - free_ram - buffer_ram;

            double ram_used_pct = total_ram > 0 ? (double)used_ram / total_ram * 100.0 : 0.0;

            result["memory"] = {
                {"total_mb", total_ram / (1024 * 1024)},
                {"used_mb", used_ram / (1024 * 1024)},
                {"free_mb", free_ram / (1024 * 1024)},
                {"buffer_mb", buffer_ram / (1024 * 1024)},
                {"used_percentage", std::round(ram_used_pct * 10.0) / 10.0}
            };

            // Uptime formatting
            long uptime_sec = s_info.uptime;
            long days = uptime_sec / 86400;
            long hours = (uptime_sec % 86400) / 3600;
            long minutes = (uptime_sec % 3600) / 60;
            long seconds = uptime_sec % 60;

            std::ostringstream uptime_str;
            uptime_str << days << "d " << hours << "h " << minutes << "m " << seconds << "s";

            result["uptime"] = {
                {"seconds", uptime_sec},
                {"formatted", uptime_str.str()}
            };

            result["process_count"] = s_info.procs;
        }

        // 3. Disk Storage Information (statvfs POSIX call)
        struct statvfs fs_info;
        if (statvfs("/", &fs_info) == 0) {
            unsigned long long total_disk = (unsigned long long)fs_info.f_blocks * fs_info.f_frsize;
            unsigned long long free_disk = (unsigned long long)fs_info.f_bfree * fs_info.f_frsize;
            unsigned long long avail_disk = (unsigned long long)fs_info.f_bavail * fs_info.f_frsize;
            unsigned long long used_disk = total_disk - free_disk;

            double disk_used_pct = total_disk > 0 ? (double)used_disk / total_disk * 100.0 : 0.0;

            result["disk_root"] = {
                {"total_gb", std::round((double)total_disk / (1024 * 1024 * 1024) * 10.0) / 10.0},
                {"used_gb", std::round((double)used_disk / (1024 * 1024 * 1024) * 10.0) / 10.0},
                {"available_gb", std::round((double)avail_disk / (1024 * 1024 * 1024) * 10.0) / 10.0},
                {"used_percentage", std::round(disk_used_pct * 10.0) / 10.0}
            };
        }

        // 4. CPU Load Average (/proc/loadavg)
        std::ifstream load_file("/proc/loadavg");
        if (load_file.is_open()) {
            double l1, l5, l15;
            load_file >> l1 >> l5 >> l15;
            result["cpu_load"] = {
                {"load_1min", l1},
                {"load_5min", l5},
                {"load_15min", l15}
            };
        }

        // 5. Thermal Sensors (/sys/class/thermal or /sys/class/hwmon)
        bool temp_found = false;
        for (int i = 0; i < 5; ++i) {
            std::string path = "/sys/class/thermal/thermal_zone" + std::to_string(i) + "/temp";
            std::ifstream tf(path);
            if (tf.is_open()) {
                double temp_val;
                if (tf >> temp_val && temp_val > 0) {
                    result["cpu_temperature"] = std::round((temp_val > 1000 ? temp_val / 1000.0 : temp_val) * 10.0) / 10.0;
                    temp_found = true;
                    break;
                }
            }
        }
        if (!temp_found) {
            for (int h = 0; h < 5; ++h) {
                std::string path = "/sys/class/hwmon/hwmon" + std::to_string(h) + "/temp1_input";
                std::ifstream hf(path);
                if (hf.is_open()) {
                    double temp_val;
                    if (hf >> temp_val && temp_val > 0) {
                        result["cpu_temperature"] = std::round((temp_val > 1000 ? temp_val / 1000.0 : temp_val) * 10.0) / 10.0;
                        temp_found = true;
                        break;
                    }
                }
            }
        }

        result["status"] = "HEALTHY";
        result["timestamp"] = std::chrono::duration_cast<std::chrono::seconds>(
            std::chrono::system_clock::now().time_since_epoch()).count();

#else
        // Mock fallback for non-Linux dev environments
        result = {
            {"status", "DEV_SIMULATION"},
            {"os_info", {{"sysname", "Linux-Simulated"}, {"machine", "x86_64"}}},
            {"memory", {{"total_mb", 8192}, {"used_mb", 3540}, {"free_mb", 4652}, {"used_percentage", 43.2}}},
            {"uptime", {{"seconds", 12345}, {"formatted", "0d 3h 25m 45s"}}},
            {"disk_root", {{"total_gb", 50.0}, {"used_gb", 14.5}, {"available_gb", 35.5}, {"used_percentage", 29.0}}},
            {"cpu_load", {{"load_1min", 0.45}, {"load_5min", 0.38}, {"load_15min", 0.30}}}
        };
#endif

        return result;
    }
};

} // namespace vku::tools

#endif // VKU_SYSTEM_TOOLS_HPP
