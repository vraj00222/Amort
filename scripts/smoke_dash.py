"""Phase 8 smoke: prove the dashboard renders charts with real data.

`streamlit run` returning HTTP 200 only proves a server started — Streamlit
executes the page script per session over a websocket, so a script that throws
still serves a 200. This runs the actual page script and intercepts every
charting call, so the assertion is "line_chart received 8 non-empty rows", not
"the port is open".

    uv run python scripts/smoke_dash.py
"""

from __future__ import annotations

import contextlib
import runpy
import sys
from pathlib import Path
from typing import Any

import streamlit as st

APP = Path(__file__).resolve().parents[1] / "amort" / "dashboard" / "app.py"

calls: list[tuple[str, Any]] = []


def _record(name: str, original: Any) -> Any:
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        # Bound DeltaGenerator methods arrive with `self` first; drop it so the
        # recorded payload is the data, not the column object.
        payload = args[1] if args and hasattr(args[0], "_get_delta_path_str") else (
            args[0] if args else None
        )
        calls.append((name, payload))
        return original(*args, **kwargs)

    return wrapper


def _shape(payload: Any) -> str:
    try:
        return f"{payload.shape[0]} row(s) x {payload.shape[1]} col(s)"
    except Exception:  # noqa: BLE001
        try:
            return f"{len(payload)} row(s)"
        except Exception:  # noqa: BLE001
            return type(payload).__name__


def main() -> int:
    # Patch DeltaGenerator, not the `st` module: the page renders into columns
    # (`left.bar_chart(...)`, `c1.metric(...)`), and those never touch `st.*`.
    from streamlit.delta_generator import DeltaGenerator

    for name in ("line_chart", "bar_chart", "dataframe", "metric"):
        setattr(DeltaGenerator, name, _record(name, getattr(DeltaGenerator, name)))
        setattr(st, name, _record(name, getattr(st, name)))

    print(f"executing {APP.relative_to(Path.cwd())} …\n")
    with contextlib.suppress(SystemExit):  # st.stop() in bare mode
        runpy.run_path(str(APP), run_name="__main__")

    charts = [c for c in calls if c[0] in ("line_chart", "bar_chart")]
    frames = [c for c in calls if c[0] == "dataframe"]
    metrics = [c for c in calls if c[0] == "metric"]

    print(f"{'call':<12} payload")
    print("-" * 48)
    for name, payload in calls:
        print(f"{name:<12} {_shape(payload)}")

    print(f"\ncharts     : {len(charts)}")
    print(f"tables     : {len(frames)}")
    print(f"metrics    : {len(metrics)}")

    assert metrics, "no metrics rendered"
    assert charts, (
        "no charts rendered — the ledger is empty. Run `amort demo` first, "
        "then re-run this smoke test."
    )
    assert frames, "no tables rendered"

    non_empty = 0
    for _name, payload in charts:
        try:
            if payload is not None and len(payload) > 0:
                non_empty += 1
        except TypeError:
            pass
    print(f"non-empty  : {non_empty}/{len(charts)} charts have data")
    assert non_empty == len(charts), "a chart was handed an empty frame"

    print("\nPHASE 8 SMOKE: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
