"""Pluggable model backends for the agent loop.

Two providers, behind one tiny interface:

* ``openai``  — any OpenAI-compatible endpoint (default). No AWS account needed to
  run the demo.
* ``bedrock`` — Amazon Bedrock via the Converse API. This is the path that
  qualifies for the hackathon's AWS Builder mini challenge.

Both return the same neutral shape, so ``agent.py`` never branches on provider.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Sequence

DEFAULT_BEDROCK_MODEL = "anthropic.claude-3-5-sonnet-20241022-v2:0"


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelReply:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMError(RuntimeError):
    """Raised when the configured model backend cannot be used."""


def describe_error(exc: BaseException) -> str:
    """Return the real cause of an error, unwrapping anyio task-group wrappers.

    An exception raised inside an MCP client session comes back as an
    `ExceptionGroup` that reads like "unhandled errors in a TaskGroup
    (1 sub-exception)" — useless to a user. The interesting part is the innermost
    exception, which is usually a plain, actionable message.
    """
    while getattr(exc, "exceptions", None):
        exc = exc.exceptions[0]
    if isinstance(exc, LLMError):
        return str(exc)
    return f"{type(exc).__name__}: {exc}"


def build_backend() -> "Backend":
    provider = (os.environ.get("LLM_PROVIDER") or "openai").strip().lower()
    if provider == "bedrock":
        return BedrockBackend()
    return OpenAICompatibleBackend()


class Backend:
    name = "base"

    def complete(
        self,
        system: str,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]],
    ) -> ModelReply:  # pragma: no cover - interface
        raise NotImplementedError


class OpenAICompatibleBackend(Backend):
    """OpenAI / OpenRouter / any compatible endpoint."""

    name = "openai"

    def __init__(self) -> None:
        from openai import OpenAI  # imported lazily so tests need no dependency

        api_key = (os.environ.get("LLM_API_KEY") or "").strip()
        if not api_key:
            raise LLMError(
                "LLM_API_KEY is not set. Either set it in .env, or set "
                "LLM_PROVIDER=bedrock and configure AWS credentials."
            )
        self._client = OpenAI(
            api_key=api_key,
            base_url=(os.environ.get("LLM_BASE_URL") or "https://api.openai.com/v1").strip(),
        )
        self._model = (os.environ.get("LLM_MODEL") or "gpt-4o-mini").strip()

    def complete(self, system, messages, tools) -> ModelReply:
        payload: list[dict[str, Any]] = [{"role": "system", "content": system}, *messages]
        response = self._client.chat.completions.create(
            model=self._model,
            messages=payload,
            tools=list(tools) or None,
            temperature=0.2,
        )
        choice = response.choices[0].message
        calls = [
            ToolCall(
                id=call.id,
                name=call.function.name,
                arguments=json.loads(call.function.arguments or "{}"),
            )
            for call in (choice.tool_calls or [])
        ]
        return ModelReply(text=choice.content or "", tool_calls=calls)


class BedrockBackend(Backend):
    """Amazon Bedrock, Converse API. Requires boto3 and AWS credentials."""

    name = "bedrock"

    def __init__(self) -> None:
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise LLMError("LLM_PROVIDER=bedrock needs boto3: pip install boto3") from exc

        # Credentials: the same layout the SmartSales-AI project uses — keep the
        # profile file inside the repo folder and point boto3 at it explicitly, so
        # the demo is self-contained instead of depending on ambient state. The
        # file itself must never be committed.
        credentials_file = (os.environ.get("AWS_SHARED_CREDENTIALS_FILE") or "").strip()
        profile = (os.environ.get("AWS_PROFILE") or "").strip()
        region = (
            os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
        ).strip()

        if credentials_file:
            if not os.path.exists(credentials_file):
                raise LLMError(
                    f"AWS_SHARED_CREDENTIALS_FILE points at a file that does not exist: "
                    f"{credentials_file}"
                )
            os.environ.setdefault("AWS_SHARED_CREDENTIALS_FILE", credentials_file)

        session = boto3.Session(profile_name=profile or None, region_name=region)
        self._client = session.client("bedrock-runtime", region_name=region)
        self._model = (
            os.environ.get("BEDROCK_MODEL_ID") or DEFAULT_BEDROCK_MODEL
        ).strip()

    def complete(self, system, messages, tools) -> ModelReply:
        request: dict[str, Any] = {
            "modelId": self._model,
            "system": [{"text": system}],
            "messages": [self._to_bedrock(message) for message in messages],
            "inferenceConfig": {"temperature": 0.2},
        }
        if tools:
            request["toolConfig"] = {
                "tools": [
                    {
                        "toolSpec": {
                            "name": tool["function"]["name"],
                            "description": tool["function"].get("description", ""),
                            "inputSchema": {"json": tool["function"]["parameters"]},
                        }
                    }
                    for tool in tools
                ]
            }

        response = self._client.converse(**request)
        content = response["output"]["message"].get("content", [])
        text_parts, calls = [], []
        for block in content:
            if "text" in block:
                text_parts.append(block["text"])
            elif "toolUse" in block:
                use = block["toolUse"]
                calls.append(ToolCall(id=use["toolUseId"], name=use["name"], arguments=use.get("input") or {}))
        return ModelReply(text="\n".join(text_parts), tool_calls=calls)

    @staticmethod
    def _to_bedrock(message: dict[str, Any]) -> dict[str, Any]:
        """Translate the neutral message shape into Bedrock's content blocks."""
        role = message["role"]
        if "tool_calls" in message:
            return {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": call["id"],
                            "name": call["function"]["name"],
                            "input": json.loads(call["function"].get("arguments") or "{}"),
                        }
                    }
                    for call in message["tool_calls"]
                ],
            }
        if role == "tool":
            return {
                "role": "user",
                "content": [
                    {"toolResult": {"toolUseId": message["tool_call_id"], "content": [{"text": message["content"]}]}}
                ],
            }
        return {"role": role, "content": [{"text": message.get("content") or ""}]}
