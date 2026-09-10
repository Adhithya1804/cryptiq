"""Application settings, loaded from the environment or a local .env file."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the deterministic analysis backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "development"

    database_url: str = "sqlite:///./cryptiq.db"

    # Root log level for the application's own loggers (``app.*``). Emitted to
    # stdout so Docker / CloudWatch capture it. Without an explicit handler the
    # default root level is WARNING and every ``logger.info`` is dropped.
    log_level: str = "INFO"

    # Expose the interactive API docs (``/docs``, ``/redoc``) and the raw
    # ``/openapi.json``. Left on for local development; the AWS demo turns it
    # off so the unauthenticated endpoint surface is minimal.
    expose_api_docs: bool = True

    # Reverse-proxy / app request body ceiling. A scan request is a tiny JSON
    # object ({repository_url, commit_sha}); anything approaching this is abuse.
    # Enforced both in nginx (client_max_body_size) and in-process so the limit
    # holds regardless of how the app is fronted.
    max_request_body_bytes: int = 1_000_000

    # Bound on scans that are QUEUED or RUNNING at once. The demo endpoint is
    # unauthenticated and single-instance; past this a submission is rejected
    # with HTTP 429 until in-flight work drains. Completed and failed scans
    # release capacity immediately. Not a distributed rate limiter.
    max_in_flight_scans: int = 10

    # --- Per-client rate limiting -------------------------------------------
    # An in-process fixed-window limiter (app/rate_limit.py). It is the abuse
    # ceiling for an unauthenticated single-instance demo: it caps scan
    # flooding, Gemini-call amplification and cheap-GET floods without any
    # external store (no Redis). Counters are per worker process; the AWS demo
    # runs one backend process so that is the whole surface.
    rate_limit_enabled: bool = True
    rate_limit_window_seconds: int = 60
    # Any request (the cheap-flood ceiling).
    rate_limit_default_max: int = 240
    # Any state-changing request (POST/PATCH) not classed as expensive.
    rate_limit_write_max: int = 40
    # The cost-amplifying endpoints: scan creation and the AI-backed
    # explanation / migration-assessment routes (each can trigger a Gemini
    # call or a full engine run).
    rate_limit_expensive_max: int = 10
    # Trust ``X-Forwarded-For`` for the client identity. Only enable when the
    # app sits behind a proxy that always sets it (the AWS nginx does). When
    # off, the socket peer address is used and forwarding headers are ignored,
    # so an Internet client cannot spoof its identity to dodge the limiter.
    trust_proxy_headers: bool = False

    # SQLite pragmas applied per connection for file-backed databases (the
    # AWS demo persists SQLite on an EBS volume). ``busy_timeout`` makes a
    # writer wait briefly for a competing write instead of failing immediately
    # with "database is locked" -- the realistic single-instance concern with
    # one worker writing while the API reads. Both are no-ops for ``:memory:``.
    #
    # WAL is left OFF by default: no locking problem has been demonstrated in
    # the suite or the audit, and enabling it adds -wal/-shm sidecar files and
    # changes checkpoint behaviour. It can be turned on (SQLITE_WAL=true) if a
    # concurrency problem ever shows up.
    sqlite_busy_timeout_ms: int = 5_000
    sqlite_wal: bool = False

    # Browser origins allowed to call the API. The Vite dev server is the
    # default; deployments set this explicitly (comma-separated) and never
    # rely on a wildcard. Value "*" is honoured only for local throwaway use.
    cors_allow_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:3000,http://127.0.0.1:3000"
    )

    # Run the in-process scan worker alongside the API. Left on for local
    # development; a deployment can disable it and run the worker separately.
    run_worker: bool = True

    github_api_url: str = "https://api.github.com"
    github_token: str | None = None
    github_timeout_seconds: int = 30

    max_archive_bytes: int = 250 * 1024 * 1024
    max_extracted_bytes: int = 500 * 1024 * 1024
    max_files: int = 20_000
    max_file_bytes: int = 5 * 1024 * 1024

    scan_timeout_seconds: int = 300

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    gemini_timeout_seconds: int = 30
    gemini_max_output_tokens: int = 1500

    parser_version: str = "python-ast-1"
    ruleset_version: str = "0.3.0"
    pqc_ruleset_version: str = "0.2.0"

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() in {"production", "prod"}

    @property
    def cors_origins(self) -> list[str]:
        """The allow-origins list, parsed from the comma-separated setting.

        A bare ``*`` is a local-only convenience and is refused under
        ``ENVIRONMENT=production``: the AWS demo is same-origin (the SPA is
        built with a relative API base behind one nginx), so a production
        wildcard can only be a misconfiguration. It collapses to "no
        cross-origin access" rather than opening the API to every site.
        """
        raw = self.cors_allow_origins.strip()
        if raw == "*":
            return [] if self.is_production else ["*"]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()
