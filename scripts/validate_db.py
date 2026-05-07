"""
Post-import validation for MSM price database.
Run after import_price_table.py to verify data integrity.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from db.database import get_connection

SPOT_CHECKS = [
    # (body_type, rating, size_mm, discount_rate, expected_price)
    ("GATE", "10K", 50, 0.0, 416800),
    ("GATE", "10K", 50, 0.40, 250100),
    ("GLOBE", "20K", 300, 0.56, 4084300),
    ("SW-CHECK", "10K", 80, 0.45, 289400),
    ("Y-STRAINER", "20K", 100, 0.50, 443000),
]


def validate():
    conn = get_connection()
    errors = []

    # 1. Product count
    product_count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    if product_count == 0:
        errors.append("No products found in database!")
    else:
        print(f"  Products: {product_count}")

    # 2. Price list item count
    price_count = conn.execute("SELECT COUNT(*) FROM price_list_items").fetchone()[0]
    if price_count == 0:
        errors.append("No price list items found!")
    elif price_count < 1000:
        errors.append(f"Unexpectedly low price count: {price_count} (expected >1000)")
    print(f"  Price list items: {price_count}")

    # 3. No NULL unit_price
    nulls = conn.execute("SELECT COUNT(*) FROM price_list_items WHERE unit_price IS NULL").fetchone()[0]
    if nulls > 0:
        errors.append(f"{nulls} rows with NULL unit_price")
    print(f"  NULL prices: {nulls}")

    # 4. Price range sanity
    min_price = conn.execute("SELECT MIN(unit_price) FROM price_list_items").fetchone()[0]
    max_price = conn.execute("SELECT MAX(unit_price) FROM price_list_items").fetchone()[0]
    if min_price <= 0:
        errors.append(f"Invalid min price: {min_price}")
    if max_price > 30000000:
        errors.append(f"Suspiciously high max price: {max_price}")
    print(f"  Price range: {min_price:,} ~ {max_price:,} KRW")

    # 5. Discount tier coverage
    tier_count = conn.execute("SELECT COUNT(DISTINCT discount_rate) FROM price_list_items").fetchone()[0]
    print(f"  Discount tiers: {tier_count}")
    if tier_count < 18:
        errors.append(f"Only {tier_count} discount tiers (expected 18)")

    # 6. Spot checks
    print("\n  Spot checks:")
    for body_type, rating, size_mm, discount_rate, expected in SPOT_CHECKS:
        row = conn.execute(
            """SELECT pli.unit_price FROM price_list_items pli
               JOIN products p ON pli.product_id = p.id
               WHERE p.body_type=? AND p.rating=? AND p.size_mm=?
                 AND pli.discount_rate=?""",
            (body_type, rating, size_mm, discount_rate),
        ).fetchone()
        if row is None:
            errors.append(f"  FAIL: {body_type} {rating} {size_mm}mm @{discount_rate} — not found")
        elif row[0] != expected:
            errors.append(f"  FAIL: {body_type} {rating} {size_mm}mm @{discount_rate} — got {row[0]:,}, expected {expected:,}")
        else:
            print(f"    PASS: {body_type} {rating} {size_mm}mm @{int(discount_rate*100)}% = {expected:,}")

    # 7. Y-STRAINER 350A+ should not exist for 10K
    bad_ystr = conn.execute(
        """SELECT COUNT(*) FROM products
           WHERE body_type='Y-STRAINER' AND size_mm >= 350""",
    ).fetchone()[0]
    if bad_ystr > 0:
        errors.append(f"Y-STRAINER has {bad_ystr} products at 350A+ (should be 주문생산/제관형)")
    print(f"\n  Y-STRAINER 350A+ products: {bad_ystr} (expected 0)")

    conn.close()

    print("\n" + "=" * 40)
    if errors:
        print("VALIDATION FAILED:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("ALL CHECKS PASSED")


if __name__ == "__main__":
    print("MSM Price Database Validation")
    print("=" * 40)
    validate()
