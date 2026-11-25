#ifndef VKU_NETWORK_TOOLS_HPP
#define VKU_NETWORK_TOOLS_HPP

#include <algorithm>
#include <cstring>
#include <nlohmann/json.hpp>
#include <regex>
#include <string>
#include <vector>

#ifdef __linux__
#include <arpa/inet.h>
#include <netdb.h>
#include <sys/socket.h>
#include <sys/types.h>
#endif

#include "security_sandbox.hpp"

namespace vku::tools {

using json = nlohmann::json;

class NetworkTools {
public:
  // Tool 22: Kiểm tra kết nối ICMP Ping tới IP hoặc tên miền (giới hạn count
  // 1..5)
  static json ping_host(const std::string &host, int count = 3) {
    std::regex host_regex("^[a-zA-Z0-9][a-zA-Z0-9.:\\-]{0,252}$");
    if (!std::regex_match(host, host_regex)) {
      return {{"success", false},
              {"allowed", false},
              {"violation", "BLOCKED_BY_SANDBOX"},
              {"error", "Invalid host/IP format for ping."}};
    }
    count = std::max(1, std::min(count, 5));

#ifdef __linux__
    json res = SecuritySandbox::run_exec_args(
        {"ping", "-c", std::to_string(count), "-W", "2", host},
        "ping_host:" + host);
    res["host"] = host;
    res["count"] = count;
    return res;
#else
    return {{"success", true},
            {"host", host},
            {"count", count},
            {"output", "Simulated ping to " + host + ": 0% packet loss."}};
#endif
  }

  // Tool 23: Phân giải tên miền DNS qua POSIX getaddrinfo() thuần C++
  static json check_dns_resolution(const std::string &domain) {
    std::regex domain_regex("^[a-zA-Z0-9][a-zA-Z0-9.\\-]{0,252}$");
    if (!std::regex_match(domain, domain_regex)) {
      return {{"success", false},
              {"allowed", false},
              {"violation", "BLOCKED_BY_SANDBOX"},
              {"error", "Invalid domain name format."}};
    }

#ifdef __linux__
    struct addrinfo hints {};
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;

    struct addrinfo *res = nullptr;
    int status = getaddrinfo(domain.c_str(), nullptr, &hints, &res);
    if (status != 0) {
      return {{"success", false},
              {"domain", domain},
              {"error", std::string("DNS resolution failed: ") +
                            gai_strerror(status)}};
    }

    json ips = json::array();
    std::vector<std::string> seen;
    for (struct addrinfo *p = res; p != nullptr; p = p->ai_next) {
      char ipstr[INET6_ADDRSTRLEN] = {0};
      void *addr = nullptr;
      std::string ip_ver;

      if (p->ai_family == AF_INET) {
        auto *ipv4 = reinterpret_cast<struct sockaddr_in *>(p->ai_addr);
        addr = &(ipv4->sin_addr);
        ip_ver = "IPv4";
      } else if (p->ai_family == AF_INET6) {
        auto *ipv6 = reinterpret_cast<struct sockaddr_in6 *>(p->ai_addr);
        addr = &(ipv6->sin6_addr);
        ip_ver = "IPv6";
      }

      if (addr && inet_ntop(p->ai_family, addr, ipstr, sizeof(ipstr))) {
        std::string ip(ipstr);
        if (std::find(seen.begin(), seen.end(), ip) == seen.end()) {
          seen.push_back(ip);
          ips.push_back({{"type", ip_ver}, {"address", ip}});
        }
      }
    }
    freeaddrinfo(res);

    return {{"success", !ips.empty()},
            {"domain", domain},
            {"record_count", ips.size()},
            {"records", ips}};
#else
    return {{"success", true},
            {"domain", domain},
            {"record_count", 1},
            {"records", json::array({{{"type", "IPv4"}, {"address", "142.250.199.14"}}})}};
#endif
  }

  // Tool 24: Kiểm tra trạng thái HTTP endpoint (chỉ nhận http:// hoặc
  // https://, timeout 5s)
  static json check_http_endpoint(const std::string &url) {
    std::regex url_regex(
        "^https?://[a-zA-Z0-9.\\-]+(:[0-9]{1,5})?(/[a-zA-Z0-9._~:/?#\\[\\]@!$&'()*+,;=%\\-]*)?$");
    if (!std::regex_match(url, url_regex) ||
        url.find_first_of(" \t\n\r`$|><") != std::string::npos) {
      return {{"success", false},
              {"allowed", false},
              {"violation", "BLOCKED_BY_SANDBOX"},
              {"error",
               "Invalid HTTP URL. Must begin with http:// or https:// without "
               "shell characters."}};
    }

#ifdef __linux__
    json res = SecuritySandbox::run_exec_args(
        {"curl", "-sS", "-o", "/dev/null", "-w",
         "HTTP_STATUS=%{http_code} | TIME_TOTAL=%{time_total}s | "
         "REMOTE_IP=%{remote_ip}",
         "--max-time", "5", url},
        "check_http_endpoint:" + url);
    res["url"] = url;
    return res;
#else
    return {{"success", true},
            {"url", url},
            {"output", "HTTP_STATUS=200 | TIME_TOTAL=0.012s | REMOTE_IP=127.0.0.1"}};
#endif
  }
};

} // namespace vku::tools

#endif // VKU_NETWORK_TOOLS_HPP

