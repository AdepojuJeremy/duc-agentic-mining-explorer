from __future__ import annotations

import asyncio
import json
import os
import random
from dataclasses import dataclass
from typing import Any, Callable

from openai import AsyncOpenAI
from pydantic import BaseModel

from .config import ModelRoleConfig, OpenAIConfig
from .models import RunMetrics, ToolEvent


class LLMError(RuntimeError):
    pass


@dataclass
class StructuredResult:
    value: BaseModel
    response_id: str


class OpenAIRoleClient:
    def __init__(self, role: str, api_cfg: OpenAIConfig, role_cfg: ModelRoleConfig, metrics: RunMetrics):
        self.role = role
        self.cfg = role_cfg
        self.api_cfg = api_cfg
        key = os.getenv(api_cfg.api_key_env)
        if not key:
            raise LLMError(f"missing API key environment variable: {api_cfg.api_key_env}")
        self.client = AsyncOpenAI(
            api_key=key,
            base_url=api_cfg.base_url,
            timeout=api_cfg.timeout_seconds,
        )
        self.metrics = metrics
        self.semaphore = asyncio.Semaphore(role_cfg.concurrency)

    def _usage(self, response: Any) -> None:
        usage = self.metrics.usage_for(self.role)
        usage.requests += 1
        obj = getattr(response, "usage", None)
        if not obj:
            return
        usage.input_tokens += int(getattr(obj, "input_tokens", 0) or 0)
        usage.output_tokens += int(getattr(obj, "output_tokens", 0) or 0)
        details = getattr(obj, "input_tokens_details", None)
        usage.cached_input_tokens += int(getattr(details, "cached_tokens", 0) or 0) if details else 0

    async def _retry(self, fn: Callable[[], Any]) -> Any:
        last: Exception | None = None
        for attempt in range(self.api_cfg.max_retries):
            try:
                async with self.semaphore:
                    return await fn()
            except Exception as exc:
                last = exc
                self.metrics.usage_for(self.role).errors += 1
                if attempt + 1 >= self.api_cfg.max_retries:
                    break
                await asyncio.sleep(min(30.0, (2**attempt) + random.random()))
        raise LLMError(f"{self.role} request failed after retries: {last}") from last

    def _common_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": self.cfg.model,
            "max_output_tokens": self.cfg.max_output_tokens,
        }
        if self.cfg.reasoning_effort:
            params["reasoning"] = {"effort": self.cfg.reasoning_effort}
        if self.cfg.temperature is not None:
            params["temperature"] = self.cfg.temperature
        return params

    async def structured(
        self,
        system: str,
        user: str,
        schema_model: type[BaseModel],
        schema_name: str,
    ) -> StructuredResult:
        schema = schema_model.model_json_schema()

        async def call():
            return await self.client.responses.create(
                **self._common_params(),
                instructions=system,
                input=user,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": schema_name,
                        "strict": True,
                        "schema": schema,
                    }
                },
            )

        response = await self._retry(call)
        self._usage(response)
        text = response.output_text
        if not text:
            raise LLMError(f"{self.role} returned no structured text")
        try:
            value = schema_model.model_validate_json(text)
        except Exception as exc:
            raise LLMError(f"{self.role} returned invalid structured output: {exc}") from exc
        return StructuredResult(value=value, response_id=response.id)

    async def tool_loop(
        self,
        instructions: str,
        initial_input: str,
        tools: list[dict[str, Any]],
        dispatch: Callable[[str, dict[str, Any]], Any],
        max_turns: int,
        on_event: Callable[[ToolEvent], None],
    ) -> str:
        inputs: list[Any] = [{"role": "user", "content": initial_input}]
        for turn in range(max_turns):

            async def call():
                return await self.client.responses.create(
                    **self._common_params(),
                    instructions=instructions,
                    input=inputs,
                    tools=tools,
                    tool_choice="auto",
                    parallel_tool_calls=False,
                )

            response = await self._retry(call)
            self._usage(response)
            on_event(
                ToolEvent(
                    kind="model_call",
                    name=self.role,
                    payload={"turn": turn + 1, "response_id": response.id},
                )
            )
            inputs.extend(response.output)
            calls = [x for x in response.output if getattr(x, "type", None) == "function_call"]
            if not calls:
                return response.output_text or ""
            for call_item in calls:
                name = call_item.name
                try:
                    args = json.loads(call_item.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                on_event(ToolEvent(kind="tool_call", name=name, payload=args))
                try:
                    result = dispatch(name, args)
                    if asyncio.iscoroutine(result):
                        result = await result
                except Exception as exc:
                    result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
                on_event(ToolEvent(kind="tool_result", name=name, payload={"result": result}))
                inputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call_item.call_id,
                        "output": json.dumps(result, ensure_ascii=False),
                    }
                )
                if isinstance(result, dict) and result.get("_stop"):
                    return ""
        raise LLMError(f"{self.role} exceeded max_turns={max_turns}")
