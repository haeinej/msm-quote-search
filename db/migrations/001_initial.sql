-- MSM Valve Management System — Supabase Postgres Schema
-- Run this in Supabase SQL Editor (Dashboard → SQL Editor → New query)

-- ============================================================
-- PRICE CATALOG (협가표 — flat denormalized, used for search)
-- ============================================================
CREATE TABLE IF NOT EXISTS price_catalog (
    id SERIAL PRIMARY KEY,
    source_file TEXT DEFAULT '한국밸브 협가표.pdf',
    source_page INTEGER,
    effective_date TEXT DEFAULT '2022-01-01',
    material_group TEXT DEFAULT 'CAST CARBON STEEL',
    material TEXT DEFAULT 'SCPH2/WCB',
    product_type TEXT,
    construction_type TEXT,
    pressure_class TEXT,
    size_a TEXT,
    size_inch TEXT,
    discount_rate TEXT,
    unit_price INTEGER,
    currency TEXT DEFAULT 'KRW',
    source_table_title TEXT,
    notes TEXT
);

-- ============================================================
-- 수주대장 (Order Book)
-- ============================================================
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    order_no TEXT,
    order_seq INTEGER,
    year_month TEXT,
    customer_name TEXT,
    discount_rate REAL,
    memo TEXT,
    order_date DATE,
    total_amount INTEGER,
    stock_amount INTEGER DEFAULT 0,
    delivery_due DATE,
    delivery_date DATE,
    delivery_amount INTEGER,
    sales_date DATE,
    sales_amount INTEGER,
    remark TEXT,
    collection_date DATE,
    collection_note TEXT,
    supplier_name TEXT,
    purchase_date DATE,
    purchase_amount INTEGER,
    purchase_due DATE,
    purchase_spec TEXT,
    invoice_date DATE,
    cost_ratio REAL,
    source_file TEXT,
    source_sheet TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    item_desc TEXT NOT NULL,
    unit_price INTEGER,
    quantity INTEGER,
    amount INTEGER,
    purchase_spec TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- 발주목록 (Purchase Order List)
-- ============================================================
CREATE TABLE IF NOT EXISTS purchase_orders (
    id SERIAL PRIMARY KEY,
    po_number TEXT,
    year INTEGER,
    supplier_name TEXT,
    item_desc TEXT,
    quantity INTEGER,
    amount INTEGER,
    order_date DATE,
    delivery_due TEXT,
    delivery_date DATE,
    shipped TEXT,
    customer_name TEXT,
    remark TEXT,
    source_file TEXT,
    source_sheet TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- 매입 내역 (Purchase Records)
-- ============================================================
CREATE TABLE IF NOT EXISTS purchases (
    id SERIAL PRIMARY KEY,
    year_month TEXT,
    invoice_no TEXT,
    order_ref TEXT,
    po_ref TEXT,
    po_amount INTEGER,
    purchase_amount INTEGER,
    category TEXT,
    memo TEXT,
    sales_amount INTEGER,
    profit_half INTEGER,
    source_file TEXT,
    source_sheet TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- INDEXES
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_orders_year_month ON orders(year_month);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_name);
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_po_number ON purchase_orders(po_number);
CREATE INDEX IF NOT EXISTS idx_po_year ON purchase_orders(year);
CREATE INDEX IF NOT EXISTS idx_purchases_year_month ON purchases(year_month);
CREATE INDEX IF NOT EXISTS idx_price_catalog_type ON price_catalog(product_type, pressure_class, size_a);
