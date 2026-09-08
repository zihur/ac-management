import os
import sys
import threading
import webbrowser
import uvicorn

# 1. 解決 --windowed 模式下 sys.stdout/stderr 為 None 的 Bug
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

# 2. 解決 PyInstaller 打包後 templates 模板路徑問題
if getattr(sys, "frozen", False):
    base_dir = sys._MEIPASS
    os.chdir(base_dir)

from main import app

# 指定通訊埠
TARGET_PORT = 8501


def open_browser():
    """伺服器啟動後自動打開瀏覽器"""
    webbrowser.open(f"http://127.0.0.1:{TARGET_PORT}")


if __name__ == "__main__":
    threading.Timer(1.5, open_browser).start()

    # 🌟 關鍵修正：加上 log_config=None 以及 color_log=False 避免抓取 isatty
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=TARGET_PORT,
        log_config=None,
        use_colors=False,
    )