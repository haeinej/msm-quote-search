"""
MSM Valve Management System — FastAPI Web Server
Uses Supabase REST API if configured, else falls back to SQLite.
"""
import os
import sys
import io
import secrets
from datetime import date, datetime
from typing import Optional

from fastapi import FastAPI, Query, Request, UploadFile, File, Body, Cookie, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from parser import parse_query
from db.connection import is_supabase, get_supabase, get_sqlite

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

# ============================================================
# Auth
# ============================================================
INTERNAL_PASSWORD = os.environ.get("MSM_PASSWORD", "msm2026!")
_valid_tokens: set[str] = set()


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path == "/api/login" or path == "/login" or path.startswith("/static"):
            return await call_next(request)
        token = request.cookies.get("msm_token")
        if not token or token not in _valid_tokens:
            if path.startswith("/api/"):
                return JSONResponse({"detail": "Unauthorized"}, status_code=401)
            login_path = os.path.join(STATIC_DIR, "login.html")
            with open(login_path, encoding="utf-8") as f:
                return HTMLResponse(f.read())
        return await call_next(request)


app = FastAPI(title="MSM Valve Management", version="2.0.0")
app.add_middleware(AuthMiddleware)


@app.post("/api/login")
async def login(request: Request):
    body = await request.json()
    if body.get("password") == INTERNAL_PASSWORD:
        token = secrets.token_hex(32)
        _valid_tokens.add(token)
        response = JSONResponse({"ok": True})
        response.set_cookie("msm_token", token, httponly=True, samesite="lax", max_age=86400 * 30)
        return response
    return JSONResponse({"ok": False, "error": "비밀번호가 틀렸습니다"}, status_code=403)


@app.post("/api/logout")
async def logout(msm_token: Optional[str] = Cookie(None)):
    if msm_token:
        _valid_tokens.discard(msm_token)
    response = JSONResponse({"ok": True})
    response.delete_cookie("msm_token")
    return response


# ============================================================
# Helpers
# ============================================================

def sb():
    return get_supabase()

def _sq(table):
    return sb().table(table)


# ============================================================
# API: Price Search
# ============================================================

@app.get("/api/search")
def search_price(q: str = Query(""), discount: str = Query("")):
    parsed = parse_query(q)
    if discount:
        parsed["discount_rate"] = discount

    if is_supabase():
        query = _sq("price_catalog").select("*")
        if parsed.get("product_type"):
            query = query.eq("product_type", parsed["product_type"])
        if parsed.get("pressure_class"):
            query = query.eq("pressure_class", parsed["pressure_class"])
        if parsed.get("size_a"):
            query = query.eq("size_a", parsed["size_a"])
        if parsed.get("discount_rate"):
            query = query.eq("discount_rate", parsed["discount_rate"])
        rows = query.order("product_type").order("pressure_class").order("size_a").order("discount_rate").execute().data
    else:
        conn = get_sqlite("한국밸브_협가표.db")
        conditions, params = [], []
        for key, col in [("product_type","product_type"),("pressure_class","pressure_class"),("size_a","size_a"),("discount_rate","discount_rate")]:
            if parsed.get(key):
                conditions.append(f"{col} = ?"); params.append(parsed[key])
        where = " AND ".join(conditions) if conditions else "1=1"
        rows = [dict(r) for r in conn.execute(f"SELECT * FROM price_list_items WHERE {where} ORDER BY product_type,pressure_class,size_a,discount_rate", params).fetchall()]
        conn.close()

    return {
        "parsed": {k: v for k, v in parsed.items() if k not in ("raw_query", "material") and v is not None and v != []},
        "count": len(rows),
        "status": "exact" if len(rows) == 1 else ("multiple" if rows else "none"),
        "results": rows,
    }


# ============================================================
# API: Orders (수주대장)
# ============================================================

@app.get("/api/orders/rows")
def list_order_rows(year_month: str = Query(""), q: str = Query("")):
    if is_supabase():
        oq = _sq("orders").select("*")
        if year_month: oq = oq.eq("year_month", year_month)
        if q: oq = oq.or_(f"customer_name.ilike.%{q}%,memo.ilike.%{q}%")
        orders = oq.order("year_month", desc=True).order("order_seq").execute().data
        if not orders: return []
        oids = [o["id"] for o in orders]
        all_items = []
        for i in range(0, len(oids), 50):
            all_items.extend(_sq("order_items").select("*").in_("order_id", oids[i:i+50]).order("id").execute().data)
        items_map = {}
        for it in all_items: items_map.setdefault(it["order_id"], []).append(it)
        rows = []
        for o in orders:
            oi_list = items_map.get(o["id"], [{"id":None,"item_desc":None,"unit_price":None,"quantity":None,"amount":None}])
            for it in oi_list:
                rows.append({**{k: o.get(k) for k in ["year_month","order_seq","customer_name","memo","stock_amount","order_date","delivery_due","delivery_date","delivery_amount","sales_date","sales_amount","remark","collection_note","supplier_name","purchase_date","purchase_amount","purchase_due","discount_rate"]},
                    "order_id": o["id"], "item_id": it.get("id"), "item_desc": it.get("item_desc"),
                    "unit_price": it.get("unit_price"), "quantity": it.get("quantity"), "amount": it.get("amount")})
        return rows
    else:
        conn = get_sqlite()
        conditions, params = [], []
        if year_month: conditions.append("o.year_month = ?"); params.append(year_month)
        if q: conditions.append("(o.customer_name LIKE ? OR o.memo LIKE ? OR oi.item_desc LIKE ?)"); params.extend([f"%{q}%"]*3)
        where = " AND ".join(conditions) if conditions else "1=1"
        rows = [dict(r) for r in conn.execute(f"""
            SELECT o.id as order_id, o.year_month, o.order_seq, o.customer_name, o.memo,
                oi.id as item_id, oi.item_desc, oi.unit_price, oi.quantity, oi.amount,
                o.stock_amount, o.order_date, o.delivery_due, o.delivery_date,
                o.delivery_amount, o.sales_date, o.sales_amount, o.remark,
                o.collection_note, o.supplier_name, o.purchase_date,
                o.purchase_amount, o.purchase_due, o.discount_rate
            FROM orders o LEFT JOIN order_items oi ON oi.order_id = o.id
            WHERE {where} ORDER BY o.year_month DESC, o.order_seq ASC, oi.id ASC
        """, params).fetchall()]
        conn.close()
        return rows

@app.get("/api/orders/months")
def order_months():
    if is_supabase():
        result = _sq("orders").select("year_month").execute()
        return sorted(set(r["year_month"] for r in result.data if r["year_month"]), reverse=True)
    else:
        conn = get_sqlite()
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
    item_fields = {"item_desc","unit_price","quantity","amount"}
    order_fields = {"customer_name","memo","order_date","stock_amount","delivery_due","delivery_date","delivery_amount","sales_date","sales_amount","remark","collection_note","supplier_name","purchase_date","purchase_amount","purchase_due","order_seq","discount_rate"}
    field, value = update.field, update.value if update.value != "" else None
    numeric = {"unit_price","quantity","amount","stock_amount","delivery_amount","sales_amount","purchase_amount"}
    if field in numeric and value is not None:
        try: value = int(float(str(value).replace(",","")))
        except: pass
    if is_supabase():
        if field in item_fields and update.item_id: _sq("order_items").update({field:value}).eq("id",update.item_id).execute()
        elif field in order_fields: _sq("orders").update({field:value}).eq("id",update.order_id).execute()
        else: return {"ok":False,"error":f"Unknown field: {field}"}
    else:
        conn = get_sqlite()
        if field in item_fields and update.item_id: conn.execute(f"UPDATE order_items SET {field}=? WHERE id=?",(value,update.item_id))
        elif field in order_fields: conn.execute(f"UPDATE orders SET {field}=? WHERE id=?",(value,update.order_id))
        else: conn.close(); return {"ok":False,"error":f"Unknown field: {field}"}
        conn.commit(); conn.close()
    return {"ok":True}

class NewOrderRow(BaseModel):
    year_month: str
    order_seq: Optional[int] = None
    customer_name: Optional[str] = None
    item_desc: Optional[str] = None

@app.post("/api/orders/add-row")
def add_order_row(row: NewOrderRow):
    if is_supabase():
        if not row.order_seq:
            r = _sq("orders").select("order_seq").ilike("year_month",f"{row.year_month[:4]}%").order("order_seq",desc=True).limit(1).execute()
            row.order_seq = (r.data[0]["order_seq"]+1) if r.data else 1
        o = _sq("orders").insert({"year_month":row.year_month,"order_seq":row.order_seq,"customer_name":row.customer_name}).execute()
        order_id = o.data[0]["id"]
        item_id = None
        if row.item_desc:
            i = _sq("order_items").insert({"order_id":order_id,"item_desc":row.item_desc}).execute()
            item_id = i.data[0]["id"]
    else:
        conn = get_sqlite()
        if not row.order_seq:
            r = conn.execute("SELECT MAX(order_seq) FROM orders WHERE year_month LIKE ?",(row.year_month[:4]+"%",)).fetchone()
            row.order_seq = (r[0] or 0)+1
        cur = conn.execute("INSERT INTO orders (year_month,order_seq,customer_name) VALUES (?,?,?)",(row.year_month,row.order_seq,row.customer_name))
        order_id = cur.lastrowid
        item_id = None
        if row.item_desc:
            cur2 = conn.execute("INSERT INTO order_items (order_id,item_desc) VALUES (?,?)",(order_id,row.item_desc))
            item_id = cur2.lastrowid
        conn.commit(); conn.close()
    return {"ok":True,"order_id":order_id,"item_id":item_id,"order_seq":row.order_seq}

@app.post("/api/orders/add-item")
def add_order_item(order_id: int = Body(...), item_desc: str = Body("")):
    if is_supabase():
        r = _sq("order_items").insert({"order_id":order_id,"item_desc":item_desc}).execute()
        return {"ok":True,"item_id":r.data[0]["id"]}
    else:
        conn = get_sqlite()
        cur = conn.execute("INSERT INTO order_items (order_id,item_desc) VALUES (?,?)",(order_id,item_desc))
        item_id = cur.lastrowid; conn.commit(); conn.close()
        return {"ok":True,"item_id":item_id}

@app.post("/api/orders/delete-row")
def delete_order_row(order_id: int = Body(...), item_id: Optional[int] = Body(None)):
    if is_supabase():
        if item_id:
            _sq("order_items").delete().eq("id",item_id).execute()
            rem = _sq("order_items").select("id",count="exact").eq("order_id",order_id).execute()
            if rem.count == 0: _sq("orders").delete().eq("id",order_id).execute()
        else:
            _sq("order_items").delete().eq("order_id",order_id).execute()
            _sq("orders").delete().eq("id",order_id).execute()
    else:
        conn = get_sqlite()
        if item_id:
            conn.execute("DELETE FROM order_items WHERE id=?",(item_id,))
            rem = conn.execute("SELECT COUNT(*) FROM order_items WHERE order_id=?",(order_id,)).fetchone()[0]
            if rem == 0: conn.execute("DELETE FROM orders WHERE id=?",(order_id,))
        else:
            conn.execute("DELETE FROM order_items WHERE order_id=?",(order_id,))
            conn.execute("DELETE FROM orders WHERE id=?",(order_id,))
        conn.commit(); conn.close()
    return {"ok":True}

@app.get("/api/orders/download")
def download_orders_excel(year_month: str = Query("")):
    import openpyxl
    from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
    from urllib.parse import quote
    if is_supabase():
        oq = _sq("orders").select("*")
        if year_month: oq = oq.eq("year_month",year_month)
        orders = oq.order("order_seq").execute().data
        oids = [o["id"] for o in orders]
        all_items = []
        for i in range(0,len(oids),50):
            all_items.extend(_sq("order_items").select("*").in_("order_id",oids[i:i+50]).order("id").execute().data)
        items_map = {}
        for it in all_items: items_map.setdefault(it["order_id"],[]).append(it)
    else:
        conn = get_sqlite()
        orders = [dict(r) for r in conn.execute("SELECT * FROM orders WHERE year_month=? ORDER BY order_seq",(year_month,)).fetchall()] if year_month else [dict(r) for r in conn.execute("SELECT * FROM orders ORDER BY year_month DESC,order_seq").fetchall()]
        items_map = {}
        for o in orders: items_map[o["id"]] = [dict(r) for r in conn.execute("SELECT * FROM order_items WHERE order_id=? ORDER BY id",(o["id"],)).fetchall()]
        conn.close()

    wb = openpyxl.Workbook(); ws = wb.active
    title = f"{year_month.split('-')[0]}년도 {int(year_month.split('-')[1])}월 수주대장 (한국밸브 서울영업소)" if year_month else "수주대장"
    ws.title = year_month or "전체"
    thin = Border(left=Side(style='thin'),right=Side(style='thin'),top=Side(style='thin'),bottom=Side(style='thin'))
    hf = PatternFill(start_color="D9E1F2",end_color="D9E1F2",fill_type="solid")
    ws.merge_cells("A1:T1"); ws["A1"]=title; ws["A1"].font=Font(bold=True,size=13); ws["A1"].alignment=Alignment(horizontal="center")
    hdrs = ["NO","업 체 명","특이사항","ITEM","단가(VAT제외)","수  량","수주일자","금액","재고판매","납기일자","납품일자","납품금액","매출일자","매출금액","REMARK","수금","매입업체","발주일자","매입금액","매입납기"]
    ws_w = [5,14,12,40,12,5,11,13,11,11,11,13,11,13,12,10,14,11,13,11]
    for i,(h,w) in enumerate(zip(hdrs,ws_w),1):
        c=ws.cell(row=3,column=i,value=h); c.font=Font(bold=True,size=9); c.fill=hf; c.border=thin; c.alignment=Alignment(horizontal="center",vertical="center",wrap_text=True)
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width=w
    rn = 4
    for order in orders:
        items = items_map.get(order["id"],[])
        fi = items[0] if items else {}
        rd = [order.get("order_seq"),order.get("customer_name"),order.get("memo") or order.get("discount_rate"),fi.get("item_desc"),fi.get("unit_price"),fi.get("quantity"),order.get("order_date"),fi.get("amount") or order.get("total_amount"),order.get("stock_amount"),order.get("delivery_due"),order.get("delivery_date"),order.get("delivery_amount"),order.get("sales_date"),order.get("sales_amount"),order.get("remark"),order.get("collection_note"),order.get("supplier_name"),order.get("purchase_date"),order.get("purchase_amount"),order.get("purchase_due")]
        for i,v in enumerate(rd,1):
            c=ws.cell(row=rn,column=i,value=v); c.border=thin
            if isinstance(v,(int,float)) and v and i in(5,8,9,12,14,19): c.number_format='#,##0'
        rn+=1
        for it in items[1:]:
            ws.cell(row=rn,column=4,value=it.get("item_desc")).border=thin
            ws.cell(row=rn,column=5,value=it.get("unit_price")).border=thin
            ws.cell(row=rn,column=6,value=it.get("quantity")).border=thin
            if it.get("amount"): c=ws.cell(row=rn,column=8,value=it.get("amount")); c.border=thin; c.number_format='#,##0'
            rn+=1
    buf=io.BytesIO(); wb.save(buf); buf.seek(0)
    fn=f"수주대장_{year_month or '전체'}.xlsx"
    return StreamingResponse(buf,media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":f"attachment; filename*=UTF-8''{quote(fn)}"})

@app.post("/api/orders/upload")
async def upload_orders_excel(file: UploadFile = File(...), year_month: str = Query("")):
    import openpyxl
    if not year_month: return {"ok":False,"error":"year_month required"}
    content = await file.read(); wb = openpyxl.load_workbook(io.BytesIO(content),data_only=True); ws = wb.active
    header_row = None
    for r in range(1,min(10,ws.max_row+1)):
        for c in range(1,ws.max_column+1):
            v = ws.cell(r,c).value
            if v and ("ITEM" in str(v) or "업 체 명" in str(v)): header_row=r; break
        if header_row: break
    if not header_row: return {"ok":False,"error":"Cannot find header row"}
    col_map={}
    for c in range(1,ws.max_column+1):
        v=str(ws.cell(header_row,c).value or "").strip()
        if "NO"==v:col_map["seq"]=c
        elif "업 체 명" in v or "업체명" in v:col_map["customer"]=c
        elif "특이사항" in v:col_map["memo"]=c
        elif "ITEM" in v:col_map["item"]=c
        elif "단가" in v:col_map["unit_price"]=c
        elif "수  량" in v or "수량" in v:col_map["qty"]=c
        elif "수주일자" in v:col_map["order_date"]=c
        elif v=="금액" and "amount" not in col_map:col_map["amount"]=c
        elif "재고판매" in v:col_map["stock"]=c
        elif "납기일자" in v and "due" not in col_map:col_map["due"]=c
        elif "납품일자" in v:col_map["delivery_date"]=c
        elif "납품금액" in v:col_map["delivery_amount"]=c
        elif "매출일자" in v:col_map["sales_date"]=c
        elif "매출금액" in v:col_map["sales_amount"]=c
        elif "REMARK" in v.upper():col_map["remark"]=c
        elif "수금" in v:col_map["collection"]=c
        elif c>14 and "업체" in v:col_map["supplier"]=c
        elif c>14 and "발주일" in v:col_map["purchase_date"]=c
        elif c>14 and "금액" in v:col_map["purchase_amount"]=c
        elif c>14 and "납기" in v:col_map["purchase_due"]=c
    def cv(r,k): c=col_map.get(k); return ws.cell(r,c).value if c else None
    def tds(v):
        if v is None: return None
        if isinstance(v,datetime): return v.strftime("%Y-%m-%d")
        if isinstance(v,date): return v.isoformat()
        return str(v).strip() or None
    def ti(v):
        if v is None or v=="": return None
        try: return int(float(v))
        except: return None
    # Delete existing
    if is_supabase():
        ex=_sq("orders").select("id").eq("year_month",year_month).execute()
        if ex.data:
            eids=[r["id"] for r in ex.data]
            for i in range(0,len(eids),50): _sq("order_items").delete().in_("order_id",eids[i:i+50]).execute()
            _sq("orders").delete().eq("year_month",year_month).execute()
    else:
        conn=get_sqlite()
        oids=[r[0] for r in conn.execute("SELECT id FROM orders WHERE year_month=?",(year_month,)).fetchall()]
        if oids:
            ph=",".join("?"*len(oids)); conn.execute(f"DELETE FROM order_items WHERE order_id IN ({ph})",oids); conn.execute(f"DELETE FROM orders WHERE id IN ({ph})",oids)
        conn.commit()
    imported=0; coid=None
    for r in range(header_row+1,ws.max_row+1):
        seq,cust,item=cv(r,"seq"),cv(r,"customer"),cv(r,"item")
        if not seq and not cust and not item: continue
        if cust and "TOTAL" in str(cust): continue
        if seq and isinstance(seq,(int,float)) and seq>0:
            mv=cv(r,"memo"); dr,ms=None,None
            if isinstance(mv,(int,float)) and 0<mv<1: dr=mv
            elif mv: ms=str(mv).strip() or None
            od={"year_month":year_month,"order_seq":int(seq),"customer_name":str(cust).strip() if cust else None,"memo":ms,"discount_rate":dr,"order_date":tds(cv(r,"order_date")),"total_amount":ti(cv(r,"amount")),"stock_amount":ti(cv(r,"stock")),"delivery_due":tds(cv(r,"due")),"delivery_date":tds(cv(r,"delivery_date")),"delivery_amount":ti(cv(r,"delivery_amount")),"sales_date":tds(cv(r,"sales_date")),"sales_amount":ti(cv(r,"sales_amount")),"remark":str(cv(r,"remark")).strip() if cv(r,"remark") else None,"collection_note":str(cv(r,"collection")).strip() if cv(r,"collection") else None,"supplier_name":str(cv(r,"supplier")).strip() if cv(r,"supplier") else None,"purchase_date":tds(cv(r,"purchase_date")),"purchase_amount":ti(cv(r,"purchase_amount")),"purchase_due":tds(cv(r,"purchase_due"))}
            if is_supabase(): res=_sq("orders").insert(od).execute(); coid=res.data[0]["id"]
            else: cur=conn.execute("INSERT INTO orders (year_month,order_seq,customer_name,memo,discount_rate,order_date,total_amount,stock_amount,delivery_due,delivery_date,delivery_amount,sales_date,sales_amount,remark,collection_note,supplier_name,purchase_date,purchase_amount,purchase_due) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",tuple(od.values())); coid=cur.lastrowid
            imported+=1
        if item and coid and str(item).strip():
            id_={"order_id":coid,"item_desc":str(item).strip(),"unit_price":ti(cv(r,"unit_price")),"quantity":ti(cv(r,"qty")),"amount":ti(cv(r,"amount"))}
            if is_supabase(): _sq("order_items").insert(id_).execute()
            else: conn.execute("INSERT INTO order_items (order_id,item_desc,unit_price,quantity,amount) VALUES (?,?,?,?,?)",tuple(id_.values()))
    if not is_supabase(): conn.commit(); conn.close()
    return {"ok":True,"imported":imported,"year_month":year_month}


# ============================================================
# API: Purchase Orders (발주목록)
# ============================================================

@app.get("/api/purchase-orders/years")
def po_years():
    if is_supabase():
        r=_sq("purchase_orders").select("year").execute()
        return sorted(set(x["year"] for x in r.data if x["year"]),reverse=True)
    else:
        conn=get_sqlite(); rows=conn.execute("SELECT DISTINCT year FROM purchase_orders ORDER BY year DESC").fetchall(); conn.close()
        return [r["year"] for r in rows]

@app.get("/api/purchase-orders/rows")
def list_po_rows(year: int = Query(0), q: str = Query("")):
    if is_supabase():
        qr=_sq("purchase_orders").select("*")
        if year: qr=qr.eq("year",year)
        if q: qr=qr.or_(f"po_number.ilike.%{q}%,item_desc.ilike.%{q}%,supplier_name.ilike.%{q}%")
        return qr.order("order_date",nullsfirst=False).order("id").execute().data
    else:
        conn=get_sqlite(); conds,params=[],[]
        if year: conds.append("year=?"); params.append(year)
        if q: conds.append("(po_number LIKE ? OR item_desc LIKE ? OR supplier_name LIKE ?)"); params.extend([f"%{q}%"]*3)
        w=" AND ".join(conds) if conds else "1=1"
        rows=[dict(r) for r in conn.execute(f"SELECT * FROM purchase_orders WHERE {w} ORDER BY order_date ASC NULLS LAST,id ASC",params).fetchall()]
        conn.close(); return rows

class POCellUpdate(BaseModel):
    po_id: int; field: str; value: Optional[str] = None

@app.post("/api/purchase-orders/update-cell")
def update_po_cell(update: POCellUpdate):
    valid={"po_number","supplier_name","item_desc","quantity","amount","order_date","delivery_due","delivery_date","shipped","customer_name","remark"}
    if update.field not in valid: return {"ok":False,"error":f"Unknown field: {update.field}"}
    value=update.value if update.value!="" else None
    if update.field in("quantity","amount") and value is not None:
        try: value=int(float(str(value).replace(",","")))
        except: pass
    if is_supabase(): _sq("purchase_orders").update({update.field:value}).eq("id",update.po_id).execute()
    else: conn=get_sqlite(); conn.execute(f"UPDATE purchase_orders SET {update.field}=? WHERE id=?",(value,update.po_id)); conn.commit(); conn.close()
    return {"ok":True}

class NewPORow(BaseModel):
    year: int; po_number: Optional[str]=None; supplier_name: Optional[str]=None; item_desc: Optional[str]=None

@app.post("/api/purchase-orders/add-row")
def add_po_row(row: NewPORow):
    d={"year":row.year,"po_number":row.po_number,"supplier_name":row.supplier_name,"item_desc":row.item_desc}
    if is_supabase(): r=_sq("purchase_orders").insert(d).execute(); return {"ok":True,"po_id":r.data[0]["id"]}
    else: conn=get_sqlite(); cur=conn.execute("INSERT INTO purchase_orders (year,po_number,supplier_name,item_desc) VALUES (?,?,?,?)",tuple(d.values())); conn.commit(); pid=cur.lastrowid; conn.close(); return {"ok":True,"po_id":pid}

@app.post("/api/purchase-orders/delete-row")
def delete_po_row(po_id: int = Body(...)):
    if is_supabase(): _sq("purchase_orders").delete().eq("id",po_id).execute()
    else: conn=get_sqlite(); conn.execute("DELETE FROM purchase_orders WHERE id=?",(po_id,)); conn.commit(); conn.close()
    return {"ok":True}

@app.get("/api/purchase-orders/download")
def download_po_excel(year: int = Query(0)):
    import openpyxl; from openpyxl.styles import Font,Alignment,Border,Side,PatternFill; from urllib.parse import quote
    if is_supabase():
        q=_sq("purchase_orders").select("*")
        if year: q=q.eq("year",year)
        rows=q.order("order_date",nullsfirst=False).order("id").execute().data
    else:
        conn=get_sqlite()
        rows=[dict(r) for r in conn.execute("SELECT * FROM purchase_orders WHERE year=? ORDER BY order_date ASC NULLS LAST,id ASC",(year,)).fetchall()] if year else [dict(r) for r in conn.execute("SELECT * FROM purchase_orders ORDER BY year DESC,order_date ASC NULLS LAST,id ASC").fetchall()]
        conn.close()
    wb=openpyxl.Workbook(); ws=wb.active; ws.title=str(year) if year else "전체"
    thin=Border(left=Side(style='thin'),right=Side(style='thin'),top=Side(style='thin'),bottom=Side(style='thin'))
    hf=PatternFill(start_color="D9E1F2",end_color="D9E1F2",fill_type="solid")
    ws.merge_cells("A1:I1"); ws["A1"]="매입발주목록"; ws["A1"].font=Font(bold=True,size=13); ws["A1"].alignment=Alignment(horizontal="center")
    hdrs=["주문번호","매입처","발주품목","Q'TY","금액(VAT제외)","발주일자","납기","출고여부","비고"]; ws_w=[20,14,50,6,14,12,14,10,16]
    for i,(h,w) in enumerate(zip(hdrs,ws_w),1):
        c=ws.cell(row=2,column=i,value=h); c.font=Font(bold=True,size=9); c.fill=hf; c.border=thin; c.alignment=Alignment(horizontal="center",vertical="center",wrap_text=True)
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width=w
    for idx,row in enumerate(rows):
        r=idx+3; rd=[row.get("po_number"),row.get("supplier_name"),row.get("item_desc"),row.get("quantity"),row.get("amount"),row.get("order_date"),row.get("delivery_due"),row.get("shipped"),row.get("remark") or row.get("customer_name")]
        for i,v in enumerate(rd,1): c=ws.cell(row=r,column=i,value=v); c.border=thin; (setattr(c,'number_format','#,##0') if isinstance(v,(int,float)) and v and i in(4,5) else None)
    buf=io.BytesIO(); wb.save(buf); buf.seek(0); fn=f"발주목록_{year or '전체'}.xlsx"
    return StreamingResponse(buf,media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":f"attachment; filename*=UTF-8''{quote(fn)}"})

@app.post("/api/purchase-orders/upload")
async def upload_po_excel(file: UploadFile = File(...), year: int = Query(0)):
    import openpyxl
    if not year: return {"ok":False,"error":"year required"}
    content=await file.read(); wb=openpyxl.load_workbook(io.BytesIO(content),data_only=True); ws=wb.active
    hr=None
    for r in range(1,min(10,ws.max_row+1)):
        for c in range(1,ws.max_column+1):
            v=ws.cell(r,c).value
            if v and ("주문번호" in str(v) or "발주서" in str(v)): hr=r; break
        if hr: break
    if not hr: return {"ok":False,"error":"Cannot find header row"}
    cm={}
    for c in range(1,ws.max_column+1):
        v=str(ws.cell(hr,c).value or "").strip()
        if "주문번호" in v or "발주서" in v:cm["po"]=c
        elif "매입처" in v:cm["sup"]=c
        elif "발주품목" in v or "DESCRIPTION" in v:cm["item"]=c
        elif "QTY" in v.upper():cm["qty"]=c
        elif "금액" in v:cm["amt"]=c
        elif "발주일자" in v:cm["od"]=c
        elif "납기" in v:cm["dd"]=c
        elif "출고" in v:cm["sh"]=c
        elif "비고" in v:cm["rm"]=c
    def cv(r,k): c=cm.get(k); return ws.cell(r,c).value if c else None
    def tds(v):
        if v is None: return None
        if isinstance(v,datetime): return v.strftime("%Y-%m-%d")
        if isinstance(v,date): return v.isoformat()
        return str(v).strip() or None
    def ti(v):
        if v is None or v=="": return None
        try: return int(float(v))
        except: return None
    if is_supabase(): _sq("purchase_orders").delete().eq("year",year).execute()
    else: conn=get_sqlite(); conn.execute("DELETE FROM purchase_orders WHERE year=?",(year,)); conn.commit()
    batch=[]; imported=0
    for r in range(hr+1,ws.max_row+1):
        po,item,amt=cv(r,"po"),cv(r,"item"),cv(r,"amt")
        if not po and not item and not amt: continue
        dd=cv(r,"dd"); dds=tds(dd) or (str(dd).strip() if dd else None)
        batch.append({"year":year,"po_number":str(po).strip() if po else None,"supplier_name":str(cv(r,"sup")).strip() if cv(r,"sup") else None,"item_desc":str(item).strip() if item else None,"quantity":ti(cv(r,"qty")),"amount":ti(amt),"order_date":tds(cv(r,"od")),"delivery_due":dds,"shipped":str(cv(r,"sh")).strip() if cv(r,"sh") else None,"remark":str(cv(r,"rm")).strip() if cv(r,"rm") else None})
        imported+=1
    if is_supabase() and batch:
        for i in range(0,len(batch),200): _sq("purchase_orders").insert(batch[i:i+200]).execute()
    elif batch:
        for rd in batch: conn.execute("INSERT INTO purchase_orders (year,po_number,supplier_name,item_desc,quantity,amount,order_date,delivery_due,shipped,remark) VALUES (?,?,?,?,?,?,?,?,?,?)",tuple(rd.values()))
        conn.commit(); conn.close()
    return {"ok":True,"imported":imported,"year":year}


# ============================================================
# API: Purchases (매입 내역)
# ============================================================

@app.get("/api/purchases")
def list_purchases(year_month: str = Query(""), q: str = Query(""), page: int = Query(1), per_page: int = Query(50)):
    off=(page-1)*per_page
    if is_supabase():
        qr=_sq("purchases").select("*",count="exact")
        if year_month: qr=qr.eq("year_month",year_month)
        if q: qr=qr.or_(f"po_ref.ilike.%{q}%,category.ilike.%{q}%,memo.ilike.%{q}%")
        r=qr.order("year_month",desc=True).order("id",desc=True).range(off,off+per_page-1).execute()
        return {"total":r.count,"page":page,"per_page":per_page,"items":r.data}
    else:
        conn=get_sqlite(); conds,params=[],[]
        if year_month: conds.append("year_month=?"); params.append(year_month)
        if q: conds.append("(po_ref LIKE ? OR category LIKE ? OR memo LIKE ?)"); params.extend([f"%{q}%"]*3)
        w=" AND ".join(conds) if conds else "1=1"
        total=conn.execute(f"SELECT COUNT(*) FROM purchases WHERE {w}",params).fetchone()[0]
        rows=[dict(r) for r in conn.execute(f"SELECT * FROM purchases WHERE {w} ORDER BY year_month DESC,id DESC LIMIT ? OFFSET ?",params+[per_page,off]).fetchall()]
        conn.close(); return {"total":total,"page":page,"per_page":per_page,"items":rows}

@app.get("/api/purchases/months")
def purchase_months():
    if is_supabase():
        r=_sq("purchases").select("year_month").execute()
        return sorted(set(x["year_month"] for x in r.data if x["year_month"]),reverse=True)
    else:
        conn=get_sqlite(); rows=conn.execute("SELECT DISTINCT year_month FROM purchases ORDER BY year_month DESC").fetchall(); conn.close()
        return [r["year_month"] for r in rows]

@app.get("/api/purchases/summary")
def purchase_summary(year_month: str = Query("")):
    if is_supabase():
        qr=_sq("purchases").select("purchase_amount,sales_amount,profit_half")
        if year_month: qr=qr.eq("year_month",year_month)
        data=qr.execute().data
        return {"cnt":len(data),"total_purchase":sum(r["purchase_amount"] or 0 for r in data),"total_sales":sum(r["sales_amount"] or 0 for r in data),"total_profit":sum(r["profit_half"] or 0 for r in data)}
    else:
        conn=get_sqlite(); w="WHERE year_month=?" if year_month else ""; p=(year_month,) if year_month else ()
        row=conn.execute(f"SELECT COUNT(*) as cnt,SUM(purchase_amount) as total_purchase,SUM(sales_amount) as total_sales,SUM(profit_half) as total_profit FROM purchases {w}",p).fetchone()
        conn.close(); return dict(row)

@app.get("/api/stats")
def dashboard_stats():
    if is_supabase():
        return {
            "orders":_sq("orders").select("id",count="exact").execute().count,
            "purchase_orders":_sq("purchase_orders").select("id",count="exact").execute().count,
            "purchases":_sq("purchases").select("id",count="exact").execute().count,
            "price_items":_sq("price_catalog").select("id",count="exact").execute().count,
        }
    else:
        conn=get_sqlite()
        r={"orders":conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0],"purchase_orders":conn.execute("SELECT COUNT(*) FROM purchase_orders").fetchone()[0],"purchases":conn.execute("SELECT COUNT(*) FROM purchases").fetchone()[0]}
        conn.close()
        conn2=get_sqlite("한국밸브_협가표.db"); r["price_items"]=conn2.execute("SELECT COUNT(*) FROM price_list_items").fetchone()[0]; conn2.close()
        return r

@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(STATIC_DIR,"index.html"),encoding="utf-8") as f: return f.read()

if __name__ == "__main__":
    import uvicorn; uvicorn.run("web.server:app",host="0.0.0.0",port=8000,reload=True)
