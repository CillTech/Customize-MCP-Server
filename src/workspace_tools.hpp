#ifndef VKU_WORKSPACE_TOOLS_HPP
#define VKU_WORKSPACE_TOOLS_HPP

#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <nlohmann/json.hpp>
#include <sstream>
#include <string>
#include <vector>

#ifdef __linux__
#include <unistd.h>
#endif

#include "security_sandbox.hpp"

namespace vku::tools {

namespace fs = std::filesystem;
using json = nlohmann::json;

class WorkspaceTools {
private:
  // Xác định thư mục gốc duy nhất được phép thao tác: Customize-MCP-Server
  static bool get_workspace_root(fs::path &out_root, std::string &err) {
    const char *env_dir = std::getenv("VKU_WORKSPACE_DIR");
    if (env_dir && std::string(env_dir).size() > 0) {
      std::error_code ec;
      fs::path cand = fs::weakly_canonical(fs::path(env_dir), ec);
      if (!ec && fs::exists(cand, ec) && fs::is_directory(cand, ec)) {
        out_root = cand;
        return true;
      }
      err = "Configured VKU_WORKSPACE_DIR does not exist or is not a directory.";
      return false;
    }

    std::error_code ec;
    fs::path cwd = fs::current_path(ec);
    if (ec) {
      err = "Unable to read current working directory.";
      return false;
    }

    fs::path cand = cwd;
    while (!cand.empty()) {
      if (cand.filename() == "Customize-MCP-Server") {
        out_root = fs::weakly_canonical(cand, ec);
        if (!ec && fs::exists(out_root, ec) && fs::is_directory(out_root, ec)) {
          return true;
        }
      }
      if (cand == cand.parent_path()) {
        break;
      }
      cand = cand.parent_path();
    }

    fs::path sub = cwd / "Customize-MCP-Server";
    if (fs::exists(sub, ec) && fs::is_directory(sub, ec)) {
      out_root = fs::weakly_canonical(sub, ec);
      return true;
    }

    err = "Locked workspace folder 'Customize-MCP-Server' could not be resolved.";
    return false;
  }

  static bool is_within_root(const fs::path &root, const fs::path &target) {
    auto r_it = root.begin();
    auto t_it = target.begin();
    for (; r_it != root.end(); ++r_it, ++t_it) {
      if (t_it == target.end() || *r_it != *t_it) {
        return false;
      }
    }
    for (const auto &part : target) {
      if (part == "..") {
        return false;
      }
    }
    return true;
  }

  static bool is_protected_git_path(const fs::path &rel_path) {
    for (const auto &part : rel_path) {
      if (part == ".git") {
        return true;
      }
    }
    return false;
  }

  // Kiểm tra đường dẫn phải nằm gọn bên trong Customize-MCP-Server
  static bool resolve_in_workspace(const fs::path &root,
                                   const std::string &raw_path,
                                   fs::path &out_abs, fs::path &out_rel,
                                   std::string &err_reason) {
    if (raw_path.find('\0') != std::string::npos) {
      err_reason = "Null byte is forbidden in workspace path.";
      return false;
    }

    std::string trimmed = raw_path;
    while (!trimmed.empty() &&
           std::isspace(static_cast<unsigned char>(trimmed.front()))) {
      trimmed.erase(trimmed.begin());
    }
    while (!trimmed.empty() &&
           std::isspace(static_cast<unsigned char>(trimmed.back()))) {
      trimmed.pop_back();
    }

    fs::path cand;
    if (trimmed.empty() || trimmed == "." ||
        trimmed == "Customize-MCP-Server" ||
        trimmed == "Customize-MCP-Server/") {
      cand = root;
    } else if (trimmed.rfind("Customize-MCP-Server/", 0) == 0) {
      cand = root / trimmed.substr(std::string("Customize-MCP-Server/").size());
    } else {
      fs::path p(trimmed);
      cand = p.is_absolute() ? p : (root / p);
    }

    std::error_code ec;
    fs::path canon = fs::weakly_canonical(cand, ec);
    if (ec) {
      err_reason = "Failed to canonicalize path '" + raw_path + "'.";
      return false;
    }

    if (!is_within_root(root, canon)) {
      SecuritySandbox::write_audit_log("BLOCKED_WORKSPACE_ESCAPE", raw_path,
                                       "Resolved outside Customize-MCP-Server: " +
                                           canon.string());
      err_reason = "Path '" + raw_path +
                   "' escapes the permitted 'Customize-MCP-Server' workspace.";
      return false;
    }

    out_abs = canon;
    out_rel = fs::relative(canon, root, ec);
    if (ec || out_rel.empty()) {
      out_rel = ".";
    }
    return true;
  }

  static std::string to_lower_ext(const fs::path &p) {
    std::string ext = p.extension().string();
    std::transform(ext.begin(), ext.end(), ext.begin(), ::tolower);
    return ext;
  }

  static json list_directory_json(const fs::path &dir_abs,
                                  const fs::path &rel_dir) {
    json entries = json::array();
    std::error_code ec;
    for (const auto &entry : fs::directory_iterator(dir_abs, ec)) {
      std::string name = entry.path().filename().string();
      if (name == ".git") {
        continue;
      }
      bool is_dir = entry.is_directory(ec);
      unsigned long long size = 0;
      if (!is_dir) {
        size = entry.file_size(ec);
      }
      entries.push_back({{"name", name},
                         {"type", is_dir ? "dir" : "file"},
                         {"size_bytes", size}});
    }

    std::sort(entries.begin(), entries.end(), [](const json &a, const json &b) {
      if (a["type"] != b["type"]) {
        return a["type"] == "dir";
      }
      return a["name"].get<std::string>() < b["name"].get<std::string>();
    });

    return {{"success", true},
            {"allowed", true},
            {"action", "list_dir"},
            {"workspace", "Customize-MCP-Server"},
            {"path", rel_dir.string()},
            {"count", entries.size()},
            {"entries", entries}};
  }

public:
  // Tool 15: Quản lý file/folder và chạy script trong duy nhất thư mục
  // Customize-MCP-Server (kèm Sandbox duyệt nội dung file)
  static json manage_workspace(const std::string &action,
                               const std::string &path = ".",
                               const std::string &content = "",
                               const std::vector<std::string> &run_args = {}) {
    fs::path root;
    std::string root_err;
    if (!get_workspace_root(root, root_err)) {
      return {{"success", false}, {"allowed", false}, {"error", root_err}};
    }

    const std::vector<std::string> valid_actions = {
        "list_dir", "read_file",   "create_dir", "create_file",
        "edit_file", "append_file", "delete",     "run_file"};
    if (std::find(valid_actions.begin(), valid_actions.end(), action) ==
        valid_actions.end()) {
      return {{"success", false},
              {"allowed", false},
              {"error",
               "Invalid action. Supported: list_dir, read_file, create_dir, "
               "create_file, edit_file, append_file, delete, run_file."}};
    }

    fs::path target_abs;
    fs::path target_rel;
    std::string path_err;
    if (!resolve_in_workspace(root, path, target_abs, target_rel, path_err)) {
      return {{"success", false},
              {"allowed", false},
              {"violation", "OUTSIDE_WORKSPACE_SCOPE"},
              {"error", path_err}};
    }

    if (is_protected_git_path(target_rel)) {
      return {{"success", false},
              {"allowed", false},
              {"violation", "PROTECTED_GIT_DIRECTORY"},
              {"error", "Direct operations on '.git' internals are blocked."}};
    }

    std::error_code ec;

    // 1. Liệt kê thư mục
    if (action == "list_dir") {
      if (!fs::exists(target_abs, ec) || !fs::is_directory(target_abs, ec)) {
        return {{"success", false},
                {"allowed", true},
                {"error", "Directory does not exist inside Customize-MCP-Server: " +
                              target_rel.string()}};
      }
      SecuritySandbox::write_audit_log("WORKSPACE_LIST", target_rel.string(),
                                       "ok");
      return list_directory_json(target_abs, target_rel);
    }

    // 2. Đọc file
    if (action == "read_file") {
      if (target_rel == "." || !fs::exists(target_abs, ec) ||
          fs::is_directory(target_abs, ec)) {
        return {{"success", false},
                {"allowed", true},
                {"error", "File not found inside Customize-MCP-Server: " +
                              target_rel.string()}};
      }
      if (target_abs.filename() == ".env") {
        return {{"success", false},
                {"allowed", false},
                {"violation", "BLOCKED_BY_SANDBOX"},
                {"error", "Reading '.env' files is restricted by Sandbox."}};
      }
      std::ifstream ifs(target_abs, std::ios::binary);
      if (!ifs.is_open()) {
        return {{"success", false},
                {"allowed", true},
                {"error", "Unable to open file for reading."}};
      }
      std::string file_data((std::istreambuf_iterator<char>(ifs)),
                            std::istreambuf_iterator<char>());
      const size_t MAX_READ = 32768;
      bool truncated = false;
      if (file_data.size() > MAX_READ) {
        file_data.resize(MAX_READ);
        truncated = true;
      }
      SecuritySandbox::write_audit_log("WORKSPACE_READ", target_rel.string(),
                                       "bytes=" + std::to_string(file_data.size()));
      return {{"success", true},
              {"allowed", true},
              {"action", "read_file"},
              {"workspace", "Customize-MCP-Server"},
              {"path", target_rel.string()},
              {"truncated", truncated},
              {"content", file_data}};
    }

    // 3. Tạo thư mục
    if (action == "create_dir") {
      if (target_rel == ".") {
        return {{"success", false},
                {"allowed", true},
                {"error", "Please specify a subfolder name to create."}};
      }
      if (fs::exists(target_abs, ec) && !fs::is_directory(target_abs, ec)) {
        return {{"success", false},
                {"allowed", true},
                {"error", "A file already exists at path: " +
                              target_rel.string()}};
      }
      bool created = fs::create_directories(target_abs, ec);
      if (ec) {
        return {{"success", false},
                {"allowed", true},
                {"error", "Failed to create directory: " + ec.message()}};
      }
      SecuritySandbox::write_audit_log(
          "WORKSPACE_MKDIR", target_rel.string(),
          created ? "created" : "already_exists");
      return {{"success", true},
              {"allowed", true},
              {"action", "create_dir"},
              {"workspace", "Customize-MCP-Server"},
              {"path", target_rel.string()},
              {"created", created}};
    }

    // 4. Thêm file / Sửa file / Ghi thêm vào file (BẮT BUỘC duyệt nội dung qua Sandbox)
    if (action == "create_file" || action == "edit_file" ||
        action == "append_file") {
      if (target_rel == ".") {
        return {{"success", false},
                {"allowed", false},
                {"error", "Please provide a valid file path inside Customize-MCP-Server."}};
      }
      if (fs::is_directory(target_abs, ec)) {
        return {{"success", false},
                {"allowed", false},
                {"error", "Target path is a directory, not a file: " +
                              target_rel.string()}};
      }
      if (action == "edit_file" && !fs::exists(target_abs, ec)) {
        return {{"success", false},
                {"allowed", true},
                {"error", "File does not exist for editing (use create_file first): " +
                              target_rel.string()}};
      }

      // Kiểm tra chế độ chỉ đọc nếu bật
      const char *ro_env = std::getenv("VKU_READONLY_MODE");
      if (ro_env && std::string(ro_env) == "1") {
        return {{"success", false},
                {"allowed", false},
                {"content_approved", false},
                {"violation", "BLOCKED_BY_READONLY_MODE"},
                {"error", "File write is disabled while VKU_READONLY_MODE=1."}};
      }

      // Nếu append_file thì duyệt cả đoạn thêm vào LẪN toàn bộ nội dung sau khi nối
      std::string content_to_audit = content;
      if (action == "append_file" && fs::exists(target_abs, ec)) {
        std::ifstream existing_ifs(target_abs, std::ios::binary);
        std::string existing_data(
            (std::istreambuf_iterator<char>(existing_ifs)),
            std::istreambuf_iterator<char>());
        content_to_audit = existing_data + content;
      }

      json audit =
          SecuritySandbox::audit_file_content(content_to_audit, target_rel.string());
      if (!audit.value("approved", false)) {
        return {{"success", false},
                {"allowed", false},
                {"content_approved", false},
                {"action", action},
                {"workspace", "Customize-MCP-Server"},
                {"path", target_rel.string()},
                {"violation",
                 audit.value("violation", "BLOCKED_BY_CONTENT_SANDBOX")},
                {"error", audit.value("reason", "Rejected by content sandbox.")}};
      }

      if (target_abs.has_parent_path()) {
        fs::create_directories(target_abs.parent_path(), ec);
        if (ec) {
          return {{"success", false},
                  {"allowed", true},
                  {"error", "Failed to create parent directory: " + ec.message()}};
        }
      }

      std::ios::openmode mode =
          (action == "append_file") ? (std::ios::app | std::ios::binary)
                                    : (std::ios::trunc | std::ios::binary);
      std::ofstream ofs(target_abs, mode);
      if (!ofs.is_open()) {
        return {{"success", false},
                {"allowed", true},
                {"error", "Failed to open file for writing: " + target_rel.string()}};
      }
      ofs.write(content.data(), static_cast<std::streamsize>(content.size()));
      ofs.close();

      SecuritySandbox::write_audit_log("WORKSPACE_WRITE_" + action,
                                       target_rel.string(),
                                       "approved_bytes=" +
                                           std::to_string(content.size()));
      return {{"success", true},
              {"allowed", true},
              {"content_approved", true},
              {"content_audit", "APPROVED"},
              {"action", action},
              {"workspace", "Customize-MCP-Server"},
              {"path", target_rel.string()},
              {"bytes_written", content.size()}};
    }

    // 5. Xóa file hoặc thư mục bên trong Customize-MCP-Server
    if (action == "delete") {
      if (target_rel == ".") {
        return {{"success", false},
                {"allowed", false},
                {"violation", "BLOCKED_ROOT_DELETE"},
                {"error", "Deleting the root 'Customize-MCP-Server' folder is forbidden."}};
      }
      if (!fs::exists(target_abs, ec)) {
        return {{"success", false},
                {"allowed", true},
                {"error", "Target does not exist: " + target_rel.string()}};
      }
      std::uintmax_t removed_count = fs::remove_all(target_abs, ec);
      if (ec) {
        return {{"success", false},
                {"allowed", true},
                {"error", "Failed to delete target: " + ec.message()}};
      }
      SecuritySandbox::write_audit_log(
          "WORKSPACE_DELETE", target_rel.string(),
          "removed_items=" + std::to_string(removed_count));
      return {{"success", true},
              {"allowed", true},
              {"action", "delete"},
              {"workspace", "Customize-MCP-Server"},
              {"path", target_rel.string()},
              {"removed_items", removed_count}};
    }

    // 6. Chạy folder (liệt kê) hoặc chạy file script/binary an toàn bên trong
    // Customize-MCP-Server
    if (action == "run_file") {
      if (!fs::exists(target_abs, ec)) {
        return {{"success", false},
                {"allowed", true},
                {"error", "Target not found inside Customize-MCP-Server: " +
                              target_rel.string()}};
      }

      // Nếu người dùng truyền vào một thư mục -> mở/liệt kê các file bên trong
      if (fs::is_directory(target_abs, ec)) {
        json dir_info = list_directory_json(target_abs, target_rel);
        dir_info["action"] = "run_file (directory opened)";
        return dir_info;
      }

      std::string ext = to_lower_ext(target_abs);
      // Nếu là script văn bản -> kiểm tra nội dung qua Sandbox trước khi chạy
      if (ext == ".sh" || ext == ".py" || ext == ".bash") {
        std::ifstream ifs(target_abs, std::ios::binary);
        std::string script_body((std::istreambuf_iterator<char>(ifs)),
                                std::istreambuf_iterator<char>());
        json audit =
            SecuritySandbox::audit_file_content(script_body, target_rel.string());
        if (!audit.value("approved", false)) {
          return {{"success", false},
                  {"allowed", false},
                  {"content_approved", false},
                  {"action", "run_file"},
                  {"workspace", "Customize-MCP-Server"},
                  {"path", target_rel.string()},
                  {"violation",
                   audit.value("violation", "BLOCKED_BY_CONTENT_SANDBOX")},
                  {"error",
                   audit.value("reason", "Script content blocked by Sandbox.")}};
        }
      }

      std::vector<std::string> exec_args;
      if (ext == ".py") {
        exec_args.push_back("python3");
        exec_args.push_back(target_abs.string());
      } else if (ext == ".sh" || ext == ".bash") {
        exec_args.push_back("bash");
        exec_args.push_back(target_abs.string());
      } else {
#ifdef __linux__
        if (access(target_abs.c_str(), X_OK) != 0) {
          return {{"success", false},
                  {"allowed", false},
                  {"error",
                   "File is not executable and has unsupported extension "
                   "(supported: .py, .sh, or executable binary): " +
                       target_rel.string()}};
        }
#endif
        exec_args.push_back(target_abs.string());
      }

      for (const auto &arg : run_args) {
        if (arg.find_first_of(";&|`$><\n\r") != std::string::npos) {
          return {{"success", false},
                  {"allowed", false},
                  {"violation", "BLOCKED_BY_SANDBOX"},
                  {"error", "Execution argument contains forbidden shell characters."}};
        }
        exec_args.push_back(arg);
      }

      json exec_res = SecuritySandbox::run_exec_args(
          exec_args, "workspace_run:" + target_rel.string(), root.string());
      exec_res["action"] = "run_file";
      exec_res["workspace"] = "Customize-MCP-Server";
      exec_res["path"] = target_rel.string();
      return exec_res;
    }

    return {{"success", false}, {"error", "Unhandled workspace action."}};
  }
};

} // namespace vku::tools

#endif // VKU_WORKSPACE_TOOLS_HPP

