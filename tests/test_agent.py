"""Tests for the agent loop's input normalisation."""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from agent.agent import clean_tool_name  # noqa: E402


class CleanToolNameTests(unittest.TestCase):
    def test_plain_name_is_untouched(self):
        self.assertEqual(clean_tool_name("get_overdue_invoices"), "get_overdue_invoices")

    def test_harmony_control_tokens_are_stripped(self):
        # Observed live from gpt-oss-20b through Converse: the model's own response
        # format leaked into the tool name, and Converse then rejected every later
        # request in the conversation.
        self.assertEqual(
            clean_tool_name("notify_finance_team<|channel|>commentary"),
            "notify_finance_team",
        )
        self.assertEqual(clean_tool_name("find_customer<|end|>"), "find_customer")

    def test_surrounding_whitespace_is_trimmed(self):
        self.assertEqual(clean_tool_name("  find_customer\n"), "find_customer")

    def test_unsalvageable_name_becomes_empty(self):
        self.assertEqual(clean_tool_name(""), "")
        self.assertEqual(clean_tool_name("not a tool!"), "")
        self.assertEqual(clean_tool_name("<|channel|>"), "")


if __name__ == "__main__":
    unittest.main()
