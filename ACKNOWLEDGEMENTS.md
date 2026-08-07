# Acknowledgements

Amortize is MIT-licensed (see [LICENSE](LICENSE)). This file credits the ideas, protocols and
projects it builds on. **No third-party source code is vendored into this repository** — everything
under `amort/` is original work. What follows is credit for prior art and for the runtime
dependencies the package installs.

## Prior art the design borrows from

**Dynamic tool discovery (Layer 1 — LIGHTEN).** The pattern of replacing a full tool catalogue with
one-line stubs plus a synthetic search tool, then hydrating only the schemas the model asks for, is
not ours. Cursor published a measured **46.9% token reduction** with this approach, and that result
is what made Layer 1 worth building. Our implementation is independent; the idea is theirs.
`amort/proxy/lighten.py` measures its own reduction rather than quoting anyone else's number.

**Case- and skill-based agent memory (Layer 2 — AMORTIZE).** The Case → Skill distinction —
recording what happened on a run, then distilling repeats into a reusable procedure — comes from
[EverOS](https://github.com/EverMind-AI/EverOS) (EverMind AI), which models `agent_case` and
`agent_skill` as first-class memory kinds. `amort/skills/store_everos.py` is an *adapter* to EverOS
rather than a reimplementation, and its local fallback deliberately mirrors EverOS's on-disk layout
(entry-id conventions, frontmatter, `<app>/<project>/agents/<id>/{.cases,skills}/`) so files written
offline are drop-in for a real EverOS memory root.

**The gateway protocol.** The Claude Code integration follows Anthropic's published
[LLM gateway documentation](https://code.claude.com/docs/en/llm-gateway-connect). Two behaviours the
proxy is careful to preserve — the positional strip of Claude Code's attribution block from the
`system` array, and the pairing of a beta header with the body field it authorizes — are documented
there, not discovered by us.

## Runtime dependencies

Installed from PyPI; none are vendored or modified. Licences are the projects' own.

| Project | Used for |
|---|---|
| [FastAPI](https://github.com/fastapi/fastapi) + [Starlette](https://github.com/encode/starlette) | the proxy and stage HTTP surfaces |
| [uvicorn](https://github.com/encode/uvicorn) | ASGI server |
| [httpx](https://github.com/encode/httpx) | upstream relay, streaming passthrough |
| [pydantic](https://github.com/pydantic/pydantic) / [pydantic-settings](https://github.com/pydantic/pydantic-settings) | `StepEvent` schema, `.env` configuration |
| [typer](https://github.com/fastapi/typer) + [rich](https://github.com/Textualize/rich) | the `amort` CLI and its tables |
| [streamlit](https://github.com/streamlit/streamlit) + [pandas](https://github.com/pandas-dev/pandas) | the dashboard |
| [snowflake-connector-python](https://github.com/snowflakedb/snowflake-connector-python) | the Snowflake ledger writer |
| [openai](https://github.com/openai/openai-python) / [anthropic](https://github.com/anthropics/anthropic-sdk-python) | demo agent loops |
| [tenacity](https://github.com/jd/tenacity) | retry around ledger writes |
| [ruff](https://github.com/astral-sh/ruff) / [uv](https://github.com/astral-sh/uv) | lint and packaging (dev) |

## Services

- **Snowflake** — the ledger's destination (`AMORTIZE.LEDGER`: `RUNS`, `STEPS`, `SKILLS`, `SAVINGS`).
  SQLite is the automatic fallback and mirrors the same DDL column for column.
- **Novita** — the OpenAI-compatible upstream the live demo runs against
  (`deepseek/deepseek-v4-flash`).
- **EverOS** — the memory service behind Cases and Skills, with a local markdown fallback.

## Assets

The stage view (`amort/demo/stage.html`) and the dashboard use **no external assets** — no CDN
scripts, no web fonts, no images. Type is the viewer's own monospace stack and every style is
inline, so both surfaces render identically on a booth machine with no network.

## Fixtures

`amort/demo/tasks/tickets.json` and `amort/demo/tasks/invoices.json` are synthetic, generated
deterministically for this project. They contain no real customer, ticket, invoice or payment data.
