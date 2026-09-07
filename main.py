import sqlite3
from typing import Optional
from fastapi import FastAPI, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from database import get_db_connection, init_db

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# 容器啟動時自動初始化 SQLite 資料庫
@app.on_event("startup")
def startup_event():
    init_db()

# 首頁 (顯示頁面)
@app.get("/", response_class=HTMLResponse)
def home(request: Request, message: Optional[str] = None, error: Optional[str] = None):
    return templates.TemplateResponse(
        request=request, 
        name="index.html", 
        context={"title": "冷氣型號管理系統", "message": message, "error": error}
    )

# 處理表單提交 (POST)
@app.post("/add")
def add_ac_model(
    brand: str = Form(...),
    model_number: str = Form(...),
    cooling_capacity: float = Form(...),
    notes: Optional[str] = Form(None)
):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO ac_models (brand, model_number, cooling_capacity, notes) VALUES (?, ?, ?, ?)",
            (brand, model_number, cooling_capacity, notes)
        )
        conn.commit()
        redirect_url = f"/?message=成功新增型號：{model_number}"
    except sqlite3.IntegrityError:
        redirect_url = f"/?error=型號 {model_number} 已存在，請勿重複新增！"
    finally:
        conn.close()

    # 重定向回首頁 (HTTP 303 防止使用者按 F5 重複提交 POST)
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)
