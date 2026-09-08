# ❄️ 冷氣型號與相關資訊管理系統 (AC Management System)

這是一個基於 **FastAPI** 與 **Docker** 打造的冷氣型號快速建立與檢索系統。本專案專為協助冷氣從業人員（家人）快速建立、搜尋冷氣型號規格及相關維修資訊而開發，旨在提升日常工作效率，同時作為邁向未來 **AI 應用（如 RAG 知識庫與 LLM 檢索）** 的前哨站。

---

## 📌 專案背景與開發初衷

* **解決實際痛點**：在冷氣裝修與維修現場，經常需要迅速查詢特定品牌與型號的冷房能力、冷媒規格或維修備註。傳統的紙本或散亂記錄效率較低，因此開發此系統提供一個直覺、快速的檢索介面。
* **技術能力提升**：藉由實作此 Side Project，熟悉現代化 Python 全棧開發流程，包含 RESTful API 設計、資料庫 CRUD 操作以及 Jinja2 模板渲染。
* **接軌 AI 應用**：本系統設計初衷即考慮到未來擴充性，後續規劃引入 **AI 向量資料庫（Vector Database）** 與 **大語言模型 (LLM)**，將非結構化的冷氣故障手冊（PDF）升級為智慧對話式檢索助手。

---

## 🛠️ 技術選型與架構 (Tech Stack)

* **後端框架**：[FastAPI](https://fastapi.tiangolo.com/) - 高效能、自動生成 OpenAPI (Swagger) 文件、原生支援數據驗證。
* **資料庫**：SQLite - 輕量級關聯式資料庫，無需複雜設定，適合快速開發與資料移植。
* **前端視圖**：HTML5 + Jinja2 模板引擎 - 輕量無負擔，提供極佳的使用者體驗。
* **容器化環境**：[Docker](https://www.docker.com/) - 保持開發環境絕對乾淨，達到「零本機 Python 依賴」與跨平台一緻性。

---

## 🚀 快速啟動指南 (Quick Start)

本專案採用 **純 Docker 環境開發**，你的電腦（包含 WSL）無需安裝 Python 即可直接運行。

### 1. 複製專案 (Clone)
```bash
git clone [https://github.com/你的帳號/ac-management.git](https://github.com/你的帳號/ac-management.git)
cd ac-management