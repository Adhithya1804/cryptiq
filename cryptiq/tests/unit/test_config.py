"""Settings load from defaults and from the environment."""

from app.config import Settings, get_settings


def test_defaults_match_the_documented_limits() -> None:
    settings = Settings(_env_file=None)

    assert settings.environment == "development"
    assert settings.database_url == "sqlite:///./cryptiq.db"
    assert settings.github_api_url == "https://api.github.com"
    assert settings.max_archive_bytes == 250 * 1024 * 1024
    assert settings.max_extracted_bytes == 500 * 1024 * 1024
    assert settings.max_files == 20_000
    assert settings.max_file_bytes == 5 * 1024 * 1024
    assert settings.scan_timeout_seconds == 300
    assert settings.parser_version == "python-ast-1"
    assert settings.ruleset_version == "0.3.0"
    assert settings.pqc_ruleset_version == "0.2.0"


def test_no_secret_is_hard_coded() -> None:
    assert Settings(_env_file=None).gemini_api_key is None


def test_environment_variables_override_defaults(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("MAX_FILES", "17")

    settings = Settings(_env_file=None)

    assert settings.environment == "test"
    assert settings.max_files == 17


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()
