import os
import sys
import time
import threading
from datetime import datetime
from typing import Any, Callable
import sqlite3
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from starlette.middleware.sessions import SessionMiddleware

from database import get_db_connection, init_db
from models import (
    ACRecordInput,
    DISCOUNT_TYPE_FIXED,
    DISCOUNT_TYPE_PERCENT,
    calc_discount_price,
    format_discount_label,
)

FILTER_YEAR_ALL = "all"

SESSION_SECRET_KEY = os.environ.get(
    "SESSION_SECRET_KEY",
    "dev-only-change-in-production-ac-management",
)


def _heartbeat_enabled() -> bool:
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
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET_KEY)
templates = Jinja2Templates(directory="templates")
templates.env.globals["calc_discount_price"] = calc_discount_price
templates.env.globals["format_discount_label"] = format_discount_label
templates.env.globals["DISCOUNT_TYPE_PERCENT"] = DISCOUNT_TYPE_PERCENT
templates.env.globals["DISCOUNT_TYPE_FIXED"] = DISCOUNT_TYPE_FIXED

last_heartbeat = time.time()
_shutdown_callback: Callable[[], None] | None = None
_monitor_started = False
_monitor_lock = threading.Lock()


def register_shutdown(callback: Callable[[], None]) -> None:
    global _shutdown_callback
    _shutdown_callback = callback


def start_heartbeat_monitor() -> None:
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


def heartbeat_monitor():
    global last_heartbeat
    while True:
        time.sleep(3)
        if time.time() - last_heartbeat > 8:
            _hard_exit()
            break


def _parse_list_filter_year(
    raw: Optional[str | int],
    *,
    default_year: int,
) -> tuple[bool, Optional[int]]:
    if raw is None or str(raw).strip() == "":
        return False, default_year
    if str(raw).lower() == FILTER_YEAR_ALL:
        return True, None
    return False, int(raw)


def _filter_year_query_value(filter_all: bool, filter_year: Optional[int]) -> str | int:
    if filter_all:
        return FILTER_YEAR_ALL
    assert filter_year is not None
    return filter_year


def _validation_error_message(exc: ValidationError) -> str:
    return exc.errors()[0]["msg"]


def _parse_record_input(
    *,
    year: int,
    cooling_capacity: float,
    official_retail_price: float,
    discount_type: str,
    discount_percent: Optional[float],
    discount_amount: Optional[float],
    cadr: Optional[float],
) -> tuple[int, float, float, str, Optional[float], Optional[float], Optional[float]]:
    try:
        record = ACRecordInput(
            year=year,
            cooling_capacity=cooling_capacity,
            official_retail_price=official_retail_price,
            discount_type=discount_type,  # type: ignore[arg-type]
            discount_percent=discount_percent,
            discount_amount=discount_amount,
            cadr=cadr,
        )
    except ValidationError as exc:
        raise ValueError(_validation_error_message(exc)) from exc
    db_type, db_ratio, db_amount = record.discount_values()
    record.calc_discount_price()
    return (
        record.year,
        record.cooling_capacity,
        record.official_retail_price,
        db_type,
        db_ratio,
        db_amount,
        record.cadr,
    )


def _pop_flash(request: Request) -> tuple[Optional[str], Optional[str]]:
    return (
        request.session.pop("flash_message", None),
        request.session.pop("flash_error", None),
    )


def _pop_form_draft(request: Request) -> Optional[dict[str, Any]]:
    return request.session.pop("form_draft", None)


def _redirect_with_session(
    request: Request,
    url: str,
    *,
    message: Optional[str] = None,
    error: Optional[str] = None,
    form_draft: Optional[dict[str, Any]] = None,
) -> RedirectResponse:
    if message:
        request.session["flash_message"] = message
    if error:
        request.session["flash_error"] = error
    if form_draft is not None:
        request.session["form_draft"] = form_draft
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


def _build_home_url(
    *,
    edit_id: int | None = None,
    year: int | str | None = None,
    keyword: str | None = None,
) -> str:
    params: list[str] = []
    if edit_id:
        params.append(f"edit_id={edit_id}")
    if year is not None:
        params.append(f"year={year}")
    if keyword:
        from urllib.parse import quote
        params.append(f"keyword={quote(keyword)}")
    query = "&".join(params)
    return f"/?{query}" if query else "/"


@app.post("/api/ping")
def ping():
    global last_heartbeat
    last_heartbeat = time.time()
    return {"status": "alive"}


@app.get("/", response_class=HTMLResponse)
def home(
    request: Request,
    keyword: Optional[str] = None,
    year: Optional[str] = None,
    edit_id: Optional[int] = None,
):
    flash_message, flash_error = _pop_flash(request)
    form_draft = _pop_form_draft(request)

    if form_draft:
        edit_id = edit_id or form_draft.get("edit_id")
        keyword = keyword or form_draft.get("keyword")
        if year is None and form_draft.get("filter_year") is not None:
            year = form_draft.get("filter_year")

    conn = get_db_connection()
    cursor = conn.cursor()
    current_year = datetime.now().year
    filter_all, filter_year = _parse_list_filter_year(year, default_year=current_year)
    filter_year_param = _filter_year_query_value(filter_all, filter_year)

    cursor.execute("SELECT * FROM brands ORDER BY id ASC")
    brands = cursor.fetchall()

    cursor.execute("SELECT DISTINCT year FROM ac_records ORDER BY year DESC")
    available_years = [row["year"] for row in cursor.fetchall()]
    if not filter_all and filter_year not in available_years:
        available_years = sorted(set(available_years + [filter_year]), reverse=True)

    base_sql = """
        SELECT
            r.id, r.brand_id, b.name AS brand_name, r.model_number, r.year,
            r.cooling_capacity, r.notes, r.official_retail_price,
            r.discount_type, r.discount_ratio, r.discount_amount, r.cadr
        FROM ac_records r
        JOIN brands b ON r.brand_id = b.id
    """
    params: list = []
    conditions: list[str] = []

    if not filter_all:
        conditions.append("r.year = ?")
        params.append(filter_year)

    if keyword:
        search_pattern = f"%{keyword}%"
        conditions.append("(b.name LIKE ? OR r.model_number LIKE ?)")
        params.extend([search_pattern, search_pattern])

    sql = base_sql
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY r.year DESC, r.id DESC"

    cursor.execute(sql, params)
    items = cursor.fetchall()

    edit_item = None
    if edit_id:
        cursor.execute(
            """
            SELECT r.*, b.name AS brand_name
            FROM ac_records r
            JOIN brands b ON r.brand_id = b.id
            WHERE r.id = ?
            """,
            (edit_id,),
        )
        edit_item = cursor.fetchone()

    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "title": "冷氣型號管理系統",
            "items": items,
            "brands": brands,
            "edit_item": edit_item,
            "form_draft": form_draft,
            "keyword": keyword,
            "filter_all": filter_all,
            "filter_year": filter_year,
            "filter_year_param": filter_year_param,
            "available_years": available_years,
            "current_year": current_year,
            "message": flash_message,
            "error": flash_error,
        },
    )


def _record_form_draft(
    *,
    form: str,
    brand_id: int,
    model_number: str,
    year: int,
    cooling_capacity: float,
    notes: Optional[str],
    official_retail_price: float,
    discount_type: str,
    discount_percent: Optional[float],
    discount_amount: Optional[float],
    cadr: Optional[float],
    filter_year_param: str | int,
    keyword: Optional[str],
    edit_id: Optional[int] = None,
) -> dict[str, Any]:
    draft: dict[str, Any] = {
        "form": form,
        "brand_id": brand_id,
        "model_number": model_number,
        "year": year,
        "cooling_capacity": cooling_capacity,
        "notes": notes or "",
        "official_retail_price": official_retail_price,
        "discount_type": discount_type,
        "discount_percent": discount_percent,
        "discount_amount": discount_amount,
        "cadr": cadr,
        "filter_year": filter_year_param,
        "keyword": keyword,
    }
    if edit_id is not None:
        draft["edit_id"] = edit_id
    return draft


@app.post("/add")
def add_record(
    request: Request,
    brand_id: int = Form(...),
    model_number: str = Form(...),
    year: int = Form(...),
    cooling_capacity: float = Form(...),
    official_retail_price: float = Form(...),
    discount_type: str = Form(DISCOUNT_TYPE_PERCENT),
    discount_percent: Optional[float] = Form(None),
    discount_amount: Optional[float] = Form(None),
    cadr: Optional[float] = Form(None),
    notes: Optional[str] = Form(None),
    filter_year: Optional[str] = Form(None),
    keyword: Optional[str] = Form(None),
):
    conn = get_db_connection()
    cursor = conn.cursor()
    current_year = datetime.now().year
    filter_all, list_filter_year = _parse_list_filter_year(filter_year, default_year=current_year)
    list_year_param = _filter_year_query_value(filter_all, list_filter_year)

    form_draft = _record_form_draft(
        form="add",
        brand_id=brand_id,
        model_number=model_number,
        year=year,
        cooling_capacity=cooling_capacity,
        notes=notes,
        official_retail_price=official_retail_price,
        discount_type=discount_type,
        discount_percent=discount_percent,
        discount_amount=discount_amount,
        cadr=cadr,
        filter_year_param=list_year_param,
        keyword=keyword,
    )

    try:
        parsed = _parse_record_input(
            year=year,
            cooling_capacity=cooling_capacity,
            official_retail_price=official_retail_price,
            discount_type=discount_type,
            discount_percent=discount_percent,
            discount_amount=discount_amount,
            cadr=cadr,
        )
        cursor.execute(
            """
            INSERT INTO ac_records (
                brand_id, model_number, year, cooling_capacity, notes,
                official_retail_price, discount_type, discount_ratio,
                discount_amount, cadr
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                brand_id,
                model_number.strip(),
                parsed[0],
                parsed[1],
                notes,
                parsed[2],
                parsed[3],
                parsed[4],
                parsed[5],
                parsed[6],
            ),
        )
        conn.commit()
        return _redirect_with_session(
            request,
            _build_home_url(year=year, keyword=keyword),
            message=f"成功新增：{model_number}（{year}）",
        )
    except ValueError as exc:
        conn.rollback()
        return _redirect_with_session(
            request,
            _build_home_url(year=list_year_param, keyword=keyword),
            error=str(exc),
            form_draft=form_draft,
        )
    except sqlite3.IntegrityError:
        conn.rollback()
        return _redirect_with_session(
            request,
            _build_home_url(year=list_year_param, keyword=keyword),
            error=f"該品牌下 {model_number} 的 {year} 年資料已存在！",
            form_draft=form_draft,
        )
    finally:
        conn.close()


@app.post("/update/{item_id}")
def update_record(
    request: Request,
    item_id: int,
    brand_id: int = Form(...),
    model_number: str = Form(...),
    year: int = Form(...),
    cooling_capacity: float = Form(...),
    official_retail_price: float = Form(...),
    discount_type: str = Form(DISCOUNT_TYPE_PERCENT),
    discount_percent: Optional[float] = Form(None),
    discount_amount: Optional[float] = Form(None),
    cadr: Optional[float] = Form(None),
    notes: Optional[str] = Form(None),
    filter_year: Optional[str] = Form(None),
    keyword: Optional[str] = Form(None),
):
    conn = get_db_connection()
    cursor = conn.cursor()
    current_year = datetime.now().year
    filter_all, list_filter_year = _parse_list_filter_year(filter_year, default_year=current_year)
    list_year_param = _filter_year_query_value(filter_all, list_filter_year)

    form_draft = _record_form_draft(
        form="edit",
        edit_id=item_id,
        brand_id=brand_id,
        model_number=model_number,
        year=year,
        cooling_capacity=cooling_capacity,
        notes=notes,
        official_retail_price=official_retail_price,
        discount_type=discount_type,
        discount_percent=discount_percent,
        discount_amount=discount_amount,
        cadr=cadr,
        filter_year_param=list_year_param,
        keyword=keyword,
    )

    try:
        parsed = _parse_record_input(
            year=year,
            cooling_capacity=cooling_capacity,
            official_retail_price=official_retail_price,
            discount_type=discount_type,
            discount_percent=discount_percent,
            discount_amount=discount_amount,
            cadr=cadr,
        )
        cursor.execute(
            """
            UPDATE ac_records
            SET brand_id = ?, model_number = ?, year = ?, cooling_capacity = ?, notes = ?,
                official_retail_price = ?, discount_type = ?, discount_ratio = ?,
                discount_amount = ?, cadr = ?
            WHERE id = ?
            """,
            (
                brand_id,
                model_number.strip(),
                parsed[0],
                parsed[1],
                notes,
                parsed[2],
                parsed[3],
                parsed[4],
                parsed[5],
                parsed[6],
                item_id,
            ),
        )
        conn.commit()
        return _redirect_with_session(
            request,
            _build_home_url(edit_id=item_id, year=list_year_param, keyword=keyword),
            message=f"成功更新：{model_number}（{year}）",
        )
    except ValueError as exc:
        return _redirect_with_session(
            request,
            _build_home_url(edit_id=item_id, year=list_year_param, keyword=keyword),
            error=str(exc),
            form_draft=form_draft,
        )
    except sqlite3.IntegrityError:
        return _redirect_with_session(
            request,
            _build_home_url(edit_id=item_id, year=list_year_param, keyword=keyword),
            error=f"更新失敗：{model_number} 的 {year} 年資料可能與其他紀錄重複！",
            form_draft=form_draft,
        )
    finally:
        conn.close()


@app.post("/delete/{item_id}")
def delete_record(
    request: Request,
    item_id: int,
    filter_year: Optional[str] = Form(None),
    keyword: Optional[str] = Form(None),
):
    conn = get_db_connection()
    cursor = conn.cursor()
    current_year = datetime.now().year
    filter_all, list_filter_year = _parse_list_filter_year(filter_year, default_year=current_year)
    cursor.execute("DELETE FROM ac_records WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    return _redirect_with_session(
        request,
        _build_home_url(
            year=_filter_year_query_value(filter_all, list_filter_year),
            keyword=keyword,
        ),
        message="已成功刪除該筆資料",
    )


@app.post("/add-brand")
def add_brand(
    request: Request,
    brand_name: str = Form(...),
    filter_year: Optional[str] = Form(None),
    keyword: Optional[str] = Form(None),
    edit_id: Optional[int] = Form(None),
):
    conn = get_db_connection()
    cursor = conn.cursor()
    current_year = datetime.now().year
    filter_all, list_filter_year = _parse_list_filter_year(filter_year, default_year=current_year)
    list_year_param = _filter_year_query_value(filter_all, list_filter_year)
    try:
        cursor.execute("INSERT INTO brands (name) VALUES (?)", (brand_name.strip(),))
        conn.commit()
        return _redirect_with_session(
            request,
            _build_home_url(edit_id=edit_id, year=list_year_param, keyword=keyword),
            message=f"成功新增品牌：{brand_name}",
        )
    except sqlite3.IntegrityError:
        return _redirect_with_session(
            request,
            _build_home_url(edit_id=edit_id, year=list_year_param, keyword=keyword),
            error=f"品牌 {brand_name} 已存在！",
        )
    finally:
        conn.close()
