"""Tests for the agent loop's input normalisation."""

from __future__ import annotations

import asyncio
import json
import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from agent.agent import (  # noqa: E402
    MAX_TOOL_ROUNDS,
    BusinessAgent,
    _stopped_message,
    _trim_history,
    clean_tool_name,
)
from agent.llm import ModelReply, ToolCall  # noqa: E402


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


def _conversation(turns: int, rounds: int = 1) -> list[dict]:
    """Build the message shape the agent appends, one user turn per question."""
    history: list[dict] = []
    for index in range(turns):
        history.append({"role": "user", "content": f"question {index}"})
        for _ in range(rounds):
            history.append({"role": "assistant", "content": "", "tool_calls": [{"id": "x"}]})
            history.append({"role": "tool", "tool_call_id": "x", "content": "{}"})
        history.append({"role": "assistant", "content": "done"})
    return history


class TrimHistoryTests(unittest.TestCase):
    def test_trim_keeps_the_history_starting_on_a_user_turn(self):
        history = _conversation(turns=4, rounds=2)
        _trim_history(history, limit=12)
        self.assertTrue(history)
        self.assertLessEqual(len(history), 12)
        self.assertEqual(history[0]["role"], "user")

    def test_trim_does_not_strand_a_tool_result(self):
        # This is the shape that failed live: a tool result at the head with the
        # toolUse it answers already dropped, which Converse rejects outright.
        history = _conversation(turns=4, rounds=2)
        _trim_history(history, limit=12)
        for index, message in enumerate(history):
            if message["role"] == "tool":
                self.assertGreater(index, 0)
                self.assertEqual(history[index - 1]["role"], "assistant")

    def test_short_history_is_left_alone(self):
        history = _conversation(turns=2)
        before = list(history)
        _trim_history(history, limit=12)
        self.assertEqual(history, before)


class StoppedMessageTests(unittest.TestCase):
    """A turn that hits a limit has to report the work it already finished."""

    def test_completed_writes_are_reported_not_discarded(self):
        trace = [
            {"tool": "find_customer", "ok": True, "spoken": "Found Acme Corp."},
            {"tool": "send_payment_reminder", "ok": True, "spoken": "I sent Acme Corp a payment reminder for O3RSQJ1Z-0004, $1,800.00."},
            {"tool": "notify_finance_team", "ok": True, "spoken": "and notified #finance."},
            {"tool": "send_payment_reminder", "ok": False, "spoken": "No such invoice"},
        ]
        message = _stopped_message(trace, {"send_payment_reminder", "notify_finance_team"})
        self.assertIn("O3RSQJ1Z-0004", message)
        self.assertIn("Notified #finance", message)
        self.assertNotIn("No such invoice", message)
        self.assertNotIn("I needed more steps", message)

    def test_read_only_trace_keeps_the_plain_fallback(self):
        trace = [{"tool": "find_customer", "ok": True, "spoken": "Found Acme Corp."}]
        self.assertEqual(
            _stopped_message(trace, set()),
            "I needed more steps than I should take. Try asking for one thing at a time.",
        )

    def test_the_same_success_is_not_reported_twice(self):
        trace = [
            {"tool": "send_payment_reminder", "ok": True, "spoken": "I sent a reminder."},
            {"tool": "send_payment_reminder", "ok": True, "spoken": "I sent a reminder."},
        ]
        self.assertEqual(_stopped_message(trace, {"send_payment_reminder"}).count("I sent a reminder."), 1)


class _FakeTool:
    def __init__(self, name: str) -> None:
        self.name = name
        self.description = ""
        self.inputSchema = {"type": "object", "properties": {}}


class _FakeTools:
    def __init__(self, names: list[str]) -> None:
        self.tools = [_FakeTool(name) for name in names]


class _Block:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeToolResult:
    def __init__(self, payload: dict) -> None:
        self.content = [_Block(json.dumps(payload))]


class _FakeSession:
    """Stands in for mcp.ClientSession, answering the way the server does."""

    def __init__(self, read, write) -> None:
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def initialize(self) -> None:
        return None

    async def list_tools(self):
        return _FakeTools(
            ["find_customer", "get_overdue_invoices", "send_payment_reminder", "notify_finance_team"]
        )

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "send_payment_reminder":
            if arguments.get("invoice_id") == "in_missing":
                return _FakeToolResult({"ok": False, "spoken": "No such invoice"})
            if arguments.get("confirmed"):
                return _FakeToolResult(
                    {"ok": True, "spoken": "I sent Acme Corp a payment reminder for O3RSQJ1Z-0004, $1,800.00."}
                )
            return _FakeToolResult({"ok": False, "needs_confirmation": True, "spoken": "Should I send it?"})
        return _FakeToolResult({"ok": True, "spoken": "Found Acme Corp."})


class _FakeMcpConnection:
    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return (None, None, None)

    async def __aexit__(self, *exc_info):
        return False


class _ScriptedBackend:
    """Canned replies first, then endless read calls so the loop reaches its limit."""

    def __init__(self, replies) -> None:
        self._replies = list(replies)
        self.rounds = 0

    def complete(self, system_prompt, history, tool_defs):
        self.rounds += 1
        if self._replies:
            return self._replies.pop(0)
        return ModelReply(
            text="",
            tool_calls=[
                ToolCall(
                    id="extra-{}".format(self.rounds),
                    name="find_customer",
                    arguments={"query": "spare {}".format(self.rounds)},
                )
            ],
        )


class TurnBudgetTests(unittest.TestCase):
    def _run(self, backend):
        agent = BusinessAgent(mcp_url="http://fake.invalid/mcp", backend=backend)
        with patch("agent.agent.streamablehttp_client", _FakeMcpConnection), patch(
            "agent.agent.ClientSession", _FakeSession
        ):
            return asyncio.run(agent.ask("chase Acme"))

    def test_cut_short_turn_reports_the_action_it_completed(self):
        # Two rounds of real work, then a model that keeps reading: the turn runs
        # out of rounds, and the reply has to mention the reminder that was sent.
        backend = _ScriptedBackend(
            [
                ModelReply(text="", tool_calls=[ToolCall(id="c1", name="send_payment_reminder", arguments={"invoice_id": "in_1"})]),
                ModelReply(
                    text="",
                    tool_calls=[
                        ToolCall(id="c2", name="send_payment_reminder", arguments={"invoice_id": "in_1", "confirmed": True})
                    ],
                ),
            ]
        )
        result = self._run(backend)
        self.assertIn("O3RSQJ1Z-0004", result["reply"])
        self.assertIn("I stopped there", result["reply"])
        self.assertEqual(backend.rounds, MAX_TOOL_ROUNDS)

    def test_repeated_failure_stops_the_turn_early(self):
        # The same call failing twice with the same arguments will not start
        # working; the turn should stop instead of spending every round on it.
        failing = ModelReply(
            text="",
            tool_calls=[ToolCall(id="c1", name="send_payment_reminder", arguments={"invoice_id": "in_missing"})],
        )
        backend = _ScriptedBackend([failing, failing, failing, failing])
        result = self._run(backend)
        self.assertEqual(backend.rounds, 2)
        self.assertEqual(
            result["reply"],
            "I needed more steps than I should take. Try asking for one thing at a time.",
        )


if __name__ == "__main__":
    unittest.main()
