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

# 1. 首頁：讀取品牌列表，並 JOIN 查詢冷氣型號
@app.get("/", response_class=HTMLResponse)
def home(
    request: Request, 
    keyword: Optional[str] = None, 
    message: Optional[str] = None, 
    error: Optional[str] = None
):
    conn = get_db_connection()
    cursor = conn.cursor()

    # 取得所有品牌供選單 <select> 使用
    cursor.execute("SELECT * FROM brands ORDER BY id ASC")
    brands = cursor.fetchall()

    # 查詢冷氣型號 (JOIN 品牌表)
    base_sql = """
        SELECT ac.id, b.name as brand_name, ac.model_number, ac.cooling_capacity, ac.notes
        FROM ac_models ac
        JOIN brands b ON ac.brand_id = b.id
    """

    if keyword:
        search_pattern = f"%{keyword}%"
        sql = base_sql + " WHERE b.name LIKE ? OR ac.model_number LIKE ? ORDER BY ac.id DESC"
        cursor.execute(sql, (search_pattern, search_pattern))
    else:
        sql = base_sql + " ORDER BY ac.id DESC"
        cursor.execute(sql)

    items = cursor.fetchall()
    conn.close()

    return templates.TemplateResponse(
        request=request, 
        name="index.html", 
        context={
            "title": "冷氣型號管理系統", 
            "items": items,
            "brands": brands,        # 傳送品牌選單資料
            "keyword": keyword,
            "message": message, 
            "error": error
        }
    )

# 2. 新增冷氣型號
@app.post("/add")
def add_ac_model(
    brand_id: int = Form(...),
    model_number: str = Form(...),
    cooling_capacity: float = Form(...),
    notes: Optional[str] = Form(None)
):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO ac_models (brand_id, model_number, cooling_capacity, notes) VALUES (?, ?, ?, ?)",
            (brand_id, model_number, cooling_capacity, notes)
        )
        conn.commit()
        redirect_url = f"/?message=成功新增型號：{model_number}"
    except sqlite3.IntegrityError:
        redirect_url = f"/?error=型號 {model_number} 已存在，請勿重複新增！"
    finally:
        conn.close()

    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)

# 3. 快速新增新品牌
@app.post("/add-brand")
def add_brand(brand_name: str = Form(...)):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO brands (name) VALUES (?)", (brand_name.strip(),))
        conn.commit()
        redirect_url = f"/?message=成功新增品牌：{brand_name}"
    except sqlite3.IntegrityError:
        redirect_url = f"/?error=品牌 {brand_name} 已存在！"
    finally:
        conn.close()

    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)