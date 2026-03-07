"""CLI logging integration tests."""

import pytest
from typer.testing import CliRunner

from openbiliclaw import cli as cli_module
from openbiliclaw.cli import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_cli_log_level_option_overrides_config(
    monkeypatch: pytest.MonkeyPatch, runner: CliRunner
) -> None:
    captured: dict[str, str | None] = {"level": None}

    def fake_init_logging(log_level_override: str | None = None) -> None:
        captured["level"] = log_level_override

    monkeypatch.setattr(cli_module, "_initialize_logging", fake_init_logging)

    result = runner.invoke(app, ["--log-level", "DEBUG", "profile"])

    assert result.exit_code == 0
    assert captured["level"] == "DEBUG"
