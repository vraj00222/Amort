"""`amort` — the CLI.

    amort up              start the proxy (the only thing most users ever run)
    amort demo            side-by-side comparison harness (demo-only)
    amort stats           what the ledger knows so far
    amort skills          compiled skills and their status
    amort dash            Streamlit dashboard
    amort snowflake-init  create AMORTIZE.LEDGER from scripts/snowflake_setup.sql
    amort doctor          check config, ledger backend, and memory backend

Every heavyweight import (uvicorn, streamlit, the demo harness) is deferred into
its command so `amort --help` stays instant and a missing optional dependency
only breaks the command that needs it.
"""

from __future__ import annotations

import sys
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from amort.config import get_settings

app = typer.Typer(
    name="amort",
    help="Amortize — a local proxy that makes AI agents cheaper to run.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


@app.command()
def up(
    port: Annotated[int, typer.Option(help="Port to listen on.")] = 0,
    host: Annotated[str, typer.Option(help="Interface to bind.")] = "",
    reload: Annotated[bool, typer.Option(help="Auto-reload on code change (dev).")] = False,
    log_level: Annotated[str, typer.Option(help="uvicorn log level.")] = "info",
) -> None:
    """Start the Amortize proxy."""
    import uvicorn

    settings = get_settings()
    settings.ensure_dirs()
    bind_host = host or settings.amort_host
    bind_port = port or settings.amort_port

    from amort.ledger.events import active_backend

    base = f"http://{bind_host}:{bind_port}"
    console.print()
    console.print("[bold]amortize[/bold] — proxy up", style="cyan")
    console.print(f"  listening    [bold]{base}[/bold]")
    console.print(f"  upstream     anthropic → {settings.amort_upstream_anthropic}")
    console.print(f"               openai    → {settings.amort_upstream_openai}")
    console.print(f"  ledger       {active_backend()}")
    console.print(f"  memory       {settings.memory_dir}")
    console.print()
    console.print("  Connect any Anthropic client (incl. Claude Code) — paste:")
    console.print(f"    [bold]export ANTHROPIC_BASE_URL={base}[/bold]")
    console.print("    [bold]export ANTHROPIC_AUTH_TOKEN=<your key>[/bold]")
    console.print("  OpenAI-compatible clients:")
    console.print(f"    [bold]base_url {base}/v1[/bold]  (api_key = your upstream key)")
    console.print("  Or make it stick in ~/.claude/settings.json:")
    console.print(
        f'    [dim]{{"env": {{"ANTHROPIC_BASE_URL": "{base}", '
        '"ANTHROPIC_AUTH_TOKEN": "<your key>"}}}}[/dim]'
    )
    console.print()

    uvicorn.run(
        "amort.proxy.server:app",
        host=bind_host,
        port=bind_port,
        reload=reload,
        log_level=log_level,
    )


@app.command()
def demo(
    task: Annotated[str, typer.Option(help="Demo task to run.")] = "ticket_triage",
    lanes: Annotated[str, typer.Option(help="Which lanes: both|baseline|amortize.")] = "both",
    repeat: Annotated[bool, typer.Option(help="Also run the warm re-prompt pass.")] = True,
    live: Annotated[
        bool, typer.Option("--live/--offline", help="Call the real API, or replay mock tools only.")
    ] = True,
    stage: Annotated[
        bool, typer.Option("--stage", help="Serve the projector stage view during the run.")
    ] = False,
    stage_port: Annotated[int, typer.Option(help="Port for the stage view.")] = 4700,
    replay: Annotated[
        str, typer.Option("--replay", help="Replay a recorded demo_report.json on the stage instead of running.")
    ] = "",
) -> None:
    """Run the side-by-side comparison harness (demo-only; not the request path)."""
    from amort.demo.harness import run_demo

    if replay:
        from amort.demo.stage import replay_report, start_stage

        url = start_stage(stage_port)
        console.print(f"\n[bold cyan]  STAGE → {url}  [/bold cyan] (replaying {replay})\n")
        events = replay_report(replay)
        console.print(f"[dim]replayed {events} recorded events — stage stays up, Ctrl+C to exit[/dim]")
        _serve_forever()
        return

    if stage:
        from amort.demo.stage import start_stage

        url = start_stage(stage_port)
        console.print(f"\n[bold cyan]  STAGE → {url}  [/bold cyan] (open on the projector)\n")

    run_demo(task=task, lanes=lanes, repeat=repeat, live=live)

    if stage:
        console.print("[dim]stage stays up — Ctrl+C to exit[/dim]")
        _serve_forever()


def _serve_forever() -> None:
    """Keep the stage's daemon thread alive until Ctrl+C."""
    import contextlib
    import threading

    with contextlib.suppress(KeyboardInterrupt):
        threading.Event().wait()


@app.command()
def stats(
    limit: Annotated[int, typer.Option(help="Rows to show.")] = 20,
) -> None:
    """Summarise what the ledger has recorded."""
    from amort.ledger.events import get_writer

    writer = get_writer()
    q = _q(writer.name)

    table = Table(title=f"amortize runs — ledger: {writer.name}", header_style="bold")
    for col in ("run_id", "lane", "mode", "model", "in", "out", "cost $", "wall ms", "parity"):
        table.add_column(col, overflow="fold")

    rows = writer.query(
        "SELECT RUN_ID, LANE, MODE, MODEL, INPUT_TOKENS, OUTPUT_TOKENS, COST_USD, WALL_MS, PARITY "
        f"FROM RUNS ORDER BY STARTED_AT DESC LIMIT {q(limit)}",
        (limit,),
    )
    for r in rows:
        table.add_row(
            str(r[0]), str(r[1]), str(r[2]), str(r[3] or "-"), f"{r[4]:,}", f"{r[5]:,}",
            f"{r[6]:.4f}", f"{r[7]:,}", str(r[8] or "-"),
        )
    console.print(table)

    # Per-task rollup. The task name lives in STEPS meta ({"task": ...}), whose
    # JSON accessor syntax differs between SQLite and Snowflake — so parse in
    # Python instead of maintaining two dialects.
    # ponytail: full STEPS scan; fine at demo scale, push into SQL if it grows.
    import json as _json

    step_rows = writer.query(
        "SELECT META, KIND, INPUT_TOKENS, OUTPUT_TOKENS, COST_USD, RUN_ID FROM STEPS"
    )
    per_task: dict[str, dict[str, object]] = {}
    for meta_raw, kind, tin, tout, cost, run_id in step_rows:
        try:
            meta = meta_raw if isinstance(meta_raw, dict) else _json.loads(meta_raw or "{}")
        except (TypeError, ValueError):
            meta = {}
        agg = per_task.setdefault(
            str(meta.get("task") or "(untagged)"),
            {"runs": set(), "llm": 0, "tool": 0, "tokens": 0, "cost": 0.0},
        )
        agg["runs"].add(run_id)  # type: ignore[union-attr]
        if kind in ("llm", "tool"):
            agg[kind] = int(agg[kind]) + 1  # type: ignore[arg-type]
        agg["tokens"] = int(agg["tokens"]) + int(tin or 0) + int(tout or 0)  # type: ignore[arg-type]
        agg["cost"] = float(agg["cost"]) + float(cost or 0.0)  # type: ignore[arg-type]
    if per_task:
        t = Table(title="by task (from STEPS meta)", header_style="bold")
        for col in ("task", "runs", "llm steps", "tool steps", "tokens", "cost $"):
            t.add_column(col, overflow="fold")
        for name, agg in sorted(per_task.items()):
            t.add_row(
                name, str(len(agg["runs"])), f"{agg['llm']:,}", f"{agg['tool']:,}",  # type: ignore[arg-type]
                f"{agg['tokens']:,}", f"{float(agg['cost']):.4f}",  # type: ignore[arg-type]
            )
        console.print(t)

    savings = writer.query("SELECT * FROM SAVINGS")
    if savings:
        s = Table(title="SAVINGS view", header_style="bold")
        for col in ("fingerprint", "baseline $", "lightened $", "warm $", "net saved $", "runs"):
            s.add_column(col, overflow="fold")
        for row in savings:
            s.add_row(
                str(row[0])[:20],
                _money(row[1]), _money(row[2]), _money(row[3]), _money(row[4]), str(row[5]),
            )
        console.print(s)

    from amort.ledger.pricing import unknown_models

    if unfamiliar := unknown_models():
        console.print(
            f"[yellow]note:[/yellow] {len(unfamiliar)} model(s) had no published rate and were "
            f"costed at $0.00: {', '.join(unfamiliar)}"
        )
    console.print(f"[dim]ledger backend: {writer.name}[/dim]")


skills_app = typer.Typer(help="Compiled skills (the markdown store is the source of truth).")
app.add_typer(skills_app, name="skills")


def _skill_front(md_path: str | None) -> dict:
    """Frontmatter of a skill's markdown — where `version`/`runs_observed` live."""
    if not md_path:
        return {}
    from pathlib import Path

    from amort.skills.store_everos import _split_markdown

    try:
        front, _ = _split_markdown(Path(md_path).read_text(encoding="utf-8"))
        return front
    except Exception:  # noqa: BLE001 — a bad file must not kill the listing
        return {}


@skills_app.callback(invoke_without_command=True)
def skills_default(ctx: typer.Context) -> None:
    """`amort skills` with no subcommand behaves like `amort skills list`."""
    if ctx.invoked_subcommand is None:
        skills_list()


@skills_app.command("list")
def skills_list() -> None:
    """List compiled skills and their promotion status."""
    from amort.skills.store_everos import get_store

    store = get_store()
    table = Table(title=f"amortize skills — memory: {store.backend_name}", header_style="bold")
    for col in ("skill_id", "name", "status", "version", "runs", "parity", "tools", "path"):
        table.add_column(col, overflow="fold")

    found = store.local.iter_skills()
    for sk in found:
        front = _skill_front(sk.md_path)
        table.add_row(
            sk.skill_id, sk.name, sk.status,
            str(front.get("version") or "-"), str(front.get("runs_observed") or "-"),
            "n/a" if sk.parity_rate is None else f"{sk.parity_rate:.0%}",
            ", ".join(sk.tools_required)[:40],
            str(sk.md_path or "-").replace(str(store.settings.memory_dir), "…"),
        )
    console.print(table)
    if not found:
        console.print(
            "[dim]No skills yet. Layer 2 (distil → replay) is a stub in this build — "
            "`amort demo` records Cases, but nothing compiles them into Skills.[/dim]"
        )


@skills_app.command("show")
def skills_show(skill_id: str) -> None:
    """Show one skill: status, parity, version, tools, and the full markdown."""
    from rich.markdown import Markdown
    from rich.panel import Panel

    from amort.skills.store_everos import get_store

    store = get_store()
    sk = store.local.load_skill(skill_id)
    if sk is None:
        console.print(f"[red]no skill with id {skill_id!r}[/red] — try `amort skills list`")
        raise typer.Exit(1)

    front = _skill_front(sk.md_path)
    head = "\n".join(
        f"[bold]{key}[/bold]: {value}"
        for key, value in (
            ("skill_id", sk.skill_id),
            ("name", sk.name),
            ("status", sk.status),
            ("version", front.get("version") or "-"),
            ("runs_observed", front.get("runs_observed") or "-"),
            ("parity_rate", "n/a" if sk.parity_rate is None else f"{sk.parity_rate:.0%}"),
            ("tools_required", ", ".join(sk.tools_required) or "-"),
            ("fingerprint", sk.task_fingerprint or "-"),
            ("path", sk.md_path or "-"),
        )
    )
    console.print(Panel(head, title=sk.skill_id, title_align="left", border_style="cyan"))
    console.print(Markdown(sk.body))


@app.command()
def dash(
    port: Annotated[int, typer.Option(help="Streamlit port.")] = 8501,
) -> None:
    """Launch the Streamlit dashboard over whichever ledger is active."""
    import subprocess
    from pathlib import Path

    app_path = Path(__file__).parent / "dashboard" / "app.py"
    cmd = [
        sys.executable, "-m", "streamlit", "run", str(app_path),
        "--server.port", str(port), "--server.headless", "true",
    ]
    console.print(f"[cyan]amortize dash[/cyan] → http://localhost:{port}")
    raise typer.Exit(subprocess.call(cmd))


@app.command()
def playground(
    port: Annotated[int, typer.Option(help="Playground port.")] = 4700,
) -> None:
    """The one-page live demo: one prompt, two lanes (direct vs Amortize), real numbers."""
    import httpx

    from amort.config import get_settings

    settings = get_settings()
    try:
        httpx.get(f"{settings.proxy_base_url}/health", timeout=3)
    except Exception:  # noqa: BLE001
        console.print(
            f"[yellow]warning:[/yellow] no proxy at {settings.proxy_base_url} — the right "
            "lane needs it. Start `amort up` in another terminal."
        )
    console.print(f"[cyan]amortize playground[/cyan] → http://127.0.0.1:{port}")
    from amort.demo.playground import serve

    serve(port=port)


@app.command(name="snowflake-init")
def snowflake_init(
    sql: Annotated[str, typer.Option(help="Path to the DDL file.")] = "",
    dry_run: Annotated[bool, typer.Option(help="Print the statements, don't run them.")] = False,
) -> None:
    """Create AMORTIZE.LEDGER (database, tables, SAVINGS view) in Snowflake."""
    from pathlib import Path

    from amort.config import project_root

    settings = get_settings()
    path = Path(sql) if sql else project_root() / "scripts" / "snowflake_setup.sql"
    statements = [s.strip() for s in path.read_text(encoding="utf-8").split(";") if s.strip()]

    if dry_run:
        console.print(f"[cyan]{len(statements)} statement(s)[/cyan] from {path}:")
        for stmt in statements:
            console.print(f"  [dim]{stmt.splitlines()[0]}…[/dim]")
        return

    if not settings.snowflake_configured:
        console.print(
            "[red]Snowflake credentials are not set.[/red] Fill SNOWFLAKE_ACCOUNT, "
            "SNOWFLAKE_USER and SNOWFLAKE_PASSWORD in .env, or run with --dry-run.\n"
            f"[dim]Amortize will keep using the local SQLite ledger at {settings.db_path}.[/dim]"
        )
        raise typer.Exit(1)

    from amort.ledger.snowflake_writer import SnowflakeWriter

    writer = SnowflakeWriter(settings)
    try:
        console.print(f"Connecting to [bold]{settings.snowflake_account}[/bold]…")
        applied, skipped = writer.ensure_schema(str(path))
        console.print(
            f"[green]✓[/green] {len(applied)} statement(s) applied to "
            f"{settings.snowflake_database}.{settings.snowflake_schema_}"
        )
        for stmt in skipped:
            console.print(
                f"[yellow]•[/yellow] skipped [dim]{stmt.splitlines()[0]}[/dim] "
                "— already exists and this role can't create it"
            )
    except Exception as exc:  # noqa: BLE001 — surface the reason, don't traceback at a booth
        console.print(f"[red]✗ Snowflake init failed:[/red] {type(exc).__name__}: {exc}")
        console.print(f"[dim]Amortize still works — the ledger falls back to {settings.db_path}.[/dim]")
        raise typer.Exit(1) from exc
    finally:
        writer.close()


@app.command()
def doctor() -> None:
    """Check config, ledger backend, memory backend, and upstream reachability."""
    import httpx

    from amort.ledger.events import active_backend
    from amort.skills.store_everos import get_store

    settings = get_settings()
    settings.ensure_dirs()

    table = Table(title="amortize doctor", header_style="bold")
    table.add_column("check")
    table.add_column("status")
    table.add_column("detail", overflow="fold")

    table.add_row("config", "[green]ok[/green]", f"port {settings.amort_port}, ledger={settings.amort_ledger}")
    table.add_row(
        "novita key",
        "[green]set[/green]" if settings.novita_api_key else "[yellow]unset[/yellow]",
        "live demo runs enabled" if settings.novita_api_key
        else "demo falls back to offline (simulated numbers)",
    )
    novita_models = f"{settings.novita_api_url.rstrip('/')}/v1/models"
    try:
        headers = (
            {"Authorization": f"Bearer {settings.novita_api_key}"}
            if settings.novita_api_key else {}
        )
        code = httpx.get(novita_models, timeout=5, headers=headers).status_code
        table.add_row("novita api", "[green]reachable[/green]", f"HTTP {code} from {novita_models}")
    except Exception as exc:  # noqa: BLE001
        table.add_row("novita api", "[red]unreachable[/red]", str(exc)[:80])
    backend = active_backend()
    table.add_row(
        "ledger",
        "[green]snowflake[/green]" if backend == "snowflake" else "[yellow]sqlite[/yellow]",
        str(settings.db_path) if backend == "sqlite" else settings.snowflake_database,
    )
    store = get_store()
    table.add_row(
        "memory",
        "[green]everos[/green]" if store.backend_name == "everos" else "[yellow]local[/yellow]",
        settings.everos_base_url if store.backend_name == "everos" else str(settings.memory_dir),
    )
    try:
        code = httpx.get(f"{settings.amort_upstream_anthropic}/v1/models", timeout=5).status_code
        table.add_row(
            "upstream (anthropic)", "[green]reachable[/green]",
            f"HTTP {code} from {settings.amort_upstream_anthropic}",
        )
    except Exception as exc:  # noqa: BLE001
        table.add_row("upstream (anthropic)", "[red]unreachable[/red]", str(exc)[:80])
    try:
        proxy_health = httpx.get(f"{settings.proxy_base_url}/health", timeout=2).json()
        table.add_row("proxy", "[green]running[/green]", str(proxy_health)[:80])
    except Exception:  # noqa: BLE001
        table.add_row("proxy", "[dim]not running[/dim]", "start it with `amort up`")

    console.print(table)


def _q(backend: str):
    """Placeholder style differs: SQLite uses `?`, the Snowflake connector `%s`."""
    return (lambda _n: "?") if backend == "sqlite" else (lambda _n: "%s")


def _money(value: object) -> str:
    return "-" if value is None else f"{float(value):.4f}"


def main() -> None:
    app()


if __name__ == "__main__":
    main()
