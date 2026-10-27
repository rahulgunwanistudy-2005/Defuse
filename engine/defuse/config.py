"""Settings. The only module that reads the environment."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DEFUSE_", extra="ignore")

    gitlab_url: str = "https://gitlab.com"
    gitlab_token: SecretStr | None = None
    sandbox_namespaces: str = "defuse-sandbox"
    concurrency: int = 8
    request_timeout: float = 20.0
    trace_max_bytes: int = 2 * 1024 * 1024

    database_url: str = "sqlite+aiosqlite:///./defuse.db"
    api_write_token: SecretStr | None = None
    seed_scenario: bool = True
    cors_origins: str = "*"

    records_dir: Path = Path("records")
    actor: str = "defuse"

    gcp_project: str | None = None
    gcp_zone: str = "us-central1-a"
    isolation_tag: str = "quarantined"
    live_tag: str = "runner-live"
    sinkhole_url: str | None = None
    sentinel_path: str = "/srv/defuse-sentinel"

    runner_hosts: dict[str, str] = {}
    token_variables: dict[str, str] = {}
    agent_identity_prefixes: str = "duo-,ai-workflow"
    auto_merge_remediation: bool = False
    action_timeout: float = 300
    known_good_refs: dict[str, str] = {}
    credential_broker_url: str | None = None
    credential_broker_token: SecretStr | None = None
    duo_enabled: bool = False
    duo_timeout: float = 180
    verification_window: float = 120
    executor_image: str = "$CI_REGISTRY_IMAGE/engine:$CI_COMMIT_SHORT_SHA"
    wif_audience: str | None = None
    wif_provider: str | None = None
    gcp_service_account: str | None = None
    record_project_id: int | None = None
    broker_journal: Path = Path("records/credential-authority.db")
    broker_gitlab_token: SecretStr | None = None
    broker_provider_commands: dict[str, list[str]] = {}

    @property
    def namespaces(self) -> tuple[str, ...]:
        return tuple(n.strip().strip("/") for n in self.sandbox_namespaces.split(",") if n.strip())

    @property
    def agent_prefixes(self) -> tuple[str, ...]:
        return tuple(p.strip() for p in self.agent_identity_prefixes.split(",") if p.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
