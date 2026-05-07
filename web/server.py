"""
MSM Valve Management System — FastAPI Web Server
Single unified backend serving API + static HTML.
"""
import sqlite3
import os
import sys
import io
import tempfile
from datetime import date, datetime
from typing import Optional, List

from fastapi import FastAPI, Query, Request, UploadFile, File, Body
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from pydantic import BaseModel

# Add parent to path for parser/lookup imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from parser import parse_query

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
MSM_DB = os.path.join(DATA_DIR, "msm.sqlite")
PRICE_DB = os.path.join(DATA_DIR, "한국밸브_협가표.db")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = FastAPI(title="MSM Valve Management", version="1.0.0")


def get_msm_db():
    conn = sqlite3.connect(MSM_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_price_db():
    conn = sqlite3.connect(PRICE_DB)
    conn.row_factory = sqlite3.Row
    return conn


# ============================================================
# API: Price Search (협가표 조회)
# ============================================================

@app.get("/api/search")
def search_price(q: str = Query(""), discount: str = Query("")):
    parsed = parse_query(q)
    if discount:
        parsed["discount_rate"] = discount

    conn = get_price_db()
    conditions = []
    params = []
    field_map = {
        "product_type": "product_type",
        "pressure_class": "pressure_class",
        "size_a": "size_a",
        "discount_rate": "discount_rate",
    }
    for key, col in field_map.items():
        val = parsed.get(key)
        if val is not None:
            conditions.append(f"{col} = ?")
            params.append(val)

    where = " AND ".join(conditions) if conditions else "1=1"
    sql = f"SELECT * FROM price_list_items WHERE {where} ORDER BY product_type, pressure_class, size_a, discount_rate"
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()

    return {
        "parsed": {k: v for k, v in parsed.items() if k not in ("raw_query",) and v is not None},
        "count": len(rows),
        "status": "exact" if len(rows) == 1 else ("multiple" if rows else "none"),
        "results": rows,
    }


# ============================================================
# API: Orders (수주대장) — flat row model for spreadsheet UI
# ============================================================

# Flat row columns matching the Excel 수주대장 layout
ORDER_COLS = [
    "id", "year_month", "order_seq", "customer_name", "memo",
    "item_desc", "unit_price", "quantity", "order_date", "amount",
    "stock_amount", "delivery_due", "delivery_date", "delivery_amount",
    "sales_date", "sales_amount", "remark", "collection_note",
    "supplier_name", "purchase_date", "purchase_amount", "purchase_due",
]


@app.get("/api/orders/rows")
def list_order_rows(year_month: str = Query(""), q: str = Query("")):
    """Return flat rows for spreadsheet view — one row per order_item."""
    conn = get_msm_db()
    conditions = []
    params = []

    if year_month:
        conditions.append("o.year_month = ?")
        params.append(year_month)
    if q:
        conditions.append("(o.customer_name LIKE ? OR o.memo LIKE ? OR oi.item_desc LIKE ?)")
        params.extend([f"%{q}%"] * 3)

    where = " AND ".join(conditions) if conditions else "1=1"

    sql = f"""
        SELECT
            o.id as order_id, o.year_month, o.order_seq, o.customer_name, o.memo,
            oi.id as item_id, oi.item_desc, oi.unit_price, oi.quantity, oi.amount,
            o.stock_amount, o.order_date, o.delivery_due, o.delivery_date,
            o.delivery_amount, o.sales_date, o.sales_amount, o.remark,
            o.collection_note, o.supplier_name, o.purchase_date,
            o.purchase_amount, o.purchase_due, o.discount_rate
        FROM orders o
        LEFT JOIN order_items oi ON oi.order_id = o.id
        WHERE {where}
        ORDER BY o.year_month DESC, o.order_seq ASC, oi.id ASC
    """
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    return rows


@app.get("/api/orders/months")
def order_months():
    conn = get_msm_db()
    rows = conn.execute("SELECT DISTINCT year_month FROM orders ORDER BY year_month DESC").fetchall()
    conn.close()
    return [r["year_month"] for r in rows]


class OrderRowUpdate(BaseModel):
    order_id: int
    item_id: Optional[int] = None
    field: str
    value: Optional[str] = None


@app.post("/api/orders/update-cell")
def update_order_cell(update: OrderRowUpdate):
    """Update a single cell in the spreadsheet."""
    conn = get_msm_db()

    # Fields that live on the order_items table
    item_fields = {"item_desc", "unit_price", "quantity", "amount"}
    # Fields that live on the orders table
    order_fields = {
        "customer_name", "memo", "order_date", "stock_amount",
        "delivery_due", "delivery_date", "delivery_amount",
        "sales_date", "sales_amount", "remark", "collection_note",
        "supplier_name", "purchase_date", "purchase_amount", "purchase_due",
        "order_seq", "discount_rate",
    }

    field = update.field
    value = update.value if update.value != "" else None

    if field in item_fields and update.item_id:
        conn.execute(
            f"UPDATE order_items SET {field} = ? WHERE id = ?",
            (value, update.item_id),
        )
    elif field in order_fields:
        conn.execute(
            f"UPDATE orders SET {field} = ? WHERE id = ?",
            (value, update.order_id),
        )
    else:
        conn.close()
        return {"ok": False, "error": f"Unknown field: {field}"}

    conn.commit()
    conn.close()
    return {"ok": True}


class NewOrderRow(BaseModel):
    year_month: str
    order_seq: Optional[int] = None
    customer_name: Optional[str] = None
    item_desc: Optional[str] = None


@app.post("/api/orders/add-row")
def add_order_row(row: NewOrderRow):
    """Add a new order + first item row."""
    conn = get_msm_db()

    # Auto-assign order_seq
    if not row.order_seq:
        r = conn.execute(
            "SELECT MAX(order_seq) FROM orders WHERE year_month = ?", (row.year_month,)
        ).fetchone()
        row.order_seq = (r[0] or 0) + 1

    cur = conn.execute(
        "INSERT INTO orders (year_month, order_seq, customer_name) VALUES (?, ?, ?)",
        (row.year_month, row.order_seq, row.customer_name),
    )
    order_id = cur.lastrowid

    item_id = None
    if row.item_desc:
        cur2 = conn.execute(
            "INSERT INTO order_items (order_id, item_desc) VALUES (?, ?)",
            (order_id, row.item_desc),
        )
        item_id = cur2.lastrowid

    conn.commit()
    conn.close()
    return {"ok": True, "order_id": order_id, "item_id": item_id, "order_seq": row.order_seq}


@app.post("/api/orders/add-item")
def add_order_item(order_id: int = Body(...), item_desc: str = Body("")):
    """Add a new item row to an existing order."""
    conn = get_msm_db()
    cur = conn.execute(
        "INSERT INTO order_items (order_id, item_desc) VALUES (?, ?)",
        (order_id, item_desc),
    )
    conn.commit()
    item_id = cur.lastrowid
    conn.close()
    return {"ok": True, "item_id": item_id}


@app.post("/api/orders/delete-row")
def delete_order_row(order_id: int = Body(...), item_id: Optional[int] = Body(None)):
    """Delete an item row, or entire order if no items left."""
    conn = get_msm_db()
    if item_id:
        conn.execute("DELETE FROM order_items WHERE id = ?", (item_id,))
        remaining = conn.execute(
            "SELECT COUNT(*) FROM order_items WHERE order_id = ?", (order_id,)
        ).fetchone()[0]
        if remaining == 0:
            conn.execute("DELETE FROM orders WHERE id = ?", (order_id,))
    else:
        conn.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
        conn.execute("DELETE FROM orders WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


# ============================================================
# API: Orders Excel Download / Upload
# ============================================================

@app.get("/api/orders/download")
def download_orders_excel(year_month: str = Query("")):
    """Download orders as Excel file matching the original 수주대장 format."""
    import openpyxl
    from openpyxl.styles import Font, Alignment, Border, Side, PatternFill

    conn = get_msm_db()
    if year_month:
        orders = conn.execute(
            "SELECT * FROM orders WHERE year_month = ? ORDER BY order_seq", (year_month,)
        ).fetchall()
    else:
        orders = conn.execute("SELECT * FROM orders ORDER BY year_month DESC, order_seq").fetchall()

    wb = openpyxl.Workbook()
    ws = wb.active

    # Parse year_month for title
    if year_month:
        parts = year_month.split("-")
        title = f"{parts[0]}년도 {int(parts[1])}월 수주대장 (한국밸브 서울영업소)"
    else:
        title = "수주대장 (한국밸브 서울영업소)"

    ws.title = year_month or "전체"
    thin = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin'),
    )
    header_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
    header_font = Font(bold=True, size=9)

    # Row 1: title
    ws.merge_cells("A1:T1")
    ws["A1"] = title
    ws["A1"].font = Font(bold=True, size=13)
    ws["A1"].alignment = Alignment(horizontal="center")

    # Row 3-4: headers (matching Excel layout)
    # 수주현황
    headers_r3 = ["NO", "업 체 명", "특이사항", "ITEM", "단가(VAT제외)", "수  량",
                   "수주일자", "금액", "재고판매", "납기일자", "납품일자", "납품금액",
                   "매출일자", "매출금액", "REMARK", "수금",
                   "매입업체", "발주일자", "매입금액", "매입납기"]

    for i, h in enumerate(headers_r3, 1):
        cell = ws.cell(row=3, column=i, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = thin
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # Column widths
    widths = [5, 14, 12, 40, 12, 5, 11, 13, 11, 11, 11, 13, 11, 13, 12, 10, 14, 11, 13, 11]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    # Data rows
    row_num = 4
    for order in orders:
        order = dict(order)
        items = conn.execute(
            "SELECT * FROM order_items WHERE order_id = ? ORDER BY id", (order["id"],)
        ).fetchall()

        # First row of this order
        first_item = dict(items[0]) if items else {}
        row_data = [
            order.get("order_seq"),
            order.get("customer_name"),
            order.get("memo") or (order.get("discount_rate") if order.get("discount_rate") else None),
            first_item.get("item_desc"),
            first_item.get("unit_price"),
            first_item.get("quantity"),
            order.get("order_date"),
            first_item.get("amount") or order.get("total_amount"),
            order.get("stock_amount"),
            order.get("delivery_due"),
            order.get("delivery_date"),
            order.get("delivery_amount"),
            order.get("sales_date"),
            order.get("sales_amount"),
            order.get("remark"),
            order.get("collection_note"),
            order.get("supplier_name"),
            order.get("purchase_date"),
            order.get("purchase_amount"),
            order.get("purchase_due"),
        ]
        for i, val in enumerate(row_data, 1):
            cell = ws.cell(row=row_num, column=i, value=val)
            cell.border = thin
            if isinstance(val, (int, float)) and val and i in (5, 8, 9, 12, 14, 19):
                cell.number_format = '#,##0'
        row_num += 1

        # Additional item rows
        for item in items[1:]:
            item = dict(item)
            ws.cell(row=row_num, column=4, value=item.get("item_desc")).border = thin
            ws.cell(row=row_num, column=5, value=item.get("unit_price")).border = thin
            ws.cell(row=row_num, column=6, value=item.get("quantity")).border = thin
            if item.get("amount"):
                c = ws.cell(row=row_num, column=8, value=item.get("amount"))
                c.border = thin
                c.number_format = '#,##0'
            row_num += 1

    conn.close()

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    from urllib.parse import quote
    filename = f"수주대장_{year_month or '전체'}.xlsx"
    encoded = quote(filename)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
    )


@app.post("/api/orders/upload")
async def upload_orders_excel(file: UploadFile = File(...), year_month: str = Query("")):
    """Upload an Excel file and import/replace orders for the given month."""
    import openpyxl

    content = await file.read()
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    ws = wb.active

    # Find header row
    header_row = None
    for r in range(1, min(10, ws.max_row + 1)):
        for c in range(1, ws.max_column + 1):
            v = ws.cell(r, c).value
            if v and ("ITEM" in str(v) or "업 체 명" in str(v)):
                header_row = r
                break
        if header_row:
            break

    if not header_row:
        return {"ok": False, "error": "Cannot find header row (ITEM or 업체명)"}

    # Build column mapping
    col_map = {}
    for c in range(1, ws.max_column + 1):
        v = str(ws.cell(header_row, c).value or "").strip()
        if "NO" == v:
            col_map["seq"] = c
        elif "업 체 명" in v or "업체명" in v:
            col_map["customer"] = c
        elif "특이사항" in v:
            col_map["memo"] = c
        elif "ITEM" in v:
            col_map["item"] = c
        elif "단가" in v:
            col_map["unit_price"] = c
        elif "수  량" in v or "수량" in v:
            col_map["qty"] = c
        elif "수주일자" in v:
            col_map["order_date"] = c
        elif v == "금액" and "amount" not in col_map:
            col_map["amount"] = c
        elif "재고판매" in v:
            col_map["stock"] = c
        elif "납기일자" in v and "due" not in col_map:
            col_map["due"] = c
        elif "납품일자" in v:
            col_map["delivery_date"] = c
        elif "납품금액" in v:
            col_map["delivery_amount"] = c
        elif "매출일자" in v:
            col_map["sales_date"] = c
        elif "매출금액" in v:
            col_map["sales_amount"] = c
        elif "REMARK" in v.upper():
            col_map["remark"] = c
        elif "수금" in v:
            col_map["collection"] = c
        elif c > 14 and "업체" in v:
            col_map["supplier"] = c
        elif c > 14 and "발주일" in v:
            col_map["purchase_date"] = c
        elif c > 14 and "금액" in v:
            col_map["purchase_amount"] = c
        elif c > 14 and "납기" in v:
            col_map["purchase_due"] = c

    def cell_val(r, key):
        c = col_map.get(key)
        if not c:
            return None
        return ws.cell(r, c).value

    def to_date_str(v):
        if v is None:
            return None
        if isinstance(v, datetime):
            return v.strftime("%Y-%m-%d")
        if isinstance(v, date):
            return v.isoformat()
        return str(v).strip() or None

    def to_int(v):
        if v is None or v == "":
            return None
        try:
            return int(float(v))
        except (ValueError, TypeError):
            return None

    # Parse rows
    conn = get_msm_db()

    # Delete existing data for this month if specified
    if year_month:
        order_ids = [r[0] for r in conn.execute(
            "SELECT id FROM orders WHERE year_month = ?", (year_month,)
        ).fetchall()]
        if order_ids:
            placeholders = ",".join("?" * len(order_ids))
            conn.execute(f"DELETE FROM order_items WHERE order_id IN ({placeholders})", order_ids)
            conn.execute(f"DELETE FROM orders WHERE id IN ({placeholders})", order_ids)
        conn.commit()

    imported = 0
    current_order_id = None

    for r in range(header_row + 1, ws.max_row + 1):
        seq = cell_val(r, "seq")
        customer = cell_val(r, "customer")
        item = cell_val(r, "item")

        # Skip completely empty rows
        if not seq and not customer and not item:
            continue
        # Skip TOTAL rows
        if customer and "TOTAL" in str(customer):
            continue

        # New order starts with a sequence number
        if seq and isinstance(seq, (int, float)) and seq > 0:
            memo = cell_val(r, "memo")
            discount_rate = None
            memo_str = None
            if isinstance(memo, (int, float)) and 0 < memo < 1:
                discount_rate = memo
            elif memo:
                memo_str = str(memo).strip() or None

            cur = conn.execute("""
                INSERT INTO orders (year_month, order_seq, customer_name, memo, discount_rate,
                    order_date, total_amount, stock_amount, delivery_due, delivery_date,
                    delivery_amount, sales_date, sales_amount, remark, collection_note,
                    supplier_name, purchase_date, purchase_amount, purchase_due)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                year_month, int(seq), str(customer).strip() if customer else None,
                memo_str, discount_rate,
                to_date_str(cell_val(r, "order_date")),
                to_int(cell_val(r, "amount")),
                to_int(cell_val(r, "stock")),
                to_date_str(cell_val(r, "due")),
                to_date_str(cell_val(r, "delivery_date")),
                to_int(cell_val(r, "delivery_amount")),
                to_date_str(cell_val(r, "sales_date")),
                to_int(cell_val(r, "sales_amount")),
                str(cell_val(r, "remark")).strip() if cell_val(r, "remark") else None,
                str(cell_val(r, "collection")).strip() if cell_val(r, "collection") else None,
                str(cell_val(r, "supplier")).strip() if cell_val(r, "supplier") else None,
                to_date_str(cell_val(r, "purchase_date")),
                to_int(cell_val(r, "purchase_amount")),
                to_date_str(cell_val(r, "purchase_due")),
            ))
            current_order_id = cur.lastrowid
            imported += 1

        # Add item if present
        if item and current_order_id and str(item).strip():
            conn.execute("""
                INSERT INTO order_items (order_id, item_desc, unit_price, quantity, amount)
                VALUES (?, ?, ?, ?, ?)
            """, (
                current_order_id,
                str(item).strip(),
                to_int(cell_val(r, "unit_price")),
                to_int(cell_val(r, "qty")),
                to_int(cell_val(r, "amount")),
            ))

    conn.commit()
    conn.close()
    return {"ok": True, "imported": imported, "year_month": year_month}


# ============================================================
# API: Orders (legacy paginated — kept for compatibility)
# ============================================================

@app.get("/api/orders")
def list_orders(
    year_month: str = Query(""), customer: str = Query(""),
    q: str = Query(""), page: int = Query(1), per_page: int = Query(50),
):
    conn = get_msm_db()
    conditions = []
    params = []
    if year_month:
        conditions.append("o.year_month = ?")
        params.append(year_month)
    if customer:
        conditions.append("o.customer_name LIKE ?")
        params.append(f"%{customer}%")
    if q:
        conditions.append("(o.order_no LIKE ? OR o.customer_name LIKE ? OR oi.item_desc LIKE ?)")
        params.extend([f"%{q}%"] * 3)
    where = " AND ".join(conditions) if conditions else "1=1"
    offset = (page - 1) * per_page
    total = conn.execute(f"SELECT COUNT(DISTINCT o.id) FROM orders o LEFT JOIN order_items oi ON oi.order_id=o.id WHERE {where}", params).fetchone()[0]
    sql = f"SELECT DISTINCT o.* FROM orders o LEFT JOIN order_items oi ON oi.order_id=o.id WHERE {where} ORDER BY o.year_month DESC, o.order_seq DESC LIMIT ? OFFSET ?"
    orders = [dict(r) for r in conn.execute(sql, params + [per_page, offset]).fetchall()]
    for order in orders:
        items = conn.execute("SELECT * FROM order_items WHERE order_id=? ORDER BY id", (order["id"],)).fetchall()
        order["items"] = [dict(i) for i in items]
    conn.close()
    return {"total": total, "page": page, "per_page": per_page, "orders": orders}


# ============================================================
# API: Purchase Orders (발주목록)
# ============================================================

@app.get("/api/purchase-orders")
def list_purchase_orders(
    year: int = Query(0), supplier: str = Query(""),
    q: str = Query(""), page: int = Query(1), per_page: int = Query(50),
):
    conn = get_msm_db()
    conditions = []
    params = []
    if year:
        conditions.append("year = ?")
        params.append(year)
    if supplier:
        conditions.append("supplier_name LIKE ?")
        params.append(f"%{supplier}%")
    if q:
        conditions.append("(po_number LIKE ? OR item_desc LIKE ? OR customer_name LIKE ?)")
        params.extend([f"%{q}%"] * 3)
    where = " AND ".join(conditions) if conditions else "1=1"
    offset = (page - 1) * per_page
    total = conn.execute(f"SELECT COUNT(*) FROM purchase_orders WHERE {where}", params).fetchone()[0]
    rows = conn.execute(f"SELECT * FROM purchase_orders WHERE {where} ORDER BY order_date DESC NULLS LAST, id DESC LIMIT ? OFFSET ?", params + [per_page, offset]).fetchall()
    conn.close()
    return {"total": total, "page": page, "per_page": per_page, "items": [dict(r) for r in rows]}

@app.get("/api/purchase-orders/years")
def po_years():
    conn = get_msm_db()
    rows = conn.execute("SELECT DISTINCT year FROM purchase_orders ORDER BY year DESC").fetchall()
    conn.close()
    return [r["year"] for r in rows]


# ============================================================
# API: Purchases (매입 내역)
# ============================================================

@app.get("/api/purchases")
def list_purchases(year_month: str = Query(""), q: str = Query(""), page: int = Query(1), per_page: int = Query(50)):
    conn = get_msm_db()
    conditions = []
    params = []
    if year_month:
        conditions.append("year_month = ?")
        params.append(year_month)
    if q:
        conditions.append("(po_ref LIKE ? OR category LIKE ? OR memo LIKE ?)")
        params.extend([f"%{q}%"] * 3)
    where = " AND ".join(conditions) if conditions else "1=1"
    offset = (page - 1) * per_page
    total = conn.execute(f"SELECT COUNT(*) FROM purchases WHERE {where}", params).fetchone()[0]
    rows = conn.execute(f"SELECT * FROM purchases WHERE {where} ORDER BY year_month DESC, id DESC LIMIT ? OFFSET ?", params + [per_page, offset]).fetchall()
    conn.close()
    return {"total": total, "page": page, "per_page": per_page, "items": [dict(r) for r in rows]}

@app.get("/api/purchases/months")
def purchase_months():
    conn = get_msm_db()
    rows = conn.execute("SELECT DISTINCT year_month FROM purchases ORDER BY year_month DESC").fetchall()
    conn.close()
    return [r["year_month"] for r in rows]

@app.get("/api/purchases/summary")
def purchase_summary(year_month: str = Query("")):
    conn = get_msm_db()
    w = "WHERE year_month = ?" if year_month else ""
    p = (year_month,) if year_month else ()
    row = conn.execute(f"SELECT COUNT(*) as cnt, SUM(purchase_amount) as total_purchase, SUM(sales_amount) as total_sales, SUM(profit_half) as total_profit FROM purchases {w}", p).fetchone()
    conn.close()
    return dict(row)


# ============================================================
# API: Dashboard stats
# ============================================================

@app.get("/api/stats")
def dashboard_stats():
    conn = get_msm_db()
    orders = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    po = conn.execute("SELECT COUNT(*) FROM purchase_orders").fetchone()[0]
    purchases = conn.execute("SELECT COUNT(*) FROM purchases").fetchone()[0]
    conn.close()
    conn2 = get_price_db()
    prices = conn2.execute("SELECT COUNT(*) FROM price_list_items").fetchone()[0]
    conn2.close()
    return {"orders": orders, "purchase_orders": po, "purchases": purchases, "price_items": prices}


# ============================================================
# Serve static HTML
# ============================================================

@app.get("/", response_class=HTMLResponse)
def index():
    html_path = os.path.join(STATIC_DIR, "index.html")
    with open(html_path, encoding="utf-8") as f:
        return f.read()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web.server:app", host="0.0.0.0", port=8000, reload=True)
