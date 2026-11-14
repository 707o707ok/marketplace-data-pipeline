-- Completed merchandise value excludes cancelled and fully refunded orders.
-- This is not marketplace revenue, profit, or a measure of actual cash movements.
SELECT
    substr(order_date, 1, 7) AS month,
    COUNT(*) AS valid_orders,
    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed_orders,
    SUM(CASE WHEN status = 'completed' THEN price_yen ELSE 0 END) AS completed_value_yen,
    COUNT(DISTINCT CASE WHEN status = 'completed' THEN buyer_id END) AS completed_buyers,
    ROUND(AVG(CASE WHEN status = 'completed' THEN price_yen END), 2) AS avg_completed_order_yen,
    ROUND(100.0 * SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) / COUNT(*), 2) AS cancellation_pct
FROM orders
GROUP BY substr(order_date, 1, 7)
ORDER BY month;
