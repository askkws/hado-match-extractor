#!/usr/bin/env python3
"""
HADO Match Extractor - Desktop App Entry Point
Starts FastAPI in a background thread, then opens a PyWebView window.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request

if sys.platform != 'darwin':
    import tkinter as tk
    from tkinter import filedialog

import uvicorn
import webview


def _find_free_port() -> int:
    """Find an available TCP port."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(host: str, port: int, timeout: float = 15.0) -> bool:
    """Block until the given port is accepting connections."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


class Api:
    """Python API exposed to the WebView via window.pywebview.api.*"""

    def __init__(self, port: int):
        self._port = port

    def pick_file(self):
        """Open a native file picker and return selected file info."""
        try:
            if sys.platform == 'darwin':
                result = subprocess.run(
                    [
                        'osascript', '-e',
                        'POSIX path of (choose file of type {"mp4", "mov"}'
                        ' with prompt "動画を選択してください")',
                    ],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    path = result.stdout.strip()
                    if path and os.path.exists(path):
                        return {
                            'path': path,
                            'name': os.path.basename(path),
                            'size': os.path.getsize(path),
                        }
            else:
                # Windows: tkinter file dialog
                root = tk.Tk()
                root.withdraw()
                root.attributes('-topmost', True)
                path = filedialog.askopenfilename(
                    title="動画を選択してください",
                    filetypes=[
                        ("動画ファイル", "*.mp4 *.mov"),
                        ("すべてのファイル", "*.*"),
                    ],
                )
                root.destroy()
                if path and os.path.exists(path):
                    return {
                        'path': path,
                        'name': os.path.basename(path),
                        'size': os.path.getsize(path),
                    }
        except Exception as e:
            print(f'pick_file error: {e}', file=sys.stderr, flush=True)
        return None

    def download_file(self, job_id, filename):
        """Save an output file to a user-selected location via native save dialog."""
        try:
            # Get the server-side file path
            url = f'http://127.0.0.1:{self._port}/output_path/{job_id}/{filename}'
            with urllib.request.urlopen(url) as resp:
                data = json.loads(resp.read())
            src_path = data['path']

            if sys.platform == 'darwin':
                # macOS: native save dialog via osascript
                result = subprocess.run(
                    [
                        'osascript', '-e',
                        f'POSIX path of (choose file name'
                        f' with prompt "保存先を選択してください"'
                        f' default name "{filename}")',
                    ],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    return None  # user cancelled
                save_path = result.stdout.strip()
            else:
                # Windows: tkinter save dialog
                root = tk.Tk()
                root.withdraw()
                root.attributes('-topmost', True)
                save_path = filedialog.asksaveasfilename(
                    title="保存先を選択してください",
                    defaultextension=".mp4",
                    initialfile=filename,
                    filetypes=[("MP4ファイル", "*.mp4")],
                )
                root.destroy()
                if not save_path:
                    return None  # user cancelled

            if os.path.exists(save_path):
                os.remove(save_path)
            shutil.copy2(src_path, save_path)
            return {'path': save_path}
        except Exception as e:
            print(f'download_file error: {e}', file=sys.stderr, flush=True)
            return {'error': str(e)}


def main():
    # PyInstaller frozen exe: change cwd to exe directory
    if getattr(sys, 'frozen', False):
        os.chdir(os.path.dirname(sys.executable))

    port = _find_free_port()

    # Direct import for PyInstaller compatibility (string "app:app" won't resolve in frozen exe)
    from app import app as fastapi_app

    # Start FastAPI/uvicorn in a daemon thread
    config = uvicorn.Config(
        fastapi_app,
        host="127.0.0.1",
        port=port,
        timeout_keep_alive=300,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for the server to be ready
    if not _wait_for_port("127.0.0.1", port):
        print("ERROR: server did not start in time", file=sys.stderr)
        sys.exit(1)

    # Open the native window (blocks until closed)
    api = Api(port)
    webview.create_window(
        "HADO Match Extractor",
        f"http://127.0.0.1:{port}",
        js_api=api,
        width=520,
        height=820,
        min_size=(400, 600),
        resizable=True,
    )
    webview.start()
    # Daemon thread exits automatically when the window is closed


if __name__ == "__main__":
    main()
