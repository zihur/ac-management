# 📄 技術需求規格書 (RFC)：冷氣管理系統打包桌面端執行檔 (.exe)

**文件狀態**：草案 / 待實作 (Draft)

**目標使用者**：現場維修/管理人員（免安裝 Docker、免設定 Python 環境，一鍵開箱即用）

---

### 一、 需求目標 (Objective)

將目前的 **FastAPI + SQLite + Jinja2** 專案，編譯打包為 Windows 單一可執行檔 (`.exe`)。
使用者下載後雙擊執行，系統須自動：

1. 在背景啟動 Uvicorn 輕量 Web 伺服器。
2. 自動建立/掛載同目錄下的 `air_conditioner.db` 資料庫。
3. 自動調用系統預設瀏覽器，打開 `[http://127.0.0.1:8000](http://127.0.0.1:8000)` 進入操作介面。

---

### 二、 技術方案與工具鏈 (Tech Stack)

* **打包核心工具**：`PyInstaller` (或 `Nuitka`)
* **自動瀏覽器喚醒**：Python 內建 `webbrowser` 與 `threading` 模組
* **CI/CD 自動化建置**：`GitHub Actions` (Windows Runner)

---

### 三、 預計實作步驟 (Implementation Steps)

#### 1. 建立入口程式 `run.py`

在專案根目錄新增啟動腳本，負責處理伺服器啟動與自動開啟瀏覽器邏輯：

```python
import threading
import sys
import os
import webbrowser
import uvicorn
from main import app

def open_browser():
    # 等待 Uvicorn 啟動後，自動開啟瀏覽器
    webbrowser.open("http://127.0.0.1:8000")

if __name__ == "__main__":
    # 解決 PyInstaller 打包後靜態檔案/模板路徑問題
    if getattr(sys, 'frozen', False):
        os.chdir(sys._MEIPASS)

    # 1.5 秒後呼叫瀏覽器
    threading.Timer(1.5, open_browser).start()
    
    # 啟動 Uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="error")

```

#### 2. 本地打包指令 (Windows 環境)

```bash
uv pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --add-data "templates;templates" --name "AC_Management" run.py

```

#### 3. 設定 GitHub Actions 自動編譯 (.github/workflows/build-exe.yml)

為解決 Mac 無法直接編譯 Windows `.exe` 的限制，建立 GitHub Workflow：

* 當推送 `tag` 或 `release` 時，觸發 Windows 雲端 VM。
* 自動執行 `PyInstaller` 編譯。
* 自動將產出的 `AC_Management.exe` 上傳至 GitHub Releases 供免費下載。

---

### 四、 資料備份與安全性考量 (Data & Backup)

* **資料庫存取**：`.exe` 執行時，`air_conditioner.db` 會生成於與 `.exe` 同級的資料夾內。
* **資料轉移/備份**：若需換電腦或備份資料，僅需將同目錄下的 `air_conditioner.db` 複製帶走即可。

---

這份文件已幫你建立完成！未來隨時想回頭接續進行這個功能時，只要跟我說一聲，我們就可以隨時開始撰寫 `run.py` 或設定 GitHub Actions 囉！