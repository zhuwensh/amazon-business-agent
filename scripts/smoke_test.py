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
import os
import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mcp import ClientSession  # noqa: E402
from mcp.client.streamable_http import streamablehttp_client  # noqa: E402

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


async def _check() -> int:
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
                        result = await asyncio.wait_for(
                            session.call_tool("find_customer", {"query": "Acme"}), timeout=30
                        )
                        text = result.content[0].text if result.content else ""
                        _say(f"PASS: live tool call returned: {text[:200]}")
                    else:
                        _say("SKIP: live Stripe tool call (STRIPE_API_KEY not set)")
            return 0
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:  # pragma: no cover
                server.kill()


async def main() -> int:
    try:
        return await asyncio.wait_for(_check(), timeout=TOTAL_TIMEOUT)
    except asyncio.TimeoutError:
        _say(f"FAIL: timed out after {TOTAL_TIMEOUT}s\n" + _server_log_tail())
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
