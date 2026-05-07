-- MSM Quote System — Full Schema
-- Matches Excel column names to reduce friction

-- ============================================================
-- REFERENCE TABLES
-- ============================================================

CREATE TABLE IF NOT EXISTS customers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,
    alias           TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS suppliers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,
    alias           TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- PRICE LIST (협가표) — existing, preserved
-- ============================================================

CREATE TABLE IF NOT EXISTS products (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    body_type       TEXT NOT NULL,          -- GATE, GLOBE, SW-CHECK, Y-STRAINER
    rating          TEXT NOT NULL,          -- 10K, 20K
    size_mm         INTEGER NOT NULL,       -- 50, 65, 80, ...
    end_connection  TEXT,                   -- RF, BW, FF, SW
    body_material   TEXT,                   -- SCPH2, WCB, CF8, CF8M, ...
    trim_material   TEXT,                   -- 13CR, 304, 316, ...
    operation_type  TEXT,                   -- HW, GEAR, G/O, MOV
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(body_type, rating, size_mm, end_connection, body_material, trim_material)
);

CREATE TABLE IF NOT EXISTS price_list_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id      INTEGER REFERENCES products(id),
    discount_rate   REAL NOT NULL,
    unit_price      INTEGER NOT NULL,
    source_table    TEXT,
    effective_from  DATE,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 수주대장 (Order Book) — mirrors Excel columns
-- ============================================================

-- One row per order (grouped by NO in Excel)
CREATE TABLE IF NOT EXISTS orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    order_no        TEXT,                   -- 발주NO (e.g. SP2305-001)
    order_seq       INTEGER,                -- NO (순번, e.g. 1, 2, 3...)
    year_month      TEXT,                   -- 시트명 기준 (e.g. "2023-05", "2026-04")
    customer_name   TEXT,                   -- 업 체 명
    discount_rate   REAL,                   -- 특이사항/할인율 (e.g. 0.5, 0.47)
    memo            TEXT,                   -- 특이사항 텍스트 (견적번호, 성적서 등)
    order_date      DATE,                   -- 수주일자
    total_amount    INTEGER,                -- 금액 합계
    stock_amount    INTEGER DEFAULT 0,      -- 재고판매 금액
    delivery_due    DATE,                   -- 납기일자
    delivery_date   DATE,                   -- 납품일자
    delivery_amount INTEGER,                -- 납품금액
    sales_date      DATE,                   -- 매출일자
    sales_amount    INTEGER,                -- 매출금액
    remark          TEXT,                   -- REMARK
    collection_date DATE,                   -- 수금일자
    collection_note TEXT,                   -- 수금 비고 (입금완결 등)
    -- 매입현황
    supplier_name   TEXT,                   -- 매입 업체명
    purchase_date   DATE,                   -- 매입 발주일자
    purchase_amount INTEGER,                -- 매입 금액(VAT제외)
    purchase_due    DATE,                   -- 매입 납기일자
    purchase_spec   TEXT,                   -- 납품사양
    invoice_date    DATE,                   -- 계산서 발행일
    cost_ratio      REAL,                   -- 원가율
    source_file     TEXT,                   -- 원본 파일명
    source_sheet    TEXT,                   -- 원본 시트명
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Line items within an order (multiple ITEM rows per order)
CREATE TABLE IF NOT EXISTS order_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id        INTEGER NOT NULL REFERENCES orders(id),
    item_desc       TEXT NOT NULL,          -- ITEM (e.g. "GATE 20K SCPH2/13CR BB OS&Y RF 50A")
    unit_price      INTEGER,                -- 단가(VAT제외)
    quantity        INTEGER,                -- 수량
    amount          INTEGER,                -- 금액 (단가 × 수량 or manual)
    purchase_spec   TEXT,                   -- 매입 납품사양
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 발주목록 (Purchase Order List) — mirrors Excel columns
-- ============================================================

CREATE TABLE IF NOT EXISTS purchase_orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    po_number       TEXT,                   -- 주문번호/발주서 No. (e.g. SP2601-001)
    year            INTEGER,                -- 시트 연도 (2024, 2025, 2026)
    supplier_name   TEXT,                   -- 매입처 (한국밸브, DKM, etc.)
    item_desc       TEXT,                   -- 발주품목/DESCRIPTION
    quantity        INTEGER,                -- Q'TY
    amount          INTEGER,                -- 금액(VAT제외)
    order_date      DATE,                   -- 발주일자
    delivery_due    TEXT,                   -- 납기 (date or text like "ASAP", "발주후 30일")
    delivery_date   DATE,                   -- 납품일자
    shipped         TEXT,                   -- 출고여부 (O, O (3), etc.)
    customer_name   TEXT,                   -- 거래처/비고 (end customer)
    remark          TEXT,                   -- 비고
    source_file     TEXT,
    source_sheet    TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 매입 내역 (Purchase Records) — mirrors Excel columns
-- ============================================================

CREATE TABLE IF NOT EXISTS purchases (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    year_month      TEXT,                   -- 시트명 기준 (e.g. "2024-11", "2026-04")
    invoice_no      TEXT,                   -- 거래명세표 번호
    order_ref       TEXT,                   -- 수주 No.
    po_ref          TEXT,                   -- 발주No.
    po_amount       INTEGER,                -- 발주금액
    purchase_amount INTEGER,                -- 매입액
    category        TEXT,                   -- 구분 (거래처명 or STOCK)
    memo            TEXT,                   -- 비고
    sales_amount    INTEGER,                -- MSM 매출액
    profit_half     INTEGER,                -- 매출이익의 50%
    source_file     TEXT,
    source_sheet    TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 재고 (Inventory) — derived from STOCK entries
-- ============================================================

CREATE TABLE IF NOT EXISTS inventory (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    item_desc       TEXT NOT NULL,
    quantity        INTEGER DEFAULT 0,
    unit_cost       INTEGER,                -- 단가
    total_cost      INTEGER,                -- 총 매입가
    location        TEXT DEFAULT '서울사무소',
    status          TEXT DEFAULT 'in_stock', -- in_stock, reserved, shipped
    po_ref          TEXT,                   -- 입고 발주번호
    received_date   DATE,                   -- 입고일
    shipped_date    DATE,                   -- 출고일
    shipped_to      TEXT,                   -- 출고처
    remark          TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 견적 이력 (Quotation History)
-- ============================================================

CREATE TABLE IF NOT EXISTS quotation_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    quote_number    TEXT,                   -- 견적번호 (MSM2604-100)
    customer_name   TEXT,
    spec_raw        TEXT,                   -- 원본 입력 텍스트
    spec_normalized TEXT,                   -- 파싱된 표준형
    product_id      INTEGER REFERENCES products(id),
    lookup_status   TEXT NOT NULL,          -- exact, multiple, none
    discount_rate   REAL,
    unit_price      INTEGER,
    quantity        INTEGER,
    total_amount    INTEGER,
    rfq_needed      BOOLEAN DEFAULT 0,      -- 협가표에 없어서 RFQ 필요
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_orders_order_no ON orders(order_no);
CREATE INDEX IF NOT EXISTS idx_orders_year_month ON orders(year_month);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_name);
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_po_number ON purchase_orders(po_number);
CREATE INDEX IF NOT EXISTS idx_po_year ON purchase_orders(year);
CREATE INDEX IF NOT EXISTS idx_po_supplier ON purchase_orders(supplier_name);
CREATE INDEX IF NOT EXISTS idx_purchases_year_month ON purchases(year_month);
CREATE INDEX IF NOT EXISTS idx_purchases_po_ref ON purchases(po_ref);
CREATE INDEX IF NOT EXISTS idx_inventory_status ON inventory(status);
