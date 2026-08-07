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

# Inline only — CONTRACTS.md forbids CDN assets, and a dashboard that needs the
# network to look right is a dashboard that breaks at a booth on venue wifi.
# Lane colours match the stage view (`stage.html`) so the two screens read as one
# system: grey = direct/baseline, green = through Amortize.
LANE_BASELINE = "#5b6b85"
LANE_AMORTIZE = "#34d399"

st.markdown(
    """
    <style>
      .block-container { padding-top: 2.4rem; max-width: 1500px; }
      h1 { letter-spacing: .04em; font-weight: 700; }
      [data-testid="stMetricValue"] { font-variant-numeric: tabular-nums; font-size: 1.9rem; }
      [data-testid="stMetricLabel"] { letter-spacing: .12em; text-transform: uppercase;
                                      font-size: .74rem; opacity: .72; }
      [data-testid="stMetric"] { padding: .5rem .9rem; border-radius: .6rem;
                                 background: rgba(255,255,255,.025); }
      div[data-testid="stDataFrame"] { font-variant-numeric: tabular-nums; }
      .stCaption, [data-testid="stCaptionContainer"] { opacity: .78; }
      hr { margin: 1.6rem 0; }
    </style>
    """,
    unsafe_allow_html=True,
)


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

# Per-lane averages, so the headline tile compares like with like: a lane that
# simply ran more times would otherwise look more expensive.
lane_avg = q(
    "SELECT LANE, COUNT(*), AVG(COST_USD), AVG(INPUT_TOKENS + OUTPUT_TOKENS) "
    "FROM RUNS GROUP BY LANE"
)
_avg = {str(r[0]): (int(r[1] or 0), float(r[2] or 0.0), float(r[3] or 0.0)) for r in lane_avg}
_base, _amort = _avg.get("baseline"), _avg.get("amortize")

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("runs", f"{n_runs:,}")
c2.metric("tokens", f"{int(n_tokens):,}")
if _base and _amort and _base[1] > 0:
    # Measured average against measured average — the same arithmetic the demo
    # harness prints. Streamlit renders a negative delta green by default, which
    # is backwards for a cost, so inverse=True flips it.
    delta_pct = (_amort[1] - _base[1]) / _base[1] * 100
    c3.metric(
        "avg cost / run · amortize",
        f"${_amort[1]:,.4f}",
        delta=f"{delta_pct:+.1f}% vs direct",
        delta_color="inverse",
        help=f"direct averages ${_base[1]:,.4f} over {_base[0]:,} run(s); "
             f"amortize ${_amort[1]:,.4f} over {_amort[0]:,}.",
    )
else:
    c3.metric("spend", f"${float(total_cost):,.4f}",
              help="Only one lane has runs, so there is nothing to compare it against.")
c4.metric("ledger", writer.name)
c5.metric("memory", str(settings.memory_dir.name))

if n_runs == 0:
    st.info(
        "No runs recorded yet. Run `amort demo` to populate the ledger, or start `amort up` "
        "and point a client at it."
    )
    st.stop()

# Show the stub warning only while NEITHER layer has measured evidence in the
# ledger: no meta.layer1 steps (LIGHTEN) and no replay steps (AMORTIZE).
_evidence = q(
    "SELECT SUM(CASE WHEN CAST(META AS VARCHAR) LIKE '%layer1%' THEN 1 ELSE 0 END), "
    "SUM(CASE WHEN KIND = 'replay' THEN 1 ELSE 0 END) FROM STEPS"
)
_l1_steps, _replay_steps = (
    (int(_evidence[0][0] or 0), int(_evidence[0][1] or 0)) if _evidence else (0, 0)
)
if _l1_steps == 0 and _replay_steps == 0:
    st.warning(
        "**Layer 1 (LIGHTEN) and Layer 2 (AMORTIZE) report no measured savings yet.** Every run "
        "below is a cold run, so the lanes cost the same and net savings are ~$0. That is the "
        "honest state of the system, not a data problem — the charts exist so the curve can be "
        "watched as the layers land.",
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

    # Colour by lane, not by arbitrary series order, so "green is cheaper" holds
    # from the stage view through to here. Warm runs get the same hue as their
    # cold sibling — the mode is the line style's job, not the colour's.
    palette = [
        LANE_AMORTIZE if str(col).startswith("amortize") else LANE_BASELINE
        for col in pivot.columns
    ]
    st.line_chart(pivot, height=300, color=palette)

    lanes = df.groupby("lane_mode").agg(
        runs=("run_id", "count"), avg_cost=("cost_usd", "mean"), avg_tokens=("tokens", "mean")
    )
    st.dataframe(
        lanes.style.format({"avg_cost": "${:.4f}", "avg_tokens": "{:,.0f}"}).bar(
            subset=["avg_cost"], color="#2b6b57", vmin=0
        ),
        width="stretch",
    )

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
    st.info(
        "**The SAVINGS view has no rows yet.** It groups runs by `TASK_FINGERPRINT`, so it fills "
        "in as soon as any task has been run — `amort demo --offline` is enough. Nothing is wrong; "
        "there is simply nothing to average.",
        icon="📭",
    )

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
    right.info(
        "**No tool steps recorded.** Only LLM calls have been logged so far — either no agent "
        "run has happened yet, or the runs that did happen never called a tool.",
        icon="🔧",
    )

# ── 4. skills ────────────────────────────────────────────────────────────────
st.subheader("Skills")

# The markdown store is the source of truth for replay; the ledger SKILLS table
# is append-only, so take the LATEST row per SKILL_ID (per CONTRACTS.md).
skills = q(
    "SELECT SKILL_ID, TASK_FINGERPRINT, STATUS, CREATED_AT, RUNS_OBSERVED, PARITY_RATE, "
    "AVG_COLD_COST, AVG_WARM_COST, TOTAL_SAVED_USD FROM SKILLS ORDER BY CREATED_AT"
)
latest = {row[0]: row for row in skills}  # dict insertion order → last write wins

md_skills: list[tuple] = []
try:
    from pathlib import Path

    from amort.skills.store_everos import _split_markdown, get_store

    for sk in get_store().local.iter_skills():
        try:
            front, _ = _split_markdown(Path(str(sk.md_path)).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            front = {}
        md_skills.append((
            sk.skill_id, sk.name, sk.status, front.get("version"),
            front.get("runs_observed"), sk.parity_rate,
            ", ".join(sk.tools_required),
        ))
except Exception as exc:  # noqa: BLE001 — a broken store must not kill the page
    st.warning(f"could not read the markdown skill store: {exc}")

if md_skills or latest:
    import pandas as pd

    if md_skills:
        st.caption("markdown store (source of truth for replay)")
        st.dataframe(
            pd.DataFrame(md_skills, columns=["skill_id", "name", "status", "version",
                                             "runs_observed", "parity_rate", "tools_required"]),
            width="stretch",
        )
    else:
        st.caption(f"markdown store: empty ({settings.skills_dir})")
    if latest:
        st.caption("ledger SKILLS (latest row per skill_id)")
        st.dataframe(
            pd.DataFrame(
                list(latest.values()),
                columns=["skill_id", "fingerprint", "status", "created_at", "runs_observed",
                         "parity_rate", "avg_cold_cost", "avg_warm_cost", "saved"],
            ),
            width="stretch",
        )
    else:
        st.caption("ledger SKILLS table: empty — the grader has not written any rollups yet.")
else:
    st.info(
        "No skills anywhere yet — neither in the markdown store "
        f"(`{settings.skills_dir}`) nor in the ledger SKILLS table. Runs are recorded as "
        "EverOS Cases, but nothing has distilled them into Skills.",
        icon="🧩",
    )

# ── footer ───────────────────────────────────────────────────────────────────
st.divider()
notes = [f"ledger backend: **{writer.name}**", f"pricing: {pricing_note()}"]
if unpriced := unknown_models():
    notes.append(f"⚠️ costed at $0.00 (no published rate): {', '.join(unpriced)}")
st.caption(" · ".join(notes))
