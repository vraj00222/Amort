"""FastAPI app — the surface a client points `ANTHROPIC_BASE_URL` at.

Routes:

    POST /v1/messages              Anthropic Messages format
    POST /v1/chat/completions      OpenAI Chat Completions format
    GET  /health                   liveness + which backends are live
    GET  /stats                    quick ledger rollup (demo convenience)
    *    /v1/{path}                catch-all relay to the matching upstream

The catch-all matters more than it looks: a real client does not only call
`/v1/messages`. Claude Code also hits `/v1/messages/count_tokens` and
`/v1/models`, and a proxy that 404s those is not transparent — it is a proxy the
client has to know about, which defeats the entire premise.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from amort.config import get_settings
from amort.proxy.interceptors import Provider
from amort.proxy.passthrough import build_client, relay

logger = logging.getLogger("amort.proxy.server")

_client: httpx.AsyncClient | None = None


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _client
    settings = get_settings()
    settings.ensure_dirs()
    _client = build_client()

    from amort.ledger.events import active_backend, flush, reset_writer

    logger.info(
        "amortize proxy ready — upstream=%s ledger=%s memory=%s",
        settings.amort_upstream_anthropic, active_backend(), settings.memory_dir,
    )
    try:
        yield
    finally:
        flush()
        reset_writer()
        if _client is not None:
            await _client.aclose()
            _client = None


app = FastAPI(
    title="amortize",
    version="0.1.0",
    description="A local proxy that makes AI agents cheaper to run.",
    lifespan=lifespan,
)


def client() -> httpx.AsyncClient:
    """The shared upstream client. Built lazily so tests can import the app."""
    global _client
    if _client is None:
        _client = build_client()
    return _client


@app.api_route("/", methods=["GET", "HEAD"])
async def root() -> Response:
    """Claude Code sends a best-effort `HEAD /` connectivity probe at startup.

    Documented in the gateway protocol reference as rejectable, but answering it
    keeps the client's startup path clean instead of logging a 404 every launch.
    """
    return Response(status_code=200, headers={"x-amortize": app.version})


@app.get("/health")
async def health() -> dict[str, Any]:
    """Liveness plus what the proxy is actually wired to right now."""
    from amort.ledger.events import active_backend
    from amort.skills.store_everos import get_store

    settings = get_settings()
    return {
        "status": "ok",
        "service": "amortize",
        "version": app.version,
        "upstream": {
            "anthropic": settings.amort_upstream_anthropic,
            "openai": settings.amort_upstream_openai,
        },
        "ledger": active_backend(),
        "memory": get_store().backend_name,
        "layers": {
            # Stated plainly so nobody demos this build believing it optimizes.
            "lighten": "stub (TODO layer1)",
            "amortize": "stub (TODO layer2)",
            "prove": "active",
        },
    }


@app.get("/stats")
async def stats() -> dict[str, Any]:
    """Ledger rollup — what `amort stats` shows, over HTTP."""
    from amort.ledger.events import get_writer

    writer = get_writer()
    try:
        totals = writer.query(
            "SELECT COUNT(*), COALESCE(SUM(INPUT_TOKENS),0), COALESCE(SUM(OUTPUT_TOKENS),0), "
            "COALESCE(SUM(COST_USD),0) FROM STEPS"
        )[0]
    except Exception as exc:  # noqa: BLE001
        return {"backend": writer.name, "error": str(exc)}
    return {
        "backend": writer.name,
        "steps": totals[0],
        "input_tokens": totals[1],
        "output_tokens": totals[2],
        "cost_usd": round(float(totals[3]), 6),
    }


@app.post("/v1/messages")
async def anthropic_messages(request: Request) -> Response:
    """Anthropic Messages API — the endpoint Claude Code and the SDK use."""
    return await relay(request, provider="anthropic", client=client())


@app.post("/v1/chat/completions")
async def openai_chat_completions(request: Request) -> Response:
    """OpenAI Chat Completions API."""
    return await relay(request, provider="openai", client=client())


@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def catch_all(request: Request, path: str) -> Response:
    """Everything else under /v1 — relayed to the provider the path implies."""
    return await relay(request, provider=_provider_for(path), client=client())


def _provider_for(path: str) -> Provider:
    """Route by path shape. Anthropic is the default: it is the primary client."""
    openai_prefixes = (
        "chat/", "completions", "embeddings", "responses", "assistants",
        "audio/", "images/", "moderations", "fine_tuning", "batches", "vector_stores",
    )
    return "openai" if path.startswith(openai_prefixes) else "anthropic"


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception) -> JSONResponse:
    """Return provider-shaped errors so client SDKs can parse them."""
    logger.exception("unhandled proxy error on %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "type": "error",
            "error": {"type": "api_error", "message": f"amortize: {type(exc).__name__}: {exc}"},
        },
    )


__all__ = ["app", "client", "lifespan"]
