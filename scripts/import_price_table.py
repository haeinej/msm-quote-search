"""
Import 한국밸브 협가표 pricing data into normalized SQLite DB.
All 18 discount tiers (0%, -40% through -56%).
Source: data/raw/한국밸브_협가표.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from db.database import get_connection, init_db, DB_PATH

# Column mapping: index -> (body_type, rating)
COLUMNS = [
    ("GATE", "10K"),
    ("GATE", "20K"),
    ("GLOBE", "10K"),
    ("GLOBE", "20K"),
    ("SW-CHECK", "10K"),
    ("SW-CHECK", "20K"),
    ("Y-STRAINER", "10K"),
    ("Y-STRAINER", "20K"),
]

SIZES_MM = [50, 65, 80, 100, 125, 150, 200, 250, 300, 350, 400, 450, 500]

DISCOUNT_TIERS = [
    "0%", "-40%", "-41%", "-42%", "-43%", "-44%", "-45%", "-46%",
    "-47%", "-48%", "-49%", "-50%", "-51%", "-52%", "-53%", "-54%",
    "-55%", "-56%",
]


def parse_discount_rate(label: str) -> float:
    """Convert discount label to float. '0%' -> 0.0, '-40%' -> 0.40"""
    if label == "0%":
        return 0.0
    return abs(int(label.replace("%", "").replace("-", ""))) / 100.0


def get_trim_material(body_type: str) -> str:
    return "304SS" if body_type == "Y-STRAINER" else "13CR"


def get_construction_type(body_type: str) -> str:
    if body_type in ("GATE", "GLOBE"):
        return "BB OS&Y"
    return "BC"


def get_or_create_product(conn, body_type, rating, size_mm):
    """Get existing product_id or insert new product."""
    trim = get_trim_material(body_type)
    row = conn.execute(
        """SELECT id FROM products
           WHERE body_type=? AND rating=? AND size_mm=?
             AND end_connection='FLGD RF' AND body_material='SCPH2/WCB'
             AND trim_material=?""",
        (body_type, rating, size_mm, trim),
    ).fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        """INSERT INTO products (body_type, rating, size_mm, end_connection, body_material, trim_material, operation_type)
           VALUES (?, ?, ?, 'FLGD RF', 'SCPH2/WCB', ?, 'H/W')""",
        (body_type, rating, size_mm, trim),
    )
    return cur.lastrowid


def load_price_data():
    """Load pricing data from the raw source file (data dict only, skip openpyxl code)."""
    raw_path = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "한국밸브_협가표.py")
    with open(raw_path, encoding="utf-8") as f:
        source = f.read()
    # Extract only the data definitions (sizes, data, sheet_order) — skip imports and functions
    # Find where the data starts (after imports) and ends (before function defs)
    # Only extract up to and including the sheet_order list — everything after is openpyxl code
    end_marker = 'sheet_order = ['
    end_idx = source.find(end_marker)
    if end_idx == -1:
        raise RuntimeError("Could not find sheet_order in source file")
    # Find the closing bracket of sheet_order
    bracket_end = source.find("]", end_idx + len(end_marker))
    truncated = source[:bracket_end + 1]
    # Remove import lines
    lines = truncated.split("\n")
    clean_lines = [l for l in lines if not l.startswith("import ") and not l.startswith("from ")]
    namespace = {}
    exec("\n".join(clean_lines), namespace)
    return namespace["data"]


def import_all():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print("Removed existing database.")

    init_db()
    conn = get_connection()
    price_data = load_price_data()

    products_created = 0
    prices_inserted = 0

    for discount_label in DISCOUNT_TIERS:
        if discount_label not in price_data:
            print(f"  WARNING: {discount_label} not found in source data, skipping.")
            continue

        discount_rate = parse_discount_rate(discount_label)
        rows = price_data[discount_label]
        source_table = f"CAST CARBON STEEL VALVE PRICE LIST({discount_label})" if discount_label != "0%" else "CAST CARBON STEEL VALVE PRICE LIST"

        for size_idx, size_mm in enumerate(SIZES_MM):
            row_data = rows[size_idx]
            for col_idx, (body_type, rating) in enumerate(COLUMNS):
                price = row_data[col_idx]
                if price is None:
                    continue

                product_id = get_or_create_product(conn, body_type, rating, size_mm)
                conn.execute(
                    """INSERT INTO price_list_items (product_id, discount_rate, unit_price, source_table, effective_from)
                       VALUES (?, ?, ?, ?, '2022-01-01')""",
                    (product_id, discount_rate, price, source_table),
                )
                prices_inserted += 1

    products_created = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    conn.commit()
    conn.close()

    print(f"Import complete.")
    print(f"  Products: {products_created}")
    print(f"  Price list items: {prices_inserted}")
    print(f"  Discount tiers: {len(DISCOUNT_TIERS)}")
    print(f"  Database: {os.path.abspath(DB_PATH)}")


if __name__ == "__main__":
    import_all()
