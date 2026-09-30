"""Verify a Bedrock configuration, including the part the agent depends on most.

Run this after filling in `.env`:

    python scripts/check_bedrock.py

It answers three questions in order, because they fail for different reasons:

1. do the credentials work at all?
2. does the configured model answer through the Converse API?
3. does the configured model *ask for a tool* when one is offered?

The third one is the one that matters here. An agent loop that cannot get a
`toolUse` block back is not an agent, and tool calling is not supported uniformly
across models, APIs and endpoints — so it is checked explicitly rather than
assumed. Exit code 0 means all three passed.
"""

from __future__ import annotations

import os
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from agent.llm import build_backend, describe_error  # noqa: E402
from mcp_server.config import bootstrap  # noqa: E402

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_overdue_invoices",
            "description": "List the overdue invoices for one customer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer": {"type": "string", "description": "The company name"}
                },
                "required": ["customer"],
            },
        },
    }
]

PROMPT = "How much does Acme owe us, and how late is it?"


def main() -> int:
    bootstrap()

    provider = (os.environ.get("LLM_PROVIDER") or "openai").strip().lower()
    if provider != "bedrock":
        print(f"NOTE: LLM_PROVIDER is '{provider}'. Set LLM_PROVIDER=bedrock in .env")
        print("      to test the Bedrock path; continuing anyway.\n")

    try:
        backend = build_backend()
    except Exception as exc:  # noqa: BLE001 - reported below
        print("FAIL 1/3: could not build the backend - " + describe_error(exc))
        return 1

    model = getattr(backend, "_model", "(unknown)")
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "(default)"
    print(f"backend: {backend.name} | model: {model} | region: {region}")
    print(f"credentials file: {os.environ.get('AWS_SHARED_CREDENTIALS_FILE') or '(default chain)'}\n")

    print("PASS 1/3: backend built")

    print("2/3 plain Converse call …")
    try:
        reply = backend.complete(
            "You are a terse assistant.",
            [{"role": "user", "content": "Reply with the single word: ready"}],
            [],
        )
    except Exception as exc:  # noqa: BLE001 - reported below
        print("FAIL 2/3: " + describe_error(exc))
        return 1
    print("PASS 2/3: " + (reply.text or "").strip()[:80])

    print("3/3 tool calling …")
    try:
        reply = backend.complete(
            "You are a finance assistant. Always use a tool when one fits the request.",
            [{"role": "user", "content": PROMPT}],
            TOOLS,
        )
    except Exception as exc:  # noqa: BLE001 - reported below
        print("FAIL 3/3: the tool-calling request itself errored - " + describe_error(exc))
        return 1

    if reply.tool_calls:
        call = reply.tool_calls[0]
        print(f"PASS 3/3: the model asked for {call.name}({call.arguments})")
        print("\nAll three checks passed. Start the server and the simulator.")
        return 0

    print("FAIL 3/3: the model answered without calling the tool:")
    print("      " + (reply.text or "(empty)").strip()[:160])
    print("      The agent loop needs tool calling. Try a different BEDROCK_MODEL_ID -")
    print("      Claude Sonnet and the Amazon Nova models are the usual choices.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
