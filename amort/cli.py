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

    console.print()
    console.print("[bold]amortize[/bold] — proxy up", style="cyan")
    console.print(f"  listening    [bold]http://{bind_host}:{bind_port}[/bold]")
    console.print(f"  upstream     {settings.amort_upstream_anthropic}")
    console.print(f"  ledger       {active_backend()}")
    console.print(f"  memory       {settings.memory_dir}")
    console.print()
    console.print("  Point any client at it with one env var:")
    console.print(f"    [dim]export ANTHROPIC_BASE_URL=http://{bind_host}:{bind_port}[/dim]")
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
) -> None:
    """Run the side-by-side comparison harness (demo-only; not the request path)."""
    from amort.demo.harness import run_demo

    run_demo(task=task, lanes=lanes, repeat=repeat, live=live)


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


@app.command()
def skills() -> None:
    """List compiled skills and their promotion status."""
    from amort.skills.store_everos import get_store

    store = get_store()
    table = Table(title=f"amortize skills — memory: {store.backend_name}", header_style="bold")
    for col in ("skill_id", "name", "status", "fingerprint", "tools", "parity", "path"):
        table.add_column(col, overflow="fold")

    found = store.local.iter_skills()
    for sk in found:
        table.add_row(
            sk.skill_id, sk.name, sk.status, sk.task_fingerprint[:14],
            ", ".join(sk.tools_required)[:40],
            "n/a" if sk.parity_rate is None else f"{sk.parity_rate:.0%}",
            str(sk.md_path or "-").replace(str(store.settings.memory_dir), "…"),
        )
    console.print(table)
    if not found:
        console.print(
            "[dim]No skills yet. Layer 2 (distil → replay) is a stub in this build — "
            "`amort demo` records Cases, but nothing compiles them into Skills.[/dim]"
        )


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
        "anthropic key",
        "[green]set[/green]" if settings.anthropic_api_key else "[yellow]unset[/yellow]",
        "clients may still send their own key" if not settings.anthropic_api_key else "fallback available",
    )
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
        table.add_row("upstream", "[green]reachable[/green]", f"HTTP {code} from {settings.amort_upstream_anthropic}")
    except Exception as exc:  # noqa: BLE001
        table.add_row("upstream", "[red]unreachable[/red]", str(exc)[:80])
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
