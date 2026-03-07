"""CLI interface for OpenBiliClaw.

Provides the command-line entry point using Typer.
"""

from __future__ import annotations

from typing import Any

import typer
from rich.console import Console

app = typer.Typer(
    name="openbiliclaw",
    help="🦀 OpenBiliClaw — 你的 B 站专属 AI 朋友",
    add_completion=False,
)
console = Console()
_APP_CONTEXT: dict[str, Any] = {}


def _initialize_logging(log_level_override: str | None = None) -> None:
    """Load config and initialize the logging system."""
    from openbiliclaw.config import load_config
    from openbiliclaw.logging_setup import configure_logging

    config = load_config()
    configure_logging(config, console_level_override=log_level_override)


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

    cfg, diagnostics = load_config_with_diagnostics()
    console.print("[bold]⚙️ 当前配置[/bold]")
    console.print(f"  语言: {cfg.language}")
    console.print(f"  LLM: {cfg.llm.default_provider}")
    console.print(f"  B站认证: {cfg.bilibili.auth_method}")
    console.print(f"  定时任务: {'开启' if cfg.scheduler.enabled else '关闭'}")
    console.print(f"  数据目录: {cfg.data_path}")
    if diagnostics.config_path:
        console.print(f"  配置文件: {diagnostics.config_path}")

    hints = diagnostics.messages + [
        f"{issue.field}: {issue.message}" for issue in diagnostics.issues
    ]
    _print_config_guidance(hints)


if __name__ == "__main__":
    app()
