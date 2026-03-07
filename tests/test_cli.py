"""CLI tests for configuration guidance behavior."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from openbiliclaw import cli as cli_module
from openbiliclaw import config as config_module
from openbiliclaw.bilibili.auth import AuthStatus
from openbiliclaw.bilibili.browser import BrowserCommandError
from openbiliclaw.cli import app


def _write_example_config(project_root: Path) -> None:
    (project_root / "config.example.toml").write_text(
        """
[general]
language = "zh"
data_dir = "data"

[llm]
default_provider = "openai"

[llm.openai]
api_key = ""
model = "gpt-4o"
base_url = ""

[llm.claude]
api_key = ""
model = "claude-sonnet-4-20250514"

[llm.deepseek]
api_key = ""
model = "deepseek-chat"
base_url = "https://api.deepseek.com"

[llm.ollama]
model = "llama3"
base_url = "http://localhost:11434"

[bilibili]
auth_method = "cookie"
cookie = ""

[bilibili.browser]
executable = ""
headed = false

[scheduler]
enabled = true
discovery_cron = "0 */4 * * *"

[storage]
db_path = "data/openbiliclaw.db"
""".strip(),
        encoding="utf-8",
    )


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_config_show_generates_template_and_prints_guidance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner
) -> None:
    monkeypatch.setattr(config_module, "_PROJECT_ROOT", tmp_path)
    _write_example_config(tmp_path)

    result = runner.invoke(app, ["config-show"])

    assert result.exit_code == 0
    assert (tmp_path / "config.toml").exists()
    assert "当前配置" in result.stdout
    assert "已自动生成" in result.stdout
    assert "llm.openai.api_key" in result.stdout


def test_recommend_reports_clear_config_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner
) -> None:
    monkeypatch.setattr(config_module, "_PROJECT_ROOT", tmp_path)
    _write_example_config(tmp_path)

    result = runner.invoke(app, ["recommend"])

    assert result.exit_code == 1
    assert "配置错误" in result.stdout
    assert "llm.openai.api_key" in result.stdout


def test_config_show_displays_registered_providers(
    monkeypatch: pytest.MonkeyPatch, runner: CliRunner
) -> None:
    class FakeRegistry:
        default_provider = "claude"
        available_providers = ["claude", "ollama"]

    monkeypatch.setattr(cli_module, "_build_registry", lambda: FakeRegistry())
    monkeypatch.setattr(cli_module, "_initialize_logging", lambda log_level_override=None: None)

    result = runner.invoke(app, ["config-show"])

    assert result.exit_code == 0
    assert "已注册 Provider" in result.stdout
    assert "claude, ollama" in result.stdout
    assert "最终默认 Provider: claude" in result.stdout


def test_health_check_reports_provider_statuses(
    monkeypatch: pytest.MonkeyPatch, runner: CliRunner
) -> None:
    class FakeResult:
        def __init__(self, available: bool, is_default: bool, error: str | None = None) -> None:
            self.available = available
            self.is_default = is_default
            self.error = error

    class FakeRegistry:
        async def health_check_all(self) -> dict[str, FakeResult]:
            return {
                "openai": FakeResult(True, True),
                "ollama": FakeResult(False, False, "connection refused"),
            }

    monkeypatch.setattr(cli_module, "_build_registry", lambda: FakeRegistry())
    monkeypatch.setattr(cli_module, "_initialize_logging", lambda log_level_override=None: None)

    result = runner.invoke(app, ["health-check"])

    assert result.exit_code == 0
    assert "Provider 健康检查" in result.stdout
    assert "openai" in result.stdout
    assert "可用" in result.stdout
    assert "connection refused" in result.stdout


def test_auth_login_accepts_interactive_cookie_and_saves_on_success(
    monkeypatch: pytest.MonkeyPatch, runner: CliRunner, tmp_path: Path
) -> None:
    class FakeAuthManager:
        def __init__(self) -> None:
            self.saved_cookie: str | None = None

        async def validate_cookie(self, cookie: str) -> AuthStatus:
            return AuthStatus(
                has_cookie=True,
                authenticated=True,
                cookie_path=tmp_path / "bilibili_cookie.json",
                username="alice",
                user_id=10086,
                message="Cookie 验证成功。",
            )

        def set_cookie(self, cookie: str) -> None:
            self.saved_cookie = cookie

    fake_manager = FakeAuthManager()
    monkeypatch.setattr(cli_module, "_build_auth_manager", lambda: fake_manager, raising=False)
    monkeypatch.setattr(cli_module, "_initialize_logging", lambda log_level_override=None: None)

    result = runner.invoke(app, ["auth", "login"], input="SESSDATA=abc123\n")

    assert result.exit_code == 0
    assert fake_manager.saved_cookie == "SESSDATA=abc123"
    assert "登录成功" in result.stdout
    assert "alice" in result.stdout


def test_auth_login_does_not_save_on_validation_failure(
    monkeypatch: pytest.MonkeyPatch, runner: CliRunner, tmp_path: Path
) -> None:
    class FakeAuthManager:
        def __init__(self) -> None:
            self.saved_cookie = False

        async def validate_cookie(self, cookie: str) -> AuthStatus:
            return AuthStatus(
                has_cookie=True,
                authenticated=False,
                cookie_path=tmp_path / "bilibili_cookie.json",
                message="cookie 已过期",
            )

        def set_cookie(self, cookie: str) -> None:
            self.saved_cookie = True

    fake_manager = FakeAuthManager()
    monkeypatch.setattr(cli_module, "_build_auth_manager", lambda: fake_manager, raising=False)
    monkeypatch.setattr(cli_module, "_initialize_logging", lambda log_level_override=None: None)

    result = runner.invoke(app, ["auth", "login", "--cookie", "SESSDATA=expired"])

    assert result.exit_code == 1
    assert fake_manager.saved_cookie is False
    assert "认证失败" in result.stdout
    assert "已过期" in result.stdout


def test_auth_status_reports_missing_cookie(
    monkeypatch: pytest.MonkeyPatch, runner: CliRunner, tmp_path: Path
) -> None:
    class FakeAuthManager:
        async def get_status(self) -> AuthStatus:
            return AuthStatus(
                has_cookie=False,
                authenticated=False,
                cookie_path=tmp_path / "bilibili_cookie.json",
                message="未配置 B 站 Cookie。",
            )

    monkeypatch.setattr(cli_module, "_build_auth_manager", lambda: FakeAuthManager(), raising=False)
    monkeypatch.setattr(cli_module, "_initialize_logging", lambda log_level_override=None: None)

    result = runner.invoke(app, ["auth", "status"])

    assert result.exit_code == 0
    assert "未配置" in result.stdout


def test_auth_status_reports_authenticated_user(
    monkeypatch: pytest.MonkeyPatch, runner: CliRunner, tmp_path: Path
) -> None:
    class FakeAuthManager:
        async def get_status(self) -> AuthStatus:
            return AuthStatus(
                has_cookie=True,
                authenticated=True,
                cookie_path=tmp_path / "bilibili_cookie.json",
                username="alice",
                user_id=10086,
                message="Cookie 验证成功。",
            )

    monkeypatch.setattr(cli_module, "_build_auth_manager", lambda: FakeAuthManager(), raising=False)
    monkeypatch.setattr(cli_module, "_initialize_logging", lambda log_level_override=None: None)

    result = runner.invoke(app, ["auth", "status"])

    assert result.exit_code == 0
    assert "已认证" in result.stdout
    assert "alice" in result.stdout
    assert "10086" in result.stdout


def test_browser_status_reports_install_guidance_when_missing(
    monkeypatch: pytest.MonkeyPatch, runner: CliRunner
) -> None:
    class FakeBrowser:
        executable = "agent-browser"
        is_available = False

        @staticmethod
        def get_install_hint() -> str:
            return "npm install -g agent-browser"

    monkeypatch.setattr(cli_module, "_build_browser", lambda: FakeBrowser(), raising=False)
    monkeypatch.setattr(cli_module, "_initialize_logging", lambda log_level_override=None: None)

    result = runner.invoke(app, ["browser", "status"])

    assert result.exit_code == 1
    assert "未安装" in result.stdout
    assert "npm install -g agent-browser" in result.stdout


def test_browser_open_reports_navigation_success(
    monkeypatch: pytest.MonkeyPatch, runner: CliRunner
) -> None:
    class FakeBrowser:
        executable = "/tmp/agent-browser"
        is_available = True

        @staticmethod
        def get_install_hint() -> str:
            return ""

        async def navigate(self, url: str) -> dict[str, object]:
            return {"success": True, "url": url}

    monkeypatch.setattr(cli_module, "_build_browser", lambda: FakeBrowser(), raising=False)
    monkeypatch.setattr(cli_module, "_initialize_logging", lambda log_level_override=None: None)

    result = runner.invoke(app, ["browser", "open", "https://example.com"])

    assert result.exit_code == 0
    assert "浏览器已打开" in result.stdout
    assert "https://example.com" in result.stdout


def test_browser_content_reports_command_failure(
    monkeypatch: pytest.MonkeyPatch, runner: CliRunner
) -> None:
    class FakeBrowser:
        executable = "/tmp/agent-browser"
        is_available = True

        @staticmethod
        def get_install_hint() -> str:
            return ""

        async def get_page_content(self, url: str) -> str:
            raise BrowserCommandError("snapshot failed")

    monkeypatch.setattr(cli_module, "_build_browser", lambda: FakeBrowser(), raising=False)
    monkeypatch.setattr(cli_module, "_initialize_logging", lambda log_level_override=None: None)

    result = runner.invoke(app, ["browser", "content", "https://example.com"])

    assert result.exit_code == 1
    assert "浏览器操作失败" in result.stdout
    assert "snapshot failed" in result.stdout
