"""End-to-end smoke test for the MCP server.

Starts the server as a subprocess on a test port, connects over **Streamable
HTTP**, initializes a session, lists the tools, and (when a Stripe key is present)
calls one read-only tool for real.

This is the check that proves the Alexa+ track's transport requirement, so it is
worth running before recording the demo:

    python scripts/smoke_test.py
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mcp import ClientSession  # noqa: E402
from mcp.client.streamable_http import streamablehttp_client  # noqa: E402

from mcp_server.config import bootstrap  # noqa: E402

PORT = int(os.environ.get("SMOKE_TEST_PORT", "8765"))
URL = f"http://127.0.0.1:{PORT}/mcp"
LOG_PATH = REPO_ROOT / "tmp_smoke_server.log"
TOTAL_TIMEOUT = 90

EXPECTED_TOOLS = {
    "find_customer",
    "get_overdue_invoices",
    "get_cashflow_summary",
    "send_payment_reminder",
    "notify_finance_team",
}


def _say(message: str) -> None:
    # Flush, so the result is visible even when stdout is redirected to a file.
    print(message, flush=True)


async def _wait_for_port(port: int, attempts: int = 40) -> bool:
    for _ in range(attempts):
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # noqa: BLE001 - best effort
                pass
            return True
        except OSError:
            await asyncio.sleep(0.5)
    return False


def _server_log_tail(lines: int = 25) -> str:
    if not LOG_PATH.exists():
        return "(no server log)"
    content = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(content[-lines:]) or "(server log empty)"


async def _call(session: ClientSession, name: str, arguments: dict) -> dict:
    result = await asyncio.wait_for(session.call_tool(name, arguments), timeout=30)
    text = result.content[0].text if result.content else ""
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return {"raw": text}


async def _check_live_scenario(session: ClientSession, query: str = "Acme") -> list[str]:
    """Exercise the demo path against the real Stripe account.

    Read-only by design: the two write tools are called with `confirmed=False`,
    which is exactly what the agent does before asking the user. Nothing is emailed
    and nothing is posted to Slack.
    """
    failures: list[str] = []

    found = await _call(session, "find_customer", {"query": query})
    candidates = (found.get("data") or {}).get("candidates") or []
    if not candidates:
        failures.append(f"find_customer returned no candidates for '{query}'")
        return failures
    top = candidates[0]
    _say(
        f"PASS: find_customer('{query}') -> {len(candidates)} candidate(s), "
        f"best: {top['name']} (score {top['match_score']})"
    )

    overdue = await _call(
        session, "get_overdue_invoices", {"customer": top["name"], "customer_id": top["id"]}
    )
    if not overdue.get("ok"):
        failures.append(f"get_overdue_invoices failed: {overdue.get('error')}")
        return failures

    data = overdue["data"]
    _say(f"PASS: get_overdue_invoices -> {data['count']} overdue from {top['name']}")
    _say("      spoken: " + str(overdue.get("spoken")))

    invoices = data.get("invoices") or []
    if not invoices:
        _say("SKIP: write-gate check (this customer has nothing overdue)")
        return failures

    gate = await _call(
        session, "send_payment_reminder", {"invoice_id": invoices[0]["id"], "confirmed": False}
    )
    if gate.get("needs_confirmation"):
        _say("PASS: send_payment_reminder asked first: " + str(gate.get("spoken")))
    else:
        failures.append("send_payment_reminder did not require confirmation")

    slack_gate = await _call(
        session, "notify_finance_team", {"message": "smoke test", "confirmed": False}
    )
    if slack_gate.get("needs_confirmation"):
        _say("PASS: notify_finance_team asked first: " + str(slack_gate.get("spoken")))
    else:
        failures.append("notify_finance_team did not require confirmation")

    # Posting for real is opt-in: it puts a message in someone's channel.
    if os.environ.get("SMOKE_TEST_SLACK") == "1":
        delivered = await _call(
            session,
            "notify_finance_team",
            {
                "message": "ChaseLine smoke test — this message proves the "
                "finance notification path works end to end.",
                "confirmed": True,
            },
        )
        if delivered.get("ok"):
            _say("PASS: notify_finance_team delivered: " + str(delivered.get("spoken")))
        else:
            failures.append("notify_finance_team delivery failed: " + str(delivered.get("error")))
    else:
        _say("SKIP: real Slack delivery (set SMOKE_TEST_SLACK=1 to post a test message)")

    return failures


async def _check() -> int:
    failures: list[str] = []
    env = {**os.environ, "MCP_HTTP": "1", "MCP_HOST": "127.0.0.1", "MCP_PORT": str(PORT)}

    # The child writes to a file rather than to a pipe: a pipe nobody drains will
    # deadlock the server once the buffer fills.
    with open(LOG_PATH, "w", encoding="utf-8", errors="replace") as log_file:
        server = subprocess.Popen(
            [sys.executable, "-u", "-m", "mcp_server.server"],
            cwd=str(REPO_ROOT),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        try:
            if not await _wait_for_port(PORT):
                _say("FAIL: the server never opened its port\n" + _server_log_tail())
                return 1

            async with streamablehttp_client(URL) as (read, write, _):
                async with ClientSession(read, write) as session:
                    info = await asyncio.wait_for(session.initialize(), timeout=30)
                    _say(f"PASS: session initialized, protocol {info.protocolVersion}")

                    listed = await asyncio.wait_for(session.list_tools(), timeout=30)
                    tools = {tool.name for tool in listed.tools}
                    missing = EXPECTED_TOOLS - tools
                    if missing:
                        _say(f"FAIL: missing tools {sorted(missing)}\n" + _server_log_tail())
                        return 1
                    _say(f"PASS: {len(tools)} tools exposed: {', '.join(sorted(tools))}")

                    if os.environ.get("STRIPE_API_KEY"):
                        failures = await _check_live_scenario(
                            session, os.environ.get("SMOKE_TEST_CUSTOMER", "Acme")
                        )
                    else:
                        _say("SKIP: live Stripe checks (STRIPE_API_KEY not set)")
            for failure in failures:
                _say("FAIL: " + failure)
            return 1 if failures else 0
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:  # pragma: no cover
                server.kill()


async def main() -> int:
    bootstrap()
    try:
        return await asyncio.wait_for(_check(), timeout=TOTAL_TIMEOUT)
    except asyncio.TimeoutError:
        _say(f"FAIL: timed out after {TOTAL_TIMEOUT}s\n" + _server_log_tail())
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
