"""One tiny LLM helper for Layer 2 — bind, verify, and compile calls.

Everything Layer 2 asks a model is small (a parameter binding, a digest check,
one compile), so one function covers all of it. Novita's OpenAI-compatible
endpoint, settings defaults, temperature 0.
"""

from __future__ import annotations

import time
from typing import Any

from amort.config import get_settings


def chat(
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    max_tokens: int = 2048,
) -> tuple[str, dict[str, Any]]:
    """One chat completion. Returns (text, usage) — usage has real API counts."""
    from openai import OpenAI

    s = get_settings()
    client = OpenAI(
        api_key=api_key or s.novita_api_key,
        base_url=base_url or f"{s.novita_api_url.rstrip('/')}/v1",
        max_retries=2,
        timeout=300.0,
    )
    started = time.perf_counter()
    response = client.chat.completions.create(
        model=model or s.novita_model,
        max_tokens=max_tokens,
        temperature=0,
        messages=messages,
    )
    wall_ms = int((time.perf_counter() - started) * 1000)
    usage = response.usage
    return response.choices[0].message.content or "", {
        "model": response.model or model or s.novita_model,
        "input_tokens": int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0,
        "output_tokens": int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0,
        "wall_ms": wall_ms,
    }


__all__ = ["chat"]
