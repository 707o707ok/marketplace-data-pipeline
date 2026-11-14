import csv
import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.generate_data import FIELDS, generate
from src.pipeline import read_orders, run


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'orders.csv'
        self.output = self.root / 'reports'
        self.db = self.root / 'test.sqlite'

    def write(self, rows):
        with self.source.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)

    def order(self, order_id='O1', buyer='B1', price='1000', status='completed'):
        return dict(zip(FIELDS, [order_id, buyer, 'Books', '2026-01-01', price, status]))

    def test_financial_and_repeat_metrics(self):
        self.write([self.order(), self.order('O2', price='2000'),
                    self.order('O3', buyer='B2', price='5000', status='refunded'),
                    self.order('O4', buyer='B3', price='8000', status='cancelled')])
        summary = run(self.source, self.db, self.output)
        self.assertEqual(summary['completed_value_yen'], 3000)
        self.assertEqual(summary['completed_buyers'], 1)
        self.assertEqual(summary['repeat_buyers'], 1)
        with (self.output / 'monthly_metrics.csv').open() as stream:
            monthly = next(csv.DictReader(stream))
        self.assertEqual(monthly['avg_completed_order_yen'], '1500.0')
        self.assertEqual(monthly['cancellation_pct'], '25.0')

    def test_invalid_first_row_does_not_block_valid_duplicate_id(self):
        self.write([self.order(price='-1'), self.order(), self.order(price='9000')])
        accepted, rejected = read_orders(self.source)
        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0]['price_yen'], 1000)
        self.assertEqual([r['reason'] for r in rejected], ['invalid_price', 'duplicate_order_id'])
        self.assertEqual([r['source_line'] for r in rejected], [2, 4])

    def test_rerun_outputs_and_database_are_stable(self):
        generate(self.source, count=100)
        first = run(self.source, self.db, self.output)
        hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.output.iterdir()}
        second = run(self.source, self.db, self.output)
        self.assertEqual(first, second)
        self.assertEqual(hashes, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.output.iterdir()})
        with sqlite3.connect(self.db) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM orders').fetchone()[0], 100)
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_seeded_quality_audit(self):
        generate(self.source)
        summary = run(self.source, self.db, self.output)
        self.assertEqual(summary['quality']['source_rows'], 2408)
        self.assertEqual(summary['quality']['accepted_rows'], 2400)
        self.assertEqual(summary['quality']['rejection_reasons'], {
            'duplicate_order_id': 2, 'invalid_date': 1, 'invalid_price': 2,
            'invalid_status': 1, 'missing_required_value': 2})

    def test_empty_input_has_defined_metrics(self):
        self.write([])
        summary = run(self.source, self.db, self.output)
        self.assertEqual(summary['completed_value_yen'], 0)
        self.assertEqual(summary['repeat_buyer_pct_within_observation_window'], 0)

    def test_malformed_header_does_not_replace_existing_database(self):
        self.write([self.order()])
        run(self.source, self.db, self.output)
        self.source.write_text('wrong,headers\n1,2\n')
        with self.assertRaises(ValueError):
            run(self.source, self.db, self.output)
        with sqlite3.connect(self.db) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM orders').fetchone()[0], 1)


if __name__ == '__main__':
    unittest.main()
