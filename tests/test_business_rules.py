"""Offline unit tests for the business rules — no Stripe, no Slack, no model."""

from __future__ import annotations

import pathlib
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from mcp_server import business_rules as rules  # noqa: E402

NOW = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)


def unix(days_from_now: int) -> int:
    from datetime import timedelta

    return int((NOW + timedelta(days=days_from_now)).timestamp())


def invoice(amount, currency="usd", status="open", due_in_days=0, number="INV-1"):
    return {
        "id": f"in_{number}",
        "number": number,
        "status": status,
        "amount_due": amount,
        "currency": currency,
        "due_date": unix(due_in_days),
        "hosted_invoice_url": f"https://pay.example/{number}",
    }


class MoneyTests(unittest.TestCase):
    def test_usd_converts_from_minor_units(self):
        self.assertEqual(rules.format_money(320000, "usd"), "$3,200.00")

    def test_zero_decimal_currency_has_no_cents(self):
        # JPY 5000 is 5000 yen, not 50.00
        self.assertEqual(rules.format_money(5000, "jpy"), "\u00a55,000")

    def test_unknown_currency_falls_back_to_code(self):
        self.assertEqual(rules.format_money(1000, "sek"), "SEK 10.00")


class OverdueTests(unittest.TestCase):
    def test_past_due_open_invoice_is_overdue(self):
        inv = invoice(100000, due_in_days=-18)
        self.assertTrue(rules.is_overdue(inv, NOW))
        self.assertEqual(rules.days_overdue(inv["due_date"], NOW), 18)

    def test_future_due_invoice_is_not_overdue(self):
        self.assertFalse(rules.is_overdue(invoice(100000, due_in_days=5), NOW))

    def test_paid_invoice_is_never_overdue(self):
        inv = invoice(100000, status="paid", due_in_days=-30)
        self.assertFalse(rules.is_overdue(inv, NOW))

    def test_missing_due_date_is_not_overdue(self):
        self.assertFalse(rules.is_overdue({"status": "open", "amount_due": 500}, NOW))

    def test_selection_is_oldest_first(self):
        invoices = [
            invoice(100, due_in_days=-6, number="B"),
            invoice(100, due_in_days=-18, number="A"),
            invoice(100, due_in_days=10, number="C"),
        ]
        picked = [inv["number"] for inv in rules.select_overdue(invoices, NOW)]
        self.assertEqual(picked, ["A", "B"])


class SummaryTests(unittest.TestCase):
    def test_totals_and_oldest(self):
        summary = rules.summarize_overdue(
            [invoice(180000, due_in_days=-18), invoice(140000, due_in_days=-6)], NOW
        )
        self.assertEqual(summary["count"], 2)
        self.assertEqual(summary["total_minor"], 320000)
        self.assertEqual(summary["currency"], "usd")
        self.assertEqual(summary["oldest_days"], 18)

    def test_nothing_overdue(self):
        summary = rules.summarize_overdue([invoice(1000, due_in_days=9)], NOW)
        self.assertEqual(summary["count"], 0)
        self.assertIsNone(summary["total_minor"])

    def test_mixed_currency_is_reported_per_currency(self):
        summary = rules.summarize_overdue(
            [invoice(100000, "usd", due_in_days=-2), invoice(5000, "jpy", due_in_days=-2)], NOW
        )
        self.assertIsNone(summary["currency"])
        self.assertIsNone(summary["total_minor"])
        self.assertEqual(summary["totals_by_currency"], {"usd": 100000, "jpy": 5000})


class MatchingTests(unittest.TestCase):
    CUSTOMERS = [
        {"id": "cus_1", "name": "Acme Corp", "email": "billing@acme.example"},
        {"id": "cus_2", "name": "Initech LLC", "email": "ap@initech.example"},
        {"id": "cus_3", "name": "Globex Corporation", "email": "finance@globex.example"},
    ]

    def test_legal_suffix_is_ignored(self):
        self.assertEqual(rules.normalize_name("Acme Corp"), "acme")
        self.assertEqual(rules.normalize_name("Globex Corporation"), "globex")

    def test_exact_name_scores_one(self):
        top = rules.match_customers("Acme", self.CUSTOMERS)[0]
        self.assertEqual(top["id"], "cus_1")
        self.assertEqual(top["match_score"], 1.0)

    def test_email_lookup(self):
        top = rules.match_customers("finance@globex.example", self.CUSTOMERS)[0]
        self.assertEqual(top["id"], "cus_3")

    def test_typo_still_finds_the_customer(self):
        top = rules.match_customers("Initehc", self.CUSTOMERS)[0]
        self.assertEqual(top["id"], "cus_2")

    def test_unrelated_query_returns_nothing(self):
        self.assertEqual(rules.match_customers("Umbrella", self.CUSTOMERS), [])


if __name__ == "__main__":
    unittest.main()
