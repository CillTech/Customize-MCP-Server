# BẢN ĐẶC TẢ CÁC CHỨC NĂNG CẦN LÀM - TOPIC 15
## Đề tài: Build and Configure an MCP Server for Agentic AI in Linux (C++17)

---

## 1. Kiến Trúc Tổng Thể Các Thành Phần

```
 [Người dùng / Giảng viên]
            │ (Nhập lệnh bằng tiếng Việt / tiếng Anh)
            ▼
 ┌────────────────────────────────────────────────────────┐
 │ 1. AI Agent Brain (Google Gemini API / Claude / Ollama) │
 └──────────────────────────┬─────────────────────────────┘
                            │ (JSON-RPC 2.0 qua Standard I/O)
                            ▼
 ┌────────────────────────────────────────────────────────┐
 │ 2. C++ MCP Server (vku_mcp_server)                     │
 │    - Giao thức: JSON-RPC Parser (nlohmann/json)        │
 │    - Core Tools Engine (POSIX Linux System Calls)      │
 └──────────────────────────┬─────────────────────────────┘
                            │
            ┌───────────────┼───────────────┐
            ▼               ▼               ▼
      [Nhân Linux]     [Systemd]      [File Logs]
     /proc, sysinfo    systemctl       /var/log
```

---

## 2. Danh Sách Các Chức Năng Cụ Thể Cần Xây Dựng

### NHÓM 1: Lõi Giao Thức MCP (MCP Protocol Engine bằng C++)
*Mục tiêu: Đảm bảo server hiểu và giao tiếp chuẩn xác với mọi Agent AI theo đặc tả Model Context Protocol.*

- [x] **Chức năng 1.1: JSON-RPC 2.0 Parser & Dispatcher**
  - Đọc từng dòng JSON từ `std::cin`.
  - Phân tích cú pháp JSON bằng thư viện `nlohmann/json.hpp`.
  - Định tuyến các phương thức (method routing):
    - `initialize`: Bắt tay với AI, khai báo tên server (`vku-linux-mcp`), version protocol (`2024-11-05`), danh sách capabilities.
    - `notifications/initialized`: Nhận xác nhận kết nối từ AI.
    - `tools/list`: Cung cấp danh sách định nghĩa (JSON Schema) của toàn bộ các công cụ Linux để AI biết công cụ nào nhận tham số gì.
    - `tools/call`: Nhận lệnh thực thi công cụ từ AI, chạy code C++ và xuất kết quả chuẩn JSON ra `std::cout`.

---

### NHÓM 2: Bộ Công Cụ Quản Trị Linux (C++ System Tools)
*Mục tiêu: Các hàm C++ trực tiếp tương tác với hệ điều hành Ubuntu để AI gọi khi cần.*

- [x] **Chức năng 2.1: `get_system_health` (Giám sát tài nguyên Linux)**
  - **Mô tả**: Cho phép AI đọc toàn bộ tình trạng phần cứng máy chủ.
  - **Kỹ thuật C++**:
    - Dùng `<sys/sysinfo.h>` (`sysinfo()`): Lấy tổng dung lượng RAM, RAM còn trống, thời gian máy đã bật (Uptime), số lượng tiến trình đang chạy.
    - Dùng `<sys/statvfs.h>` (`statvfs()`): Lấy thông số ổ cứng gốc `/` (Tổng dung lượng, đã dùng, còn trống tính theo GB).
    - Đọc file ảo `/proc/loadavg`: Lấy chỉ số tải CPU trung bình 1m, 5m, 15m.
  - **Dữ liệu trả về**: Chuỗi JSON có cấu trúc rõ ràng để AI phân tích.

- [x] **Chức năng 2.2: `manage_service` (Bật / Tắt / Khởi động lại dịch vụ)**
  - **Mô tả**: Cho phép AI kiểm tra trạng thái hoặc thao tác với dịch vụ Linux (như `nginx`, `ssh`, `ufw`, `mysql`).
  - **Tham số nhận vào**:
    - `service_name`: Tên dịch vụ (ví dụ: `"nginx"`, `"ssh"`).
    - `action`: Hành động (`"status"`, `"start"`, `"stop"`, `"restart"`).
  - **Kỹ thuật C++**: Gọi lệnh `systemctl <action> <service>` qua system call Linux, bắt mã lỗi (exit code) và chuỗi phản hồi.

- [x] **Chức năng 2.3: `inspect_logs` (Đọc và chẩn đoán lỗi qua Logs)**
  - **Mô tả**: Cho phép AI xem các dòng nhật ký gần nhất để tìm nguyên nhân khi dịch vụ bị crash hoặc có cảnh báo.
  - **Tham số nhận vào**:
    - `log_type`: Loại log cần xem (`"syslog"`, `"auth"`, `"nginx"`).
    - `lines`: Số dòng cuối cần đọc (mặc định 20 dòng).
  - **Kỹ thuật C++**: Mở file `/var/log/...`, đọc ngược hoặc dùng lệnh `tail -n` an toàn trả về đoạn log cho AI tóm tắt.

- [x] **Chức năng 2.4: `audit_network_ports` (Kiểm tra an toàn cổng mạng)**
  - **Mô tả**: Cho phép AI rà soát xem máy chủ đang mở những cổng mạng (Port) nào.
  - **Kỹ thuật C++**: Đọc socket bảng định tuyến qua lệnh `ss -tulpn` hoặc đọc `/proc/net/tcp`, trả về danh sách Port đang `LISTEN` (ví dụ: port 22, 80, 443).

- [x] **Chức năng 2.5: `execute_safe_command` (Thực thi lệnh Linux có bộ lọc an toàn)**
  - **Mô tả**: Cho phép AI chạy lệnh bash cần thiết nhưng có cơ chế **chặn lệnh nguy hiểm (Command Blacklist)** để chống phá hoại hệ thống.
  - **Kỹ thuật C++**: Kiểm tra chuỗi đầu vào, chặn các mẫu nguy hiểm (`rm -rf`, `mkfs`, `:(){ :|:& };:`, `dd if=`), nếu an toàn mới cấp quyền thực thi qua `popen()`.

---

### NHÓM 3: Giao Diện Tương Tác & Cầu Nối AI (Agent Controller & Demo UI)
*Mục tiêu: Đưa bộ não AI vào để điều khiển file C++ và tạo giao diện demo mượt mà.*

- [x] **Chức năng 3.1: AI Agent Client (Cầu nối)**
  - Một script chạy siêu nhẹ (kết nối API miễn phí của Google Gemini qua thư viện requests hoặc curl).
  - Nhận câu hỏi từ người dùng $\rightarrow$ Gửi lên Gemini $\rightarrow$ Gemini trả về yêu cầu: *"Hãy gọi tool get_system_health"* $\rightarrow$ Client đẩy lệnh vào `stdin` của file C++ $\rightarrow$ Nhận kết quả từ `stdout` của C++ gửi lại cho Gemini tóm tắt.

- [x] **Chức năng 3.2: Giao diện Chat Dòng Lệnh (Interactive Terminal UI)**
  - Mở một khung chat terminal trực tiếp:
    ```
    VKU-AI-Agent> Hãy kiểm tra xem Nginx có đang chạy không?
    [AI] Đang gọi C++ MCP Tool: manage_service(service="nginx", action="status")...
    [C++ MCP] Status: Active (Running)
    [AI] Dạ thưa bạn, dịch vụ NGINX trên máy chủ Ubuntu đang hoạt động bình thường!
    ```

---

### NHÓM 4: Đóng Gói & Tự Động Hóa (Build System)

- [x] **Chức năng 4.1: `Makefile`**:
  - Biên dịch toàn bộ mã nguồn C++ với cờ tối ưu hóa:
    `g++ -O3 -std=c++17 src/vku_mcp_server.cpp -Iinclude -o bin/vku_mcp_server`
- [x] **Chức năng 4.2: Script Demo 1-Click (`run_agent.sh`)**:
  - Tự động kiểm tra toolchain `g++`, biên dịch file C++, khởi động phiên làm việc tương tác với AI Agent để trình diễn trước thầy.
