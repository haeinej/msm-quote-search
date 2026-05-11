"""
MSM PDF Generator — 견적서, 발주서, 거래명세표
Uses reportlab with Korean font support (AppleGothic on macOS).
"""
import io
import os
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# ============================================================
# Font Setup
# ============================================================

_font_registered = False

def _register_font():
    global _font_registered
    if _font_registered:
        return
    # Try common Korean font paths
    font_paths = [
        "/System/Library/Fonts/Supplemental/AppleGothic.ttf",  # macOS
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",     # Ubuntu
        "/usr/share/fonts/NanumGothic.ttf",                    # CentOS
    ]
    for path in font_paths:
        if os.path.exists(path):
            pdfmetrics.registerFont(TTFont("Korean", path))
            _font_registered = True
            return
    # Fallback — use Helvetica (no Korean support, but won't crash)
    _font_registered = True


def _korean_style(name="Korean", size=10, bold=False, align=0):
    """Create a ParagraphStyle with Korean font."""
    _register_font()
    font_name = "Korean" if _font_registered else "Helvetica"
    return ParagraphStyle(
        name=name,
        fontName=font_name,
        fontSize=size,
        leading=size * 1.4,
        alignment=align,  # 0=left, 1=center, 2=right
    )


# ============================================================
# Helpers
# ============================================================

def _fmt_num(n):
    """Format number with commas."""
    if n is None:
        return ""
    return f"{int(n):,}"


def _fmt_date(d):
    """Format date string."""
    if not d:
        return ""
    if isinstance(d, str):
        return d[:10]
    return str(d)[:10]


def _p(text, style):
    """Create a Paragraph from text."""
    return Paragraph(str(text or ""), style)


# ============================================================
# 견적서 (Quotation PDF)
# ============================================================

def generate_quotation_pdf(order: dict) -> io.BytesIO:
    """Generate a quotation PDF for an order."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20*mm, bottomMargin=15*mm,
                            leftMargin=15*mm, rightMargin=15*mm)

    title_style = _korean_style("Title", 18, align=1)
    header_style = _korean_style("Header", 11)
    cell_style = _korean_style("Cell", 9)
    cell_r_style = _korean_style("CellR", 9, align=2)
    note_style = _korean_style("Note", 9)

    elements = []

    # Title
    elements.append(_p("견 적 서", title_style))
    elements.append(Spacer(1, 10*mm))

    # Header info
    today = _fmt_date(order.get("quoted_at") or datetime.now().isoformat())
    header_data = [
        [_p("견적일자", header_style), _p(today, header_style),
         _p("문서번호", header_style), _p(f"MSM-Q-{order.get('id', '')}", header_style)],
        [_p("수 신", header_style), _p(order.get("customer_name", ""), header_style),
         _p("발 신", header_style), _p("(주)엠에스엠솔루션", header_style)],
    ]
    ht = Table(header_data, colWidths=[25*mm, 55*mm, 25*mm, 55*mm])
    ht.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (0, -1), colors.Color(0.9, 0.92, 0.96)),
        ("BACKGROUND", (2, 0), (2, -1), colors.Color(0.9, 0.92, 0.96)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(ht)
    elements.append(Spacer(1, 8*mm))

    # Item table
    unit_price = order.get("unit_price") or 0
    qty = order.get("quantity") or 1
    amount = unit_price * qty
    vat = int(amount * 0.1)
    total = amount + vat

    item_data = [
        [_p("No", cell_style), _p("품명 / 규격", cell_style), _p("수량", cell_style),
         _p("단가", cell_style), _p("공급가액", cell_style), _p("세액", cell_style)],
        [_p("1", cell_style), _p(order.get("spec_text", ""), cell_style),
         _p(str(qty), cell_r_style), _p(_fmt_num(unit_price), cell_r_style),
         _p(_fmt_num(amount), cell_r_style), _p(_fmt_num(vat), cell_r_style)],
    ]

    # Add empty rows for padding
    for i in range(4):
        item_data.append([_p("", cell_style)] * 6)

    # Totals row
    item_data.append([
        _p("", cell_style), _p("합 계", cell_style), _p("", cell_style),
        _p("", cell_style), _p(_fmt_num(amount), cell_r_style), _p(_fmt_num(vat), cell_r_style),
    ])

    it = Table(item_data, colWidths=[12*mm, 65*mm, 18*mm, 28*mm, 28*mm, 28*mm])
    it.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.9, 0.92, 0.96)),
        ("BACKGROUND", (0, -1), (-1, -1), colors.Color(0.95, 0.95, 0.95)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(it)
    elements.append(Spacer(1, 5*mm))

    # Total amount
    total_data = [[_p("총 합계 (VAT 포함)", header_style), _p(f"{_fmt_num(total)} 원", _korean_style("Big", 14, align=2))]]
    tt = Table(total_data, colWidths=[80*mm, 100*mm])
    tt.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 1, colors.Color(0.1, 0.14, 0.49)),
        ("BACKGROUND", (0, 0), (0, 0), colors.Color(0.9, 0.92, 0.96)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(tt)
    elements.append(Spacer(1, 8*mm))

    # Note
    if order.get("note"):
        elements.append(_p(f"비고: {order['note']}", note_style))

    doc.build(elements)
    buf.seek(0)
    return buf


# ============================================================
# 발주서 (Purchase Order PDF)
# ============================================================

def generate_po_pdf(order: dict) -> io.BytesIO:
    """Generate a purchase order PDF."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20*mm, bottomMargin=15*mm,
                            leftMargin=15*mm, rightMargin=15*mm)

    title_style = _korean_style("Title", 18, align=1)
    header_style = _korean_style("Header", 11)
    cell_style = _korean_style("Cell", 9)
    cell_r_style = _korean_style("CellR", 9, align=2)

    elements = []

    elements.append(_p("발 주 서", title_style))
    elements.append(Spacer(1, 10*mm))

    today = _fmt_date(order.get("po_issued_at") or datetime.now().isoformat())
    header_data = [
        [_p("발주일자", header_style), _p(today, header_style),
         _p("발주번호", header_style), _p(f"MSM-PO-{order.get('id', '')}", header_style)],
        [_p("발주처", header_style), _p(order.get("manufacturer", "한국밸브"), header_style),
         _p("발주자", header_style), _p("(주)엠에스엠솔루션", header_style)],
        [_p("납기일자", header_style), _p(_fmt_date(order.get("requested_delivery_at")), header_style),
         _p("고객사", header_style), _p(order.get("customer_name", ""), header_style)],
    ]
    ht = Table(header_data, colWidths=[25*mm, 55*mm, 25*mm, 55*mm])
    ht.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (0, -1), colors.Color(0.9, 0.92, 0.96)),
        ("BACKGROUND", (2, 0), (2, -1), colors.Color(0.9, 0.92, 0.96)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(ht)
    elements.append(Spacer(1, 8*mm))

    qty = order.get("quantity") or 1
    cost = order.get("cost") or 0
    cost_unit = cost // qty if qty else 0
    vat = int(cost * 0.1)

    item_data = [
        [_p("No", cell_style), _p("품명 / 규격", cell_style), _p("수량", cell_style),
         _p("단가", cell_style), _p("공급가액", cell_style), _p("세액", cell_style)],
        [_p("1", cell_style), _p(order.get("spec_text", ""), cell_style),
         _p(str(qty), cell_r_style), _p(_fmt_num(cost_unit), cell_r_style),
         _p(_fmt_num(cost), cell_r_style), _p(_fmt_num(vat), cell_r_style)],
    ]
    for _ in range(3):
        item_data.append([_p("", cell_style)] * 6)
    item_data.append([
        _p("", cell_style), _p("합 계", cell_style), _p("", cell_style),
        _p("", cell_style), _p(_fmt_num(cost), cell_r_style), _p(_fmt_num(vat), cell_r_style),
    ])

    it = Table(item_data, colWidths=[12*mm, 65*mm, 18*mm, 28*mm, 28*mm, 28*mm])
    it.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.9, 0.92, 0.96)),
        ("BACKGROUND", (0, -1), (-1, -1), colors.Color(0.95, 0.95, 0.95)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(it)

    doc.build(elements)
    buf.seek(0)
    return buf


# ============================================================
# 거래명세표 (Transaction Statement PDF)
# ============================================================

def generate_invoice_pdf(orders: list) -> io.BytesIO:
    """Generate a transaction statement PDF for one or more orders."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20*mm, bottomMargin=15*mm,
                            leftMargin=15*mm, rightMargin=15*mm)

    title_style = _korean_style("Title", 16, align=1)
    header_style = _korean_style("Header", 10)
    cell_style = _korean_style("Cell", 9)
    cell_r_style = _korean_style("CellR", 9, align=2)

    elements = []

    elements.append(_p("거 래 명 세 표", title_style))
    elements.append(Spacer(1, 8*mm))

    # Header
    first = orders[0] if orders else {}
    today = datetime.now().strftime("%Y-%m-%d")
    header_data = [
        [_p("작성일", header_style), _p(today, header_style),
         _p("공급자", header_style), _p("(주)엠에스엠솔루션", header_style)],
        [_p("거래처", header_style), _p(first.get("customer_name", ""), header_style),
         _p("", header_style), _p("한국밸브 서울영업소", header_style)],
    ]
    ht = Table(header_data, colWidths=[20*mm, 55*mm, 20*mm, 65*mm])
    ht.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (0, -1), colors.Color(0.9, 0.92, 0.96)),
        ("BACKGROUND", (2, 0), (2, -1), colors.Color(0.9, 0.92, 0.96)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(ht)
    elements.append(Spacer(1, 6*mm))

    # Items table
    item_data = [
        [_p("No", cell_style), _p("품명 / 규격", cell_style), _p("수량", cell_style),
         _p("단가", cell_style), _p("공급가액", cell_style), _p("세액", cell_style), _p("비고", cell_style)],
    ]

    total_supply = 0
    total_vat = 0
    for i, o in enumerate(orders, 1):
        up = o.get("unit_price") or 0
        qty = o.get("quantity") or 1
        supply = up * qty
        vat = int(supply * 0.1)
        total_supply += supply
        total_vat += vat

        item_data.append([
            _p(str(i), cell_style),
            _p(o.get("spec_text", ""), cell_style),
            _p(str(qty), cell_r_style),
            _p(_fmt_num(up), cell_r_style),
            _p(_fmt_num(supply), cell_r_style),
            _p(_fmt_num(vat), cell_r_style),
            _p(o.get("note", ""), cell_style),
        ])

    # Totals
    item_data.append([
        _p("", cell_style), _p("합 계", cell_style), _p("", cell_style),
        _p("", cell_style), _p(_fmt_num(total_supply), cell_r_style),
        _p(_fmt_num(total_vat), cell_r_style), _p("", cell_style),
    ])

    it = Table(item_data, colWidths=[10*mm, 55*mm, 15*mm, 25*mm, 25*mm, 22*mm, 25*mm])
    it.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.9, 0.92, 0.96)),
        ("BACKGROUND", (0, -1), (-1, -1), colors.Color(0.95, 0.95, 0.95)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(it)
    elements.append(Spacer(1, 5*mm))

    # Grand total
    grand = total_supply + total_vat
    total_data = [[_p("합계금액 (VAT 포함)", header_style),
                   _p(f"{_fmt_num(grand)} 원", _korean_style("Big", 13, align=2))]]
    tt = Table(total_data, colWidths=[70*mm, 107*mm])
    tt.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 1, colors.Color(0.1, 0.14, 0.49)),
        ("BACKGROUND", (0, 0), (0, 0), colors.Color(0.9, 0.92, 0.96)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    elements.append(tt)

    doc.build(elements)
    buf.seek(0)
    return buf
