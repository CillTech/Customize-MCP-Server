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

        // 2. Memory & Process Information
        struct sysinfo s_info;
        long uptime_sec = 0;
        int proc_count = 0;
        if (sysinfo(&s_info) == 0) {
            uptime_sec = s_info.uptime;
            proc_count = s_info.procs;

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

            result["process_count"] = proc_count;
        }

        // Exact memory calculation matching Linux standard 'free -m' via /proc/meminfo
        unsigned long long mem_total_kb = 0, mem_free_kb = 0, mem_avail_kb = 0;
        unsigned long long mem_buffers_kb = 0, mem_cached_kb = 0, mem_reclaim_kb = 0;

        std::ifstream meminfo_file("/proc/meminfo");
        if (meminfo_file.is_open()) {
            std::string key;
            unsigned long long val;
            while (meminfo_file >> key >> val) {
                if (key == "MemTotal:") mem_total_kb = val;
                else if (key == "MemFree:") mem_free_kb = val;
                else if (key == "MemAvailable:") mem_avail_kb = val;
                else if (key == "Buffers:") mem_buffers_kb = val;
                else if (key == "Cached:") mem_cached_kb = val;
                else if (key == "SReclaimable:") mem_reclaim_kb = val;
                std::string rest;
                std::getline(meminfo_file, rest);
            }
        }

        if (mem_total_kb > 0) {
            unsigned long long buff_cache_kb = mem_buffers_kb + mem_cached_kb + mem_reclaim_kb;
            unsigned long long mem_used_kb = (mem_total_kb >= (mem_free_kb + buff_cache_kb)) ? (mem_total_kb - mem_free_kb - buff_cache_kb) : 0;
            if (mem_avail_kb == 0) mem_avail_kb = mem_free_kb + buff_cache_kb;

            double ram_used_pct = (double)mem_used_kb / mem_total_kb * 100.0;

            result["memory"] = {
                {"total_mb", mem_total_kb / 1024},
                {"used_mb", mem_used_kb / 1024},
                {"free_mb", mem_free_kb / 1024},
                {"available_mb", mem_avail_kb / 1024},
                {"buff_cache_mb", buff_cache_kb / 1024},
                {"used_percentage", std::round(ram_used_pct * 10.0) / 10.0}
            };
        } else if (sysinfo(&s_info) == 0) {
            // Fallback to sysinfo
            unsigned long long total_ram = (unsigned long long)s_info.totalram * s_info.mem_unit;
            unsigned long long free_ram = (unsigned long long)s_info.freeram * s_info.mem_unit;
            unsigned long long used_ram = total_ram - free_ram;
            double ram_used_pct = total_ram > 0 ? (double)used_ram / total_ram * 100.0 : 0.0;

            result["memory"] = {
                {"total_mb", total_ram / (1024 * 1024)},
                {"used_mb", used_ram / (1024 * 1024)},
                {"free_mb", free_ram / (1024 * 1024)},
                {"available_mb", free_ram / (1024 * 1024)},
                {"buff_cache_mb", 0},
                {"used_percentage", std::round(ram_used_pct * 10.0) / 10.0}
            };
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
            {"memory", {{"total_mb", 16936}, {"used_mb", 1333}, {"free_mb", 12371}, {"available_mb", 15329}, {"buff_cache_mb", 3231}, {"used_percentage", 7.9}}},
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
