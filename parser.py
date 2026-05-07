"""
검색어 파서: 사용자 입력 → 구조화된 조건 + 재고/견적 분류

재고품 기본 사양:
  BODY TYPE : GATE / GLOBE / CHECK / Y-STR
  RATING    : 10K / 20K  or  150# / 300#
  END CONN. : FLGD RF
  BODY MAT  : SCPH2 (K규격) / WCB (#규격)
  TRIM MAT  : 13CR  (Y-STR는 304SS)
  OPER.     : H/W   (대구경은 GEAR가 기본)

기본 사양을 벗어나면 → 제조사 견적 요청(RFQ) 대상
"""
import re


PRODUCT_ALIASES = {
    "GATE": "GATE",
    "GATE VALVE": "GATE",
    "GATE V/V": "GATE",
    "게이트": "GATE",
    "게이트밸브": "GATE",
    "게이트 밸브": "GATE",
    "GLOBE": "GLOBE",
    "GLOBE VALVE": "GLOBE",
    "GLOBE V/V": "GLOBE",
    "글로브": "GLOBE",
    "글로브밸브": "GLOBE",
    "글로브 밸브": "GLOBE",
    "SW-CHECK": "SW-CHECK",
    "SW CHECK": "SW-CHECK",
    "SWING CHECK": "SW-CHECK",
    "스윙체크": "SW-CHECK",
    "스윙 체크": "SW-CHECK",
    "체크밸브": "SW-CHECK",
    "체크 밸브": "SW-CHECK",
    "CHECK": "SW-CHECK",
    "CHECK VALVE": "SW-CHECK",
    "CHECK V/V": "SW-CHECK",
    "Y-STRAINER": "Y-STRAINER",
    "Y STRAINER": "Y-STRAINER",
    "STRAINER": "Y-STRAINER",
    "스트레이너": "Y-STRAINER",
    "와이스트레이너": "Y-STRAINER",
}

PRESSURE_ALIASES = {
    "10K": "10K", "150#": "10K", "150": "10K",
    "20K": "20K", "300#": "20K", "300": "20K",
}

SIZE_ALIASES = {
    '2"': "50A", '2"': "50A", "2인치": "50A", "50A": "50A", "50": "50A",
    '2 1/2"': "65A", '2.5"': "65A", "65A": "65A", "65": "65A",
    '3"': "80A", "3인치": "80A", "80A": "80A", "80": "80A",
    '4"': "100A", "4인치": "100A", "100A": "100A", "100": "100A",
    '5"': "125A", "5인치": "125A", "125A": "125A", "125": "125A",
    '6"': "150A", "6인치": "150A", "150A": "150A",
    '8"': "200A", "8인치": "200A", "200A": "200A", "200": "200A",
    '10"': "250A", "10인치": "250A", "250A": "250A", "250": "250A",
    '12"': "300A", "12인치": "300A", "300A": "300A",
    '14"': "350A", "14인치": "350A", "350A": "350A", "350": "350A",
    '16"': "400A", "16인치": "400A", "400A": "400A", "400": "400A",
    '18"': "450A", "18인치": "450A", "450A": "450A", "450": "450A",
    '20"': "500A", "20인치": "500A", "500A": "500A", "500": "500A",
}

VALID_DISCOUNT_RATES = {
    "0%", "-40%", "-41%", "-42%", "-43%", "-44%", "-45%", "-46%",
    "-47%", "-48%", "-49%", "-50%", "-51%", "-52%", "-53%", "-54%",
    "-55%", "-56%",
}

# Standard (stock) ratings
STOCK_RATINGS = {"10K", "20K"}
# Ratings that require RFQ
HIGH_RATINGS_K = {"30K", "40K", "50K", "60K"}
HIGH_RATINGS_HASH = {"600#", "800#", "900#", "1500#", "2500#"}

# Standard end connections
STOCK_END_CONN = {"RF", "FLGD", "FLANGE"}
# Non-standard end connections that require RFQ
RFQ_END_CONN = {"SW", "BW", "RTJ", "FF", "BUTT WELD", "BUTTWELD", "SOCKET WELD"}

# Standard trim materials (for stock)
STOCK_TRIM = {"13CR", "304SS", "304", "STS304"}

# Non-standard trim additions that require RFQ
RFQ_TRIM = {"HF", "STL", "STELLITE", "HARD FACE", "HARDFACE", "FHF"}

# Size threshold for GEAR being standard (at or above this size, GEAR is default)
GEAR_STANDARD_SIZE_A = 200  # 200A and above = GEAR is standard


def parse_query(query: str) -> dict:
    """Parse a search query into structured conditions + RFQ classification."""
    result = {
        "product_type": None,
        "material": "SCPH2/WCB",
        "material_raw": None,
        "pressure_class": None,
        "pressure_raw": None,       # raw pressure string before mapping to stock
        "size_a": None,
        "discount_rate": None,
        "connection_type": None,
        "operator_type": None,       # H/W, GEAR, MOTOR, etc.
        "trim_extras": [],           # HF, STL, etc.
        "raw_query": query,
        "warnings": [],
        "rfq_required": False,       # True if non-standard spec detected
        "rfq_reasons": [],           # list of reasons why RFQ is needed
    }

    q = query.strip().upper()

    # 1. Product type (check longer aliases first)
    sorted_aliases = sorted(PRODUCT_ALIASES.keys(), key=len, reverse=True)
    for alias in sorted_aliases:
        if alias.upper() in q:
            result["product_type"] = PRODUCT_ALIASES[alias]
            break

    # Also check Korean in original (not uppercased) query
    if result["product_type"] is None:
        for alias in sorted_aliases:
            if alias in query:
                result["product_type"] = PRODUCT_ALIASES[alias]
                break

    # 2. Pressure class — detect ALL ratings, map stock ones, flag high ones
    # Check high K ratings first (30K, 40K, ...)
    high_k = re.search(r'\b(30|40|50|60)\s*K\b', q)
    if high_k:
        raw_pressure = f"{high_k.group(1)}K"
        result["pressure_raw"] = raw_pressure
        result["rfq_required"] = True
        result["rfq_reasons"].append(f"고압 등급 ({raw_pressure}) — 재고품 범위(10K/20K) 초과")

    # Check high # ratings (600#, 900#, ...)
    high_hash = re.search(r'\b(600|800|900|1500|2500)\s*#', q)
    if high_hash:
        raw_pressure = f"{high_hash.group(1)}#"
        result["pressure_raw"] = raw_pressure
        result["rfq_required"] = True
        result["rfq_reasons"].append(f"고압 등급 ({raw_pressure}) — 재고품 범위(150#/300#) 초과")

    # Check standard ratings
    if result["pressure_class"] is None and not result["pressure_raw"]:
        for alias, val in PRESSURE_ALIASES.items():
            if alias in q:
                if alias in ("150", "300"):
                    pattern = re.compile(re.escape(alias) + r'(?:#|K)', re.IGNORECASE)
                    if pattern.search(q):
                        result["pressure_class"] = val
                        result["pressure_raw"] = alias
                        break
                else:
                    result["pressure_class"] = val
                    result["pressure_raw"] = alias
                    break

    # Fallback: look for 10K or 20K pattern
    if result["pressure_class"] is None and not result["pressure_raw"]:
        m = re.search(r'\b(10|20)\s*K\b', q, re.IGNORECASE)
        if m:
            result["pressure_class"] = f"{m.group(1)}K"
            result["pressure_raw"] = f"{m.group(1)}K"

    # 3. Size — look for patterns like "80A", "3인치", '3"'
    m = re.search(r'\b(\d{2,3})A\b', q)
    if m:
        size_key = f"{m.group(1)}A"
        if size_key in SIZE_ALIASES:
            result["size_a"] = SIZE_ALIASES[size_key]

    if result["size_a"] is None:
        # Match whole inches but NOT fractional like 3/4" (those are small-bore, not in stock table)
        m = re.search(r'(?<!/)\b(\d+(?:\s*1/2)?)\s*[""인치]', query)
        if m:
            inch_key = f'{m.group(1)}"'
            if inch_key in SIZE_ALIASES:
                result["size_a"] = SIZE_ALIASES[inch_key]
        # Detect small-bore fractional inches (3/4", 1/2", 1") as RFQ
        small_bore = re.search(r'\b(\d/\d|\d+/\d+)\s*["""]', query)
        if small_bore and result["size_a"] is None:
            result["warnings"].append(f"소구경 ({small_bore.group(1)}\") — 협가표 범위(50A~) 외, 별도 견적 필요")

    # 4. Discount rate
    if re.search(r'\b0\s*%|정가', q):
        result["discount_rate"] = "0%"

    if result["discount_rate"] is None:
        m = re.search(r'-\s*(\d{2})(?:\s*%)?', q)
        if m:
            rate = f"-{m.group(1)}%"
            if rate in VALID_DISCOUNT_RATES:
                result["discount_rate"] = rate

    if result["discount_rate"] is None:
        m = re.search(r'\b(4[0-9]|5[0-6])\s*%?(?:\s|$)', q)
        if m:
            rate = f"-{m.group(1)}%"
            if rate in VALID_DISCOUNT_RATES:
                result["discount_rate"] = rate

    if result["discount_rate"] is None:
        m = re.search(r'할인\s*(?:율\s*)?(\d{2})', query)
        if m:
            rate = f"-{m.group(1)}%"
            if rate in VALID_DISCOUNT_RATES:
                result["discount_rate"] = rate

    # 5. End connection type — detect and flag non-standard
    # Check for non-standard first (SW, BW, RTJ)
    for ec in RFQ_END_CONN:
        if re.search(r'\b' + re.escape(ec) + r'\b', q):
            result["connection_type"] = ec.replace("BUTT WELD", "BW").replace("BUTTWELD", "BW").replace("SOCKET WELD", "SW")
            result["rfq_required"] = True
            result["rfq_reasons"].append(f"END CONN: {result['connection_type']} — 재고품은 FLGD RF 기본")
            break

    # Standard end connections
    if result["connection_type"] is None:
        conn_match = re.search(r'\b(RF|FLGD|FLANGE)\b', q)
        if conn_match:
            result["connection_type"] = "RF"

    # 6. Trim material — detect HF, STL, STELLITE extras
    for trim in RFQ_TRIM:
        if re.search(r'\b' + re.escape(trim) + r'\b', q):
            result["trim_extras"].append(trim)

    if result["trim_extras"]:
        extras = " + ".join(result["trim_extras"])
        result["rfq_required"] = True
        result["rfq_reasons"].append(f"TRIM 추가 옵션: {extras} — 재고품 기본(13CR) 외 사양")

    # 7. Operator type — detect GEAR, MOTOR, H/W
    if re.search(r'\bMOTOR\b', q):
        result["operator_type"] = "MOTOR"
        result["rfq_required"] = True
        result["rfq_reasons"].append("OPERATOR: MOTOR — 제조사 견적 필요")
    elif re.search(r'\bGEAR\b', q):
        result["operator_type"] = "GEAR"
        # GEAR is standard for large sizes, RFQ for small sizes
        size_num = 0
        if result["size_a"]:
            m2 = re.match(r'(\d+)A', result["size_a"])
            if m2:
                size_num = int(m2.group(1))
        if size_num > 0 and size_num < GEAR_STANDARD_SIZE_A:
            result["rfq_required"] = True
            result["rfq_reasons"].append(f"GEAR 요청 ({result['size_a']}) — {GEAR_STANDARD_SIZE_A}A 미만은 H/W 기본, GEAR 시 제조사 견적 필요")
    elif re.search(r'\bH/?W\b', q):
        result["operator_type"] = "H/W"

    # 8. Body material detection
    mat_match = re.search(
        r'\b(WCB/13CR|13CR\+HF|SUS\d+|CF8M|CF8|A351|A216|SCPH2|WCB|SCS\d+|DUPLEX|INCONEL|MONEL|HASTELLOY)\b',
        q,
    )
    if mat_match:
        raw_mat = mat_match.group(0)
        result["material_raw"] = raw_mat
        # Non-standard exotic materials
        if raw_mat in ("DUPLEX", "INCONEL", "MONEL", "HASTELLOY"):
            result["rfq_required"] = True
            result["rfq_reasons"].append(f"특수 재질: {raw_mat} — 제조사 견적 필요")
        elif raw_mat not in ("SCPH2", "WCB", "WCB/13CR"):
            result["warnings"].append(
                f"입력 재질 '{raw_mat}'은(는) 현재 협가표(SCPH2/WCB)와 다릅니다. 조회 결과는 SCPH2/WCB 기준입니다."
            )

    # 9. Build summary warnings for RFQ
    if result["rfq_required"]:
        result["warnings"].insert(0, "⚠ 제조사 견적 요청(RFQ) 대상 — 기본 사양을 벗어남")

    return result


if __name__ == "__main__":
    tests = [
        "SCPH2 GATE V/V RF 10K 80A -40%",
        "GLOBE 20K 100A -45%",
        "GATE WCB/13CR+HF 300# BW GEAR 12\"",
        "GATE SCPH2/13CR+STL 30K RF H/W 65A",
        "GLOBE A105/13CR+FHF 600# SW 3/4\"",
        "CHECK 10K FLGD RF 100A -42%",
        "Y-STRAINER 20K 200A -40%",
        "GATE 800# INCONEL TRIM BW 4\"",
        "GATE 10K RF 80A GEAR",
        "GATE 10K RF 300A GEAR",
    ]
    for t in tests:
        r = parse_query(t)
        parsed = {k: v for k, v in r.items()
                  if k not in ("raw_query", "material") and v is not None and v != [] and v is not False}
        print(f"  Input: {t}")
        print(f"  Parsed: {parsed}")
        if r["rfq_required"]:
            print(f"  ** RFQ REQUIRED: {'; '.join(r['rfq_reasons'])}")
        print()
