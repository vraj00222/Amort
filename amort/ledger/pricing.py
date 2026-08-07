"""Token pricing — the only place a dollar figure is computed.

Rates live in `pricing.json` (data, not code) so a booth engineer can correct a
price the morning of without touching Python.

Load-bearing invariants:

* **An unknown model costs `0.0`, never a guess.** A fabricated rate on the PROVE
  dashboard is worse than a visible gap: it makes the savings claim unfalsifiable.
  Unknown models are counted in `unknown_models()` so the dashboard can say
  "3 runs on an unpriced model" instead of quietly under-reporting.
* Cached tokens are priced separately. Anthropic bills cache reads at ~0.1x the
  base input rate and cache writes at 1.25x (5-minute TTL) or 2x (1-hour). A
  proxy that ignores this over-reports the cost of every cached prefix — which
  would inflate exactly the number Amortize is trying to prove it reduces.
* Model ids are matched exactly, then by alias, then by longest known prefix
  (so `claude-haiku-4-5-20251001` prices as `claude-haiku-4-5`).
"""

from __future__ import annotations

import functools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PRICING_PATH = Path(__file__).with_name("pricing.json")

_UNKNOWN_MODELS: set[str] = set()


@dataclass(frozen=True)
class Rate:
    """Dollars per 1M tokens for one model."""

    model: str
    input: float
    output: float
    cache_read: float
    cache_write_5m: float
    cache_write_1h: float
    known: bool = True


@functools.lru_cache(maxsize=1)
def _table() -> dict[str, Any]:
    with PRICING_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


@functools.lru_cache(maxsize=1)
def _multipliers() -> dict[str, float]:
    m = _table()["_meta"]["cache_multipliers"]
    return {"read": m["read"], "write_5m": m["write_5m"], "write_1h": m["write_1h"]}


@functools.lru_cache(maxsize=256)
def rate_for(model: str | None) -> Rate:
    """Resolve a model id to its rate. Never raises; unknown → all-zero rate."""
    models: dict[str, Any] = _table()["models"]
    mult = _multipliers()
    key = _resolve_key(model, models)

    if key is None:
        if model:
            _UNKNOWN_MODELS.add(model)
        return Rate(model or "", 0.0, 0.0, 0.0, 0.0, 0.0, known=False)

    entry = models[key]
    base_in = float(entry["input"])
    return Rate(
        model=key,
        input=base_in,
        output=float(entry["output"]),
        cache_read=float(entry.get("cache_read", base_in * mult["read"])),
        cache_write_5m=float(entry.get("cache_write_5m", base_in * mult["write_5m"])),
        cache_write_1h=float(entry.get("cache_write_1h", base_in * mult["write_1h"])),
    )


def _resolve_key(model: str | None, models: dict[str, Any]) -> str | None:
    if not model:
        return None
    if model in models:
        return model
    for key, entry in models.items():
        if model in (entry.get("aliases") or []):
            return key
    # Longest known prefix: dated snapshots price as their base model.
    candidates = [k for k in models if model.startswith(k)]
    return max(candidates, key=len) if candidates else None


def cost_usd(
    model: str | None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    *,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    cache_ttl: str = "5m",
) -> float:
    """Dollar cost of one LLM call. Returns 0.0 for an unpriced model.

    `input_tokens` is the *uncached* remainder — Anthropic reports the three
    buckets separately (`input_tokens`, `cache_read_input_tokens`,
    `cache_creation_input_tokens`) and they do not overlap, so they are summed
    at their own rates rather than double-counted.
    """
    r = rate_for(model)
    write_rate = r.cache_write_1h if cache_ttl == "1h" else r.cache_write_5m
    total = (
        input_tokens * r.input
        + output_tokens * r.output
        + cache_read_tokens * r.cache_read
        + cache_write_tokens * write_rate
    ) / 1_000_000
    return round(total, 8)


def is_known(model: str | None) -> bool:
    return rate_for(model).known


def unknown_models() -> list[str]:
    """Models seen at runtime with no published rate — surfaced, not hidden."""
    return sorted(_UNKNOWN_MODELS)


def known_models() -> list[str]:
    return sorted(k for k in _table()["models"] if not k.startswith("gpt-unverified"))


def pricing_note() -> str:
    return str(_table()["_meta"]["TODO"])


__all__ = [
    "Rate",
    "cost_usd",
    "is_known",
    "known_models",
    "pricing_note",
    "rate_for",
    "unknown_models",
]
