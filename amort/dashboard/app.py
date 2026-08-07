"""Streamlit dashboard — the PROVE layer's screen. `amort dash`.

Reads whichever ledger backend is active. The queries are written once, in SQL
that both Snowflake and SQLite accept, because `sqlite_writer` mirrors the
Snowflake DDL column for column — including the `SAVINGS` view.

Four panels:

1. **The amortization curve** — cost per run over time, split by lane. The whole
   pitch in one line chart: baseline flat, amortize bending down as skills form.
2. **Cumulative $ saved** — baseline spend minus amortize spend, running total.
3. **Cost by tool / step** — where the money actually goes.
4. **Skills** — what has been distilled, and its measured parity rate.

Design rule for every panel: **when there is nothing to show, say so and say
why.** A dashboard that renders an empty chart next to a "$0.00 saved" tile reads
as "it saved nothing"; one that says "Layer 2 is a stub, so no warm runs exist
yet" reads as the truth.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from amort.config import get_settings
from amort.ledger.events import get_writer
from amort.ledger.pricing import pricing_note, unknown_models

st.set_page_config(page_title="amortize", page_icon="📉", layout="wide")


@st.cache_resource
def _writer() -> Any:
    return get_writer()


def q(sql: str) -> list[tuple[Any, ...]]:
    try:
        return _writer().query(sql)
    except Exception as exc:  # noqa: BLE001 — a broken panel must not kill the page
        st.warning(f"query failed: {exc}")
        return []


settings = get_settings()
writer = _writer()

st.title("amortize")
st.caption("A local proxy that makes AI agents cheaper to run — lighten every run, amortize repeats, prove it.")

# ── header ───────────────────────────────────────────────────────────────────
totals = q(
    "SELECT COUNT(*), COALESCE(SUM(INPUT_TOKENS + OUTPUT_TOKENS), 0), "
    "COALESCE(SUM(COST_USD), 0), COALESCE(SUM(WALL_MS), 0) FROM RUNS"
)
n_runs, n_tokens, total_cost, total_wall = totals[0] if totals else (0, 0, 0.0, 0)

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("runs", f"{n_runs:,}")
c2.metric("tokens", f"{int(n_tokens):,}")
c3.metric("spend", f"${float(total_cost):,.4f}")
c4.metric("ledger", writer.name)
c5.metric("memory", str(settings.memory_dir.name))

if n_runs == 0:
    st.info(
        "No runs recorded yet. Run `amort demo` to populate the ledger, or start `amort up` "
        "and point a client at it."
    )
    st.stop()

st.warning(
    "**Layer 1 (LIGHTEN) and Layer 2 (AMORTIZE) are stubs in this build.** Every run below is a "
    "cold run, so the lanes cost the same and net savings are ~$0. That is the honest state of "
    "the system, not a data problem — the charts exist so the curve can be watched as the layers land.",
    icon="⚠️",
)

# ── 1. the amortization curve ────────────────────────────────────────────────
st.subheader("Cost per run")
st.caption("The amortization curve: baseline stays flat, the amortize lane should bend down as skills form.")

rows = q(
    "SELECT STARTED_AT, LANE, MODE, COST_USD, INPUT_TOKENS + OUTPUT_TOKENS, RUN_ID "
    "FROM RUNS ORDER BY STARTED_AT"
)
if rows:
    import pandas as pd

    df = pd.DataFrame(rows, columns=["started_at", "lane", "mode", "cost_usd", "tokens", "run_id"])
    df["started_at"] = pd.to_datetime(df["started_at"], format="mixed", utc=True)
    df["n"] = range(1, len(df) + 1)
    df["lane_mode"] = df["lane"] + "/" + df["mode"]

    metric = st.radio("plot", ["cost_usd", "tokens"], horizontal=True, label_visibility="collapsed")
    pivot = df.pivot_table(index="n", columns="lane_mode", values=metric, aggfunc="mean")
    st.line_chart(pivot, height=280)

    lanes = df.groupby("lane_mode").agg(
        runs=("run_id", "count"), avg_cost=("cost_usd", "mean"), avg_tokens=("tokens", "mean")
    )
    st.dataframe(lanes.style.format({"avg_cost": "${:.4f}", "avg_tokens": "{:,.0f}"}),
                 width="stretch")

# ── 2. cumulative saved ──────────────────────────────────────────────────────
st.subheader("Cumulative $ saved")
savings = q("SELECT TASK_FINGERPRINT, AVG_BASELINE_COST, AVG_LIGHTENED_COST, "
            "AVG_WARM_COST, NET_SAVED_USD, TOTAL_RUNS FROM SAVINGS")
if savings:
    import pandas as pd

    sdf = pd.DataFrame(
        savings,
        columns=["fingerprint", "avg_baseline", "avg_lightened", "avg_warm", "net_saved", "runs"],
    )
    net = float(sdf["net_saved"].fillna(0).sum())
    left, right = st.columns([1, 2])
    left.metric("net saved", f"${net:,.4f}",
                help="SUM(baseline cost) − SUM(amortize cost), straight from the SAVINGS view.")
    if abs(net) < 1e-9:
        left.caption("Exactly $0 — the lanes are identical because the optimizers are stubs.")
    right.dataframe(
        sdf.style.format({
            "avg_baseline": "${:.4f}", "avg_lightened": "${:.4f}",
            "avg_warm": "${:.4f}", "net_saved": "${:.4f}",
        }),
        width="stretch",
    )
else:
    st.caption("The SAVINGS view is empty — no runs have been grouped by fingerprint yet.")

# ── 3. where the money goes ──────────────────────────────────────────────────
st.subheader("Cost by step")
left, right = st.columns(2)

by_kind = q("SELECT KIND, COUNT(*), COALESCE(SUM(COST_USD), 0), COALESCE(SUM(WALL_MS), 0) FROM STEPS GROUP BY KIND")
if by_kind:
    import pandas as pd

    kdf = pd.DataFrame(by_kind, columns=["kind", "steps", "cost_usd", "wall_ms"]).set_index("kind")
    left.caption("by step kind")
    left.bar_chart(kdf["cost_usd"], height=220)
    left.dataframe(kdf.style.format({"cost_usd": "${:.4f}", "wall_ms": "{:,.0f}"}), width="stretch")

by_tool = q(
    "SELECT NAME, COUNT(*), COALESCE(SUM(WALL_MS), 0) FROM STEPS WHERE KIND = 'tool' "
    "GROUP BY NAME ORDER BY COUNT(*) DESC"
)
if by_tool:
    import pandas as pd

    tdf = pd.DataFrame(by_tool, columns=["tool", "calls", "wall_ms"]).set_index("tool")
    right.caption("tool calls (tools are free — the cost they drive is the context they return)")
    right.bar_chart(tdf["calls"], height=220)
    right.dataframe(tdf, width="stretch")
else:
    right.caption("No tool steps recorded yet.")

# ── 4. skills ────────────────────────────────────────────────────────────────
st.subheader("Skills")
skills = q(
    "SELECT SKILL_ID, TASK_FINGERPRINT, STATUS, RUNS_OBSERVED, PARITY_RATE, "
    "AVG_COLD_COST, AVG_WARM_COST, TOTAL_SAVED_USD FROM SKILLS"
)
if skills:
    import pandas as pd

    st.dataframe(
        pd.DataFrame(skills, columns=["skill_id", "fingerprint", "status", "runs_observed",
                                      "parity_rate", "avg_cold_cost", "avg_warm_cost", "saved"]),
        width="stretch",
    )
else:
    st.info(
        "No skills in the ledger. `skills/compiler.py` is a **TODO(layer2) stub** — runs are "
        "recorded as EverOS Cases, but nothing distils them into Skills yet. Locally-written "
        "skills (from the Phase 4 smoke test) live in "
        f"`{settings.skills_dir}` and are listed by `amort skills`.",
        icon="🧩",
    )

# ── footer ───────────────────────────────────────────────────────────────────
st.divider()
notes = [f"ledger backend: **{writer.name}**", f"pricing: {pricing_note()}"]
if unpriced := unknown_models():
    notes.append(f"⚠️ costed at $0.00 (no published rate): {', '.join(unpriced)}")
st.caption(" · ".join(notes))
