"""
검색어 파서: 사용자 입력 → 구조화된 조건
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

VALID_DISCOUNT_RATES = {"0%", "-40%", "-42%", "-45%", "-47%"}


def parse_query(query: str) -> dict:
    """Parse a search query into structured conditions."""
    result = {
        "product_type": None,
        "material": "SCPH2/WCB",  # default material in current data
        "material_raw": None,     # raw material string from input (for mismatch detection)
        "pressure_class": None,
        "size_a": None,
        "discount_rate": None,
        "connection_type": None,  # RF, BW, FF, SW — informational
        "raw_query": query,
        "warnings": [],
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

    # 2. Pressure class
    # Check explicit patterns first
    for alias, val in PRESSURE_ALIASES.items():
        if alias in q:
            # Avoid matching "150A" as pressure 150#
            if alias in ("150", "300"):
                # Only match if not followed by 'A'
                pattern = re.compile(re.escape(alias) + r'(?:#|K)', re.IGNORECASE)
                if pattern.search(q):
                    result["pressure_class"] = val
                    break
            else:
                result["pressure_class"] = val
                break

    # Fallback: look for 10K or 20K pattern
    if result["pressure_class"] is None:
        m = re.search(r'\b(10|20)\s*K\b', q, re.IGNORECASE)
        if m:
            result["pressure_class"] = f"{m.group(1)}K"

    # 3. Size — look for patterns like "80A", "3인치", '3"'
    # First try explicit "xxxA" pattern
    m = re.search(r'\b(\d{2,3})A\b', q)
    if m:
        size_key = f"{m.group(1)}A"
        if size_key in SIZE_ALIASES:
            result["size_a"] = SIZE_ALIASES[size_key]

    # Fallback: inch pattern
    if result["size_a"] is None:
        m = re.search(r'\b(\d+(?:\s*1/2)?)\s*[""인치]', query)
        if m:
            inch_key = f'{m.group(1)}"'
            if inch_key in SIZE_ALIASES:
                result["size_a"] = SIZE_ALIASES[inch_key]

    # 4. Discount rate
    # Check for "0%" or "정가" first
    if re.search(r'\b0\s*%|정가', q):
        result["discount_rate"] = "0%"

    # Pattern: -40%, -40, 40%
    if result["discount_rate"] is None:
        m = re.search(r'-\s*(\d{2})(?:\s*%)?', q)
        if m:
            rate = f"-{m.group(1)}%"
            if rate in VALID_DISCOUNT_RATES:
                result["discount_rate"] = rate

    # Bare number pattern: "40%", "40" (without dash — assume discount)
    if result["discount_rate"] is None:
        m = re.search(r'\b(4[0257])\s*%?(?:\s|$)', q)
        if m:
            rate = f"-{m.group(1)}%"
            if rate in VALID_DISCOUNT_RATES:
                result["discount_rate"] = rate

    # Korean pattern: 할인 40, 할인율 45
    if result["discount_rate"] is None:
        m = re.search(r'할인\s*(?:율\s*)?(\d{2})', query)
        if m:
            rate = f"-{m.group(1)}%"
            if rate in VALID_DISCOUNT_RATES:
                result["discount_rate"] = rate

    # 5. Connection type (informational)
    conn_match = re.search(r'\b(RF|BW|FF|SW|FLANGE|BUTT\s*WELD)\b', q)
    if conn_match:
        conn_map = {"RF": "RF", "BW": "BW", "FF": "FF", "SW": "SW",
                     "FLANGE": "RF", "BUTTWELD": "BW", "BUTT WELD": "BW"}
        result["connection_type"] = conn_map.get(conn_match.group(1).replace(" ", ""), conn_match.group(1))

    # 6. Material detection — check if input specifies a non-standard material
    mat_match = re.search(
        r'\b(WCB/13CR|13CR\+HF|SUS\d+|CF8M|CF8|A351|A216|SCPH2|WCB|SCS\d+|DUPLEX|INCONEL|MONEL|HASTELLOY)\b',
        q,
    )
    if mat_match:
        raw_mat = mat_match.group(0)
        result["material_raw"] = raw_mat
        # Check if it's a non-standard material
        if raw_mat not in ("SCPH2", "WCB"):
            result["warnings"].append(
                f"입력 재질 '{raw_mat}'은(는) 현재 협가표(SCPH2/WCB)와 다릅니다. 조회 결과는 SCPH2/WCB 기준입니다."
            )

    return result


if __name__ == "__main__":
    tests = [
        "SCPH2 GATE V/V RF 10K 80A -40%",
        "SCPH2 게이트밸브 RF 10K 80A 할인 40 적용해서 견적",
        "GLOBE 20K 100A -45%",
        "스트레이너 10K 50A",
        "SW-CHECK 300A 20K -47%",
        "체크밸브 80A",
    ]
    for t in tests:
        r = parse_query(t)
        parsed = {k: v for k, v in r.items() if k != "raw_query" and v is not None}
        print(f"  Input: {t}")
        print(f"  Parsed: {parsed}")
        print()
