-- MSM Unified Order Entity Migration
-- Adds state machine columns to existing orders table
-- Run in Supabase SQL Editor or via migrate script

-- Order type and state
ALTER TABLE orders ADD COLUMN IF NOT EXISTS type TEXT CHECK(type IN ('재고품', '제조품'));
ALTER TABLE orders ADD COLUMN IF NOT EXISTS state TEXT DEFAULT '견적'
  CHECK(state IN ('견적','수주확정','발주중','입고완료','출고완료','정산완료','반품','교환','취소'));

-- Core fields for unified entry
ALTER TABLE orders ADD COLUMN IF NOT EXISTS spec_text TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS quantity INTEGER DEFAULT 1;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS unit_price INTEGER;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS revenue INTEGER;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS cost INTEGER;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS profit INTEGER;

-- Workflow dates
ALTER TABLE orders ADD COLUMN IF NOT EXISTS quoted_at TIMESTAMPTZ;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS ordered_at TIMESTAMPTZ;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS po_issued_at TIMESTAMPTZ;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS requested_delivery_at TIMESTAMPTZ;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS received_at TIMESTAMPTZ;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS shipped_at TIMESTAMPTZ;

-- Manufacturer fields (제조품 only)
ALTER TABLE orders ADD COLUMN IF NOT EXISTS manufacturer TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS po_number TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS manufacturer_invoice_number TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS manufacturer_invoice_amount INTEGER;

ALTER TABLE orders ADD COLUMN IF NOT EXISTS note TEXT;

-- ERP inventory table (for stock checks)
CREATE TABLE IF NOT EXISTS erp_inventory (
    id SERIAL PRIMARY KEY,
    item_code TEXT NOT NULL,
    product_type TEXT,
    pressure_class TEXT,
    size_value TEXT,
    stock_quantity INTEGER DEFAULT 0,
    imported_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(item_code)
);

CREATE INDEX IF NOT EXISTS idx_erp_inventory_type ON erp_inventory(product_type, pressure_class, size_value);
CREATE INDEX IF NOT EXISTS idx_orders_state ON orders(state);
CREATE INDEX IF NOT EXISTS idx_orders_type ON orders(type);
