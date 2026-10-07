"""A small LLM client for any OpenAI-compatible chat endpoint (Groq, Ollama, HF router, ...)."""

import json
import time
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from auraltrans.config import settings
from auraltrans.db.models import LLMCall
from auraltrans.db.session import session_scope


class LLMError(RuntimeError):
    """The model could not be reached or answered with an error."""


class GroundingError(RuntimeError):
    """The model answered, but not with usable, valid JSON even after one repair attempt."""


@dataclass
class LLMResult:
    text: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int = 0


Schema = dict[str, Any]


class LLM(Protocol):
    model: str

    def complete(
        self, system: str, user: str, *, max_tokens: int = 2000, schema: Schema | None = None
    ) -> LLMResult: ...


class OpenAICompatLLM:
    def __init__(self, base_url: str, api_key: str, model: str, timeout_s: float = 120.0) -> None:
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._timeout = timeout_s
        mode = settings.llm_strict_schema
        self.strict_schema = mode == "on" or (mode == "auto" and model.startswith("openai/gpt-oss"))

    def complete(
        self, system: str, user: str, *, max_tokens: int = 2000, schema: Schema | None = None
    ) -> LLMResult:
        body: dict[str, object] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        if schema is not None and self.strict_schema:
            # Constrained decoding (Groq: gpt-oss models). Falls back to json_object if rejected.
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "result", "strict": True, "schema": schema},
            }
        if settings.llm_reasoning_effort and self.model.startswith("openai/gpt-oss"):
            body["reasoning_effort"] = settings.llm_reasoning_effort
        started = time.perf_counter()
        data = self._post(body)
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("the model endpoint returned an unexpected response shape") from exc
        usage = data.get("usage") or {}
        return LLMResult(
            text=text,
            model=self.model,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    def _post(self, body: dict[str, object]) -> dict:  # type: ignore[type-arg]
        for attempt in range(6):
            try:
                r = httpx.post(self.url, json=body, headers=self._headers, timeout=self._timeout)
            except httpx.HTTPError as exc:
                raise LLMError(f"could not reach the language model: {exc}") from exc
            rf = body.get("response_format")
            if r.status_code == 400 and isinstance(rf, dict) and rf.get("type") == "json_schema":
                body = {**body, "response_format": {"type": "json_object"}}  # schema not supported here
                continue
            if r.status_code == 400 and rf is not None:
                # Some servers do not support JSON mode; the prompt still demands JSON.
                body = {k: v for k, v in body.items() if k != "response_format"}
                continue
            if r.status_code in (429, 503) and attempt < 4:
                # Free tiers limit tokens per minute: wait for the window to reset.
                time.sleep(min(float(r.headers.get("retry-after", 5 * (attempt + 1))) + 1, 60.0))
                continue
            if r.status_code == 413:
                raise LLMError(
                    "this request is larger than the model's per-request limit; lower LLM_CHUNK_CHARS / "
                    "LLM_CONTEXT_CHARS or use a higher-limit plan or model"
                )
            if r.status_code >= 400:
                raise LLMError(f"language model error {r.status_code}: {r.text[:200]}")
            return r.json()  # type: ignore[no-any-return]
        raise LLMError("the language model is rate limiting requests; try again in a minute")


def get_llm() -> LLM | None:
    """FastAPI dependency. None means no model is configured, so Insights and Ask are off."""
    if not settings.llm_configured:
        return None
    return OpenAICompatLLM(
        settings.llm_base_url, settings.llm_api_key, settings.llm_model, settings.llm_timeout_s
    )


def record_call(purpose: str, model: str, prompt_version: str, status: str, r: LLMResult | None) -> None:
    with session_scope() as s:
        s.add(
            LLMCall(
                purpose=purpose,
                model=model,
                prompt_version=prompt_version,
                input_tokens=r.input_tokens if r else None,
                output_tokens=r.output_tokens if r else None,
                latency_ms=r.latency_ms if r else None,
                status=status,
            )
        )


def extract_json(text: str) -> object:
    """Parse model output as JSON, tolerating code fences and prose around the object."""
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[t.find("{") :] if "{" in t else t
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in the reply")
    return json.loads(t[start : end + 1])


M = TypeVar("M", bound=BaseModel)


def complete_validated(
    llm: LLM, system: str, user: str, model_cls: type[M], *, purpose: str, prompt_version: str,
    max_tokens: int = 2000, schema: Schema | None = None,
) -> tuple[M, bool]:
    """Call the model, validate against `model_cls`, and retry once with the errors fed back.

    Returns (parsed, repaired). Every call is logged to llm_calls.
    """
    last_error = ""
    reply = user
    for attempt in range(2):
        try:
            result = llm.complete(system, reply, max_tokens=max_tokens, schema=schema)
        except LLMError:
            record_call(purpose, llm.model, prompt_version, "error", None)
            raise
        try:
            parsed = model_cls.model_validate(extract_json(result.text))
        except (ValueError, ValidationError) as exc:
            last_error = str(exc)[:600]
            record_call(purpose, llm.model, prompt_version, "invalid", result)
            reply = (
                f"{user}\n\nYour previous reply was rejected:\n{last_error}\n"
                "Reply again with ONLY one valid JSON object that follows the schema exactly."
            )
            continue
        record_call(purpose, llm.model, prompt_version, "ok" if attempt == 0 else "repaired", result)
        return parsed, attempt == 1
    raise GroundingError(f"the model did not return valid JSON after a retry: {last_error}")
