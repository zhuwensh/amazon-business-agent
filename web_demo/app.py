"""Simulated Alexa+ experience, in the browser.

The hackathon FAQ is explicit that participants build their own front end: the
gated Alexa+ Web Simulator is not available to us. This is that front end — voice
in, voice out, and a visible tool trace so the orchestration is inspectable.

    python -m web_demo.app     ->  http://127.0.0.1:8080
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from pydantic import BaseModel

from agent.agent import DEFAULT_MCP_URL, BusinessAgent
from mcp_server.config import bootstrap

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="BusinessFlow Agent — simulated Alexa+ experience")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

_agent = BusinessAgent(mcp_url=(os.environ.get("MCP_URL") or DEFAULT_MCP_URL).strip())


class AskRequest(BaseModel):
    text: str
    session_id: str = "web"


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health() -> dict[str, Any]:
    """Report whether the MCP server is reachable, and which tools it exposes."""
    try:
        async with streamablehttp_client(_agent.mcp_url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = [tool.name for tool in (await session.list_tools()).tools]
        return {"connected": True, "mcp_url": _agent.mcp_url, "tools": tools}
    except Exception as exc:  # noqa: BLE001 - reported to the UI
        return {"connected": False, "mcp_url": _agent.mcp_url, "error": str(exc), "tools": []}


@app.post("/api/ask")
async def ask(request: AskRequest) -> dict[str, Any]:
    try:
        return await _agent.ask(request.text, session_id=request.session_id)
    except Exception as exc:  # noqa: BLE001 - reported to the UI
        return {
            "reply": f"I could not complete that: {exc}",
            "trace": [],
            "error": str(exc),
        }


@app.post("/api/reset")
async def reset(session_id: str = "web") -> dict[str, Any]:
    _agent.reset(session_id)
    return {"ok": True}


def main() -> None:
    import uvicorn

    bootstrap()

    port = int((os.environ.get("WEB_PORT") or "8080").strip() or "8080")
    print(f"BusinessFlow Agent simulator: http://127.0.0.1:{port}")
    print(f"MCP server expected at: {_agent.mcp_url}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
