"""
협가표 Lookup 엔진: 파싱된 조건 → DB 조회 → 결과 반환
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "한국밸브_협가표.db")


def lookup(parsed: dict) -> dict:
    """
    Look up prices from the price list database.

    Returns:
        {
            "status": "exact" | "multiple" | "none",
            "results": [list of matching rows],
            "query": parsed conditions used
        }
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

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
    query = f"SELECT * FROM price_list_items WHERE {where} ORDER BY product_type, pressure_class, size_a, discount_rate"

    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    if len(rows) == 1:
        status = "exact"
    elif len(rows) > 1:
        status = "multiple"
    else:
        status = "none"

    return {
        "status": status,
        "count": len(rows),
        "results": rows,
        "query": {k: v for k, v in parsed.items() if k != "raw_query" and v is not None},
    }


def get_price_table(product_type: str, pressure_class: str, discount_rate: str) -> list[dict]:
    """Get the full price table for a specific product/pressure/discount combination (for validation view)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM price_list_items WHERE product_type=? AND pressure_class=? AND discount_rate=? ORDER BY CAST(REPLACE(size_a, 'A', '') AS INTEGER)",
        (product_type, pressure_class, discount_rate),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_full_discount_table(discount_rate: str) -> list[dict]:
    """Get all products for a given discount rate (for full table validation view)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM price_list_items WHERE discount_rate=? ORDER BY product_type, pressure_class, CAST(REPLACE(size_a, 'A', '') AS INTEGER)",
        (discount_rate,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


if __name__ == "__main__":
    from parser import parse_query

    test = "GATE 10K 80A -40%"
    parsed = parse_query(test)
    result = lookup(parsed)
    print(f"Query: {test}")
    print(f"Status: {result['status']} ({result['count']} results)")
    if result["results"]:
        r = result["results"][0]
        print(f"Price: {r['unit_price']:,} KRW")
        print(f"Source: {r['source_table_title']} / {r['product_type']} {r['pressure_class']} / {r['size_a']}")
