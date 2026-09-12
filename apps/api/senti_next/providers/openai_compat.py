"""OpenAI-compatible LLM provider (supports OpenAI, DeepSeek, and Ollama)."""
from __future__ import annotations

import json
import logging
import os
import random
import time
import uuid
from typing import Any, Dict, List, Optional

from .base import LLMProvider
from .errors import EmptyResponseError, ProxyDependencyError, ProviderFailure
from .circuit import provider_operation_circuit

logger = logging.getLogger(__name__)

OPENAI_TIMEOUT_SECONDS = int(os.getenv("SENTINEXT_LLM_TIMEOUT", "30"))
OLLAMA_TIMEOUT_SECONDS = int(os.getenv("SENTINEXT_OLLAMA_TIMEOUT", "120"))
LLM_MAX_RETRIES = int(os.getenv("SENTINEXT_LLM_MAX_RETRIES", "3"))

def _default_ollama_url() -> str:
    """Return the default Ollama base URL, auto-detecting Docker environments."""
    # Inside Docker, localhost doesn't reach the host — use host.docker.internal
    if os.path.exists("/.dockerenv"):
        return "http://host.docker.internal:11434/v1"
    return "http://localhost:11434/v1"


def _calculate_retry_delay(attempt: int, error_type: str) -> float:
    base_delay = 2.0
    if error_type == "rate_limited":
        base_delay = 20.0
    elif error_type == "server_error":
        base_delay = 5.0
    delay = base_delay * (2 ** (attempt - 1))
    jitter = random.uniform(0, delay * 0.1)
    return min(delay + jitter, 60.0)


class OpenAICompatProvider(LLMProvider):
    """Provider for OpenAI and Ollama (both use the openai Python SDK).

    Args:
        provider_type: "openai", "deepseek", or "ollama"
        model_name: Model to use (e.g. "gpt-4o-mini" or "llama3.1:8b")
    """

    def __init__(self, provider_type: str = "openai", model_name: str | None = None):
        self._provider_type = provider_type
        self.usage_history: list[dict[str, int | None]] = []

        if provider_type in {"openai", "deepseek"}:
            from .config import DEFAULT_MODELS
            env_prefix = provider_type.upper()
            self._model = model_name or os.getenv(
                f"SENTINEXT_{env_prefix}_MODEL",
                DEFAULT_MODELS.get(provider_type, "gpt-4o-mini"),
            )
            self._base_url = (
                "https://api.deepseek.com/v1"
                if provider_type == "deepseek"
                else "https://api.openai.com/v1"
            )
            self._timeout_seconds = OPENAI_TIMEOUT_SECONDS
        else:
            from .config import DEFAULT_MODELS
            self._model = model_name or os.getenv("SENTINEXT_OLLAMA_MODEL", DEFAULT_MODELS.get("ollama", "llama3.1:8b"))
            self._base_url = os.getenv("SENTINEXT_OLLAMA_BASE_URL", _default_ollama_url())
            self._timeout_seconds = OLLAMA_TIMEOUT_SECONDS

    @property
    def name(self) -> str:
        return self._provider_type

    @property
    def model(self) -> str:
        return self._model

    def _get_api_key(self) -> str:
        """Return the API key, reading from env at call time for OpenAI so runtime key updates work."""
        if self._provider_type in {"openai", "deepseek"}:
            return os.getenv(f"{self._provider_type.upper()}_API_KEY", "")
        return "ollama"  # Ollama doesn't need a real key but the SDK requires one

    def _get_client(self) -> Any:
        """Create a synchronous OpenAI client."""
        from openai import OpenAI
        return OpenAI(
            api_key=self._get_api_key(),
            base_url=self._base_url,
            timeout=self._timeout_seconds,
        )

    def _get_async_client(self) -> Any:
        """Create an async OpenAI client."""
        from openai import AsyncOpenAI
        return AsyncOpenAI(
            api_key=self._get_api_key(),
            base_url=self._base_url,
            timeout=self._timeout_seconds,
        )

    # ---- core generation ----

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        response_schema: dict | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        messages: List[Dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs: Dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        if response_schema:
            if self._provider_type == "deepseek":
                # DeepSeek currently exposes JSON mode rather than OpenAI's
                # strict json_schema format. The caller still validates the
                # returned JSON against its Pydantic model.
                kwargs["response_format"] = {"type": "json_object"}
            else:
                kwargs["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": "response", "strict": True, "schema": response_schema},
                }
        if self._provider_type == "deepseek":
            # Structured semantic classification needs visible JSON content.
            # DeepSeek reasoning can consume the entire completion budget and
            # return finish_reason=length with empty message.content.
            thinking = os.getenv("SENTINEXT_DEEPSEEK_THINKING", "disabled").strip().lower()
            if thinking not in {"enabled", "disabled"}:
                thinking = "enabled"
            kwargs["extra_body"] = {"thinking": {"type": thinking}}

        return self._call_with_retry(kwargs)

    def generate_structured(
        self,
        prompt: str,
        response_schema: dict,
        system: str | None = None,
        temperature: float = 0.0,
    ) -> dict:
        raw = self.generate(prompt, system=system, response_schema=response_schema, temperature=temperature)
        return json.loads(raw)

    def generate_with_pydantic(
        self,
        prompt: str,
        parse_model: type,
        system: str | None = None,
        temperature: float = 0.0,
    ) -> str:
        """Use JSON schema from Pydantic model for structured output."""
        schema = parse_model.model_json_schema()
        return self.generate(prompt, system=system, response_schema=schema, temperature=temperature)

    async def generate_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str | None = None,
        temperature: float = 0.0,
    ) -> dict:
        """Generate with OpenAI-compatible function calling."""
        client = self._get_async_client()

        # Build messages list
        api_messages: List[Dict[str, Any]] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "tool":
                # Tool results - parse and add as individual tool messages
                try:
                    tool_results = json.loads(content) if isinstance(content, str) else content
                    if isinstance(tool_results, list):
                        for result in tool_results:
                            api_messages.append({
                                "role": "tool",
                                "tool_call_id": result.get("tool_call_id", result.get("tool", "unknown")),
                                "content": json.dumps(result.get("result", {})),
                            })
                    else:
                        api_messages.append({"role": "tool", "tool_call_id": "unknown", "content": str(content)})
                except (json.JSONDecodeError, TypeError):
                    api_messages.append({"role": "tool", "tool_call_id": "unknown", "content": str(content)})
            elif role == "assistant":
                tool_calls = msg.get("tool_calls")
                if tool_calls:
                    api_messages.append({
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": tc.get("id", tc.get("name", "call")),
                                "type": "function",
                                "function": {
                                    "name": tc.get("name", ""),
                                    "arguments": json.dumps(tc.get("parameters", {})),
                                },
                            }
                            for tc in tool_calls
                        ],
                    })
                else:
                    api_messages.append({"role": role, "content": content})
            else:
                api_messages.append({"role": role, "content": content})

        # Convert tools to OpenAI format
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {}),
                },
            }
            for tool in tools
        ]

        attempt = 0
        operation_id = str(uuid.uuid4())
        while attempt < LLM_MAX_RETRIES:
            attempt += 1
            call_started = time.time()
            from .. import cost_ledger
            call_id, _ = cost_ledger.start_call(self._provider_type, self._model, attempt_number=attempt, operation_id=operation_id, input_text=json.dumps(api_messages, ensure_ascii=False), purpose="chat_agent")
            try:
                response = await client.chat.completions.create(
                    model=self._model,
                    messages=api_messages,
                    tools=openai_tools if openai_tools else None,
                    temperature=temperature,
                    **(
                        {
                            "extra_body": {
                                "thinking": {
                                    "type": "enabled"
                                    if os.getenv("SENTINEXT_DEEPSEEK_THINKING", "disabled").strip().lower() == "enabled"
                                    else "disabled"
                                }
                            }
                        }
                        if self._provider_type == "deepseek"
                        else {}
                    ),
                )

                choice = response.choices[0]
                content = choice.message.content
                tool_calls_out: List[Dict[str, Any]] = []

                if choice.message.tool_calls:
                    for tc in choice.message.tool_calls:
                        tool_calls_out.append({
                            "name": tc.function.name,
                            "parameters": json.loads(tc.function.arguments) if tc.function.arguments else {},
                        })

                usage = self._usage_dict(response)
                cost_ledger.finish_call(call_id, started_at=__import__("datetime").datetime.fromtimestamp(call_started, tz=__import__("datetime").timezone.utc), status="completed", usage=usage)
                self._record_usage(response, attempt=attempt)
                return {"content": content, "tool_calls": tool_calls_out, "model": self.model_id()}

            except Exception as e:
                error_str = str(e).lower()
                is_transient = any(
                    tok in error_str
                    for tok in ("timeout", "429", "rate", "temporar", "unavailable", "503", "502", "500", "connection")
                )
                cost_ledger.finish_call(call_id, started_at=__import__("datetime").datetime.fromtimestamp(call_started, tz=__import__("datetime").timezone.utc), status="failed", error=e, retryable=is_transient)
                logger.warning("OpenAI-compat tool-calling error: %s (attempt %d/%d)", e, attempt, LLM_MAX_RETRIES)

                if not is_transient or attempt >= LLM_MAX_RETRIES:
                    raise RuntimeError(f"OpenAI-compat tool-calling error: {e}") from e

                import asyncio
                delay = _calculate_retry_delay(attempt, "server_error")
                await asyncio.sleep(delay)

        raise RuntimeError(f"OpenAI-compat tool-calling failed after {LLM_MAX_RETRIES} attempts")

    # ---- internal sync call with retry ----

    def _call_with_retry(self, kwargs: Dict[str, Any]) -> str:
        """Call OpenAI-compatible API with retry logic."""
        client = self._get_client()
        attempt = 0
        start_time = time.time()
        operation_id = str(uuid.uuid4())

        while attempt < LLM_MAX_RETRIES:
            attempt += 1
            call_started = time.time()
            circuit_key = f"{self._provider_type}:{self._model}"
            from .. import cost_ledger
            call_id, _ = cost_ledger.start_call(
                self._provider_type, self._model, attempt_number=attempt,
                operation_id=operation_id if 'operation_id' in locals() else str(uuid.uuid4()),
                input_text=json.dumps(kwargs.get("messages", []), ensure_ascii=False),
                purpose=None, requested_max_tokens=kwargs.get("max_tokens"),
            )
            try:
                provider_operation_circuit.check(circuit_key)
                response = client.chat.completions.create(**kwargs)
                content = response.choices[0].message.content
                choice = response.choices[0]
                finish_reason = getattr(choice, "finish_reason", None)
                if finish_reason == "length":
                    metadata = {
                        "finish_reason": finish_reason,
                        "requested_max_tokens": kwargs.get("max_tokens"),
                        "raw_response_chars": len(content or ""),
                        **self._usage_dict(response),
                    }
                    error = ProviderFailure(
                        "OUTPUT_TRUNCATED",
                        "Provider response reached the requested output token limit.",
                        metadata,
                        retryable=False,
                    )
                    cost_ledger.finish_call(
                        call_id,
                        started_at=__import__("datetime").datetime.fromtimestamp(call_started, tz=__import__("datetime").timezone.utc),
                        status="failed",
                        usage=self._usage_dict(response),
                        error=error,
                        metadata={**metadata, "schema_valid": 0},
                    )
                    raise error
                elapsed = time.time() - start_time
                logger.info(
                    "%s API call completed in %.2fs (attempt %d)",
                    self._provider_type, elapsed, attempt,
                )

                if not content or not content.strip():
                    choice = response.choices[0] if response.choices else None
                    usage = getattr(response, "usage", None)
                    safe_metadata = {
                        "provider": self._provider_type,
                        "configured_model": self._model,
                        "response_model": getattr(response, "model", None),
                        "finish_reason": finish_reason,
                        "choice_count": len(response.choices or []),
                        "content_length": 0,
                        "reasoning_content_present": bool(getattr(getattr(choice, "message", None), "reasoning_content", None)),
                        "tool_call_count": len(getattr(getattr(choice, "message", None), "tool_calls", None) or []),
                        "usage_present": usage is not None,
                        "thinking_mode": kwargs.get("extra_body", {}).get("thinking", {}).get("type"),
                        "json_mode": kwargs.get("response_format", {}).get("type") == "json_object",
                        "attempt": attempt,
                    }
                    raise EmptyResponseError(safe_metadata)

                cost_ledger.finish_call(
                    call_id, started_at=__import__("datetime").datetime.fromtimestamp(call_started, tz=__import__("datetime").timezone.utc),
                    status="completed", usage=self._usage_dict(response),
                    metadata={
                        "finish_reason": finish_reason,
                        "raw_response_chars": len(content or ""),
                        "schema_valid": None,
                    },
                )
                self._record_usage(response)
                provider_operation_circuit.close(circuit_key)
                return content

            except EmptyResponseError as e:
                provider_operation_circuit.open(circuit_key)
                cost_ledger.finish_call(call_id, started_at=__import__("datetime").datetime.fromtimestamp(call_started, tz=__import__("datetime").timezone.utc), status="failed", error=e, retryable=False)
                raise
            except ProxyDependencyError as e:
                cost_ledger.finish_call(call_id, started_at=__import__("datetime").datetime.fromtimestamp(call_started, tz=__import__("datetime").timezone.utc), status="failed", error=e, retryable=False)
                raise
            except RuntimeError as e:
                cost_ledger.finish_call(call_id, started_at=__import__("datetime").datetime.fromtimestamp(call_started, tz=__import__("datetime").timezone.utc), status="failed", error=e, retryable=False)
                raise
            except Exception as e:
                error_str = str(e).lower()
                if "socksio" in error_str and "proxy" in error_str:
                    error = ProxyDependencyError("SOCKS proxy is configured but the socksio dependency is unavailable.")
                    cost_ledger.finish_call(call_id, started_at=__import__("datetime").datetime.fromtimestamp(call_started, tz=__import__("datetime").timezone.utc), status="failed", error=error, retryable=False)
                    raise error from e
                is_transient = any(
                    tok in error_str
                    for tok in ("timeout", "429", "rate", "temporar", "unavailable", "503", "502", "500", "connection")
                )

                cost_ledger.finish_call(call_id, started_at=__import__("datetime").datetime.fromtimestamp(call_started, tz=__import__("datetime").timezone.utc), status="failed", error=e, retryable=is_transient)
                logger.warning(
                    "%s API error: %s (attempt %d/%d)",
                    self._provider_type, e, attempt, LLM_MAX_RETRIES,
                )

                if not is_transient:
                    raise RuntimeError(f"{self._provider_type} API error: {e}") from e

                if attempt < LLM_MAX_RETRIES:
                    if "429" in str(e) or "rate" in error_str:
                        delay = _calculate_retry_delay(attempt, "rate_limited")
                    else:
                        delay = _calculate_retry_delay(attempt, "server_error")
                    logger.info("Retrying in %.1fs...", delay)
                    time.sleep(delay)
                    continue

                raise RuntimeError(
                    f"{self._provider_type} API error after {LLM_MAX_RETRIES} attempts: {e}"
                ) from e

        raise RuntimeError(f"{self._provider_type} API call failed after {LLM_MAX_RETRIES} attempts")

    @staticmethod
    def _usage_dict(response: Any) -> dict[str, int | None]:
        usage = getattr(response, "usage", None)
        if usage is None:
            return {}
        def value(*names: str) -> int | None:
            for name in names:
                raw = getattr(usage, name, None)
                if raw is not None:
                    try:
                        return int(raw)
                    except (TypeError, ValueError):
                        return None
            return None
        return {
            "input_tokens": value("prompt_tokens", "input_tokens"),
            "output_tokens": value("completion_tokens", "output_tokens"),
            "total_tokens": value("total_tokens"),
            "cached_input_tokens": value("cached_tokens", "prompt_cache_hit_tokens"),
        }

    def _record_usage(self, response: Any, *, attempt: int = 1) -> None:
        """Best-effort usage logging."""
        try:
            usage = response.usage
            if usage is None:
                return
            def value(*names: str) -> int | None:
                for name in names:
                    result = getattr(usage, name, None)
                    if result is not None:
                        try:
                            return int(result)
                        except (TypeError, ValueError):
                            return None
                return None
            usage_row = {
                "prompt_tokens": value("prompt_tokens", "input_tokens"),
                "completion_tokens": value("completion_tokens", "output_tokens"),
                "total_tokens": value("total_tokens"),
                "cached_tokens": value("cached_tokens", "prompt_cache_hit_tokens"),
                "attempts": attempt,
                "retries": max(0, attempt - 1),
            }
            self.usage_history.append(usage_row)
            if os.getenv("SENTINEXT_EVAL_ISOLATED", "").lower() in {"1", "true", "yes"}:
                return
            from ..llm import _record_llm_usage, _safe_int
            if usage:
                _record_llm_usage(
                    None,
                    self._model,
                    provider=self._provider_type,
                    prompt_tokens=_safe_int(getattr(usage, "prompt_tokens", None)),
                    response_tokens=_safe_int(getattr(usage, "completion_tokens", None)),
                    total_tokens=_safe_int(getattr(usage, "total_tokens", None)),
                )
        except Exception:
            pass
