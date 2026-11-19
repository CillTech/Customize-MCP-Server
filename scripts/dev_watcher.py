#!/usr/bin/env python3
"""
==============================================================================
 VKU OSS 2026 - Real-time Hot Reload & Live Build Engine
 Watches src/, include/, client/ for modifications:
 - When C++ changes: triggers 'make', then restarts Web Server.
 - When Web UI changes: restarts Web Server.
 Browser automatically detects the restart and refreshes page via /api/version!
==============================================================================
"""

import os
import sys
import time
import subprocess

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCH_DIRS = [
    os.path.join(ROOT_DIR, "src"),
    os.path.join(ROOT_DIR, "include"),
    os.path.join(ROOT_DIR, "client"),
]

def get_file_mtimes():
    mtimes = {}
    for d in WATCH_DIRS:
        if not os.path.exists(d):
            continue
        for root, _, files in os.walk(d):
            for f in files:
                if f.endswith((".cpp", ".hpp", ".h", ".py", ".html", ".css", ".js")):
                    path = os.path.join(root, f)
                    try:
                        mtimes[path] = os.path.getmtime(path)
                    except OSError:
                        pass
    return mtimes

def build_cpp():
    print("\n[⚡ DEV WATCHER] Detected C++ code change! Recompiling with make...", flush=True)
    res = subprocess.run(["make"], cwd=ROOT_DIR)
    return res.returncode == 0

def main():
    print("======================================================================")
    print(" [VKU OSS 2026] LIVE RELOAD & AUTO-BUILD DEV MODE STARTED")
    print(" Watching directories: src/, include/, client/")
    print(" -> Just edit & save files on Fedora (Ctrl+S)!")
    print(" -> Auto recompile C++ & Live reload browser automatically!")
    print("======================================================================", flush=True)

    # Initial build if binary not present
    bin_path = os.path.join(ROOT_DIR, "bin", "vku_mcp_server")
    if not os.path.exists(bin_path):
        build_cpp()

    # Start web_ui.py
    web_proc = subprocess.Popen([sys.executable, os.path.join(ROOT_DIR, "client", "web_ui.py")])
    last_mtimes = get_file_mtimes()

    try:
        while True:
            time.sleep(0.8)
            current_mtimes = get_file_mtimes()

            changed_files = []
            for path, mtime in current_mtimes.items():
                if path not in last_mtimes or mtime > last_mtimes[path]:
                    changed_files.append(path)

            if changed_files:
                last_mtimes = current_mtimes
                cpp_changed = any(f.endswith((".cpp", ".hpp", ".h")) for f in changed_files)

                print(f"\n[⚡ CHANGE DETECTED] {len(changed_files)} file(s) modified:", flush=True)
                for f in changed_files:
                    print(f"  -> {os.path.relpath(f, ROOT_DIR)}", flush=True)

                if cpp_changed:
                    success = build_cpp()
                    if not success:
                        print("[❌ BUILD FAILED] Compilation error! Fix syntax to reload.", flush=True)
                        continue

                # Restart web_ui process
                print("[🔄 RESTARTING SERVER] Restarting Web Dashboard...", flush=True)
                if web_proc.poll() is None:
                    web_proc.terminate()
                    try:
                        web_proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        web_proc.kill()

                # Start fresh web_ui process
                web_proc = subprocess.Popen([sys.executable, os.path.join(ROOT_DIR, "client", "web_ui.py")])
                print("[✅ LIVE] Server reloaded! Browser will auto-refresh.\n", flush=True)

    except KeyboardInterrupt:
        print("\n[!] Stopping Dev Watcher...", flush=True)
        if web_proc.poll() is None:
            web_proc.terminate()
        sys.exit(0)

if __name__ == "__main__":
    main()

