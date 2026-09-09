import os
import sys
import time
import threading
from datetime import datetime
from typing import Callable
import sqlite3
from contextlib import asynccontextmanager
from typing import Optional
from urllib.parse import quote

from fastapi import FastAPI, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from database import get_db_connection, init_db


def _heartbeat_enabled() -> bool:
    """桌面 .exe 模式啟用心跳；Docker / 一般 uvicorn 預設關閉。"""
    flag = os.environ.get("ENABLE_HEARTBEAT", "").lower()
    if flag in ("1", "true", "yes"):
        return True
    if flag in ("0", "false", "no"):
        return False
    return getattr(sys, "frozen", False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_heartbeat_monitor()
    yield


app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

# ---------------------------------------------------------
# 💓 心跳包 (Heartbeat) 自動關閉機制
# ---------------------------------------------------------
last_heartbeat = time.time()
_shutdown_callback: Callable[[], None] | None = None
_monitor_started = False
_monitor_lock = threading.Lock()


def register_shutdown(callback: Callable[[], None]) -> None:
    """由 run.py 註冊 uvicorn 優雅關閉；未註冊時改走 os._exit。"""
    global _shutdown_callback
    _shutdown_callback = callback


def start_heartbeat_monitor() -> None:
    """啟動心跳監控（lifespan 與 run.py 皆可呼叫，僅啟動一次）。"""
    global _monitor_started, last_heartbeat
    if not _heartbeat_enabled():
        return
    with _monitor_lock:
        if _monitor_started:
            return
        _monitor_started = True
        last_heartbeat = time.time()
        threading.Thread(
            target=heartbeat_monitor,
            daemon=True,
            name="heartbeat_monitor",
        ).start()


def _hard_exit() -> None:
    """Windows windowed exe 無控制台，SIGINT / 延遲 Timer 皆不可靠。"""
    try:
        if _shutdown_callback is not None:
            _shutdown_callback()
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.TerminateProcess(
                ctypes.windll.kernel32.GetCurrentProcess(), 0
            )
        except Exception:
            pass
    os._exit(0)


def _shutdown_process() -> None:
    """關閉背景程序。"""
    _hard_exit()


def heartbeat_monitor():
    """背景線程：每 3 秒檢查一次心跳，超過 8 秒沒收到心跳就自動關閉行程"""
    global last_heartbeat
    while True:
        time.sleep(3)
        if time.time() - last_heartbeat > 8:
            _shutdown_process()
            break


DISCOUNT_TYPE_PERCENT = "percent"
DISCOUNT_TYPE_FIXED = "fixed"


def _parse_discount_percent(discount_percent: float) -> float:
    if discount_percent <= 0 or discount_percent > 100:
        raise ValueError("折數必須介於 1 至 100 之間")
    return discount_percent / 100


def calc_discount_price(
    official_retail_price: float,
    discount_type: str,
    discount_ratio: Optional[float],
    discount_amount: Optional[float],
) -> float:
    if discount_type == DISCOUNT_TYPE_FIXED:
        if discount_amount is None or discount_amount < 0:
            raise ValueError("固定扣款金額不可為空")
        price = official_retail_price - discount_amount
        if price <= 0:
            raise ValueError("扣減金額必須小於官方零售價")
        return price

    if discount_ratio is None:
        raise ValueError("折數不可為空")
    return official_retail_price * discount_ratio


def format_discount_label(
    discount_type: str,
    discount_ratio: Optional[float],
    discount_amount: Optional[float],
) -> str:
    if discount_type == DISCOUNT_TYPE_FIXED:
        amount = discount_amount or 0
        return f"扣 {amount:,.0f} 元"
    ratio = discount_ratio or 0
    return f"{round(ratio * 100)} 折"


def _parse_yearly_discount(
    discount_type: str,
    official_retail_price: float,
    discount_percent: Optional[float],
    discount_amount: Optional[float],
) -> tuple[str, Optional[float], Optional[float]]:
    if discount_type not in (DISCOUNT_TYPE_PERCENT, DISCOUNT_TYPE_FIXED):
        raise ValueError("優惠方式無效")

    if discount_type == DISCOUNT_TYPE_FIXED:
        if discount_amount is None or discount_amount <= 0:
            raise ValueError("固定扣款金額必須大於 0")
        if discount_amount >= official_retail_price:
            raise ValueError("扣減金額必須小於官方零售價")
        return discount_type, None, discount_amount

    if discount_percent is None:
        raise ValueError("折數不可為空")
    return discount_type, _parse_discount_percent(discount_percent), None


def _optional_float(value: Optional[str]) -> Optional[float]:
    if value is None or str(value).strip() == "":
        return None
    return float(value)


def _optional_int(value: Optional[str]) -> Optional[int]:
    if value is None or str(value).strip() == "":
        return None
    return int(value)


templates.env.globals["calc_discount_price"] = calc_discount_price
templates.env.globals["format_discount_label"] = format_discount_label
templates.env.globals["DISCOUNT_TYPE_PERCENT"] = DISCOUNT_TYPE_PERCENT
templates.env.globals["DISCOUNT_TYPE_FIXED"] = DISCOUNT_TYPE_FIXED


def _build_redirect_url(
    message: str | None = None,
    error: str | None = None,
    edit_id: int | None = None,
    edit_yearly_id: int | None = None,
    year: int | None = None,
    keyword: str | None = None,
) -> str:
    params: list[str] = []
    if message:
        params.append(f"message={quote(message)}")
    if error:
        params.append(f"error={quote(error)}")
    if edit_id:
        params.append(f"edit_id={edit_id}")
    if edit_yearly_id:
        params.append(f"edit_yearly_id={edit_yearly_id}")
    if year is not None:
        params.append(f"year={year}")
    if keyword:
        params.append(f"keyword={quote(keyword)}")
    query = "&".join(params)
    return f"/?{query}" if query else "/"


@app.post("/api/ping")
def ping():
    """前端心跳接收 API"""
    global last_heartbeat
    last_heartbeat = time.time()
    return {"status": "alive"}


# 1. 首頁：列表、搜尋，以及支援帶入待編輯項目 (edit_id)
@app.get("/", response_class=HTMLResponse)
def home(
    request: Request,
    keyword: Optional[str] = None,
    year: Optional[int] = None,
    edit_id: Optional[int] = None,
    edit_yearly_id: Optional[int] = None,
    message: Optional[str] = None,
    error: Optional[str] = None,
):
    conn = get_db_connection()
    cursor = conn.cursor()
    current_year = datetime.now().year
    filter_year = year if year is not None else current_year

    cursor.execute("SELECT * FROM brands ORDER BY id ASC")
    brands = cursor.fetchall()

    cursor.execute("SELECT DISTINCT year FROM ac_model_yearly ORDER BY year DESC")
    available_years = [row["year"] for row in cursor.fetchall()]
    if filter_year not in available_years:
        available_years = sorted(set(available_years + [filter_year]), reverse=True)

    base_sql = """
        SELECT
            ac.id, ac.brand_id, b.name AS brand_name, ac.model_number,
            ac.cooling_capacity, ac.notes,
            y.id AS yearly_id, y.year AS yearly_year,
            y.official_retail_price, y.discount_type, y.discount_ratio,
            y.discount_amount, y.cadr AS yearly_cadr, y.notes AS yearly_notes
        FROM ac_models ac
        JOIN brands b ON ac.brand_id = b.id
        LEFT JOIN ac_model_yearly y ON y.ac_model_id = ac.id AND y.year = ?
    """
    params: list = [filter_year]

    if keyword:
        search_pattern = f"%{keyword}%"
        sql = base_sql + " WHERE b.name LIKE ? OR ac.model_number LIKE ? ORDER BY ac.id DESC"
        params.extend([search_pattern, search_pattern])
    else:
        sql = base_sql + " ORDER BY ac.id DESC"

    cursor.execute(sql, params)
    items = cursor.fetchall()

    edit_item = None
    yearly_records = []
    edit_yearly = None
    if edit_id:
        cursor.execute("SELECT * FROM ac_models WHERE id = ?", (edit_id,))
        edit_item = cursor.fetchone()
        if edit_item:
            cursor.execute(
                """
                SELECT * FROM ac_model_yearly
                WHERE ac_model_id = ?
                ORDER BY year DESC
                """,
                (edit_id,),
            )
            yearly_records = cursor.fetchall()
            if edit_yearly_id:
                cursor.execute(
                    "SELECT * FROM ac_model_yearly WHERE id = ? AND ac_model_id = ?",
                    (edit_yearly_id, edit_id),
                )
                edit_yearly = cursor.fetchone()

    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "title": "冷氣型號管理系統",
            "items": items,
            "brands": brands,
            "edit_item": edit_item,
            "yearly_records": yearly_records,
            "edit_yearly": edit_yearly,
            "keyword": keyword,
            "filter_year": filter_year,
            "available_years": available_years,
            "current_year": current_year,
            "message": message,
            "error": error,
        },
    )


def _insert_yearly_record(
    cursor: sqlite3.Cursor,
    ac_model_id: int,
    data_year: int,
    official_retail_price: float,
    discount_type: str,
    discount_ratio: Optional[float],
    discount_amount: Optional[float],
    cadr: Optional[float],
    yearly_notes: Optional[str],
) -> None:
    calc_discount_price(
        official_retail_price, discount_type, discount_ratio, discount_amount
    )
    cursor.execute(
        """
        INSERT INTO ac_model_yearly (
            ac_model_id, year, official_retail_price,
            discount_type, discount_ratio, discount_amount, cadr, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ac_model_id,
            data_year,
            official_retail_price,
            discount_type,
            discount_ratio,
            discount_amount,
            cadr,
            yearly_notes,
        ),
    )


# 2. 新增冷氣型號（可一併新增當年度資料）
@app.post("/add")
def add_ac_model(
    brand_id: int = Form(...),
    model_number: str = Form(...),
    cooling_capacity: float = Form(...),
    notes: Optional[str] = Form(None),
    data_year: Optional[str] = Form(None),
    official_retail_price: Optional[str] = Form(None),
    discount_type: Optional[str] = Form(DISCOUNT_TYPE_PERCENT),
    discount_percent: Optional[str] = Form(None),
    discount_amount: Optional[str] = Form(None),
    cadr: Optional[str] = Form(None),
    yearly_notes: Optional[str] = Form(None),
    year: Optional[int] = Form(None),
    keyword: Optional[str] = Form(None),
):
    conn = get_db_connection()
    cursor = conn.cursor()
    current_year = datetime.now().year
    parsed_data_year = _optional_int(data_year)
    parsed_retail_price = _optional_float(official_retail_price)
    parsed_discount = _optional_float(discount_percent)
    parsed_discount_amount = _optional_float(discount_amount)
    parsed_cadr = _optional_float(cadr)
    selected_discount_type = discount_type or DISCOUNT_TYPE_PERCENT
    yearly_year = parsed_data_year if parsed_data_year is not None else (
        year if year is not None else current_year
    )
    has_yearly_input = (
        parsed_retail_price is not None
        or parsed_discount is not None
        or parsed_discount_amount is not None
        or parsed_cadr is not None
        or bool(yearly_notes and yearly_notes.strip())
    )

    try:
        parsed_discount_type = selected_discount_type
        parsed_discount_ratio: Optional[float] = None
        parsed_discount_amount_value: Optional[float] = None

        if has_yearly_input:
            if parsed_retail_price is None:
                raise ValueError("填寫年度資料時，官方零售價為必填")
            (
                parsed_discount_type,
                parsed_discount_ratio,
                parsed_discount_amount_value,
            ) = _parse_yearly_discount(
                selected_discount_type,
                parsed_retail_price,
                parsed_discount,
                parsed_discount_amount,
            )

        cursor.execute(
            "INSERT INTO ac_models (brand_id, model_number, cooling_capacity, notes) VALUES (?, ?, ?, ?)",
            (brand_id, model_number, cooling_capacity, notes),
        )
        model_id = cursor.lastrowid

        if has_yearly_input:
            _insert_yearly_record(
                cursor,
                model_id,
                yearly_year,
                parsed_retail_price,
                parsed_discount_type,
                parsed_discount_ratio,
                parsed_discount_amount_value,
                parsed_cadr,
                yearly_notes,
            )

        conn.commit()
        msg = f"成功新增型號：{model_number}"
        if has_yearly_input:
            msg += f"（含 {yearly_year} 年度資料）"
        redirect_url = _build_redirect_url(
            message=msg,
            year=yearly_year if has_yearly_input else year,
            keyword=keyword,
        )
    except ValueError as exc:
        conn.rollback()
        redirect_url = _build_redirect_url(
            error=str(exc),
            year=year,
            keyword=keyword,
        )
    except sqlite3.IntegrityError:
        conn.rollback()
        if cursor.execute(
            "SELECT 1 FROM ac_models WHERE model_number = ?", (model_number,)
        ).fetchone():
            error = f"型號 {model_number} 已存在，請勿重複新增！"
        else:
            error = f"{yearly_year} 年度資料已存在，請改用編輯功能！"
        redirect_url = _build_redirect_url(
            error=error,
            year=year,
            keyword=keyword,
        )
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
    notes: Optional[str] = Form(None),
    year: Optional[int] = Form(None),
    keyword: Optional[str] = Form(None),
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
            (brand_id, model_number, cooling_capacity, notes, item_id),
        )
        conn.commit()
        redirect_url = _build_redirect_url(
            message=f"成功更新型號：{model_number}",
            edit_id=item_id,
            year=year,
            keyword=keyword,
        )
    except sqlite3.IntegrityError:
        redirect_url = _build_redirect_url(
            error=f"更新失敗：型號 {model_number} 可能與其他紀錄重複！",
            edit_id=item_id,
            year=year,
            keyword=keyword,
        )
    finally:
        conn.close()

    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)


# 4. 刪除冷氣型號 (Delete)
@app.post("/delete/{item_id}")
def delete_ac_model(
    item_id: int,
    year: Optional[int] = Form(None),
    keyword: Optional[str] = Form(None),
):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM ac_models WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    return RedirectResponse(
        url=_build_redirect_url(message="已成功刪除該筆資料", year=year, keyword=keyword),
        status_code=status.HTTP_303_SEE_OTHER,
    )


# 5. 快速新增新品牌
@app.post("/add-brand")
def add_brand(
    brand_name: str = Form(...),
    year: Optional[int] = Form(None),
    keyword: Optional[str] = Form(None),
    edit_id: Optional[int] = Form(None),
):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO brands (name) VALUES (?)", (brand_name.strip(),))
        conn.commit()
        redirect_url = _build_redirect_url(
            message=f"成功新增品牌：{brand_name}",
            edit_id=edit_id,
            year=year,
            keyword=keyword,
        )
    except sqlite3.IntegrityError:
        redirect_url = _build_redirect_url(
            error=f"品牌 {brand_name} 已存在！",
            edit_id=edit_id,
            year=year,
            keyword=keyword,
        )
    finally:
        conn.close()

    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)


# 6. 新增年度資料
@app.post("/models/{model_id}/yearly/add")
def add_yearly_data(
    model_id: int,
    year: int = Form(...),
    official_retail_price: float = Form(...),
    discount_type: str = Form(DISCOUNT_TYPE_PERCENT),
    discount_percent: Optional[float] = Form(None),
    discount_amount: Optional[float] = Form(None),
    cadr: Optional[float] = Form(None),
    notes: Optional[str] = Form(None),
    filter_year: Optional[int] = Form(None),
    keyword: Optional[str] = Form(None),
):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        parsed_type, parsed_ratio, parsed_amount = _parse_yearly_discount(
            discount_type, official_retail_price, discount_percent, discount_amount
        )
        _insert_yearly_record(
            cursor,
            model_id,
            year,
            official_retail_price,
            parsed_type,
            parsed_ratio,
            parsed_amount,
            cadr,
            notes,
        )
        conn.commit()
        redirect_url = _build_redirect_url(
            message=f"成功新增 {year} 年度資料",
            edit_id=model_id,
            year=filter_year,
            keyword=keyword,
        )
    except ValueError as exc:
        redirect_url = _build_redirect_url(
            error=str(exc),
            edit_id=model_id,
            year=filter_year,
            keyword=keyword,
        )
    except sqlite3.IntegrityError:
        redirect_url = _build_redirect_url(
            error=f"{year} 年度資料已存在，請改用編輯功能！",
            edit_id=model_id,
            year=filter_year,
            keyword=keyword,
        )
    finally:
        conn.close()

    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)


# 7. 更新年度資料
@app.post("/yearly/update/{yearly_id}")
def update_yearly_data(
    yearly_id: int,
    ac_model_id: int = Form(...),
    year: int = Form(...),
    official_retail_price: float = Form(...),
    discount_type: str = Form(DISCOUNT_TYPE_PERCENT),
    discount_percent: Optional[float] = Form(None),
    discount_amount: Optional[float] = Form(None),
    cadr: Optional[float] = Form(None),
    notes: Optional[str] = Form(None),
    filter_year: Optional[int] = Form(None),
    keyword: Optional[str] = Form(None),
):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        parsed_type, parsed_ratio, parsed_amount = _parse_yearly_discount(
            discount_type, official_retail_price, discount_percent, discount_amount
        )
        calc_discount_price(
            official_retail_price, parsed_type, parsed_ratio, parsed_amount
        )
        cursor.execute(
            """
            UPDATE ac_model_yearly
            SET year = ?, official_retail_price = ?, discount_type = ?,
                discount_ratio = ?, discount_amount = ?, cadr = ?, notes = ?
            WHERE id = ? AND ac_model_id = ?
            """,
            (
                year,
                official_retail_price,
                parsed_type,
                parsed_ratio,
                parsed_amount,
                cadr,
                notes,
                yearly_id,
                ac_model_id,
            ),
        )
        conn.commit()
        redirect_url = _build_redirect_url(
            message=f"成功更新 {year} 年度資料",
            edit_id=ac_model_id,
            year=filter_year,
            keyword=keyword,
        )
    except ValueError as exc:
        redirect_url = _build_redirect_url(
            error=str(exc),
            edit_id=ac_model_id,
            edit_yearly_id=yearly_id,
            year=filter_year,
            keyword=keyword,
        )
    except sqlite3.IntegrityError:
        redirect_url = _build_redirect_url(
            error=f"更新失敗：{year} 年度資料可能與其他紀錄重複！",
            edit_id=ac_model_id,
            edit_yearly_id=yearly_id,
            year=filter_year,
            keyword=keyword,
        )
    finally:
        conn.close()

    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)


# 8. 刪除年度資料
@app.post("/yearly/delete/{yearly_id}")
def delete_yearly_data(
    yearly_id: int,
    ac_model_id: int = Form(...),
    filter_year: Optional[int] = Form(None),
    keyword: Optional[str] = Form(None),
):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM ac_model_yearly WHERE id = ? AND ac_model_id = ?",
        (yearly_id, ac_model_id),
    )
    conn.commit()
    conn.close()
    return RedirectResponse(
        url=_build_redirect_url(
            message="已成功刪除年度資料",
            edit_id=ac_model_id,
            year=filter_year,
            keyword=keyword,
        ),
        status_code=status.HTTP_303_SEE_OTHER,
    )
