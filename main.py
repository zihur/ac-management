import sqlite3
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from database import get_db_connection, init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

# 1. 首頁：列表、搜尋，以及支援帶入待編輯項目 (edit_id)
@app.get("/", response_class=HTMLResponse)
def home(
    request: Request, 
    keyword: Optional[str] = None, 
    edit_id: Optional[int] = None,
    message: Optional[str] = None, 
    error: Optional[str] = None
):
    conn = get_db_connection()
    cursor = conn.cursor()

    # 取得所有品牌
    cursor.execute("SELECT * FROM brands ORDER BY id ASC")
    brands = cursor.fetchall()

    # 查詢冷氣型號 (JOIN 品牌表)
    base_sql = """
        SELECT ac.id, ac.brand_id, b.name as brand_name, ac.model_number, ac.cooling_capacity, ac.notes
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

    # 如果有帶入 edit_id，查詢該筆資料供表單預填
    edit_item = None
    if edit_id:
        cursor.execute("SELECT * FROM ac_models WHERE id = ?", (edit_id,))
        edit_item = cursor.fetchone()

    conn.close()

    return templates.TemplateResponse(
        request=request, 
        name="index.html", 
        context={
            "title": "冷氣型號管理系統", 
            "items": items,
            "brands": brands,
            "edit_item": edit_item,  # 帶入正要編輯的資料 (若有)
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

# 3. 更新冷氣型號 (Update)
@app.post("/update/{item_id}")
def update_ac_model(
    item_id: int,
    brand_id: int = Form(...),
    model_number: str = Form(...),
    cooling_capacity: float = Form(...),
    notes: Optional[str] = Form(None)
):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE ac_models 
            SET brand_id = ?, model_number = ?, cooling_capacity = ?, notes = ?
            WHERE id = ?
            """,
            (brand_id, model_number, cooling_capacity, notes, item_id)
        )
        conn.commit()
        redirect_url = f"/?message=成功更新型號：{model_number}"
    except sqlite3.IntegrityError:
        redirect_url = f"/?error=更新失敗：型號 {model_number} 可能與其他紀錄重複！"
    finally:
        conn.close()

    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)

# 4. 刪除冷氣型號 (Delete)
@app.post("/delete/{item_id}")
def delete_ac_model(item_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM ac_models WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/?message=已成功刪除該筆資料", status_code=status.HTTP_303_SEE_OTHER)

# 5. 快速新增新品牌
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