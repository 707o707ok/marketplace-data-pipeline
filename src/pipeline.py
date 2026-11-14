"""Validate a CSV snapshot, rebuild SQLite tables, and export reproducible metrics."""
import argparse
import csv
import html
import json
import re
import sqlite3
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ['order_id', 'buyer_id', 'category', 'order_date', 'price_yen', 'status']
STATUSES = {'completed', 'cancelled', 'refunded'}


def read_orders(path: Path):
    """Return accepted records and audit rows; first valid occurrence wins per ID."""
    accepted, rejected, seen = [], [], set()
    with path.open(newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != FIELDS:
            raise ValueError(f'CSV headers must be exactly {FIELDS}')
        for line, raw in enumerate(reader, start=2):
            row = {field: (raw.get(field) or '').strip() for field in FIELDS}
            reason = ''
            if None in raw or any(raw.get(field) is None for field in FIELDS):
                reason = 'wrong_column_count'
            elif not all(row.values()):
                reason = 'missing_required_value'
            elif row['status'] not in STATUSES:
                reason = 'invalid_status'
            else:
                try:
                    parsed_date = date.fromisoformat(row['order_date'])
                    if parsed_date.isoformat() != row['order_date']:
                        raise ValueError('Date must be YYYY-MM-DD')
                except ValueError:
                    reason = 'invalid_date'
                price = row['price_yen']
                if not reason and (not re.fullmatch(r'[0-9]+', price) or not 0 < int(price) <= 10**12):
                    reason = 'invalid_price'
            if not reason and row['order_id'] in seen:
                reason = 'duplicate_order_id'
            if reason:
                rejected.append({'source_line': line, 'reason': reason, **row})
            else:
                seen.add(row['order_id'])
                row['price_yen'] = int(row['price_yen'])
                accepted.append(row)
    return accepted, rejected


def write_csv(path: Path, fields, rows):
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def make_chart(path: Path, monthly):
    """SVG bars, zero baseline, labelled values; works without plotting dependencies."""
    width, height, left, top, plot_h = 900, 390, 70, 95, 210
    maximum = max([r['completed_value_yen'] for r in monthly] or [1]) or 1
    step = 740 / max(len(monthly), 1)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
             '<title id="title">Monthly completed merchandise value</title>',
             '<desc id="desc">Synthetic marketplace data. Completed orders only; cancelled and fully refunded orders excluded. Bars start at zero.</desc>',
             '<rect width="900" height="390" fill="#f5f7fb"/>',
             '<g font-family="Arial, sans-serif" fill="#18273f">',
             '<text x="40" y="35" font-size="23" font-weight="bold">Marketplace activity</text>',
             '<text x="40" y="60" font-size="13">SYNTHETIC DATA · completed merchandise value · JPY · not revenue</text>']
    for fraction in (0, .5, 1):
        y = top + plot_h * (1 - fraction)
        parts.extend([f'<line x1="{left}" y1="{y}" x2="840" y2="{y}" stroke="#dce3ed"/>',
                      f'<text x="{left - 10}" y="{y + 4}" text-anchor="end" font-size="11">{maximum * fraction / 1_000_000:.1f}m</text>'])
    for i, row in enumerate(monthly):
        x = left + step * i + step * .2
        bar_h = plot_h * row['completed_value_yen'] / maximum
        y = top + plot_h - bar_h
        label = html.escape(row['month'])
        parts.extend([f'<rect x="{x}" y="{y}" width="{step * .6}" height="{bar_h}" rx="4" fill="#285ad6"/>',
                      f'<text x="{x + step * .3}" y="{y - 9}" text-anchor="middle" font-size="12">{row["completed_value_yen"]:,}</text>',
                      f'<text x="{x + step * .3}" y="330" text-anchor="middle" font-size="12">{label}</text>'])
    if not monthly:
        parts.append('<text x="450" y="200" text-anchor="middle">No valid orders</text>')
    parts.extend(['<text x="40" y="368" font-size="12">Illustrative output from a local Python + SQLite portfolio pipeline.</text>', '</g></svg>'])
    path.write_text('\n'.join(parts) + '\n', encoding='utf-8')


def run(input_path: Path, db_path: Path, output: Path):
    # Validate before touching the database. A malformed CSV leaves the previous database intact.
    accepted, rejected = read_orders(input_path)
    output.mkdir(parents=True, exist_ok=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        connection.executescript((ROOT / 'sql/schema.sql').read_text(encoding='utf-8'))
        with connection:
            connection.executemany('INSERT INTO buyers VALUES (?)',
                                   [(value,) for value in sorted({r['buyer_id'] for r in accepted})])
            connection.executemany('INSERT INTO categories VALUES (?)',
                                   [(value,) for value in sorted({r['category'] for r in accepted})])
            connection.executemany('INSERT INTO orders VALUES (?,?,?,?,?,?)',
                                   [tuple(r[f] for f in FIELDS) for r in accepted])
        monthly = [dict(r) for r in connection.execute((ROOT / 'sql/metrics.sql').read_text())]
        categories = [dict(r) for r in connection.execute('''
            SELECT category, COUNT(*) AS completed_orders, SUM(price_yen) AS completed_value_yen
            FROM orders WHERE status = 'completed' GROUP BY category
            ORDER BY completed_value_yen DESC, category
        ''')]
        buyers = dict(connection.execute('''
            SELECT COUNT(*) AS completed_buyers,
                   COALESCE(SUM(CASE WHEN completed_orders >= 2 THEN 1 ELSE 0 END), 0) AS repeat_buyers
            FROM (SELECT buyer_id, COUNT(*) AS completed_orders FROM orders
                  WHERE status = 'completed' GROUP BY buyer_id)
        ''').fetchone())
        completed_value = connection.execute("SELECT COALESCE(SUM(price_yen),0) FROM orders WHERE status='completed'").fetchone()[0]
        integrity = connection.execute('PRAGMA integrity_check').fetchone()[0]
        if integrity != 'ok' or connection.execute('PRAGMA foreign_key_check').fetchall():
            raise RuntimeError('SQLite integrity check failed')
    finally:
        connection.close()
    monthly_fields = ['month', 'valid_orders', 'completed_orders', 'completed_value_yen',
                      'completed_buyers', 'avg_completed_order_yen', 'cancellation_pct']
    write_csv(output / 'monthly_metrics.csv', monthly_fields, monthly)
    write_csv(output / 'category_metrics.csv', ['category', 'completed_orders', 'completed_value_yen'], categories)
    write_csv(output / 'rejected_rows.csv', ['source_line', 'reason', *FIELDS], rejected)
    quality = {'source_rows': len(accepted) + len(rejected), 'accepted_rows': len(accepted),
               'rejected_rows': len(rejected), 'rejection_reasons': dict(sorted(Counter(r['reason'] for r in rejected).items()))}
    repeat_pct = round(100 * buyers['repeat_buyers'] / buyers['completed_buyers'], 2) if buyers['completed_buyers'] else 0
    summary = {'data_type': 'synthetic', 'quality': quality,
               'completed_value_yen': completed_value, **buyers,
               'repeat_buyer_pct_within_observation_window': repeat_pct}
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    make_chart(output / 'monthly_completed_value.svg', monthly)
    reason_table = '\n'.join(f'| {reason} | {count} |' for reason, count in quality['rejection_reasons'].items()) or '| None | 0 |'
    report = f'''# Pipeline output

**Synthetic data only. These are generated examples, not results about Mercari or a real business.**

![Monthly completed merchandise value](monthly_completed_value.svg)

| Check / metric | Value |
| --- | ---: |
| Source rows | {quality['source_rows']:,} |
| Accepted rows | {quality['accepted_rows']:,} |
| Rejected rows | {quality['rejected_rows']:,} |
| Completed merchandise value (JPY) | {completed_value:,} |
| Buyers with a completed order | {buyers['completed_buyers']:,} |
| Buyers with at least two completed orders | {buyers['repeat_buyers']:,} |
| Repeat-buyer share within this observation window | {repeat_pct}% |

## Rejection audit

Each rejected row has one primary reason; CSV source lines include the header.

| Reason | Rows |
| --- | ---: |
{reason_table}

## Interpretation and limits

- Completed merchandise value sums final-state completed orders. It excludes cancellations and full refunds; it is **not revenue**.
- Repeat-buyer share describes this finite synthetic observation window. It is **not cohort retention** and depends on observation length.
- There is no intentional business trend in the generator. Month-to-month differences are random variation and calendar-length effects.
- Review `monthly_metrics.csv`, `category_metrics.csv`, and `rejected_rows.csv` for underlying outputs.
'''
    (output / 'report.md').write_text(report, encoding='utf-8')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'data/raw/orders.csv')
    parser.add_argument('--db', type=Path, default=ROOT / 'data/marketplace.sqlite')
    parser.add_argument('--output', type=Path, default=ROOT / 'reports')
    args = parser.parse_args()
    print(json.dumps(run(args.input, args.db, args.output), indent=2))
