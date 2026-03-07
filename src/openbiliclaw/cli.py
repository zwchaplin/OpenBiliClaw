"""CLI interface for OpenBiliClaw.

Provides the command-line entry point using Typer.
"""

from __future__ import annotations

import asyncio
from typing import Any

import typer
from rich.console import Console

app = typer.Typer(
    name="openbiliclaw",
    help="🦀 OpenBiliClaw — 你的 B 站专属 AI 朋友",
    add_completion=False,
)
auth_app = typer.Typer(help="B 站认证命令")
browser_app = typer.Typer(help="agent-browser 浏览器命令")
app.add_typer(auth_app, name="auth")
app.add_typer(browser_app, name="browser")
console = Console()
_APP_CONTEXT: dict[str, Any] = {}


def _initialize_logging(log_level_override: str | None = None) -> None:
    """Load config and initialize the logging system."""
    from openbiliclaw.config import load_config
    from openbiliclaw.logging_setup import configure_logging

    config = load_config()
    configure_logging(config, console_level_override=log_level_override)


def _build_registry() -> Any:
    """Build the configured LLM registry."""
    from openbiliclaw.config import load_config
    from openbiliclaw.llm import build_llm_registry

    return build_llm_registry(load_config())


def _build_auth_manager() -> Any:
    """Build the configured Bilibili auth manager."""
    from openbiliclaw.bilibili.auth import AuthManager
    from openbiliclaw.config import load_config

    return AuthManager(load_config().data_path)


def _build_browser() -> Any:
    """Build the configured Bilibili browser integration."""
    from openbiliclaw.bilibili.browser import BilibiliBrowser
    from openbiliclaw.config import load_config

    config = load_config()
    return BilibiliBrowser(
        executable=config.bilibili.browser_executable,
        headed=config.bilibili.browser_headed,
        cookie=config.bilibili.cookie,
    )


@app.callback()
def main(log_level: str | None = typer.Option(None, "--log-level")) -> None:
    """Global CLI options."""
    _APP_CONTEXT["log_level"] = log_level
    _initialize_logging(log_level_override=log_level)


def _print_config_guidance(messages: list[str]) -> None:
    """Render config hints in a consistent way."""
    if not messages:
        return
    console.print("[bold yellow]配置提示[/bold yellow]")
    for message in messages:
        console.print(f"  - {message}")


def _print_auth_status(status: Any) -> None:
    """Render auth status consistently."""
    state_label = "已认证" if status.authenticated else "未认证"
    console.print("[bold]B站认证状态[/bold]")
    console.print(f"  状态: {state_label}")
    console.print(f"  Cookie 文件: {status.cookie_path}")
    if status.username:
        console.print(f"  用户名: {status.username}")
    if status.user_id:
        console.print(f"  UID: {status.user_id}")
    if status.message:
        console.print(f"  说明: {status.message}")


def _print_browser_status(browser: Any) -> None:
    """Render browser installation status."""
    availability = "已安装" if browser.is_available else "未安装"
    console.print("[bold]agent-browser 状态[/bold]")
    console.print(f"  状态: {availability}")
    console.print(f"  可执行文件: {browser.executable}")


def _require_runtime_config() -> None:
    """Exit with a clear message when runtime config is incomplete."""
    from openbiliclaw.config import (
        ConfigError,
        load_config_with_diagnostics,
        validate_runtime_config,
    )

    config, diagnostics = load_config_with_diagnostics()
    try:
        validate_runtime_config(config)
    except ConfigError as exc:
        console.print("[bold red]配置错误[/bold red]")
        hints = diagnostics.messages + [
            f"{issue.field}: {issue.message}" for issue in diagnostics.issues
        ]
        _print_config_guidance(hints)
        console.print(f"  {exc}")
        raise typer.Exit(code=1) from exc


@app.command()
def start() -> None:
    """启动 OpenBiliClaw Agent."""
    _require_runtime_config()
    console.print("[bold green]🦀 OpenBiliClaw[/bold green] 正在启动...")
    console.print("[dim]v0.1.0-dev — 项目处于早期开发阶段[/dim]")
    # TODO: Initialize and start the agent orchestrator


@app.command()
def recommend() -> None:
    """查看推荐内容."""
    _require_runtime_config()
    console.print("[bold]📬 推荐内容[/bold]")
    console.print("[dim]功能开发中...[/dim]")
    # TODO: Display latest recommendations


@app.command()
def profile() -> None:
    """查看用户画像."""
    console.print("[bold]🧠 用户画像[/bold]")
    console.print("[dim]功能开发中...[/dim]")
    # TODO: Display user soul profile


@app.command()
def discover() -> None:
    """手动触发内容发现."""
    _require_runtime_config()
    console.print("[bold]🔍 内容发现[/bold]")
    console.print("[dim]功能开发中...[/dim]")
    # TODO: Trigger content discovery


@app.command()
def chat() -> None:
    """与 Agent 对话（苏格拉底式深度交流）."""
    _require_runtime_config()
    console.print("[bold]💬 对话模式[/bold]")
    console.print("[dim]功能开发中...[/dim]")
    # TODO: Interactive chat with the agent


@app.command()
def config_show() -> None:
    """显示当前配置."""
    from openbiliclaw.config import load_config_with_diagnostics
    from openbiliclaw.llm import RegistryBuildError, summarize_registry

    cfg, diagnostics = load_config_with_diagnostics()
    console.print("[bold]⚙️ 当前配置[/bold]")
    console.print(f"  语言: {cfg.language}")
    console.print(f"  LLM: {cfg.llm.default_provider}")
    console.print(f"  B站认证: {cfg.bilibili.auth_method}")
    console.print(f"  定时任务: {'开启' if cfg.scheduler.enabled else '关闭'}")
    console.print(f"  数据目录: {cfg.data_path}")
    if diagnostics.config_path:
        console.print(f"  配置文件: {diagnostics.config_path}")

    try:
        registry = _build_registry()
        summary = summarize_registry(cfg, registry)
        console.print(f"  已注册 Provider: {', '.join(summary.registered_providers)}")
        console.print(f"  最终默认 Provider: {summary.effective_default}")
    except RegistryBuildError as exc:
        console.print("  已注册 Provider: 无")
        console.print(f"  Provider 状态: {exc}")

    hints = diagnostics.messages + [
        f"{issue.field}: {issue.message}" for issue in diagnostics.issues
    ]
    _print_config_guidance(hints)


@auth_app.command("login")
def auth_login(
    cookie: str | None = typer.Option(None, "--cookie", help="直接传入完整 Cookie"),
) -> None:
    """交互式设置并验证 B 站 Cookie."""
    manager = _build_auth_manager()
    cookie_value = cookie or typer.prompt("请输入 B 站 Cookie", prompt_suffix=": ")
    status = asyncio.run(manager.validate_cookie(cookie_value))
    if not status.authenticated:
        console.print("[bold red]认证失败[/bold red]")
        _print_auth_status(status)
        raise typer.Exit(code=1)

    manager.set_cookie(cookie_value)
    console.print("[bold green]登录成功[/bold green]")
    _print_auth_status(status)


@auth_app.command("status")
def auth_status() -> None:
    """查看当前 B 站 Cookie 认证状态."""
    manager = _build_auth_manager()
    status = asyncio.run(manager.get_status())
    _print_auth_status(status)


@app.command("health-check")
def health_check() -> None:
    """检查当前已注册 LLM provider 的可用性."""
    from openbiliclaw.llm import RegistryBuildError

    try:
        registry = _build_registry()
    except RegistryBuildError as exc:
        console.print("[bold red]Provider 健康检查失败[/bold red]")
        console.print(f"  {exc}")
        raise typer.Exit(code=1) from exc

    results = asyncio.run(registry.health_check_all())
    console.print("[bold]Provider 健康检查[/bold]")
    for name, result in results.items():
        status = "可用" if result.available else "不可用"
        default_label = " (default)" if result.is_default else ""
        console.print(f"  {name}{default_label}: {status}")
        if result.error:
            console.print(f"    原因: {result.error}")


@browser_app.command("status")
def browser_status() -> None:
    """检查 agent-browser 是否可用."""
    browser = _build_browser()
    _print_browser_status(browser)
    if browser.is_available:
        return
    console.print(f"  安装提示: {browser.get_install_hint()}")
    raise typer.Exit(code=1)


@browser_app.command("open")
def browser_open(url: str) -> None:
    """通过 agent-browser 打开一个页面."""
    from openbiliclaw.bilibili.browser import BrowserCommandError

    browser = _build_browser()
    if not browser.is_available:
        console.print("[bold red]agent-browser 未安装[/bold red]")
        console.print(f"  {browser.get_install_hint()}")
        raise typer.Exit(code=1)

    try:
        asyncio.run(browser.navigate(url))
    except BrowserCommandError as exc:
        console.print("[bold red]浏览器操作失败[/bold red]")
        console.print(f"  {exc}")
        raise typer.Exit(code=1) from exc

    console.print("[bold green]浏览器已打开[/bold green]")
    console.print(f"  {url}")


@browser_app.command("content")
def browser_content(url: str) -> None:
    """抓取当前页面可见文本."""
    from openbiliclaw.bilibili.browser import BrowserCommandError

    browser = _build_browser()
    if not browser.is_available:
        console.print("[bold red]agent-browser 未安装[/bold red]")
        console.print(f"  {browser.get_install_hint()}")
        raise typer.Exit(code=1)

    try:
        content = asyncio.run(browser.get_page_content(url))
    except BrowserCommandError as exc:
        console.print("[bold red]浏览器操作失败[/bold red]")
        console.print(f"  {exc}")
        raise typer.Exit(code=1) from exc

    console.print("[bold]页面内容[/bold]")
    console.print(content)


if __name__ == "__main__":
    app()
