"""The agent loop: plan -> call MCP tool -> observe -> answer.

The loop is deliberately thin. All business logic lives in the MCP server, all
model access lives behind `llm.Backend`, and this file only decides *how many*
tool calls to make and *when to stop*.

Run it directly:
    python -m agent.agent "Does Acme have anything overdue?"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from typing import Any, Sequence

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from mcp_server.config import bootstrap

from . import prompts
from .llm import Backend, ModelReply, build_backend, describe_error

DEFAULT_MCP_URL = "http://127.0.0.1:8000/mcp"
# A turn is bounded three ways, because a voice turn that runs long has already
# failed even when it eventually answers. Rounds cap model calls (latency and
# cost); the deadline caps wall-clock time, so a slow model simply gets fewer
# rounds; the write budget caps how many irreversible actions one request can
# take. The round count is sized for the intended path - find, read, confirm,
# write, notify - and is a backstop rather than a target: a request that needs
# more is better served by doing one thing at a time than by hanging.
MAX_TOOL_ROUNDS = 10
MAX_HISTORY_TURNS = 12
TURN_DEADLINE_SECONDS = 25.0
MAX_WRITE_ACTIONS = 6

TOOL_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def clean_tool_name(raw: str) -> str:
    """Normalise a tool name the model produced.

    gpt-oss models render their own response format, and its control tokens leak:
    a call for `notify_finance_team` can arrive as
    `notify_finance_team<|channel|>commentary`. Converse accepts that on the way
    out but rejects it on the way back in — every later request in the conversation
    then fails validation — so the name is normalised as soon as it is received,
    before it reaches the history or the MCP server.

    Returns an empty string when nothing usable is left.
    """
    name = (raw or "").split("<")[0].strip()
    return name if TOOL_NAME_PATTERN.match(name) else ""


def _trim_history(history: list[dict[str, Any]], limit: int = MAX_HISTORY_TURNS) -> None:
    """Drop the oldest messages without cutting a tool exchange in half.

    Trimming by raw message count leaves a tool result at the head of the list
    with the assistant toolUse it answers already dropped. Converse rejects that
    with "Expected toolResult blocks at messages.0.content", and because the
    error is raised before the next trim runs, the session never recovers.
    """
    if len(history) <= limit:
        return
    cut = len(history) - limit
    while cut < len(history) and history[cut].get("role") != "user":
        cut += 1
    del history[:cut]


def _mcp_tool_to_openai(tool: Any) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": (tool.description or "").strip(),
            "parameters": tool.inputSchema or {"type": "object", "properties": {}},
        },
    }


def _parse_tool_result(result: Any) -> Any:
    """FastMCP returns JSON text for dict results; fall back to the raw string."""
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text is None:
            continue
        try:
            return json.loads(text)
        except (TypeError, ValueError):
            return text
    return {}


def _stopped_message(trace: list[dict[str, Any]], consequential: set[str]) -> str:
    """Report what a turn actually did when it ran out of budget.

    Hitting a limit used to replace the whole turn with "I needed more steps",
    which is how a user hears that nothing happened *after* the reminder went
    out. The actions that did run are already in the trace, so say them, then say
    that the request was cut short instead of pretending it failed.
    """
    done: list[str] = []
    for step in trace:
        spoken = step.get("spoken")
        if not (step.get("ok") and spoken and step.get("tool") in consequential):
            continue
        fragment = str(spoken).strip()
        if fragment[:4].lower() == "and ":
            fragment = fragment[4:]
        if fragment:
            fragment = fragment[0].upper() + fragment[1:]
        if fragment and fragment not in done:
            done.append(fragment)
    if not done:
        return "I needed more steps than I should take. Try asking for one thing at a time."
    return (
        " ".join(done)
        + " I stopped there - one request can only do so much at a time, so ask me for whatever is left."
    )


class BusinessAgent:
    """Stateful agent: one conversation per `session_id`."""

    def __init__(self, mcp_url: str | None = None, backend: Backend | None = None) -> None:
        self.mcp_url = mcp_url or (os.environ.get("MCP_URL") or DEFAULT_MCP_URL).strip()
        self._backend = backend
        self._history: dict[str, list[dict[str, Any]]] = {}

    @property
    def backend(self) -> Backend:
        if self._backend is None:
            self._backend = build_backend()
        return self._backend

    def _messages(self, session_id: str) -> list[dict[str, Any]]:
        return self._history.setdefault(session_id, [])

    def reset(self, session_id: str) -> None:
        self._history.pop(session_id, None)

    async def ask(self, text: str, session_id: str = "default") -> dict[str, Any]:
        """Answer one user turn, calling MCP tools as needed."""
        trace: list[dict[str, Any]] = []
        history = self._messages(session_id)
        history.append({"role": "user", "content": text})

        # Resolve the model before touching the network: a missing key should read
        # as a configuration message, not as a transport error.
        backend = self.backend

        async with streamablehttp_client(self.mcp_url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tool_defs = [_mcp_tool_to_openai(tool) for tool in (await session.list_tools()).tools]
                tool_names = [tool["function"]["name"] for tool in tool_defs]

                reply = ModelReply(text="")
                consequential: set[str] = set()
                repeated_failures: dict[str, int] = {}
                writes_done = 0
                stopped: str | None = None
                deadline = time.monotonic() + TURN_DEADLINE_SECONDS

                for _ in range(MAX_TOOL_ROUNDS):
                    if time.monotonic() > deadline:
                        stopped = "deadline"
                        break

                    reply = backend.complete(prompts.SYSTEM_PROMPT, history, tool_defs)
                    if not reply.tool_calls:
                        break

                    # Normalise before the name reaches the history or the server.
                    for call in reply.tool_calls:
                        call.name = clean_tool_name(call.name)

                    if any(not call.name for call in reply.tool_calls):
                        # A name that cannot be normalised cannot be sent back to
                        # Converse either, so end the turn instead of poisoning the
                        # conversation with an invalid toolUse block.
                        reply = ModelReply(
                            text="I lost track of which tool to use there. Say that again?"
                        )
                        break

                    history.append(
                        {
                            "role": "assistant",
                            "content": reply.text or "",
                            "tool_calls": [
                                {
                                    "id": call.id,
                                    "type": "function",
                                    "function": {
                                        "name": call.name,
                                        "arguments": json.dumps(call.arguments, ensure_ascii=False),
                                    },
                                }
                                for call in reply.tool_calls
                            ],
                        }
                    )
                    for call in reply.tool_calls:
                        if call.name not in tool_names:
                            # Never forward an unknown name: it costs a round trip and
                            # tells the model nothing about what it should have used.
                            parsed = {
                                "ok": False,
                                "error": f"There is no tool called '{call.name}'.",
                                "available_tools": tool_names,
                            }
                        else:
                            try:
                                raw = await session.call_tool(call.name, call.arguments)
                                parsed = _parse_tool_result(raw)
                            except asyncio.CancelledError:
                                # The client went away mid-call (barge-in, closed
                                # tab). Record a result before unwinding: a
                                # stranded toolUse makes every later request in
                                # this session fail Converse validation.
                                parsed = {"ok": False, "spoken": "Cancelled."}
                                trace.append(prompts.trace_entry(call.name, call.arguments, parsed))
                                history.append(
                                    {
                                        "role": "tool",
                                        "tool_call_id": call.id,
                                        "content": json.dumps(parsed, ensure_ascii=False),
                                    }
                                )
                                raise
                            except Exception as exc:  # noqa: BLE001 - surfaced to the model
                                parsed = {
                                    "ok": False,
                                    "spoken": f"The tool {call.name} failed: {exc}",
                                }
                        if isinstance(parsed, dict):
                            # A tool that asks to be confirmed is a consequential
                            # one; remember it so its successes can be counted and
                            # reported rather than thrown away at the limit.
                            if parsed.get("needs_confirmation"):
                                consequential.add(call.name)
                            if parsed.get("ok") and call.name in consequential:
                                writes_done += 1
                            if not parsed.get("ok") and not parsed.get("needs_confirmation"):
                                signature = call.name + "|" + json.dumps(call.arguments, sort_keys=True, ensure_ascii=False)
                                repeated_failures[signature] = repeated_failures.get(signature, 0) + 1
                        trace.append(prompts.trace_entry(call.name, call.arguments, parsed))
                        history.append(
                            {
                                "role": "tool",
                                "tool_call_id": call.id,
                                "content": json.dumps(parsed, ensure_ascii=False)[:4000],
                            }
                        )
                    if writes_done >= MAX_WRITE_ACTIONS:
                        stopped = "writes"
                        break
                    if any(count >= 2 for count in repeated_failures.values()):
                        # The same call failing twice with the same arguments is
                        # not going to start working; stop rather than spend the
                        # rest of the budget on it.
                        stopped = "repeat"
                        break
                else:
                    stopped = "rounds"

                if stopped is not None:
                    reply = ModelReply(text=_stopped_message(trace, consequential))

        spoken = (reply.text or "").strip()
        if not spoken and trace:
            spoken = trace[-1].get("spoken") or ""

        history.append({"role": "assistant", "content": spoken})
        _trim_history(history)

        return {"reply": spoken, "trace": trace, "tools_available": tool_names}


async def _amain(argv: Sequence[str] | None = None) -> int:
    bootstrap()

    parser = argparse.ArgumentParser(description="BusinessFlow Agent — CLI")
    parser.add_argument("question", nargs="*", help="the request, in natural language")
    parser.add_argument("--mcp-url", default=None, help=f"default: {DEFAULT_MCP_URL}")
    args = parser.parse_args(argv)

    agent = BusinessAgent(mcp_url=args.mcp_url)
    question = " ".join(args.question) or "Does Acme have anything overdue?"

    result = await agent.ask(question)
    print(f"\nYou:    {question}")
    print(f"Agent:  {result['reply']}\n")
    if result["trace"]:
        print("Tool trace:")
        for step in result["trace"]:
            flag = "needs confirmation" if step.get("needs_confirmation") else ("ok" if step.get("ok") else "error")
            print(f"  {step['tool']}({json.dumps(step['arguments'], ensure_ascii=False)}) -> {flag}")
    return 0


def main() -> None:
    try:
        raise SystemExit(asyncio.run(_amain()))
    except KeyboardInterrupt:  # pragma: no cover
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001 - one readable line beats a traceback
        print(describe_error(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
