from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from openbiliclaw.bilibili.browser import BilibiliBrowser, BrowserCommandError

if TYPE_CHECKING:
    from pathlib import Path


class _FakeProcess:
    def __init__(
        self,
        returncode: int = 0,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        self.returncode = returncode
        self._stdout = stdout.encode("utf-8")
        self._stderr = stderr.encode("utf-8")

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr


def test_is_available_accepts_explicit_executable_path(tmp_path: Path) -> None:
    executable = tmp_path / "agent-browser"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)

    browser = BilibiliBrowser(executable=str(executable))

    assert browser.is_available is True


def test_install_hint_mentions_official_setup() -> None:
    hint = BilibiliBrowser.get_install_hint()

    assert "npm install -g agent-browser" in hint
    assert "agent-browser install" in hint


@pytest.mark.asyncio
async def test_navigate_uses_official_open_command(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, ...]] = []

    async def fake_exec(*cmd: str, **kwargs: object) -> _FakeProcess:
        calls.append(tuple(cmd))
        return _FakeProcess(stdout='{"success": true}')

    monkeypatch.setattr(
        "openbiliclaw.bilibili.browser.asyncio.create_subprocess_exec",
        fake_exec,
    )

    browser = BilibiliBrowser(executable="agent-browser", headed=True)

    await browser.navigate("https://www.bilibili.com")

    assert calls == [
        ("agent-browser", "open", "https://www.bilibili.com", "--headed")
    ]


@pytest.mark.asyncio
async def test_get_page_content_uses_open_then_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, ...]] = []
    snapshot_payload = json.dumps(
        {
            "success": True,
            "data": {
                "snapshot": '- heading "Example Domain" [ref=e1]',
            },
        }
    )

    async def fake_exec(*cmd: str, **kwargs: object) -> _FakeProcess:
        calls.append(tuple(cmd))
        if cmd[1] == "open":
            return _FakeProcess(stdout='{"success": true}')
        return _FakeProcess(stdout=snapshot_payload)

    monkeypatch.setattr(
        "openbiliclaw.bilibili.browser.asyncio.create_subprocess_exec",
        fake_exec,
    )

    browser = BilibiliBrowser(executable="agent-browser")

    content = await browser.get_page_content("https://example.com")

    assert content == '- heading "Example Domain" [ref=e1]'
    assert calls == [
        ("agent-browser", "open", "https://example.com"),
        ("agent-browser", "snapshot", "-i", "--json"),
    ]


@pytest.mark.asyncio
async def test_navigate_raises_clear_error_on_cli_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_exec(*cmd: str, **kwargs: object) -> _FakeProcess:
        return _FakeProcess(returncode=1, stderr="browser failed")

    monkeypatch.setattr(
        "openbiliclaw.bilibili.browser.asyncio.create_subprocess_exec",
        fake_exec,
    )

    browser = BilibiliBrowser(executable="agent-browser")

    with pytest.raises(BrowserCommandError, match="browser failed"):
        await browser.navigate("https://example.com")
