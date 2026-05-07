"""
MSM Valve Management System — FastAPI Web Server
Single unified backend serving API + static HTML.
"""
import sqlite3
import os
import sys
from datetime import date
from typing import Optional

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
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
    """Search price list by pasting valve spec text."""
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
# API: Orders (수주대장)
# ============================================================

@app.get("/api/orders")
def list_orders(
    year_month: str = Query(""),
    customer: str = Query(""),
    q: str = Query(""),
    page: int = Query(1),
    per_page: int = Query(50),
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
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])

    where = " AND ".join(conditions) if conditions else "1=1"
    offset = (page - 1) * per_page

    # Count
    count_sql = f"""
        SELECT COUNT(DISTINCT o.id) FROM orders o
        LEFT JOIN order_items oi ON oi.order_id = o.id
        WHERE {where}
    """
    total = conn.execute(count_sql, params).fetchone()[0]

    # Data
    sql = f"""
        SELECT DISTINCT o.* FROM orders o
        LEFT JOIN order_items oi ON oi.order_id = o.id
        WHERE {where}
        ORDER BY o.year_month DESC, o.order_seq DESC
        LIMIT ? OFFSET ?
    """
    orders = [dict(r) for r in conn.execute(sql, params + [per_page, offset]).fetchall()]

    # Attach items
    for order in orders:
        items = conn.execute(
            "SELECT * FROM order_items WHERE order_id = ? ORDER BY id", (order["id"],)
        ).fetchall()
        order["items"] = [dict(i) for i in items]

    conn.close()
    return {"total": total, "page": page, "per_page": per_page, "orders": orders}


@app.get("/api/orders/months")
def order_months():
    conn = get_msm_db()
    rows = conn.execute(
        "SELECT DISTINCT year_month FROM orders ORDER BY year_month DESC"
    ).fetchall()
    conn.close()
    return [r["year_month"] for r in rows]


# ============================================================
# API: Purchase Orders (발주목록)
# ============================================================

@app.get("/api/purchase-orders")
def list_purchase_orders(
    year: int = Query(0),
    supplier: str = Query(""),
    q: str = Query(""),
    page: int = Query(1),
    per_page: int = Query(50),
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
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])

    where = " AND ".join(conditions) if conditions else "1=1"
    offset = (page - 1) * per_page

    total = conn.execute(f"SELECT COUNT(*) FROM purchase_orders WHERE {where}", params).fetchone()[0]

    rows = conn.execute(
        f"SELECT * FROM purchase_orders WHERE {where} ORDER BY order_date DESC NULLS LAST, id DESC LIMIT ? OFFSET ?",
        params + [per_page, offset],
    ).fetchall()
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
def list_purchases(
    year_month: str = Query(""),
    q: str = Query(""),
    page: int = Query(1),
    per_page: int = Query(50),
):
    conn = get_msm_db()
    conditions = []
    params = []

    if year_month:
        conditions.append("year_month = ?")
        params.append(year_month)
    if q:
        conditions.append("(po_ref LIKE ? OR category LIKE ? OR memo LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])

    where = " AND ".join(conditions) if conditions else "1=1"
    offset = (page - 1) * per_page

    total = conn.execute(f"SELECT COUNT(*) FROM purchases WHERE {where}", params).fetchone()[0]

    rows = conn.execute(
        f"SELECT * FROM purchases WHERE {where} ORDER BY year_month DESC, id DESC LIMIT ? OFFSET ?",
        params + [per_page, offset],
    ).fetchall()
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
    if year_month:
        row = conn.execute("""
            SELECT COUNT(*) as cnt,
                   SUM(purchase_amount) as total_purchase,
                   SUM(sales_amount) as total_sales,
                   SUM(profit_half) as total_profit
            FROM purchases WHERE year_month = ?
        """, (year_month,)).fetchone()
    else:
        row = conn.execute("""
            SELECT COUNT(*) as cnt,
                   SUM(purchase_amount) as total_purchase,
                   SUM(sales_amount) as total_sales,
                   SUM(profit_half) as total_profit
            FROM purchases
        """).fetchone()
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

    return {
        "orders": orders,
        "purchase_orders": po,
        "purchases": purchases,
        "price_items": prices,
    }


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
