import sqlite3
from typing import Optional
from fastapi import FastAPI, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from database import get_db_connection, init_db

app = FastAPI()
templates = Jinja2Templates(directory="templates")

@app.on_event("startup")
def startup_event():
    init_db()

# 1. 首頁路由：兼具列表展示與關鍵字搜尋
@app.get("/", response_class=HTMLResponse)
def home(
    request: Request, 
    keyword: Optional[str] = None, 
    message: Optional[str] = None, 
    error: Optional[str] = None
):
    conn = get_db_connection()
    cursor = conn.cursor()

    # 如果有輸入關鍵字，執行 LIKE 模糊搜尋 (同時比對品牌與型號)
    if keyword:
        search_pattern = f"%{keyword}%"
        cursor.execute(
            "SELECT * FROM ac_models WHERE brand LIKE ? OR model_number LIKE ? ORDER BY id DESC",
            (search_pattern, search_pattern)
        )
    else:
        # 沒有關鍵字則列出全部資料 (按 ID 倒序排列，最新建立的在最上面)
        cursor.execute("SELECT * FROM ac_models ORDER BY id DESC")

    items = cursor.fetchall()
    conn.close()

    return templates.TemplateResponse(
        request=request, 
        name="index.html", 
        context={
            "title": "冷氣型號管理系統", 
            "items": items,          # 傳送查詢出來的資料清單
            "keyword": keyword,      # 傳回關鍵字，讓搜尋框能保留輸入的值
            "message": message, 
            "error": error
        }
    )

# 2. 新增資料路由
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

    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)