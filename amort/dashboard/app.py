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

# ── palette ──────────────────────────────────────────────────────────────────
# The same roles as `stage.html`, so the two screens read as one product: a
# blue-ink canvas with every neutral tinted to the same hue, and a warm/cool
# opposition carrying the data — bronze is the money burning on the direct path,
# jade is the engineered one. Within a lane, cold vs warm is a lightness step,
# not a new hue: hue means lane, lightness means mode.
#
# Inline only. CONTRACTS.md forbids CDN assets, and a dashboard that needs the
# network to look right is one that breaks at a booth on venue wifi.
#
# Contrast against the panel: fg 16.7:1 · dim 8.7:1 · label 5.3:1 · jade 10.7:1
# · bronze 6.6:1. Verified, not eyeballed.
INK       = "#080d12"
PANEL     = "#12181e"
PANEL_2   = "#1b222b"
LINE      = "#2a323d"
FG        = "#f5f7f9"
DIM       = "#abb5c2"
LABEL     = "#828d9c"
BRONZE    = "#ba9776"   # direct / baseline
BRONZE_LO = "#8c6e52"
JADE      = "#4edfb8"   # through amortize
JADE_LO   = "#1fb895"

SERIES_COLOURS = {
    "baseline/cold": BRONZE,
    "baseline/warm": BRONZE_LO,
    "amortize/cold": JADE_LO,
    "amortize/warm": JADE,
}

st.markdown(
    f"""
    <style>
      .stApp {{ background: {INK}; }}
      .block-container {{ padding-top: 2.2rem; max-width: 1560px; }}
      h1 {{ letter-spacing: .06em; font-weight: 800; color: {FG}; }}
      h2, h3 {{ color: {FG}; letter-spacing: .01em; }}

      /* KPI tiles: one elevation, declared as a border — not a border under a
         shadow, which is the ghost card. */
      [data-testid="stMetric"] {{
        background: {PANEL}; border: 1px solid {LINE};
        padding: .85rem 1.1rem; border-radius: 12px;
      }}
      [data-testid="stMetricValue"] {{
        font-variant-numeric: tabular-nums; font-size: 1.85rem;
        font-weight: 700; color: {FG};
      }}
      [data-testid="stMetricLabel"] {{
        letter-spacing: .16em; text-transform: uppercase;
        font-size: .7rem; font-weight: 700; color: {LABEL};
      }}
      [data-testid="stMetricDelta"] {{ font-variant-numeric: tabular-nums; }}

      div[data-testid="stDataFrame"] {{ font-variant-numeric: tabular-nums; }}
      [data-testid="stCaptionContainer"] {{ color: {LABEL}; }}
      hr {{ margin: 1.7rem 0; border-color: {LINE}; }}

      /* Browser surfaces ship with defaults belonging to no design system. */
      ::selection {{ background: {JADE}; color: {INK}; }}
      ::-webkit-scrollbar {{ width: 10px; height: 10px; }}
      ::-webkit-scrollbar-track {{ background: {PANEL}; }}
      ::-webkit-scrollbar-thumb {{ background: {LINE}; border-radius: 5px; }}
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
c4.metric("ledger", writer.name, help=f"Rows are read from {writer.name}.")
# `memory_dir.name` is the folder's basename — it rendered as the literal word
# "memory", which names nothing. The backend is what a reader needs.
try:
    from amort.skills.store_everos import get_store

    _mem = get_store().backend_name
except Exception:  # noqa: BLE001 — a broken store must not kill the header
    _mem = "unavailable"
c5.metric("memory", _mem, help=str(settings.memory_dir))

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
    df["lane_mode"] = df["lane"] + "/" + df["mode"]

    # Index by each series' OWN run number, not the global row number.
    # Indexing on a global counter put every series on a quarter of the x
    # positions and NaN on the rest, so the amortization curve — the chart this
    # whole dashboard exists for — rendered as four disconnected stubs across an
    # empty field. `cumcount` makes each line continuous, and "run #" is the
    # honest x-axis for a curve that claims cost falls as a lane repeats work.
    df["seq"] = df.groupby("lane_mode").cumcount() + 1

    metric = st.radio("plot", ["cost_usd", "tokens"], horizontal=True, label_visibility="collapsed")
    pivot = df.pivot_table(index="seq", columns="lane_mode", values=metric, aggfunc="mean")
    pivot.index.name = "run # within lane"

    # Hue carries the lane, lightness carries the mode — so the four series stay
    # distinguishable without inventing four unrelated colours.
    palette = [SERIES_COLOURS.get(str(c), LABEL) for c in pivot.columns]
    st.line_chart(pivot, height=320, color=palette)

    density = float(pivot.notna().sum().mean() / max(1, len(pivot)))
    if density < 0.9:
        st.caption(
            f"Series cover {density:.0%} of run positions — lanes have run an unequal "
            "number of times, so the shorter lines simply stop where that lane did."
        )

    lanes = df.groupby("lane_mode").agg(
        runs=("run_id", "count"), avg_cost=("cost_usd", "mean"), avg_tokens=("tokens", "mean")
    )
    st.dataframe(
        lanes.style.format({"avg_cost": "${:.4f}", "avg_tokens": "{:,.0f}"}).bar(
            subset=["avg_cost"], color=JADE_LO, vmin=0
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
    left.bar_chart(kdf["cost_usd"], height=230, color=JADE_LO)
    left.dataframe(kdf.style.format({"cost_usd": "${:.4f}", "wall_ms": "{:,.0f}"}), width="stretch")

by_tool = q(
    "SELECT NAME, COUNT(*), COALESCE(SUM(WALL_MS), 0) FROM STEPS WHERE KIND = 'tool' "
    "GROUP BY NAME ORDER BY COUNT(*) DESC"
)
if by_tool:
    import pandas as pd

    tdf = pd.DataFrame(by_tool, columns=["tool", "calls", "wall_ms"]).set_index("tool")
    right.caption("tool calls (tools are free — the cost they drive is the context they return)")
    right.bar_chart(tdf["calls"], height=230, color=BRONZE)
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
