import json
import os
import time
from typing import Any, Sequence

import requests
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool

from config import DEEPSEEK_API_KEY, DEEPSEEK_API_URL, DEEPSEEK_MODEL
from deepseek_client import DeepSeekError


_MODEL_CALL_TIMINGS: list[dict[str, Any]] = []


def reset_model_call_timings() -> None:
    _MODEL_CALL_TIMINGS.clear()


def get_model_call_timings() -> list[dict[str, Any]]:
    return [dict(item) for item in _MODEL_CALL_TIMINGS]


def _record_model_call_timing(timing: dict[str, Any]) -> None:
    _MODEL_CALL_TIMINGS.append({**timing, "call_index": len(_MODEL_CALL_TIMINGS) + 1})


class ChatDeepSeek(BaseChatModel):
    """Minimal DeepSeek chat model adapter for LangChain agents."""

    model: str = DEEPSEEK_MODEL
    api_url: str = DEEPSEEK_API_URL
    api_key: str = ""
    temperature: float = 0
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | None = None

    @property
    def _llm_type(self) -> str:
        return "deepseek-chat"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | BaseTool | Any],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> "ChatDeepSeek":
        openai_tools = [convert_to_openai_tool(tool) for tool in tools]
        return self.model_copy(update={"tools": openai_tools, "tool_choice": tool_choice})

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [self._convert_message(message) for message in messages],
            "temperature": self.temperature,
        }
        if stop:
            payload["stop"] = stop
        if self.tools:
            payload["tools"] = self.tools
        if self.tool_choice:
            payload["tool_choice"] = self.tool_choice

        started_at = time.perf_counter()
        response = requests.post(
            self.api_url,
            headers={
                "Authorization": f"Bearer {self._get_api_key()}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        duration_ms = int((time.perf_counter() - started_at) * 1000)

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            _record_model_call_timing(
                {
                    "duration_ms": duration_ms,
                    "http_status": response.status_code,
                    "model": self.model,
                    "error": "non_json_response",
                }
            )
            raise DeepSeekError(f"DeepSeek returned non-JSON response: HTTP {response.status_code}") from exc

        usage = data.get("usage") or {}
        _record_model_call_timing(
            {
                "duration_ms": duration_ms,
                "http_status": response.status_code,
                "model": data.get("model") or self.model,
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "tool_count": len(self.tools or []),
            }
        )

        if response.status_code >= 400:
            message = data.get("error", {}).get("message") or response.text
            raise DeepSeekError(f"DeepSeek API call failed: HTTP {response.status_code}: {message}")

        choices = data.get("choices") or []
        if not choices:
            raise DeepSeekError(f"DeepSeek response missing choices: {data}")

        raw_message = choices[0].get("message", {})
        ai_message = self._build_ai_message(raw_message)
        return ChatResult(
            generations=[ChatGeneration(message=ai_message)],
            llm_output={
                "model": data.get("model"),
                "usage": data.get("usage"),
            },
        )

    def _get_api_key(self) -> str:
        api_key = (self.api_key or os.getenv("DEEPSEEK_API_KEY") or DEEPSEEK_API_KEY).strip()
        if not api_key:
            try:
                import streamlit as st

                api_key = str(st.secrets.get("DEEPSEEK_API_KEY", "")).strip()
            except Exception:
                api_key = ""
        if not api_key:
            raise DeepSeekError("DEEPSEEK_API_KEY is not configured.")
        return api_key

    def _convert_message(self, message: BaseMessage) -> dict[str, Any]:
        if isinstance(message, SystemMessage):
            return {"role": "system", "content": message.content}
        if isinstance(message, HumanMessage):
            return {"role": "user", "content": message.content}
        if isinstance(message, ToolMessage):
            return {
                "role": "tool",
                "tool_call_id": message.tool_call_id,
                "content": self._stringify_content(message.content),
            }
        if isinstance(message, AIMessage):
            payload: dict[str, Any] = {
                "role": "assistant",
                "content": self._stringify_content(message.content),
            }
            tool_calls = message.additional_kwargs.get("tool_calls")
            if tool_calls:
                payload["tool_calls"] = tool_calls
            elif message.tool_calls:
                payload["tool_calls"] = [
                    {
                        "id": tool_call["id"],
                        "type": "function",
                        "function": {
                            "name": tool_call["name"],
                            "arguments": json.dumps(tool_call["args"], ensure_ascii=False),
                        },
                    }
                    for tool_call in message.tool_calls
                ]
            return payload

        return {"role": message.type, "content": self._stringify_content(message.content)}

    def _build_ai_message(self, raw_message: dict[str, Any]) -> AIMessage:
        raw_tool_calls = raw_message.get("tool_calls") or []
        tool_calls = []
        for raw_tool_call in raw_tool_calls:
            function = raw_tool_call.get("function", {})
            arguments = function.get("arguments") or "{}"
            try:
                args = json.loads(arguments)
            except json.JSONDecodeError:
                args = {"arguments": arguments}
            tool_calls.append(
                {
                    "name": function.get("name", ""),
                    "args": args,
                    "id": raw_tool_call.get("id", ""),
                    "type": "tool_call",
                }
            )

        return AIMessage(
            content=raw_message.get("content") or "",
            additional_kwargs={"tool_calls": raw_tool_calls} if raw_tool_calls else {},
            tool_calls=tool_calls,
        )

    def _stringify_content(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        return json.dumps(content, ensure_ascii=False)
