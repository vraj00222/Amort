"""The demo's centerpiece: the 2x2 table, and `demo_report.json`.

    ─────────────────┬───────────────────────────┬───────────────────────────┬────────
                     │ DIRECT (no Amortize)      │ THROUGH AMORTIZE          │ Δ
    First request    │ 48,210 tok · $0.19 · 41s  │ 26,904 tok · $0.11 · 24s  │ −44%
    Re-prompt (same) │ 47,988 tok · $0.19 · 40s  │  3,102 tok · $0.01 ·  6s  │ −93% · parity ✓

Every number is read from a measured run. The Δ column is computed, never
asserted — with Layers 1 and 2 stubbed it prints `0%`, and that is the correct
output for this build. The table is also explicitly labelled when the underlying
numbers are estimated rather than API-reported.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.box import SQUARE
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from amort.config import project_root

if TYPE_CHECKING:
    from amort.demo.harness import DemoResult, RunResult

console = Console()

REPORT_PATH = project_root() / "demo_report.json"


def _duration(wall_ms: int) -> str:
    """Never round a real duration down to `0s` — a demo that reports 0s reads as broken."""
    if wall_ms < 1000:
        return f"{wall_ms}ms"
    if wall_ms < 60_000:
        return f"{wall_ms / 1000:.1f}s"
    return f"{wall_ms // 60000}m{(wall_ms % 60000) // 1000:02d}s"


def _money(cost: float) -> str:
    """Enough precision to be true, few enough digits to fit the table."""
    if cost >= 0.10:
        return f"${cost:.2f}"
    if cost >= 0.001:
        return f"${cost:.3f}"
    return f"${cost:.4f}"


def _cell(run: RunResult | None) -> str:
    if run is None:
        return "[dim]—[/dim]"
    body = f"{run.total_tokens:,} tok · {_money(run.cost_usd)} · {_duration(run.wall_ms)}"
    return body if run.ok else f"{body} [red](failed)[/red]"


def _delta(baseline: RunResult | None, amortize: RunResult | None) -> str:
    """Token delta, computed. Prints `0%` when there is no difference."""
    if baseline is None or amortize is None:
        return "[dim]n/a[/dim]"
    if baseline.total_tokens == 0:
        return "[dim]n/a[/dim]"
    pct = (amortize.total_tokens - baseline.total_tokens) / baseline.total_tokens * 100
    if abs(pct) < 0.05:
        return "[yellow]0%[/yellow]"
    colour = "green" if pct < 0 else "red"
    return f"[{colour}]{pct:+.0f}%[/{colour}]"


def render(result: DemoResult) -> None:
    """Print the 2x2 plus the honest caveats."""
    table = Table(
        title=f"amortize · {result.task} · {result.model}",
        box=SQUARE, header_style="bold", title_style="bold cyan", pad_edge=False,
    )
    # Data columns wrap rather than truncate: a `…` in a cost table hides the
    # number the whole demo exists to show.
    table.add_column("", style="bold", no_wrap=True)
    table.add_column("DIRECT (no Amortize)", justify="right")
    table.add_column("THROUGH AMORTIZE", justify="right")
    table.add_column("Δ", justify="right")

    a_cold, b_cold = result.runs.get("A_cold"), result.runs.get("B_cold")
    a_warm, b_warm = result.runs.get("A_warm"), result.runs.get("B_warm")

    table.add_row("First request", _cell(a_cold), _cell(b_cold), _delta(a_cold, b_cold))

    if a_warm or b_warm:
        parity = result.parity.get("B_cold_vs_B_warm")
        suffix = f" · parity {parity.symbol}" if parity else ""
        table.add_row(
            "Re-prompt (same)", _cell(a_warm), _cell(b_warm),
            _delta(a_warm, b_warm) + suffix,
        )
    console.print()
    console.print(table)

    # --- what the table does not say on its own -----------------------------
    lines: list[str] = []
    if result.simulated:
        lines.append(
            "[yellow]SIMULATED[/yellow] — no API key, so a scripted agent ran the same 8 tools and "
            "token counts are estimated from the real payload size (chars/4), not API-reported."
        )
    lines.append(
        "[bold]Both columns are equal on purpose.[/bold] Layer 1 (tool dieting, result spill) and "
        "Layer 2 (skill distil + replay) are stubs in this build, so routing through Amortize "
        "changes nothing yet. The harness measures rather than asserts, which is why it prints 0%."
    )
    for key, parity in result.parity.items():
        lines.append(f"{key.replace('_', ' ')}: {parity.summary()}")
    if result.accuracy:
        wrong = [k for k, v in result.accuracy.items() if v.verdict == "mismatch"]
        lines.append(
            "accuracy vs ground truth: "
            + ("all runs correct ✓" if not wrong else f"[red]{', '.join(wrong)} incorrect[/red]")
        )
    lines.extend(result.notes)
    lines.append(
        f"[dim]ledger={result.ledger_backend} · memory={result.memory_backend} · "
        f"proxy={result.proxy_url}[/dim]"
    )
    console.print(Panel("\n\n".join(lines), border_style="dim", title="what this shows", title_align="left"))


def to_dict(result: DemoResult) -> dict[str, Any]:
    a_cold, b_cold = result.runs.get("A_cold"), result.runs.get("B_cold")
    a_warm, b_warm = result.runs.get("A_warm"), result.runs.get("B_warm")

    def pct(base: RunResult | None, other: RunResult | None) -> float | None:
        if not base or not other or base.total_tokens == 0:
            return None
        return round((other.total_tokens - base.total_tokens) / base.total_tokens * 100, 2)

    def cost_pct(base: RunResult | None, other: RunResult | None) -> float | None:
        if not base or not other or base.cost_usd == 0:
            return None
        return round((other.cost_usd - base.cost_usd) / base.cost_usd * 100, 2)

    return {
        "task": result.task,
        "model": result.model,
        "started_at": result.started_at,
        "live": result.live,
        "simulated": result.simulated,
        "simulated_note": (
            "Token counts are estimated from payload size (chars/4), not API-reported."
            if result.simulated else None
        ),
        "layers": {
            "lighten": "stub (TODO layer1)",
            "amortize": "stub (TODO layer2)",
            "prove": "active",
        },
        "backends": {
            "ledger": result.ledger_backend,
            "memory": result.memory_backend,
            "proxy": result.proxy_url,
        },
        "runs": {k: v.to_dict() for k, v in result.runs.items()},
        "deltas": {
            "cold_tokens_pct": pct(a_cold, b_cold),
            "cold_cost_pct": cost_pct(a_cold, b_cold),
            "warm_tokens_pct": pct(a_warm, b_warm),
            "warm_cost_pct": cost_pct(a_warm, b_warm),
        },
        "parity": {
            k: {"verdict": v.verdict, "compared": v.compared,
                "mismatches": v.mismatches[:20], "reason": v.reason}
            for k, v in result.parity.items()
        },
        "accuracy": {
            k: {"verdict": v.verdict, "compared": v.compared, "mismatches": v.mismatches[:20]}
            for k, v in result.accuracy.items()
        },
        "notes": result.notes,
    }


def write_json(result: DemoResult, path: Path | None = None) -> Path:
    target = path or REPORT_PATH
    target.write_text(json.dumps(to_dict(result), indent=2) + "\n", encoding="utf-8")
    return target


__all__ = ["REPORT_PATH", "render", "to_dict", "write_json"]
