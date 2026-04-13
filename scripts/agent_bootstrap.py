#!/usr/bin/env python3
"""Agent-driven bootstrap script for OpenBiliClaw.

This script is intended to be invoked by an AI coding agent (Claude Code,
Codex CLI, OpenClaw, Cursor, etc.) after the user pastes the README "Agent
deployment prompt" into the agent. The agent parses the prompt, runs this
script with the appropriate flags, then handles any interactive follow-ups
(missing API key, missing Bilibili cookie) that the script reports.

The script is intentionally non-interactive and machine-friendly:
- emits structured JSON status lines prefixed with ``BOOTSTRAP_STATUS:``
- exits 0 on success, non-zero on failure
- never prompts stdin (agent/user input is driven from outside the script)

Supported flows:
1. Docker path (preferred if Docker + docker compose are available)
2. Local Python path (uv preferred, pip fallback)
3. Reuse secrets from an existing OpenBiliClaw checkout

Typical agent workflow:

    1. Detect or clone repo into target directory.
    2. Run ``python scripts/agent_bootstrap.py --mode auto`` (add
       ``--reuse-from <path>`` when the user already has a working install).
    3. Parse ``BOOTSTRAP_STATUS`` JSON lines to decide next steps.
    4. If the final status says ``missing_llm_key`` or ``missing_cookie``,
       ask the user for the value and re-run with ``--llm-api-key`` or
       ``--bilibili-cookie``.
    5. Poll ``http://127.0.0.1:8420/api/health`` to confirm the service is
       ready.

All secrets accepted via flags are written directly to ``config.toml`` and
``data/bilibili_cookie.json``. Nothing is uploaded off the machine.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8420
DEFAULT_REPO_URL = "https://github.com/whiteguo233/OpenBiliClaw.git"
DEFAULT_HEALTH_PATH = "/api/health"
HEALTH_TIMEOUT_SECONDS = 90
HEALTH_POLL_INTERVAL = 2.0

SUPPORTED_PROVIDERS = ("openai", "claude", "gemini", "deepseek", "ollama", "openrouter")
REMOTE_PROVIDERS = ("openai", "claude", "gemini", "deepseek", "openrouter")


# ---------------------------------------------------------------------------
# Immutable status + exit codes


@dataclass(frozen=True)
class BootstrapResult:
    """Immutable result emitted to the agent."""

    status: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


def emit(result: BootstrapResult) -> None:
    """Emit a machine-parseable status line for the caller agent."""

    payload = {
        "status": result.status,
        "message": result.message,
        "details": result.details,
    }
    print(f"BOOTSTRAP_STATUS: {json.dumps(payload, ensure_ascii=False)}")
    sys.stdout.flush()


def info(message: str) -> None:
    """Human-readable log line that sits above BOOTSTRAP_STATUS events."""

    print(f"[bootstrap] {message}")
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# CLI argument parsing


def build_arg_parser() -> argparse.ArgumentParser:
    """Return the immutable argument parser."""

    parser = argparse.ArgumentParser(
        description="Automated OpenBiliClaw bootstrap for AI coding agents.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--project-dir",
        default=".",
        help="Target project directory (default: current directory).",
    )
    parser.add_argument(
        "--mode",
        choices=("auto", "docker", "local"),
        default="auto",
        help="Deployment mode. 'auto' prefers Docker when available.",
    )
    parser.add_argument(
        "--repo-url",
        default=DEFAULT_REPO_URL,
        help="Git repository URL to clone when project-dir is empty.",
    )
    parser.add_argument(
        "--branch",
        default="main",
        help="Git branch to check out on fresh clones (default: main).",
    )
    parser.add_argument(
        "--reuse-from",
        default=None,
        help="Path to an existing OpenBiliClaw checkout whose secrets (API keys + Bilibili cookie) should be copied into the new install.",
    )
    parser.add_argument(
        "--provider",
        choices=SUPPORTED_PROVIDERS,
        default=None,
        help="Override default LLM provider.",
    )
    parser.add_argument(
        "--llm-api-key",
        default=None,
        help="LLM API key for the (current or overridden) provider. Stored in config.toml.",
    )
    parser.add_argument(
        "--bilibili-cookie",
        default=None,
        help="Bilibili cookie string. Stored in config.toml and data/bilibili_cookie.json.",
    )
    parser.add_argument(
        "--skip-start",
        action="store_true",
        help="Prepare config and dependencies but do not start the backend.",
    )
    parser.add_argument(
        "--skip-init",
        action="store_true",
        help="Do not run 'openbiliclaw init' after the backend is healthy.",
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Assume dependencies are already installed (local mode only).",
    )
    parser.add_argument(
        "--skip-health-check",
        action="store_true",
        help="Do not poll /api/health after starting the backend.",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help="API host to bind on local mode (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help="API port (default: 8420).",
    )
    parser.add_argument(
        "--install-cmd",
        default=None,
        help="Override the dependency install command. Default: 'uv sync' when uv is available, otherwise 'pip install -e .'.",
    )
    parser.add_argument(
        "--python",
        default=None,
        help="Path to the Python interpreter to use for the virtual environment. Default: current interpreter.",
    )
    return parser


# ---------------------------------------------------------------------------
# Environment detection


def which(binary: str) -> str | None:
    """Return the absolute path to a binary or None if unavailable."""

    return shutil.which(binary)


def detect_docker() -> bool:
    """Return True when Docker + docker compose V2 are usable."""

    docker = which("docker")
    if docker is None:
        return False
    probe = run_capture([docker, "compose", "version"], check=False)
    return probe.returncode == 0


def detect_uv() -> bool:
    """Return True when `uv` is available on PATH."""

    return which("uv") is not None


# ---------------------------------------------------------------------------
# Subprocess helpers


@dataclass(frozen=True)
class CommandResult:
    """Immutable result of a subprocess run."""

    returncode: int
    stdout: str
    stderr: str


def run_capture(cmd: list[str], *, check: bool = True, cwd: Path | None = None) -> CommandResult:
    """Run a command and capture its output."""

    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=False,
    )
    result = CommandResult(
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {shlex.join(cmd)}\n{result.stderr}"
        )
    return result


def run_streaming(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> int:
    """Run a command, streaming stdout/stderr to the parent process."""

    info(f"$ {shlex.join(cmd)}")
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        check=False,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"Command failed ({proc.returncode}): {shlex.join(cmd)}")
    return proc.returncode


# ---------------------------------------------------------------------------
# Repository preparation


def ensure_repo_checkout(project_dir: Path, repo_url: str, branch: str) -> Path:
    """Ensure a working OpenBiliClaw checkout exists at project_dir.

    Rules:
    * If project_dir already contains pyproject.toml + config.example.toml, assume it's already a checkout.
    * Otherwise, clone the repo into project_dir.
    * Refuses to clone into a non-empty directory that does not already look like OpenBiliClaw.
    """

    project_dir = project_dir.expanduser().resolve()
    if (project_dir / "pyproject.toml").exists() and (project_dir / "config.example.toml").exists():
        info(f"Using existing OpenBiliClaw checkout at {project_dir}")
        return project_dir

    project_dir.mkdir(parents=True, exist_ok=True)
    entries = [entry for entry in project_dir.iterdir() if entry.name != ".DS_Store"]
    if entries:
        raise RuntimeError(
            f"Target directory is not empty and does not look like OpenBiliClaw: {project_dir}"
        )

    git = which("git")
    if git is None:
        raise RuntimeError("git is required to clone OpenBiliClaw but was not found on PATH.")

    info(f"Cloning {repo_url} (branch {branch}) into {project_dir}")
    run_streaming([git, "clone", "--branch", branch, "--depth", "1", repo_url, str(project_dir)])
    return project_dir


# ---------------------------------------------------------------------------
# Config + secret handling


def ensure_config_toml(project_dir: Path) -> Path:
    """Ensure config.toml exists, creating it from the example when missing."""

    config_path = project_dir / "config.toml"
    example_path = project_dir / "config.example.toml"
    if not example_path.exists():
        raise RuntimeError(f"config.example.toml not found in {project_dir}")

    if not config_path.exists():
        info(f"Creating {config_path} from config.example.toml")
        config_path.write_text(example_path.read_text(encoding="utf-8"), encoding="utf-8")
    return config_path


def read_simple_toml(path: Path) -> dict[str, Any]:
    """Read a TOML file using the stdlib tomllib."""

    import tomllib

    with path.open("rb") as handle:
        return tomllib.load(handle)


def set_toml_string_value(content: str, section: str, key: str, value: str) -> str:
    """Rewrite ``key = "..."`` under ``[section]`` with the new value.

    This is a minimal line-based editor; it preserves the rest of the file as
    much as possible so operators can keep their own comments. It does not
    handle multi-line strings or inline tables, which is fine because the
    OpenBiliClaw config template uses only single-line string values for the
    fields we need to update.
    """

    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    new_line = f'{key} = "{escaped}"'
    section_header = f"[{section}]"

    lines = content.splitlines()
    in_section = False
    updated = False
    for index, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_section = stripped == section_header
            continue
        if not in_section:
            continue
        if stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        lhs = stripped.split("=", 1)[0].strip()
        if lhs == key:
            indent = raw_line[: len(raw_line) - len(raw_line.lstrip())]
            lines[index] = f"{indent}{new_line}"
            updated = True
            break

    if not updated:
        # Append the section if missing
        append_lines = []
        if not content.endswith("\n"):
            append_lines.append("")
        append_lines.append(section_header)
        append_lines.append(new_line)
        return content + "\n".join(append_lines) + "\n"

    trailing_newline = "\n" if content.endswith("\n") else ""
    return "\n".join(lines) + trailing_newline


def update_config_secret(config_path: Path, section: str, key: str, value: str) -> None:
    """Patch a single secret value inside config.toml."""

    original = config_path.read_text(encoding="utf-8")
    updated = set_toml_string_value(original, section, key, value)
    if updated != original:
        config_path.write_text(updated, encoding="utf-8")


def reuse_config_secrets(project_dir: Path, source_dir: Path) -> dict[str, Any]:
    """Copy API keys + Bilibili cookie from an existing OpenBiliClaw checkout."""

    source_dir = source_dir.expanduser().resolve()
    if not source_dir.exists():
        raise RuntimeError(f"--reuse-from path does not exist: {source_dir}")

    source_config = source_dir / "config.toml"
    summary: dict[str, Any] = {"reused": [], "skipped": [], "source": str(source_dir)}
    if not source_config.exists():
        summary["skipped"].append("config.toml missing in source")
    else:
        source_data = read_simple_toml(source_config)
        llm_section = source_data.get("llm", {})
        provider = llm_section.get("default_provider")
        if provider:
            update_config_secret(project_dir / "config.toml", "llm", "default_provider", provider)
            summary["reused"].append("llm.default_provider")

        for name in REMOTE_PROVIDERS:
            provider_cfg = llm_section.get(name, {})
            api_key = str(provider_cfg.get("api_key", "")).strip()
            if api_key:
                update_config_secret(project_dir / "config.toml", f"llm.{name}", "api_key", api_key)
                summary["reused"].append(f"llm.{name}.api_key")

        gemini_cfg = llm_section.get("gemini", {})
        gemini_model = str(gemini_cfg.get("model", "")).strip()
        if gemini_model:
            update_config_secret(project_dir / "config.toml", "llm.gemini", "model", gemini_model)
            summary["reused"].append("llm.gemini.model")

        bilibili_section = source_data.get("bilibili", {})
        cookie_value = str(bilibili_section.get("cookie", "")).strip()
        if cookie_value:
            update_config_secret(project_dir / "config.toml", "bilibili", "cookie", cookie_value)
            summary["reused"].append("bilibili.cookie")

    source_cookie_file = source_dir / "data" / "bilibili_cookie.json"
    if source_cookie_file.exists():
        data_dir = project_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        target_cookie = data_dir / "bilibili_cookie.json"
        target_cookie.write_text(source_cookie_file.read_text(encoding="utf-8"), encoding="utf-8")
        summary["reused"].append("data/bilibili_cookie.json")
    else:
        summary["skipped"].append("data/bilibili_cookie.json missing in source")

    return summary


def persist_cookie_file(project_dir: Path, cookie: str) -> None:
    """Persist the cookie string in the on-disk Bilibili cookie file."""

    data_dir = project_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    cookie_path = data_dir / "bilibili_cookie.json"
    cookie_path.write_text(json.dumps({"cookie": cookie}, ensure_ascii=False), encoding="utf-8")


def apply_provider_override(project_dir: Path, provider: str) -> None:
    update_config_secret(project_dir / "config.toml", "llm", "default_provider", provider)


def apply_llm_api_key(project_dir: Path, provider: str, api_key: str) -> None:
    update_config_secret(project_dir / "config.toml", f"llm.{provider}", "api_key", api_key)


def detect_missing_secrets(project_dir: Path) -> dict[str, Any]:
    """Return a structured summary of missing secrets in config.toml."""

    config_path = project_dir / "config.toml"
    data = read_simple_toml(config_path)
    llm_section = data.get("llm", {})
    provider = str(llm_section.get("default_provider", "") or "").strip() or "openai"

    provider_cfg = llm_section.get(provider, {})
    api_key = str(provider_cfg.get("api_key", "") or "").strip()
    bilibili_section = data.get("bilibili", {})
    cookie_inline = str(bilibili_section.get("cookie", "") or "").strip()
    cookie_file = project_dir / "data" / "bilibili_cookie.json"
    cookie_on_disk = False
    if cookie_file.exists():
        try:
            cookie_data = json.loads(cookie_file.read_text(encoding="utf-8"))
            cookie_on_disk = bool(str(cookie_data.get("cookie", "")).strip())
        except json.JSONDecodeError:
            cookie_on_disk = False

    missing: list[str] = []
    if provider in REMOTE_PROVIDERS and not api_key:
        missing.append(f"llm.{provider}.api_key")
    if not (cookie_inline or cookie_on_disk):
        missing.append("bilibili.cookie")

    return {
        "provider": provider,
        "missing": missing,
        "has_cookie_inline": bool(cookie_inline),
        "has_cookie_file": cookie_on_disk,
    }


# ---------------------------------------------------------------------------
# Local deployment


def local_install(project_dir: Path, install_cmd: str | None, python_override: str | None) -> None:
    """Install python dependencies using uv (preferred) or pip."""

    if install_cmd:
        run_streaming(shlex.split(install_cmd), cwd=project_dir)
        return

    if detect_uv():
        run_streaming(["uv", "sync"], cwd=project_dir)
        return

    venv_python = python_override or sys.executable
    venv_dir = project_dir / ".venv"
    if not venv_dir.exists():
        run_streaming([venv_python, "-m", "venv", str(venv_dir)])
    pip = venv_dir / ("Scripts/pip.exe" if os.name == "nt" else "bin/pip")
    run_streaming([str(pip), "install", "-e", ".[dev]"], cwd=project_dir)


def local_serve_command(project_dir: Path, host: str, port: int) -> list[str]:
    """Return the command used to start the API server in local mode."""

    if detect_uv():
        return ["uv", "run", "openbiliclaw", "serve-api", "--host", host, "--port", str(port)]

    venv_bin = project_dir / (".venv/Scripts" if os.name == "nt" else ".venv/bin")
    openbiliclaw = venv_bin / "openbiliclaw"
    if openbiliclaw.exists():
        return [str(openbiliclaw), "serve-api", "--host", host, "--port", str(port)]

    python = venv_bin / ("python.exe" if os.name == "nt" else "python")
    return [str(python), "-m", "openbiliclaw.cli", "serve-api", "--host", host, "--port", str(port)]


def start_local_backend(project_dir: Path, host: str, port: int) -> subprocess.Popen[bytes]:
    """Start the local FastAPI backend as a detached subprocess."""

    cmd = local_serve_command(project_dir, host, port)
    log_dir = project_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = (log_dir / "agent-bootstrap.log").open("ab")
    info(f"Starting local backend: {shlex.join(cmd)} (logs -> {log_dir / 'agent-bootstrap.log'})")
    return subprocess.Popen(
        cmd,
        cwd=str(project_dir),
        stdout=log_file,
        stderr=log_file,
        start_new_session=True,
    )


# ---------------------------------------------------------------------------
# Docker deployment


def docker_compose_up(project_dir: Path) -> None:
    docker = which("docker")
    if docker is None:
        raise RuntimeError("docker is not available on PATH")
    run_streaming([docker, "compose", "up", "-d", "--build"], cwd=project_dir)


# ---------------------------------------------------------------------------
# Health check


def wait_for_health(host: str, port: int, timeout: float = HEALTH_TIMEOUT_SECONDS) -> bool:
    """Poll /api/health until it returns 200 or timeout expires."""

    url = f"http://{host}:{port}{DEFAULT_HEALTH_PATH}"
    deadline = time.monotonic() + timeout
    last_error: str | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=HEALTH_POLL_INTERVAL) as response:  # noqa: S310
                if 200 <= response.status < 300:
                    return True
                last_error = f"status={response.status}"
        except urllib.error.URLError as exc:
            last_error = str(exc)
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(HEALTH_POLL_INTERVAL)
    info(f"health check timed out: {last_error}")
    return False


# ---------------------------------------------------------------------------
# Orchestration


def run(args: argparse.Namespace) -> int:
    project_dir = Path(args.project_dir)
    try:
        project_dir = ensure_repo_checkout(project_dir, args.repo_url, args.branch)
    except RuntimeError as exc:
        emit(BootstrapResult("error", str(exc), {"step": "clone"}))
        return 2

    emit(BootstrapResult("ok", "repo_ready", {"project_dir": str(project_dir)}))

    try:
        ensure_config_toml(project_dir)
    except RuntimeError as exc:
        emit(BootstrapResult("error", str(exc), {"step": "config"}))
        return 2

    if args.reuse_from:
        try:
            reuse_summary = reuse_config_secrets(project_dir, Path(args.reuse_from))
        except RuntimeError as exc:
            emit(BootstrapResult("error", str(exc), {"step": "reuse"}))
            return 2
        emit(BootstrapResult("ok", "secrets_reused", reuse_summary))

    if args.provider:
        apply_provider_override(project_dir, args.provider)
        emit(BootstrapResult("ok", "provider_set", {"provider": args.provider}))

    current_provider = detect_missing_secrets(project_dir)["provider"]
    if args.llm_api_key:
        provider = args.provider or current_provider
        apply_llm_api_key(project_dir, provider, args.llm_api_key)
        emit(BootstrapResult("ok", "api_key_set", {"provider": provider}))

    if args.bilibili_cookie:
        update_config_secret(
            project_dir / "config.toml", "bilibili", "cookie", args.bilibili_cookie
        )
        persist_cookie_file(project_dir, args.bilibili_cookie)
        emit(BootstrapResult("ok", "cookie_set", {}))

    status = detect_missing_secrets(project_dir)
    emit(BootstrapResult("ok", "config_summary", status))

    mode = args.mode
    if mode == "auto":
        mode = "docker" if detect_docker() else "local"
    emit(BootstrapResult("ok", "mode_selected", {"mode": mode}))

    if not args.skip_install and mode == "local":
        try:
            local_install(project_dir, args.install_cmd, args.python)
        except RuntimeError as exc:
            emit(BootstrapResult("error", str(exc), {"step": "install"}))
            return 3
        emit(BootstrapResult("ok", "dependencies_installed", {}))

    if args.skip_start:
        remaining = detect_missing_secrets(project_dir)
        skipped_label = "complete" if not remaining["missing"] else "needs_secrets"
        emit(BootstrapResult(skipped_label, "skipped_start", remaining))
        return 0

    if mode == "docker":
        try:
            docker_compose_up(project_dir)
        except RuntimeError as exc:
            emit(BootstrapResult("error", str(exc), {"step": "docker_up"}))
            return 4
        emit(BootstrapResult("ok", "docker_started", {}))
    else:
        start_local_backend(project_dir, args.host, args.port)
        emit(BootstrapResult("ok", "local_started", {"host": args.host, "port": args.port}))

    if args.skip_health_check:
        final_status = detect_missing_secrets(project_dir)
        final_label = "complete" if not final_status["missing"] else "needs_secrets"
        emit(BootstrapResult(final_label, "health_check_skipped", final_status))
        return 0

    healthy = wait_for_health(args.host, args.port)
    final_status = detect_missing_secrets(project_dir)
    if healthy:
        label = "complete" if not final_status["missing"] else "running_with_missing_secrets"
        emit(
            BootstrapResult(
                label,
                "backend_healthy",
                {
                    "health_url": f"http://{args.host}:{args.port}{DEFAULT_HEALTH_PATH}",
                    **final_status,
                },
            )
        )

        # Auto-run init when all credentials are present and --skip-init is not set
        if not final_status["missing"] and not args.skip_init:
            info("All credentials present — running 'openbiliclaw init' to reach usable state...")
            try:
                init_cmd: list[str] = []
                if detect_uv():
                    init_cmd = ["uv", "run", "openbiliclaw", "init"]
                else:
                    venv_python = project_dir / ".venv" / "bin" / "python"
                    if venv_python.exists():
                        init_cmd = [str(venv_python), "-m", "openbiliclaw.cli", "init"]
                    else:
                        init_cmd = ["python3", "-m", "openbiliclaw.cli", "init"]
                run_streaming(init_cmd, cwd=project_dir, check=False)
                emit(BootstrapResult("ok", "init_complete", {}))
            except Exception as exc:
                emit(BootstrapResult("warning", "init_failed", {"error": str(exc)}))
                info(f"Init failed ({exc}), but the backend is running. You can run 'openbiliclaw init' manually later.")

        return 0

    emit(
        BootstrapResult(
            "error",
            "health_check_failed",
            {
                "health_url": f"http://{args.host}:{args.port}{DEFAULT_HEALTH_PATH}",
                **final_status,
            },
        )
    )
    return 5


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    try:
        return run(args)
    except KeyboardInterrupt:
        emit(BootstrapResult("error", "interrupted", {}))
        return 130
    except Exception as exc:  # noqa: BLE001
        emit(BootstrapResult("error", f"unexpected: {exc}", {}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
