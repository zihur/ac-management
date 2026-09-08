import os
import sys
import threading
import subprocess
import platform
import webbrowser
import uvicorn

# 1. 解決 PyInstaller 打包後 templates 模板路徑問題
if getattr(sys, "frozen", False):
    base_dir = sys._MEIPASS
    os.chdir(base_dir)

from main import app

def open_browser():
    url = "http://127.0.0.1:8000"
    
    # 特殊處理：如果在 WSL 環境下，呼叫 Windows 本機指令開啟瀏覽器
    if "microsoft-standard" in platform.release().lower() or "wsl" in platform.release().lower():
        try:
            subprocess.run(["cmd.exe", "/c", "start", url], check=True)
            return
        except Exception:
            pass
            
    # 一般 Mac / Linux / 原生 Windows 環境
    webbrowser.open(url)

if __name__ == "__main__":
    threading.Timer(1.5, open_browser).start()
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")