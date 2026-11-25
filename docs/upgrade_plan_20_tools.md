# KẾ HOẠCH NÂNG CẤP PROJECT: MỞ RỘNG LÊN 20 MCP TOOLS
**Đề tài:** Build and Configure an MCP Server for Agentic AI in Linux  
**Mục tiêu:** Mở rộng từ **5 tools** hiện tại lên **20 tools** quản trị Linux toàn diện, giữ nguyên kiến trúc **Native C++17 + Security Sandbox**.

---

## 1. TỔNG QUAN KIẾN TRÚC MODULE (20 TOOLS)

Hiện tại project đã có **5 tools**:
1. `get_system_health` (`src/system_tools.hpp`)
2. `manage_service` (`src/service_tools.hpp`)
3. `inspect_logs` (`src/log_tools.hpp`)
4. `audit_network_ports` (`src/security_sandbox.hpp`)
5. `execute_safe_command` (`src/security_sandbox.hpp`)

Kế hoạch bổ sung **15 tools mới**, chia làm **5 module C++** mới trong thư mục `src/`:

---

## 2. CHI TIẾT 15 TOOLS MỚI

### Nhóm 1: Quản lý Tiến trình & Tài nguyên (`src/process_tools.hpp`) — 3 tools
| STT | Tên Tool | Chức năng | Tham số (`inputSchema`) | Bảo mật Sandbox |
| :-: | :--- | :--- | :--- | :--- |
| 6 | `list_top_processes` | Liệt kê top N tiến trình ăn CPU/RAM nhiều nhất | `sort_by` (`cpu` / `mem`), `limit` (1–30) | Chỉ đọc `/proc` hoặc `ps` |
| 7 | `kill_process` | Dừng tiến trình bị treo theo PID | `pid` (integer), `signal` (`SIGTERM` / `SIGKILL`) | Chặn kill PID <= 100 (tiến trình lõi OS) |
| 8 | `get_disk_partitions` | Kiểm tra chi tiết các phân vùng mount & dung lượng | Không có | Chỉ đọc `df -h` / `getmntent` |

### Nhóm 2: Quản lý Tệp tin & Cấu hình An toàn (`src/file_tools.hpp`) — 3 tools
| STT | Tên Tool | Chức năng | Tham số (`inputSchema`) | Bảo mật Sandbox |
| :-: | :--- | :--- | :--- | :--- |
| 9 | `read_file_safe` | Đọc file cấu hình hệ thống | `path` (string), `max_lines` (1–200) | Whitelist thư mục (`/etc/nginx`, `/var/log`...); chặn `/etc/shadow`, SSH key |
| 10 | `search_in_logs` | Tìm từ khóa lỗi (`ERROR`, `Failed`...) trong log | `keyword` (string), `log_source` (string) | Regex lọc ký tự đặc biệt chống Command Injection |
| 11 | `check_file_permissions` | Kiểm tra quyền `chmod`/`chown` của file/thư mục | `path` (string) | Dùng `stat()` POSIX, không thực thi shell |

### Nhóm 3: Bảo mật & Tường lửa (`src/firewall_tools.hpp`) — 3 tools
| STT | Tên Tool | Chức năng | Tham số (`inputSchema`) | Bảo mật Sandbox |
| :-: | :--- | :--- | :--- | :--- |
| 12 | `check_firewall_status` | Xem trạng thái tường lửa `ufw` và danh sách rule | Không có | Chỉ đọc `ufw status` |
| 13 | `manage_firewall_rule` | Chặn IP tấn công hoặc mở/đóng port | `action` (`allow` / `deny`), `target` (IP hoặc Port) | Validate chặt chẽ định dạng IP/Port bằng Regex |
| 14 | `check_failed_logins` | Thống kê đăng nhập SSH thất bại (chống Brute-force) | `limit` (integer, mặc định 20) | Chỉ đọc từ `/var/log/auth.log` hoặc `lastb` |

### Nhóm 4: Mạng & Chẩn đoán Kết nối (`src/network_tools.hpp`) — 3 tools
| STT | Tên Tool | Chức năng | Tham số (`inputSchema`) | Bảo mật Sandbox |
| :-: | :--- | :--- | :--- | :--- |
| 15 | `ping_host` | Kiểm tra kết nối tới IP/Domain | `host` (string), `count` (1–5) | Giới hạn `count <= 5` tránh treo tiến trình |
| 16 | `check_dns_resolution` | Kiểm tra phân giải tên miền | `domain` (string) | Dùng `getaddrinfo()` POSIX hoặc `nslookup` |
| 17 | `check_http_endpoint` | Kiểm tra dịch vụ web có trả về HTTP 200 OK không | `url` (string) | Chỉ cho phép `http://` hoặc `https://`, timeout 5s |

### Nhóm 5: Tự động hóa, User & Container (`src/devops_tools.hpp`) — 3 tools
| STT | Tên Tool | Chức năng | Tham số (`inputSchema`) | Bảo mật Sandbox |
| :-: | :--- | :--- | :--- | :--- |
| 18 | `list_cron_jobs` | Liệt kê các tác vụ chạy định kỳ (`crontab`) | Không có | Chỉ đọc `crontab -l` |
| 19 | `get_user_sessions` | Xem danh sách user đang đăng nhập vào máy chủ | Không có | Chỉ đọc `who` / `w` |
| 20 | `manage_docker_containers` | Liệt kê, xem log hoặc restart Docker container | `action` (`ps` / `logs` / `restart`), `container_name` | Validate tên container bằng Regex `^[a-zA-Z0-9_\-\.]+$` |

---

## 3. LỘ TRÌNH TRIỂN KHAI (4 GIAI ĐOẠN)

- [ ] **Giai đoạn 1: Xây dựng các module C++ mới (`src/*.hpp`)**
  - Tạo 5 file: `process_tools.hpp`, `file_tools.hpp`, `firewall_tools.hpp`, `network_tools.hpp`, `devops_tools.hpp`.
  - Mọi hàm đều trả về `nlohmann::json` thống nhất cấu trúc `{"success": true/false, ...}`.
- [ ] **Giai đoạn 2: Tích hợp vào `src/mcp_server.hpp`**
  - Include 5 file header mới.
  - Khai báo schema cho 15 tool mới trong `get_tool_definitions()` *(lưu ý: viết `description` ngắn gọn để model nhỏ như `qwen2.5:1.5b` không bị quá tải context)*.
  - Thêm điều hướng `else if (tool_name == ...)` trong `handle_request()`.
- [ ] **Giai đoạn 3: Cập nhật AI Client (`client/agent_cli.py` & `client/web_ui.py`)**
  - Cập nhật từ khóa nhận diện cho chế độ Offline Rule-based Reasoner.
  - Thêm các nút Quick Action mẫu trên Web UI nếu cần.
- [ ] **Giai đoạn 4: Biên dịch & Kiểm thử**
  - Chạy `make` để biên dịch lại `bin/vku_mcp_server`.
  - Mở rộng `client/test_mcp_direct.py` để test đủ 20 tools và kiểm tra các rule Sandbox mới.

---

## 4. CÁCH KIỂM THỬ (TEST) TOÀN BỘ 20 TOOLS

### Cách 1: Chạy bộ test tự động (Nhanh nhất)
```bash
python3 client/test_mcp_direct.py
```

### Cách 2: Test trực tiếp từng tool bằng JSON-RPC trên Linux (`echo` + pipe)

#### 5 Tool hiện tại:
```bash
# 1. get_system_health
echo '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_system_health","arguments":{}}}' | ./bin/vku_mcp_server

# 2. manage_service
echo '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"manage_service","arguments":{"service_name":"ssh","action":"status"}}}' | ./bin/vku_mcp_server

# 3. inspect_logs
echo '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"inspect_logs","arguments":{"log_source":"syslog","lines":10}}}' | ./bin/vku_mcp_server

# 4. audit_network_ports
echo '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"audit_network_ports","arguments":{}}}' | ./bin/vku_mcp_server

# 5. execute_safe_command (Hợp lệ & Bị Sandbox chặn)
echo '{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"execute_safe_command","arguments":{"command":"uname -a"}}}' | ./bin/vku_mcp_server
echo '{"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"execute_safe_command","arguments":{"command":"rm -rf /tmp"}}}' | ./bin/vku_mcp_server
```

#### 15 Tool mới (sau khi hoàn thiện code):
```bash
# 6. list_top_processes
echo '{"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"name":"list_top_processes","arguments":{"sort_by":"cpu","limit":5}}}' | ./bin/vku_mcp_server

# 7. kill_process (Test cả PID hệ thống để kiểm tra Sandbox chặn)
echo '{"jsonrpc":"2.0","id":8,"method":"tools/call","params":{"name":"kill_process","arguments":{"pid":1,"signal":"SIGTERM"}}}' | ./bin/vku_mcp_server

# 8. get_disk_partitions
echo '{"jsonrpc":"2.0","id":9,"method":"tools/call","params":{"name":"get_disk_partitions","arguments":{}}}' | ./bin/vku_mcp_server

# 9. read_file_safe (Test đọc /etc/os-release và test chặn /etc/shadow)
echo '{"jsonrpc":"2.0","id":10,"method":"tools/call","params":{"name":"read_file_safe","arguments":{"path":"/etc/os-release","max_lines":20}}}' | ./bin/vku_mcp_server
echo '{"jsonrpc":"2.0","id":11,"method":"tools/call","params":{"name":"read_file_safe","arguments":{"path":"/etc/shadow","max_lines":10}}}' | ./bin/vku_mcp_server

# 10. search_in_logs
echo '{"jsonrpc":"2.0","id":12,"method":"tools/call","params":{"name":"search_in_logs","arguments":{"keyword":"error","log_source":"syslog"}}}' | ./bin/vku_mcp_server

# 11. check_file_permissions
echo '{"jsonrpc":"2.0","id":13,"method":"tools/call","params":{"name":"check_file_permissions","arguments":{"path":"/etc/passwd"}}}' | ./bin/vku_mcp_server

# 12. check_firewall_status
echo '{"jsonrpc":"2.0","id":14,"method":"tools/call","params":{"name":"check_firewall_status","arguments":{}}}' | ./bin/vku_mcp_server

# 13. manage_firewall_rule
echo '{"jsonrpc":"2.0","id":15,"method":"tools/call","params":{"name":"manage_firewall_rule","arguments":{"action":"allow","target":"8080"}}}' | ./bin/vku_mcp_server

# 14. check_failed_logins
echo '{"jsonrpc":"2.0","id":16,"method":"tools/call","params":{"name":"check_failed_logins","arguments":{"limit":10}}}' | ./bin/vku_mcp_server

# 15. ping_host
echo '{"jsonrpc":"2.0","id":17,"method":"tools/call","params":{"name":"ping_host","arguments":{"host":"8.8.8.8","count":3}}}' | ./bin/vku_mcp_server

# 16. check_dns_resolution
echo '{"jsonrpc":"2.0","id":18,"method":"tools/call","params":{"name":"check_dns_resolution","arguments":{"domain":"google.com"}}}' | ./bin/vku_mcp_server

# 17. check_http_endpoint
echo '{"jsonrpc":"2.0","id":19,"method":"tools/call","params":{"name":"check_http_endpoint","arguments":{"url":"http://localhost:8080"}}}' | ./bin/vku_mcp_server

# 18. list_cron_jobs
echo '{"jsonrpc":"2.0","id":20,"method":"tools/call","params":{"name":"list_cron_jobs","arguments":{}}}' | ./bin/vku_mcp_server

# 19. get_user_sessions
echo '{"jsonrpc":"2.0","id":21,"method":"tools/call","params":{"name":"get_user_sessions","arguments":{}}}' | ./bin/vku_mcp_server

# 20. manage_docker_containers
echo '{"jsonrpc":"2.0","id":22,"method":"tools/call","params":{"name":"manage_docker_containers","arguments":{"action":"ps","container_name":""}}}' | ./bin/vku_mcp_server
```

### Cách 3: Test qua AI Agent (Ngôn ngữ tự nhiên)
Khởi chạy CLI hoặc Web UI:
```bash
python3 client/agent_cli.py
# hoặc
python3 client/web_ui.py
```
Sau đó thử các câu lệnh tiếng Việt tương ứng như:
* *"Xem top 5 tiến trình đang ăn CPU nhiều nhất"*
* *"Kiểm tra các phân vùng ổ đĩa còn trống bao nhiêu"*
* *"Kiểm tra xem có ai đăng nhập SSH thất bại gần đây không"*
* *"Ping thử tới 8.8.8.8 xem có mạng không"*
* *"Xem các Docker container đang chạy"*

---

## 5. MỞ RỘNG NHÓM 6: AGENTIC AI TỰ HÀNH & PHÒNG THỦ CHỦ ĐỘNG (`src/ai_tools.hpp` + Agent Watchdog)

Thay vì chỉ đọc thông tin thụ động, Nhóm 6 biến hệ thống thành **Kỹ sư SRE tự hành (Autonomous Agent)** biết tự phát hiện lỗi, tự sửa dịch vụ, tự chặn hacker và ghi nhớ kinh nghiệm:

### A. Các Tool C++ chuyên sâu cho Agentic AI (`src/ai_tools.hpp`)
| STT | Tên Tool | Chức năng "WOW" | Tham số (`inputSchema`) | Bảo mật Sandbox |
| :-: | :--- | :--- | :--- | :--- |
| 21 | `collect_incident_snapshot` | Gom nhanh RAM + Top CPU + Log lỗi + Port trong 1 lần gọi để AI chẩn đoán sự cố tức thì | `log_lines` (integer, mặc định 15) | Giới hạn output tối đa 64 KB |
| 22 | `auto_mitigate_ssh_attack` | Quét `/var/log/auth.log`, tự lọc các IP brute-force (>5 lần sai pass) và đề xuất/chặn ngay qua UFW | `threshold` (int), `auto_block` (bool) | Validate IPv4 chặt chẽ, không bao giờ tự chặn IP nội bộ `127.0.0.1` |
| 23 | `incident_memory` | Lưu và tra cứu bộ nhớ kinh nghiệm xử lý sự cố (`logs/incident_memory.json`) | `action` (`search` / `save`), `keyword`, `solution` | Chỉ đọc/ghi duy nhất trong `logs/incident_memory.json` |
| 24 | `manage_ollama_models` | Liệt kê model AI (`ollama list`), model đang nạp RAM (`ollama ps`) & kiểm tra cổng `11434` | `action` (`list` / `ps` / `status`) | Chỉ đọc trạng thái Ollama & cổng `11434` |
| 25 | `check_ai_hardware` | Kiểm tra GPU NVIDIA (`nvidia-smi`), VRAM, nhiệt độ & tập lệnh CPU (`AVX2`/`AVX-512`) | Không có | Chỉ đọc thông số phần cứng |
| 26 | `ai_model_router` | Tự đo RAM/CPU trống hiện tại để tự động chọn model LLM tối ưu (`0.5b` / `1.5b` / `7b`) | `prefer_speed` (bool) | Chỉ đọc `/proc/meminfo` & gợi ý model |

### B. Tính năng Tự Phục Hồi & Cảnh Báo Chạy Ngầm (Autonomous Self-Healing Watchdog)
* **Cơ chế**: Tích hợp luồng nền (Background Thread) trong `client/web_ui.py` chạy định kỳ mỗi **15–30 giây**:
  1. Tự động gọi `get_system_health` và `manage_service` kiểm tra các dịch vụ trọng yếu (`nginx`, `ssh`, `ollama`).
  2. **Nếu phát hiện dịch vụ chết hoặc RAM > 90%**: AI tự gọi `inspect_logs` tìm nguyên nhân → tự gọi `manage_service(restart)` để cứu dịch vụ → lưu sự cố vào `incident_memory`.
  3. **Gửi cảnh báo tức thì (Telegram / Discord Webhook)**: Bắn thông báo kèm nguyên nhân & kết quả tự sửa về điện thoại/kênh chat và hiển thị banner cảnh báo trên Web Dashboard.
* **Kịch bản Demo ấn tượng**: Thử gõ `sudo systemctl stop nginx` trên terminal Ubuntu, 10 giây sau AI tự phát hiện, tự đọc log, tự bật lại Nginx và gửi tin nhắn báo cáo về Telegram/Web UI.

### Lệnh test nhanh Nhóm 6:
```bash
# 21. collect_incident_snapshot
echo '{"jsonrpc":"2.0","id":23,"method":"tools/call","params":{"name":"collect_incident_snapshot","arguments":{"log_lines":15}}}' | ./bin/vku_mcp_server

# 22. auto_mitigate_ssh_attack (chế độ quét thử, chưa auto block)
echo '{"jsonrpc":"2.0","id":24,"method":"tools/call","params":{"name":"auto_mitigate_ssh_attack","arguments":{"threshold":5,"auto_block":false}}}' | ./bin/vku_mcp_server

# 23. incident_memory (tra cứu kinh nghiệm sửa lỗi)
echo '{"jsonrpc":"2.0","id":25,"method":"tools/call","params":{"name":"incident_memory","arguments":{"action":"search","keyword":"nginx"}}}' | ./bin/vku_mcp_server

# 24. manage_ollama_models
echo '{"jsonrpc":"2.0","id":26,"method":"tools/call","params":{"name":"manage_ollama_models","arguments":{"action":"list"}}}' | ./bin/vku_mcp_server

# 25. check_ai_hardware
echo '{"jsonrpc":"2.0","id":27,"method":"tools/call","params":{"name":"check_ai_hardware","arguments":{}}}' | ./bin/vku_mcp_server

# 26. ai_model_router
echo '{"jsonrpc":"2.0","id":28,"method":"tools/call","params":{"name":"ai_model_router","arguments":{"prefer_speed":false}}}' | ./bin/vku_mcp_server
```

---

## 6. KẾ HOẠCH TỐI ƯU GIAO DIỆN WEB UI (`client/web_ui.py`)

Khi tăng từ 5 lên 23 tools, nếu hiển thị tất cả nút bấm ra màn hình sẽ rất rối. Giao diện Web cần được thiết kế lại theo nguyên tắc **Tối giản – Phân nhóm – Ẩn/Hiện linh hoạt**:

### 1. Bố cục 3 phần rõ ràng, không rối mắt
* **Thanh Telemetry trên cùng (Compact Header)**:
  * Giữ gọn 4 chỉ số chính: **CPU Load**, **RAM**, **Disk**, **Uptime** kèm thanh tiến trình (progress bar) đổi màu theo ngưỡng (Xanh `< 70%`, Vàng `70–85%`, Đỏ `> 85%`).
  * Hiển thị **Badge trạng thái AI** đang dùng (ví dụ: `🟢 Qwen 2.5 Local` / `🔵 Gemini Cloud` / `🟡 Offline Mode`).
* **Sidebar trái — Danh mục 23 Tools dạng Accordion (Đóng/Mở theo nhóm)**:
  * Thay vì trải 23 nút tràn lan, gom toàn bộ tool vào **6 nhóm thu gọn được**:
    1. 🖥️ *Hệ thống & Dịch vụ* (`get_system_health`, `manage_service`, `inspect_logs`)
    2. ⚙️ *Tiến trình & Ổ đĩa* (`list_top_processes`, `kill_process`, `get_disk_partitions`)
    3. 📁 *Tệp tin & Log* (`read_file_safe`, `search_in_logs`, `check_file_permissions`)
    4. 🛡️ *Bảo mật & Tường lửa* (`audit_network_ports`, `execute_safe_command`, `check_firewall_status`, `manage_firewall_rule`, `check_failed_logins`)
    5. 🌐 *Mạng & DevOps* (`ping_host`, `check_dns_resolution`, `check_http_endpoint`, `list_cron_jobs`, `get_user_sessions`, `manage_docker_containers`)
    6. 🤖 *Hạ tầng AI* (`manage_ollama_models`, `check_ai_hardware`, `collect_incident_snapshot`)
  * Click vào tên tool sẽ tự điền câu lệnh mẫu vào ô chat để test nhanh.
* **Khung Chat chính ở giữa**:
  * Hỗ trợ hiển thị **Markdown** (bảng biểu, danh sách, khối code) để kết quả từ 23 tool (như bảng tiến trình, bảng port, log lỗi) hiện ra sạch đẹp, dễ đọc.
  * Chỉ giữ **4 nút Quick Action** hay dùng nhất ngay trên ô nhập liệu (*Sức khỏe hệ thống*, *Snapshot sự cố*, *Quét bảo mật*, *Kiểm tra Ollama*).
* **Panel phải — Live MCP Inspector (Có nút Toggle Ẩn/Hiện)**:
  * Cho phép bấm **Thu gọn** khi chỉ muốn chat, và **Mở rộng** khi cần trình diễn luồng JSON-RPC 2.0 cho giảng viên xem.
  * Thêm bộ lọc nhanh: `Tất cả` | `Thành công` | `Bị Sandbox chặn`.

### 2. Nâng cấp thẩm mỹ (Visual Polish)
* Sử dụng tông màu **Dark Slate** dịu mắt, tăng khoảng trống (`padding` / `gap`) giữa các thẻ để giao diện thoáng.
* Phân biệt rõ màu sắc trạng thái: Xanh lá (an toàn/thành công), Vàng (cảnh báo), Đỏ (lỗi hoặc bị Sandbox chặn).

---

## 7. KẾ HOẠCH NÂNG CẤP SECURITY SANDBOX (`src/security_sandbox.hpp`)

Hiện tại `SecuritySandbox` mới kiểm tra Blacklist chuỗi cơ bản và Whitelist từ đầu tiên (`first_word`). Để đạt chuẩn bảo mật thực tế cho hệ thống Linux và làm điểm nhấn mạnh khi bảo vệ đồ án, cần nâng cấp Sandbox theo **5 lớp phòng thủ (Defense-in-Depth)**:

### 1. Chống Command Chaining & Shell Injection (Quan trọng nhất)
* **Lỗ hổng hiện tại**: Nếu chỉ kiểm tra `first_word` là `ls` hoặc `echo`, kẻ tấn công (hoặc Prompt Injection) vẫn có thể nối lệnh như `ls; cat /etc/shadow`, `echo $(whoami)`, hoặc ``ls `id` ``.
* **Nâng cấp**:
  * Chặn các toán tử nối/chuyển hướng shell trong `execute_safe_command`: `;`, `&&`, `||`, `` ` ``, `$(`, `>`, `>>`, `| sh`, `| bash`.
  * **Nâng cao**: Thay `popen()` (vốn gọi qua `/bin/sh -c`) bằng `fork()` + `execvp()` để tách tham số trực tiếp, loại bỏ hoàn toàn nguy cơ Shell Injection.

### 2. Bảo vệ Đường dẫn Nhạy cảm (Sensitive Path Guard)
* **Lỗ hổng hiện tại**: `cat`, `head`, `tail`, `grep` nằm trong Whitelist nên AI vẫn có thể đọc `/etc/shadow`, SSH private key (`id_rsa`), hoặc file `.env`.
* **Nâng cấp**: Thêm danh sách đường dẫn cấm (Forbidden Paths):
  * `/etc/shadow`, `/etc/gshadow`, `/etc/sudoers`
  * Thư mục/file chứa key: `.ssh/id_rsa`, `.ssh/id_ed25519`, `.env`
  * `/proc/*/environ`, `/dev/sd*`, `/dev/nvme*`

### 3. Chuẩn hóa Lệnh & Chống Lách Luật (Anti-Bypass Normalization)
* **Lỗ hổng hiện tại**: Chỉ chặn chuỗi `"rm -rf"` cố định nên có thể bị lách bằng `"rm  -rf"` (2 dấu cách), `"rm -fr"`, hoặc `"/bin/rm -rf"`.
* **Nâng cấp**:
  * Chuẩn hóa khoảng trắng liên tiếp thành 1 khoảng trắng duy nhất trước khi kiểm tra.
  * Tách bỏ đường dẫn tuyệt đối ở từ đầu tiên (ví dụ `/bin/ls` -> `ls`) trước khi đối chiếu Whitelist.

### 4. Giới hạn Thời gian & Tài nguyên (Timeout & `rlimit`)
* **Lỗ hổng hiện tại**: Các lệnh như `ping 8.8.8.8` (quên `-c`) hoặc `find /` chạy vô tận sẽ làm treo luôn MCP Server.
* **Nâng cấp**:
  * Bọc lệnh thực thi với **Timeout cứng (ví dụ 5–10 giây)** bằng `fork()` + theo dõi thời gian / `kill(pid, SIGKILL)` nếu quá hạn.
  * Dùng `setrlimit()` giới hạn bộ nhớ và kích thước output tối đa (64 KB) cho tiến trình con.

### 5. Nhật ký Kiểm toán & Phân cấp Rủi ro (Audit Log & Risk Tiers)
* **Audit Logging**: Tự động ghi lại mọi yêu cầu bị chặn (`BLOCKED_BY_SANDBOX`) và các lệnh thay đổi hệ thống (`manage_service`, `manage_firewall_rule`, `kill_process`) vào file `logs/sandbox_audit.log` kèm timestamp để truy vết.
* **Chế độ Read-Only Mode (Tùy chọn an toàn khi Demo)**: Cho phép bật cờ môi trường `VKU_READONLY_MODE=1` để chỉ cho phép các tool giám sát/đọc dữ liệu, tạm khóa mọi hành động ghi/sửa/xóa.

### Lộ trình & Lệnh test kiểm chứng Sandbox mới:
```bash
# Test 1: Chặn nối lệnh (Command Chaining)
echo '{"jsonrpc":"2.0","id":30,"method":"tools/call","params":{"name":"execute_safe_command","arguments":{"command":"ls; id"}}}' | ./bin/vku_mcp_server

# Test 2: Chặn đọc file mật khẩu (/etc/shadow)
echo '{"jsonrpc":"2.0","id":31,"method":"tools/call","params":{"name":"execute_safe_command","arguments":{"command":"cat /etc/shadow"}}}' | ./bin/vku_mcp_server

# Test 3: Chặn lách dấu cách / đường dẫn (/bin/rm  -fr)
echo '{"jsonrpc":"2.0","id":32,"method":"tools/call","params":{"name":"execute_safe_command","arguments":{"command":"/bin/rm  -fr /tmp"}}}' | ./bin/vku_mcp_server

# Test 4: Chặn lệnh chạy treo quá timeout
echo '{"jsonrpc":"2.0","id":33,"method":"tools/call","params":{"name":"execute_safe_command","arguments":{"command":"ping 8.8.8.8"}}}' | ./bin/vku_mcp_server
```
