# 📖 Hướng Dẫn Cài Đặt Qwen 2.5 LLM & Cấu Hình Alias Quản Lý

Tài liệu này hướng dẫn chi tiết cách cài đặt **Ollama**, tải mô hình ngôn ngữ lớn **Qwen 2.5 (Offline)** và cấu hình bộ phím tắt (**alias**) trên hệ điều hành Linux (Ubuntu / Debian / Fedora) để phục vụ dự án MCP Server hoặc nghiên cứu AI cục bộ.

---

## 📌 1. Giới thiệu tổng quan

* **Ollama**: Nền tảng quản lý và chạy mô hình AI cục bộ (Local LLM) mã nguồn mở, tối ưu cho CPU và GPU, cung cấp sẵn REST API tại cổng `11434`.
* **Qwen 2.5**: Mô hình AI của Alibaba, có khả năng hiểu và phản hồi Tiếng Việt cực kỳ xuất sắc, nắm vững kiến thức quản trị hệ thống Linux và lập trình.
* **Qwen 2.5:1.5B (Khuyên dùng)**: Dung lượng chỉ ~986 MB, chiếm khoảng 1.5 - 2GB RAM khi chạy, tốc độ phản hồi trên CPU máy ảo rất mượt và chuẩn xác.

---

## 🚀 2. Các bước cài đặt chi tiết

### Bước 1: Cài đặt Ollama vào hệ thống

Mở terminal trên máy Linux (hoặc SSH vào máy ảo Ubuntu) và chạy lệnh cài đặt chính thức:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

> **Ghi chú**: Lệnh trên sẽ tự động tải binary, cấu hình biến môi trường và tạo dịch vụ hệ thống `ollama.service` tự chạy ngầm cùng OS.

Kiểm tra dịch vụ Ollama xem đã hoạt động chưa:
```bash
systemctl status ollama
```
*(Nếu thấy dòng màu xanh `active (running)` là đã thành công! Nhấn phím `q` để thoát màn hình status).*

---

### Bước 2: Tải mô hình Qwen 2.5 về máy

Tùy vào cấu hình phần cứng (RAM / CPU) của máy bạn, chọn phiên bản phù hợp:

| Phiên bản | Dung lượng tải | Yêu cầu RAM tối thiểu | Đánh giá sử dụng |
| :--- | :--- | :--- | :--- |
| **`qwen2.5:1.5b`** *(Khuyên dùng)* | **~986 MB** | **>= 2 GB** | Tiếng Việt rất chuẩn, phân tích log/RAM thông minh, chạy nhanh trên CPU. |
| **`qwen2.5:0.5b`** | ~397 MB | >= 1 GB | Siêu nhẹ cho máy cấu hình cực yếu, tiếng Việt cơ bản. |
| **`qwen2.5:7b`** | ~4.7 GB | >= 8 GB | Cực kỳ thông minh, cần máy có RAM lớn hoặc card đồ họa rời (GPU). |

#### Lệnh tải bản 1.5B (Khuyên dùng cho dự án):
```bash
ollama pull qwen2.5:1.5b
```

#### (Tùy chọn) Tải thêm bản siêu nhẹ 0.5B dự phòng:
```bash
ollama pull qwen2.5:0.5b
```

Kiểm tra danh sách mô hình đã tải thành công:
```bash
ollama list
```

---

### Bước 3: Thử nghiệm trò chuyện với Qwen trong Terminal

Bạn có thể trò chuyện trực tiếp với Qwen ngay trong terminal bằng lệnh:

```bash
ollama run qwen2.5:1.5b
```

* Bạn có thể gõ câu hỏi bằng Tiếng Việt (Ví dụ: *"Kiểm tra dung lượng ổ đĩa trên Linux dùng lệnh gì?"*).
* Để **thoát** khỏi màn hình chat, gõ `/bye` và nhấn **Enter** (hoặc nhấn tổ hợp phím `Ctrl + D`).

---

## ⚡ 3. Cài đặt bộ Alias quản lý dịch vụ (`serverQwen`, `stopQwen`, `statusQwen`)

Mặc định Ollama chạy dưới dạng daemon hệ thống. Để thuận tiện bật/tắt và tiết kiệm tài nguyên RAM/CPU khi không sử dụng, hãy thêm bộ alias vào file cấu hình shell `~/.bashrc`.

### Cách cài nhanh (Copy & Paste nguyên khối lệnh):

Chạy toàn bộ đoạn lệnh sau vào terminal:

```bash
cat << 'EOF' >> ~/.bashrc

# ==========================================
# VKU OSS - Qwen LLM Service Management
# ==========================================
alias serverQwen='sudo systemctl start ollama && echo -e "\e[32m[OK] Dịch vụ Qwen LLM (Ollama) đã được KHỞI ĐỘNG thành công!\e[0m"'
alias stopQwen='sudo systemctl stop ollama && echo -e "\e[33m[OK] Dịch vụ Qwen LLM (Ollama) đã được DỪNG (Giải phóng RAM/CPU)!\e[0m"'
alias statusQwen='systemctl status ollama'
# ==========================================
EOF
source ~/.bashrc
```

### Cách sử dụng các lệnh vừa tạo:

* **Bật dịch vụ Qwen**:
  ```bash
  serverQwen
  ```
* **Tắt dịch vụ Qwen** *(khi muốn giải phóng RAM/CPU cho các tác vụ khác)*:
  ```bash
  stopQwen
  ```
* **Kiểm tra trạng thái server**:
  ```bash
  statusQwen
  ```

---

## 🌐 4. Kiểm tra kết nối API cục bộ (Dành cho MCP Controller / Web UI)

Ollama lắng nghe tại địa chỉ `http://127.0.0.1:11434`. Bạn có thể kiểm tra xem API đã sẵn sàng phục vụ các ứng dụng khác chưa:

```bash
curl http://127.0.0.1:11434
```
👉 Nếu terminal trả về dòng chữ: `Ollama is running` tức là server đã hoạt động hoàn hảo!

Khi khởi chạy giao diện Web UI hoặc Agent CLI của dự án MCP Server:
```bash
python3 client/web_ui.py
# hoặc
./demo_verify.sh
```
Hệ thống sẽ tự động phát hiện server Qwen đang chạy ngầm và chuyển toàn bộ tính năng AI sang chế độ **100% Offline**.

---

## ❓ 5. Các câu hỏi thường gặp (FAQ)

### Q1: Tắt máy hoặc khởi động lại (Reboot) thì có phải tải lại model không?
* **Không.** Tất cả các model đã tải được lưu vĩnh viễn trên ổ cứng (tại `/usr/share/ollama/.ollama` hoặc `~/.ollama`).
* Khi bật lại máy, Ollama được cấu hình `enabled` theo mặc định của systemd nên sẽ **tự động khởi chạy ngầm**. Bạn không cần làm gì thêm!

### Q2: Muốn giải phóng ổ cứng, xóa bớt model không dùng thì làm thế nào?
Dùng lệnh `ollama rm <tên_model>`:
```bash
ollama rm qwen2.5:0.5b
```

### Q3: Nếu đang dùng zsh (hoặc Oh My Zsh) thay vì bash thì sao?
Chỉ cần đổi đường dẫn ghi cấu hình từ `~/.bashrc` sang `~/.zshrc`:
```bash
source ~/.zshrc
```

---
*Biên soạn bởi **VKU OSS Team / Topic 15 Research Team** - Dự án Native C++ Linux MCP Server.*

