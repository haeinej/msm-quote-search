"""POST /quote/lookup — price lookup endpoint"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from db.database import get_connection

router = APIRouter(prefix="/quote", tags=["quote"])

# Normalization aliases
RATING_ALIASES = {
    "10k": "10K", "20k": "20K",
    "150#": "10K", "150lb": "10K", "150lbs": "10K",
    "300#": "20K", "300lb": "20K", "300lbs": "20K",
}

BODY_TYPE_ALIASES = {
    "gate": "GATE", "globe": "GLOBE", "check": "SW-CHECK",
    "sw-check": "SW-CHECK", "y-str": "Y-STRAINER", "strainer": "Y-STRAINER",
    "y-strainer": "Y-STRAINER",
}

SIZE_ALIASES = {
    '2"': 50, '2.5"': 65, '3"': 80, '4"': 100,
    '5"': 125, '6"': 150, '8"': 200, '10"': 250,
    '12"': 300, '14"': 350, '16"': 400, '18"': 450, '20"': 500,
}

# Standard spec definitions
STANDARD_RATINGS = {"10K", "20K"}
HIGH_RATINGS = {"30K", "600#", "900#", "1500#"}
SPECIAL_END_CONN = {"SW", "BW", "RTJ"}
SPECIAL_TRIM = {"HF", "STL"}
GEAR_SIZE_THRESHOLD_MM = 150


class QuoteLookupRequest(BaseModel):
    body_type: str
    rating: str
    size: str
    end_connection: Optional[str] = "FLGD RF"
    body_material: Optional[str] = None
    trim_material: Optional[str] = None
    operation: Optional[str] = "H/W"
    discount_rate: float = 0.40


class QuoteLookupResponse(BaseModel):
    status: str
    unit_price: Optional[int] = None
    product_id: Optional[int] = None
    discount_rate: Optional[float] = None
    message: Optional[str] = None


def normalize_body_type(raw: str) -> str:
    return BODY_TYPE_ALIASES.get(raw.lower().strip(), raw.upper().strip())


def normalize_rating(raw: str) -> str:
    return RATING_ALIASES.get(raw.lower().strip(), raw.upper().strip())


def normalize_size_mm(raw: str) -> Optional[int]:
    raw = raw.strip()
    # "50A" -> 50, "80A" -> 80
    if raw.upper().endswith("A"):
        try:
            return int(raw[:-1])
        except ValueError:
            pass
    # inch format
    if raw in SIZE_ALIASES:
        return SIZE_ALIASES[raw]
    # bare number
    try:
        return int(raw)
    except ValueError:
        return None


def classify(body_type, rating, size_mm, end_connection, operation):
    """Classify spec as STANDARD, NEEDS_MAKER_QUOTE, or MISSING_INFO."""
    if not all([body_type, rating, size_mm]):
        return "MISSING_INFO", "Required field missing"

    if rating in HIGH_RATINGS:
        return "NEEDS_MAKER_QUOTE", f"Non-standard rating: {rating}"
    if end_connection and end_connection.upper() in SPECIAL_END_CONN:
        return "NEEDS_MAKER_QUOTE", f"Non-standard end connection: {end_connection}"
    if operation and operation.upper() == "GEAR" and size_mm < GEAR_SIZE_THRESHOLD_MM:
        return "NEEDS_MAKER_QUOTE", f"GEAR operation below {GEAR_SIZE_THRESHOLD_MM}mm"

    if rating not in STANDARD_RATINGS:
        return "NEEDS_MAKER_QUOTE", f"Non-standard rating: {rating}"

    return "STANDARD", None


@router.post("/lookup", response_model=QuoteLookupResponse)
def lookup_quote(req: QuoteLookupRequest):
    body_type = normalize_body_type(req.body_type)
    rating = normalize_rating(req.rating)
    size_mm = normalize_size_mm(req.size)
    end_connection = req.end_connection or "FLGD RF"
    operation = req.operation or "H/W"

    if size_mm is None:
        return QuoteLookupResponse(
            status="MISSING_INFO",
            message=f"Cannot parse size: {req.size}",
        )

    status, message = classify(body_type, rating, size_mm, end_connection, operation)
    if status != "STANDARD":
        return QuoteLookupResponse(status=status, message=message)

    conn = get_connection()
    row = conn.execute(
        """SELECT pli.unit_price, pli.product_id
           FROM price_list_items pli
           JOIN products p ON pli.product_id = p.id
           WHERE p.body_type = ? AND p.rating = ? AND p.size_mm = ?
             AND pli.discount_rate = ?""",
        (body_type, rating, size_mm, req.discount_rate),
    ).fetchone()
    conn.close()

    if row is None:
        return QuoteLookupResponse(
            status="NOT_FOUND",
            message=f"No price for {body_type} {rating} {size_mm}A @{int(req.discount_rate*100)}%",
        )

    return QuoteLookupResponse(
        status="FOUND",
        unit_price=row["unit_price"],
        product_id=row["product_id"],
        discount_rate=req.discount_rate,
    )
