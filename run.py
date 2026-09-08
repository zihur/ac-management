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

# 桌面版啟用心跳自動關閉；Docker 等環境不設定此變數即維持關閉
os.environ.setdefault("ENABLE_HEARTBEAT", "1")

from main import app, register_shutdown, start_heartbeat_monitor

# 指定通訊埠
TARGET_PORT = 8501

config = uvicorn.Config(
    app,
    host="127.0.0.1",
    port=TARGET_PORT,
    log_config=None,
    use_colors=False,
)
server = uvicorn.Server(config)
register_shutdown(lambda: setattr(server, "should_exit", True))


def open_browser():
    """伺服器啟動後自動打開瀏覽器"""
    webbrowser.open(f"http://127.0.0.1:{TARGET_PORT}")


if __name__ == "__main__":
    start_heartbeat_monitor()
    threading.Timer(1.5, open_browser).start()
    server.run()