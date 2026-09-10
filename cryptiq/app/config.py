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
    def cors_origins(self) -> list[str]:
        """The allow-origins list, parsed from the comma-separated setting."""
        raw = self.cors_allow_origins.strip()
        if raw == "*":
            return ["*"]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()
