"""Tests for WebSourceAdapter / XiaohongshuAdapter with pluggable browser backend."""

from __future__ import annotations

from typing import Any

import pytest

from openbiliclaw.sources import web_adapter as web_adapter_module
from openbiliclaw.sources.protocol import SourceRecipe
from openbiliclaw.sources.web_adapter import WebSourceAdapter, XiaohongshuAdapter


class _RecordingBrowser:
    """Stand-in for BrowserManager that records how it was built and called."""

    last_init: dict[str, Any] = {}

    def __init__(self, **kwargs: Any) -> None:
        _RecordingBrowser.last_init = dict(kwargs)
        self._closed = False

    @property
    def is_available(self) -> bool:
        return True

    async def get_page_text(self, url: str) -> str:
        _RecordingBrowser.last_init["visited_url"] = url
        return "fake-xhs-page"

    async def close(self) -> None:
        self._closed = True


class TestWebSourceAdapterBrowserWiring:
    """WebSourceAdapter must forward cdp_url to BrowserManager."""

    @pytest.mark.asyncio
    async def test_forwards_cdp_url_to_browser_manager(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(web_adapter_module, "BrowserManager", _RecordingBrowser)

        async def fake_extract(text: str, **kwargs: Any) -> list[Any]:
            return []

        monkeypatch.setattr(web_adapter_module, "extract_content_from_page", fake_extract)

        adapter = XiaohongshuAdapter(
            llm_service=None,
            browser_cdp_url="http://127.0.0.1:9222",
        )

        recipe = SourceRecipe(
            id="r1",
            source_type="xiaohongshu",
            name="小红书",
            strategy="search",
            config={"query": "机械键盘"},
        )

        await adapter.fetch(recipe, profile=None, limit=5)  # type: ignore[arg-type]

        assert _RecordingBrowser.last_init["cdp_url"] == "http://127.0.0.1:9222"
        assert (
            _RecordingBrowser.last_init["visited_url"]
            == "https://www.xiaohongshu.com/search_result?keyword=机械键盘"
        )

    @pytest.mark.asyncio
    async def test_empty_cdp_url_passes_empty_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(web_adapter_module, "BrowserManager", _RecordingBrowser)

        async def fake_extract(text: str, **kwargs: Any) -> list[Any]:
            return []

        monkeypatch.setattr(web_adapter_module, "extract_content_from_page", fake_extract)

        adapter = WebSourceAdapter(llm_service=None)
        recipe = SourceRecipe(
            id="r2",
            source_type="web",
            name="generic",
            strategy="web_extract",
            config={"url": "https://example.com"},
        )

        await adapter.fetch(recipe, profile=None, limit=5)  # type: ignore[arg-type]

        assert _RecordingBrowser.last_init["cdp_url"] == ""
