"""Voice phrasing tests — the sentences a user actually hears."""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from mcp_server import business_rules as rules  # noqa: E402
from mcp_server import messages  # noqa: E402


def summary(count, total_minor=320000, currency="usd", oldest_days=18):
    return {
        "count": count,
        "oldest_days": oldest_days,
        "currency": currency,
        "total_minor": total_minor,
        "totals_by_currency": {currency: total_minor} if currency else {},
        "invoices": [],
    }


class SpokenSummaryTests(unittest.TestCase):
    def test_two_overdue_invoices(self):
        spoken = messages.spoken_overdue_summary("Acme Corp", summary(2))
        self.assertEqual(
            spoken,
            "Acme Corp has two overdue invoices totalling $3,200.00. "
            "The oldest is 18 days overdue.",
        )

    def test_one_overdue_invoice_is_singular(self):
        spoken = messages.spoken_overdue_summary("Initech", summary(1, 60000, oldest_days=11))
        self.assertEqual(
            spoken,
            "Initech has one overdue invoice totalling $600.00. It is 11 days overdue.",
        )

    def test_nothing_overdue(self):
        spoken = messages.spoken_overdue_summary("Globex", summary(0, None, None, 0))
        self.assertEqual(spoken, "Globex has nothing overdue.")

    def test_mixed_currency_is_not_added_up_silently(self):
        spoken = messages.spoken_overdue_summary(
            "Acme Corp",
            {
                "count": 2,
                "oldest_days": 4,
                "currency": None,
                "total_minor": None,
                "totals_by_currency": {"usd": 100000, "jpy": 5000},
                "invoices": [],
            },
        )
        self.assertIn("$1,000.00", spoken)
        self.assertIn("\u00a55,000", spoken)


class ActionPhrasingTests(unittest.TestCase):
    def test_reminder_sentence_names_invoice_and_amount(self):
        spoken = messages.spoken_reminder_sent("Acme Corp", "INV-0042", 180000, "usd")
        self.assertEqual(
            spoken, "I sent Acme Corp a payment reminder for INV-0042, $1,800.00."
        )

    def test_full_action_summary(self):
        spoken = messages.spoken_action_summary("Acme Corp", "INV-0042", 180000, "usd", "#finance")
        self.assertEqual(
            spoken,
            "I sent Acme Corp a payment reminder for INV-0042, $1,800.00. "
            "And notified #finance.",
        )

    def test_disambiguation_asks_a_question(self):
        candidates = [
            {"id": "cus_1", "name": "Acme Corp"},
            {"id": "cus_2", "name": "Acme Holdings"},
        ]
        spoken = messages.spoken_disambiguation(candidates)
        self.assertIn("Acme Corp", spoken)
        self.assertIn("Which one", spoken)

    def test_single_confident_match_is_a_statement_not_a_question(self):
        spoken = messages.spoken_customer_found([{"id": "cus_1", "name": "Acme Corp"}])
        self.assertEqual(spoken, "Found Acme Corp.")
        self.assertNotIn("?", spoken)

    def test_confident_match_still_asks_when_there_are_several(self):
        candidates = [{"id": "cus_1", "name": "Acme Corp"}, {"id": "cus_2", "name": "Acme Ltd"}]
        self.assertIn("Which one", messages.spoken_customer_found(candidates))


class SlackTextTests(unittest.TestCase):
    def test_detail_lines_show_reference_amount_and_age(self):
        inv = {
            "id": "in_1",
            "number": "INV-0042",
            "amount_due": 180000,
            "currency": "usd",
            "due_date": 0,
        }
        lines = messages.overdue_detail_lines({"invoices": [inv]})
        self.assertEqual(len(lines), 1)
        self.assertIn("INV-0042", lines[0])
        self.assertIn("$1,800.00", lines[0])

    def test_slack_text_includes_bullets(self):
        text = messages.slack_overdue_text("Acme Corp", summary(2))
        self.assertIn("*Overdue invoices — Acme Corp*", text)
        self.assertIn("two overdue invoices", text)




class CashflowSummaryTests(unittest.TestCase):
    """The account-wide answer has to name who owes money, not just report totals."""

    def _customer(self, name, minor):
        return {
            "customer": name,
            "currency": "usd",
            "total_minor": minor,
            "totals_by_currency": {"usd": minor},
        }

    def test_names_every_customer(self):
        spoken = messages.spoken_cashflow_summary(
            5,
            summary(3, 380000),
            [self._customer("Acme Corp", 320000), self._customer("Initech LLC", 60000)],
        )

        self.assertEqual(
            spoken,
            "5 invoices are open. Three are overdue, totalling $3,800.00: "
            "Acme Corp owes $3,200.00 and Initech LLC owes $600.00.",
        )
        self.assertNotIn("cus_", spoken)

    def test_caps_the_names_read_aloud(self):
        spoken = messages.spoken_cashflow_summary(
            9,
            summary(4, 400000),
            [self._customer(name, 100000) for name in ["Alpha", "Beta", "Gamma", "Delta"]],
        )

        self.assertIn("Alpha owes $1,000.00, Beta owes $1,000.00, Gamma owes $1,000.00 and one more.", spoken)

    def test_nothing_overdue_is_one_short_sentence(self):
        spoken = messages.spoken_cashflow_summary(2, summary(0, 0), [])

        self.assertEqual(spoken, "2 invoices are open, and nothing is overdue.")

    def test_single_open_invoice_is_singular(self):
        spoken = messages.spoken_cashflow_summary(1, summary(1, 60000), [self._customer("Initech LLC", 60000)])

        self.assertTrue(spoken.startswith("1 invoice is open. One is overdue"), spoken)

if __name__ == "__main__":
    unittest.main()
