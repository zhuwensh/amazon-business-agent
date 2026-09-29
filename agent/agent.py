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
import sys
from typing import Any, Sequence

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from mcp_server.config import bootstrap

from . import prompts
from .llm import Backend, ModelReply, build_backend

DEFAULT_MCP_URL = "http://127.0.0.1:8000/mcp"
MAX_TOOL_ROUNDS = 6
MAX_HISTORY_TURNS = 12


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

        async with streamablehttp_client(self.mcp_url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tool_defs = [_mcp_tool_to_openai(tool) for tool in (await session.list_tools()).tools]
                tool_names = [tool["function"]["name"] for tool in tool_defs]

                reply = ModelReply(text="")
                for _ in range(MAX_TOOL_ROUNDS):
                    reply = self.backend.complete(prompts.SYSTEM_PROMPT, history, tool_defs)
                    if not reply.tool_calls:
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
                        try:
                            raw = await session.call_tool(call.name, call.arguments)
                            parsed = _parse_tool_result(raw)
                        except Exception as exc:  # noqa: BLE001 - surfaced to the model
                            parsed = {"ok": False, "spoken": f"The tool {call.name} failed: {exc}"}
                        trace.append(prompts.trace_entry(call.name, call.arguments, parsed))
                        history.append(
                            {
                                "role": "tool",
                                "tool_call_id": call.id,
                                "content": json.dumps(parsed, ensure_ascii=False)[:4000],
                            }
                        )
                else:
                    reply = ModelReply(
                        text="I needed more steps than I should take. Try asking for one thing at a time."
                    )

        spoken = (reply.text or "").strip()
        if not spoken and trace:
            spoken = trace[-1].get("spoken") or ""

        history.append({"role": "assistant", "content": spoken})
        del history[:-MAX_HISTORY_TURNS]

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


if __name__ == "__main__":
    main()
