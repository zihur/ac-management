import os
import sys
import threading
import webbrowser
import uvicorn

# 解決 PyInstaller 打包後 templates 模板路徑問題
if getattr(sys, "frozen", False):
    base_dir = sys._MEIPASS
    os.chdir(base_dir)

from main import app

# 🌟 在這裡指定你想要使用的 Port
TARGET_PORT = 8501


def open_browser():
    """伺服器啟動後自動打開瀏覽器"""
    webbrowser.open(f"http://127.0.0.1:{TARGET_PORT}")


if __name__ == "__main__":
    threading.Timer(1.5, open_browser).start()
    # 🌟 將 uvicorn 的 port 參數同步修改
    uvicorn.run(app, host="127.0.0.1", port=TARGET_PORT, log_level="error")