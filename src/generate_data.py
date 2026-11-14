"""Generate fictional final-state orders with deliberate quality issues. No external data."""
import argparse
import csv
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ['order_id', 'buyer_id', 'category', 'order_date', 'price_yen', 'status']


def generate(path: Path, count: int = 2400, seed: int = 42) -> None:
    rng = random.Random(seed)
    categories = ['Books', 'Clothing', 'Electronics', 'Home', 'Hobbies']
    rows = []
    for i in range(count):
        rows.append({
            'order_id': f'O{i + 1:06d}',
            'buyer_id': f'B{rng.randint(1, 600):04d}',
            'category': rng.choice(categories),
            'order_date': (date(2026, 1, 1) + timedelta(days=rng.randrange(181))).isoformat(),
            'price_yen': str(rng.randint(3, 200) * 100),
            'status': rng.choices(['completed', 'cancelled', 'refunded'], [85, 10, 5])[0],
        })
    # Append bad records so the intended rejection reasons are easy to audit.
    if rows:
        rows.extend([dict(rows[0]), dict(rows[-1])])
        bad_rows = [
            {'buyer_id': ''}, {'order_date': '2026-02-30'},
            {'price_yen': '-500'}, {'price_yen': '900.50'},
            {'status': 'pending'}, {'category': ''},
        ]
        for i, changes in enumerate(bad_rows):
            rows.append({**rows[0], 'order_id': f'BAD{i + 1}', **changes})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'data/raw/orders.csv')
    parser.add_argument('--count', type=int, default=2400)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    if args.count < 0:
        parser.error('--count must be non-negative')
    generate(args.output, args.count, args.seed)
