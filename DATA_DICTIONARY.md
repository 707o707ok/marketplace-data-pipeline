# Data dictionary

Source: locally generated fictional orders in `src/generate_data.py`, seed 42 by default. No scraping, personal data, or third-party dataset.

**Grain:** one order's final state at a single snapshot. The default observation dates are 2026-01-01 through 2026-06-30. These dates describe fictional records, not when this project was developed.

| Field | Raw type | Validated type | Rule |
| --- | --- | --- | --- |
| order_id | String | Text primary key | Nonempty; first valid occurrence retained |
| buyer_id | String | Text foreign key | Nonempty; fictional ID |
| category | String | Text foreign key | Nonempty; source generator uses five categories |
| order_date | String | ISO date text | Strict `YYYY-MM-DD`; valid calendar date |
| price_yen | String | Integer | Digits only; 1 to 1,000,000,000,000 JPY |
| status | String | Constrained text | `completed`, `cancelled`, or `refunded` |

The loader accepts nonempty categories outside the generator's five categories and builds the dimension from accepted input values. It does not assume a global category taxonomy.

Whitespace is stripped around all values. Every field is required. The CSV header must match the expected columns and order exactly; a mismatch stops the run before database changes. Records with missing or extra columns are rejected.

If several rules fail, a rejected row receives one primary reason in this order: column count, missing values, invalid status, invalid date, invalid price, duplicate ID. An invalid earlier row does not reserve its ID. The rejection file stores normalized field values, original source line numbers (header = line 1), and a reason. The original CSV is retained separately.

## Generator assumptions

- 2,400 base orders, 600 possible buyer IDs, five categories.
- Uniform day selection across the six-month date interval.
- Positive prices in 100-JPY increments, 300 to 20,000 JPY.
- Independent random statuses with weights 85% completed, 10% cancelled, 5% fully refunded. Realized proportions differ.
- Two duplicate rows and six invalid rows appended for quality checks.

The generator is deliberately simple. It does not model seasonality, real buying behaviour, category-specific price distributions, fraud, or partial refunds.
