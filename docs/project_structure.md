# CẤU TRÚC THƯ MỤC & CHI TIẾT TÁC DỤNG TỪNG FILE
## Đề tài: Build and Configure an MCP Server for Agentic AI in Linux
**Môn học:** Linux & Phần mềm mã nguồn mở (Linux OSS 2026 - VKU)  
**Sinh viên thực hiện:** Trần Duy Đức Anh (Mã SV: 24IT009) & Nhóm

---

## 1. CÂY THƯ MỤC TỔNG THỂ DỰ ÁN (PROJECT DIRECTORY TREE)

```
Linux-Final/
│
├── .gitignore                           # Danh sách các file/folder bỏ qua không đẩy lên Git
├── .vscode/                             # Cấu hình môi trường phát triển trên VS Code
│   └── sftp.json                        # Cấu hình tự động đồng bộ file qua SFTP (port 2222)
│
├── bin/                                 # Chứa file thực thi nhị phân sau khi biên dịch C++
│   ├── vku_mcp_server                   # Binary chạy trên máy ảo Ubuntu Linux (~1.4 MB)
│   └── vku_mcp_server.exe               # Binary chạy thử nghiệm trên Windows (~837 KB)
│
├── client/                              # Tầng Trợ lý AI và các giao diện người dùng (UX/UI)
│   ├── agent_cli.py                     # Bộ điều khiển AI Agent & giao diện chat Terminal
│   ├── test_mcp_direct.py               # Bộ kiểm thử tự động 6/6 test cases giao thức MCP
│   └── web_ui.py                        # Server giao diện Web Dashboard UI (Port 8080)
│
├── docs/                                # Hồ sơ học thuật, tài liệu kiến trúc & báo cáo
│   ├── architecture.md                  # Bản vẽ kiến trúc hệ thống & đặc tả giao thức MCP
│   ├── features_summary.md              # Bảng tóm tắt toàn bộ chức năng dự án
│   ├── final_report_en.md               # Báo cáo cuối kỳ 5 chương bằng 100% Tiếng Anh
│   ├── presentation_slides_en.md        # Dàn ý 15 slide thuyết trình bằng Tiếng Anh
│   ├── project_structure.md             # Tài liệu này (Giải thích cấu trúc thư mục & file)
│   └── topic15_features_plan.md         # Bản đặc tả kỹ thuật các chức năng đã xây dựng
│
├── include/                             # Thư viện ngoài phụ thuộc (Header-only libraries)
│   └── nlohmann/
│       └── json.hpp                     # Thư viện JSON-RPC 2.0 chuẩn quốc tế của C++
│
├── scripts/                             # Các Bash script hỗ trợ vận hành tự động trên Linux
│   ├── build.sh                         # Script gọi Makefile để biên dịch file C++
│   ├── run_demo.sh                      # Script khởi chạy nhanh giao diện chat Terminal
│   ├── run_web_ui.sh                    # Script khởi chạy nhanh giao diện Web Dashboard
│   └── setup_env.sh                     # Script cài đặt g++, make, python3 trên Ubuntu
│
├── src/                                 # Mã nguồn C++17 nguyên bản (Lõi của toàn bộ dự án)
│   ├── log_tools.hpp                    # Module C++ đọc và phân tích nhật ký hệ thống
│   ├── main.cpp                         # Điểm vào chương trình C++ (Vòng lặp stdin/stdout)
│   ├── mcp_server.hpp                   # Lõi giao thức MCP: initialize, tools/list, tools/call
│   ├── security_sandbox.hpp             # Hộp cát bảo mật: Blacklist chặn lệnh phá hoại & quét port
│   ├── service_tools.hpp                # Module C++ quản lý Systemd daemons (nginx, ssh, ufw)
│   └── system_tools.hpp                 # Module C++ gọi sysinfo(), statvfs(), /proc/loadavg
│
├── systemd/                             # Tích hợp chạy nền dạng Linux Daemon
│   └── vku-mcp.service                  # File cấu hình service unit để Ubuntu quản lý
│
├── Makefile                             # File cấu hình biên dịch tự động của trình biên dịch GNU Make
├── README.md                            # Tài liệu hướng dẫn sử dụng tổng quan chuẩn GitHub
├── setup_and_build.sh                   # Script gốc 1-Click: Cài toolchain và biên dịch C++
└── demo_verify.sh                       # Script gốc 1-Click: Chạy test tự động và mở Web UI
```

---

## 2. PHÂN TÍCH TÁC DỤNG CỦA TỪNG THƯ MỤC (FOLDERS)

| Thư mục | Vai trò và Mục đích kỹ thuật |
| :--- | :--- |
| **`.vscode/`** | Chứa file cấu hình kết nối của VS Code. Giúp lập trình viên chỉ cần gõ code bên Windows, bấm `Ctrl + S` là file tự động được đẩy sang máy ảo Ubuntu qua cổng SSH `2222` mà không cần copy thủ công. |
| **`bin/`** | Thư mục đầu ra (build output) chứa các file nhị phân sau khi biên dịch từ C++. File thực thi này là standalone (chạy độc lập, không cần cài đặt thêm thư viện runtime). |
| **`client/`** | Chứa toàn bộ tầng ứng dụng phía người dùng viết bằng Python siêu nhẹ: kết nối AI, kiểm thử tự động, giao diện dòng lệnh và web dashboard. |
| **`docs/`** | Trung tâm tài liệu học thuật hoàn chỉnh của đồ án: báo cáo tiếng Anh chuẩn ĐACS 3, 4, slide thuyết trình, sơ đồ kiến trúc và các bản đặc tả chức năng. |
| **`include/`** | Chứa các file header C++ của bên thứ ba. Ở đây dự án sử dụng `nlohmann/json.hpp` (thư viện JSON số 1 thế giới cho C++). |
| **`scripts/`** | Bộ công cụ tự động hóa Linux (Automation Shell Scripts) giúp người dùng thực hiện cài đặt, build và chạy demo chỉ với một dòng lệnh duy nhất. |
| **`src/`** | **Trái tim của dự án**. Toàn bộ mã nguồn C++17 Native POSIX thực hiện giao thức Model Context Protocol và tương tác trực tiếp với nhân hệ điều hành Ubuntu. |
| **`systemd/`** | Chứa cấu hình dịch vụ chuẩn Linux để server C++ có thể tự động khởi động cùng hệ điều hành hoặc chạy nền liên tục. |

---

## 3. BẢNG TRA CỨU CHI TIẾT TỪNG FILE TRONG DỰ ÁN

### 3.1 Nhóm File Gốc (Root Files)
| Tên File | Định dạng | Tác dụng chi tiết |
| :--- | :---: | :--- |
| **`demo_verify.sh`** | Bash Script | **File chính dùng để trình diễn trước giảng viên**. Tự động chạy 6 bài test giao thức JSON-RPC, sau đó cung cấp menu chọn mở Web Dashboard hoặc Terminal CLI. |
| **`setup_and_build.sh`** | Bash Script | **File cài đặt trọn gói 1-Click**. Tự động cài đặt `build-essential`, `g++`, `make`, `python3` và gọi lệnh `make` biên dịch ra file thực thi nhị phân. |
| **`Makefile`** | GNU Make | Định nghĩa quy trình biên dịch C++17 với cờ tối ưu hóa `-O3`, cảnh báo `-Wall -Wextra`, và cờ `strip` giúp giảm kích thước file chạy xuống mức tối thiểu (~1.4 MB). |
| **`README.md`** | Markdown | Tài liệu hướng dẫn sử dụng toàn diện dự án chuẩn GitHub: tổng quan, kiến trúc, bảng so sánh hiệu năng và hướng dẫn cài đặt từng bước. |
| **`.gitignore`** | Git Config | Quy định các file rác, file nhị phân (`bin/`, `*.exe`, `__pycache__/`) không bị đẩy lên GitHub khi làm việc nhóm. |

---

### 3.2 Nhóm File Mã Nguồn C++ (`src/`)
| Tên File | Định dạng | Tác dụng chi tiết |
| :--- | :---: | :--- |
| **`src/main.cpp`** | C++ Source | Điểm vào (`main()`) của server. Đọc dữ liệu từ `std::cin`, chuyển cho bộ định tuyến xử lý, bắt lỗi ngoại lệ (`try-catch`) và đẩy kết quả ra `std::cout`. |
| **`src/mcp_server.hpp`** | C++ Header | Lõi giao thức MCP. Khai báo danh sách Schema của 5 công cụ (`tools/list`), xử lý bắt tay (`initialize`), và định tuyến gọi hàm (`tools/call`). |
| **`src/system_tools.hpp`** | C++ Header | Chứa các hàm C++ gọi trực tiếp system call của nhân Linux: `sysinfo()` để lấy thông số RAM, `statvfs()` để đo dung lượng ổ cứng, đọc `/proc/loadavg` để lấy CPU load. |
| **`src/service_tools.hpp`** | C++ Header | Chứa các hàm C++ tương tác với tiến trình quản lý dịch vụ `systemctl` (start, stop, restart, status) kèm bộ lọc Regex chống lỗi chèn lệnh. |
| **`src/log_tools.hpp`** | C++ Header | Chứa các hàm C++ mở và đọc an toàn các dòng log cuối cùng từ `journalctl` và `/var/log` với giới hạn bộ đệm để tránh tràn RAM. |
| **`src/security_sandbox.hpp`** | C++ Header | Hiện thực hóa Hộp cát bảo mật: Blacklist chặn các lệnh phá hoại hệ thống (`rm -rf`, `mkfs`, fork bomb) và hàm quét socket cổng mạng đang mở (`ss -tulpn`). |

---

### 3.3 Nhóm File Phía Client & Giao Diện (`client/`)
| Tên File | Định dạng | Tác dụng chi tiết |
| :--- | :---: | :--- |
| **`client/web_ui.py`** | Python 3 | Khởi chạy một Web Server siêu nhẹ trên cổng **8080**, phục vụ giao diện Web Dashboard Glassmorphic, cung cấp API lấy dữ liệu phần cứng (`/api/telemetry`) và API chat AI (`/api/chat`). |
| **`client/agent_cli.py`** | Python 3 | Bộ điều khiển Trợ lý AI (Agent Controller). Kết nối hai chiều với tiến trình C++ qua pipe (`stdin`/`stdout`), hỗ trợ cả chế độ Cloud AI (Google Gemini API) và bộ suy luận Offline tự hành. |
| **`client/test_mcp_direct.py`** | Python 3 | Bộ kịch bản kiểm thử tự động 6 bài test theo chuẩn MCP. Gửi trực tiếp các gói tin JSON-RPC vào file C++ và xác thực tính đúng đắn của dữ liệu trả về. |

---

### 3.4 Nhóm File Hỗ Trợ Khác (`scripts/`, `systemd/`, `.vscode/`)
| Tên File | Định dạng | Tác dụng chi tiết |
| :--- | :---: | :--- |
| **`scripts/setup_env.sh`** | Bash Script | Cài đặt tự động các gói phần mềm cần thiết trên Ubuntu: `build-essential`, `g++`, `make`, `python3`, `curl`. |
| **`scripts/build.sh`** | Bash Script | Di chuyển vào thư mục dự án và kích hoạt `make all` để biên dịch binary. |
| **`scripts/run_web_ui.sh`** | Bash Script | Khởi chạy nhanh máy chủ Web Dashboard trên cổng 8080. |
| **`scripts/run_demo.sh`** | Bash Script | Khởi chạy nhanh phiên làm việc chat AI trên Terminal. |
| **`systemd/vku-mcp.service`**| Systemd Unit | Cấu hình cho phép máy chủ Ubuntu quản lý server C++ MCP như một dịch vụ chạy nền liên tục. |
| **`.vscode/sftp.json`** | JSON | Cấu hình tiện ích mở rộng SFTP của VS Code để đồng bộ hóa mã nguồn sang Ubuntu qua port `2222`. |

---

## 4. SƠ ĐỒ LUỒNG DỮ LIỆU HOẠT ĐỘNG (DATA FLOW DIAGRAM)

Dưới đây là cách các file phối hợp nhịp nhàng với nhau khi người dùng gửi một yêu cầu:

```
[Người dùng gõ lệnh trên Web Dashboard: http://localhost:8080]
                        │
                        ▼ (HTTP POST /api/chat)
                 [client/web_ui.py]
                        │
                        ▼ (Gọi bộ điều khiển AI)
                [client/agent_cli.py]
                        │
                        ▼ (Gửi bản tin JSON-RPC 2.0 qua Standard Input)
                 [bin/vku_mcp_server]
                        │
                        ├─► [src/main.cpp] (Đọc chuỗi JSON từ cin)
                        │
                        ├─► [src/mcp_server.hpp] (Định tuyến tới công cụ cần chạy)
                        │
                        ├─► [src/system_tools.hpp] (Gọi sysinfo, statvfs, /proc)
                        ├─► [src/service_tools.hpp] (Thao tác systemctl dịch vụ)
                        └─► [src/security_sandbox.hpp] (Kiểm tra chặn lệnh nguy hiểm)
                        │
                        ▼ (Xuất kết quả JSON-RPC chuẩn qua Standard Output)
                [client/agent_cli.py] (AI nhận kết quả & tổng hợp câu trả lời)
                        │
                        ▼ (Trả kết quả JSON qua HTTP Response)
                 [client/web_ui.py]
                        │
                        ▼ (Cập nhật giao diện và vẽ lại đồ thị)
        [Màn hình Web hiển thị câu trả lời và gói tin MCP Inspector]
```
