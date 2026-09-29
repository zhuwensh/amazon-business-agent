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
            import boto3  # noqa: F401
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise LLMError("LLM_PROVIDER=bedrock needs boto3: pip install boto3") from exc

        import boto3

        self._client = boto3.client(
            "bedrock-runtime",
            region_name=(os.environ.get("AWS_REGION") or "us-east-1").strip(),
        )
        self._model = (
            os.environ.get("BEDROCK_MODEL_ID") or "anthropic.claude-3-5-sonnet-20241022-v2:0"
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
