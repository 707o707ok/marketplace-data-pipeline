PRAGMA foreign_keys = ON;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS buyers;
DROP TABLE IF EXISTS categories;

CREATE TABLE buyers (
    buyer_id TEXT PRIMARY KEY
);
CREATE TABLE categories (
    category TEXT PRIMARY KEY
);
-- Grain: one final-state order, rather than one payment or status event.
CREATE TABLE orders (
    order_id TEXT PRIMARY KEY,
    buyer_id TEXT NOT NULL REFERENCES buyers(buyer_id),
    category TEXT NOT NULL REFERENCES categories(category),
    order_date TEXT NOT NULL,
    price_yen INTEGER NOT NULL CHECK(price_yen > 0),
    status TEXT NOT NULL CHECK(status IN ('completed', 'cancelled', 'refunded'))
);
CREATE INDEX orders_date_idx ON orders(order_date);
CREATE INDEX orders_buyer_idx ON orders(buyer_id);
