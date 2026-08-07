"""Amortize configuration — one `Settings` object loaded from `.env`.

Load-bearing invariants:

* **Nothing here is required.** Every field has a default and an empty
  Snowflake/EverOS/provider block is a supported, tested state — Amortize
  degrades to the local SQLite ledger and the local markdown memory store
  rather than failing at import time. `Settings()` must never raise.
* Field names are the env var names, lower-cased. pydantic-settings matches
  them case-insensitively, so `amort_port` ← `AMORT_PORT`.
* Path fields are resolved against `project_root()` (the repo root, i.e. the
  nearest ancestor holding `pyproject.toml`, else CWD) so `amort up` behaves the
  same whichever directory it is launched from.
"""

from __future__ import annotations

import functools
import os
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LedgerBackend = Literal["auto", "snowflake", "sqlite"]
EverosMode = Literal["local", "cloud"]


def project_root() -> Path:
    """Nearest ancestor directory containing `pyproject.toml`, else CWD."""
    here = Path(__file__).resolve()
    for parent in (here, *here.parents):
        if (parent / "pyproject.toml").is_file():
            return parent
    return Path.cwd()


class Settings(BaseSettings):
    """Runtime configuration. See `.env.example` for the annotated template."""

    model_config = SettingsConfigDict(
        env_file=os.environ.get("AMORT_ENV_FILE", str(project_root() / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- upstream providers -------------------------------------------------
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    amort_upstream_anthropic: str = "https://api.anthropic.com"
    amort_upstream_openai: str = "https://api.openai.com"

    # --- novita (the working demo upstream; OpenAI-compatible) ---------------
    novita_api_url: str = "https://api.novita.ai/openai"
    novita_api_key: str | None = None
    novita_model: str = "deepseek/deepseek-v4-flash"
    novita_embed_model: str = "baai/bge-m3"

    # --- optimizer knobs -----------------------------------------------------
    amort_lighten: bool = True
    amort_tool_stub_threshold: int = 4
    amort_spill_threshold: int = 1500  # tokens (chars/4 on the serialized result)
    amort_inject_budget: int = 2000  # tokens, cap on an injected plan + schemas

    # --- amortize -----------------------------------------------------------
    amort_port: int = 4000
    amort_host: str = "127.0.0.1"
    amort_ledger: LedgerBackend = "auto"
    amort_memory_dir: Path = Path(".amort/memory")
    amort_spill_dir: Path = Path(".amort/spill")
    amort_db_path: Path = Path(".amort/amort.db")

    # --- everos -------------------------------------------------------------
    everos_mode: EverosMode = "local"
    everos_api_key: str | None = None
    everos_base_url: str = "http://127.0.0.1:8000"
    everos_agent_id: str = "amortize"
    everos_app_id: str = "amortize"
    everos_project_id: str = "default"

    # --- snowflake ----------------------------------------------------------
    snowflake_account: str | None = None
    snowflake_user: str | None = None
    snowflake_password: str | None = None
    snowflake_role: str = "ACCOUNTADMIN"
    snowflake_warehouse: str = "COMPUTE_WH"
    snowflake_database: str = "AMORTIZE"
    snowflake_schema_: str = Field(default="LEDGER", alias="SNOWFLAKE_SCHEMA")

    # --- demo ---------------------------------------------------------------
    amort_demo_model: str = "claude-haiku-4-5-20251001"

    # --- normalisation ------------------------------------------------------
    @field_validator(
        "anthropic_api_key",
        "openai_api_key",
        "novita_api_key",
        "everos_api_key",
        "snowflake_account",
        "snowflake_user",
        "snowflake_password",
        mode="before",
    )
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        """Treat an unfilled template line as absent, not as a credential.

        `KEY=` yields `""`, and `KEY=   # a comment` yields the comment text
        (dotenv keeps trailing comments when the value is otherwise empty). Both
        must become `None`, or the proxy would forward `Authorization: Bearer
        # only if cloud` upstream and Snowflake would try to dial a host named
        after a comment. No real credential is blank or starts with `#`.
        """
        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned or cleaned.startswith("#"):
                return None
            return cleaned
        return value

    # --- derived ------------------------------------------------------------
    @property
    def memory_dir(self) -> Path:
        return self._abs(self.amort_memory_dir)

    @property
    def spill_dir(self) -> Path:
        return self._abs(self.amort_spill_dir)

    @property
    def db_path(self) -> Path:
        return self._abs(self.amort_db_path)

    @property
    def agent_scope_dir(self) -> Path:
        """`<memory_root>/<app_dir>/<project_dir>/agents/<agent_id>/`.

        Mirrors EverOS's on-disk partitioning exactly (see its
        `core/persistence/memory_root.py`), including the reserved-name mapping
        `default` → `default_app` / `default_project`, so a local store written
        by Amortize can be dropped into an EverOS memory root as-is.
        """
        app_dir = "default_app" if self.everos_app_id == "default" else self.everos_app_id
        proj_dir = (
            "default_project" if self.everos_project_id == "default" else self.everos_project_id
        )
        return self.memory_dir / app_dir / proj_dir / "agents" / self.everos_agent_id

    @property
    def skills_dir(self) -> Path:
        """Skill-named dirs: `skills/skill_<name>/SKILL.md`."""
        return self.agent_scope_dir / "skills"

    @property
    def cases_dir(self) -> Path:
        """Dot-hidden daily-log Case dir: `.cases/agent_case-<YYYY-MM-DD>.md`."""
        return self.agent_scope_dir / ".cases"

    @property
    def snowflake_configured(self) -> bool:
        """True when the three credentials a connection actually needs are set."""
        return bool(self.snowflake_account and self.snowflake_user and self.snowflake_password)

    def snowflake_connect_kwargs(self) -> dict[str, str]:
        """kwargs for `snowflake.connector.connect(**kwargs)`."""
        return {
            "account": self.snowflake_account or "",
            "user": self.snowflake_user or "",
            "password": self.snowflake_password or "",
            "role": self.snowflake_role,
            "warehouse": self.snowflake_warehouse,
            "database": self.snowflake_database,
            "schema": self.snowflake_schema_,
        }

    @property
    def proxy_base_url(self) -> str:
        return f"http://{self.amort_host}:{self.amort_port}"

    def ensure_dirs(self) -> None:
        """Create the runtime dirs. Idempotent; safe to call on every startup."""
        for path in (self.memory_dir, self.spill_dir, self.skills_dir, self.cases_dir):
            path.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _abs(path: Path) -> Path:
        return path if path.is_absolute() else project_root() / path


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide singleton. `get_settings.cache_clear()` in tests."""
    return Settings()  # type: ignore[call-arg]  # every field has a default
