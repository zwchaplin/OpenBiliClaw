"""Generic web source adapter — fetches and extracts content from any web page.

Uses a browser backend (Playwright CDP or agent-browser) to load pages
and an LLM to extract structured content. Works for any platform that
doesn't have a dedicated API adapter.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from openbiliclaw.sources.browser import BrowserManager
from openbiliclaw.sources.llm_extractor import extract_content_from_page

if TYPE_CHECKING:
    from openbiliclaw.discovery.engine import DiscoveredContent
    from openbiliclaw.soul.profile import SoulProfile
    from openbiliclaw.sources.protocol import SourceRecipe

logger = logging.getLogger(__name__)


class WebSourceAdapter:
    """Generic web content adapter using browser + LLM extraction.

    Recipe config keys:
        url_template: URL pattern, may contain ``{query}`` placeholder.
        query: Search query (substituted into url_template).
        url: Direct URL to fetch (used when url_template is not set).
    """

    def __init__(
        self,
        *,
        llm_service: Any,
        browser_executable: str = "",
        browser_headed: bool = False,
        browser_cdp_url: str = "",
    ) -> None:
        self._llm_service = llm_service
        self._browser_executable = browser_executable
        self._browser_headed = browser_headed
        self._browser_cdp_url = browser_cdp_url

    @property
    def source_type(self) -> str:
        return "web"

    async def fetch(
        self,
        recipe: SourceRecipe,
        profile: SoulProfile,
        limit: int = 20,
    ) -> list[DiscoveredContent]:
        """Fetch content from a web page defined by the recipe."""
        url = self._build_url(recipe)
        if not url:
            logger.warning("WebSourceAdapter: no URL for recipe %s", recipe.id)
            return []

        browser = BrowserManager(
            executable=self._browser_executable,
            headed=self._browser_headed,
            cdp_url=self._browser_cdp_url,
        )

        if not browser.is_available:
            logger.warning(
                "WebSourceAdapter: agent-browser not available, skipping recipe %s",
                recipe.id,
            )
            return []

        try:
            page_text = await browser.get_page_text(url)
        except Exception:
            logger.exception("WebSourceAdapter: failed to fetch %s", url)
            return []
        finally:
            try:
                await browser.close()
            except Exception:
                pass

        items = await extract_content_from_page(
            page_text,
            source_platform=recipe.source_type,
            llm_service=self._llm_service,
            base_url=url,
        )

        # Apply recipe source_type and limit
        for item in items:
            if not item.source_platform:
                item.source_platform = recipe.source_type

        return items[:limit]

    @staticmethod
    def _build_url(recipe: SourceRecipe) -> str:
        """Build the target URL from recipe config."""
        config = recipe.config or {}
        url_template = config.get("url_template", "")
        query = config.get("query", "")
        url = config.get("url", "")

        if url_template and query:
            return url_template.replace("{query}", query)
        if url:
            return url
        if url_template:
            return url_template
        return ""


class XiaohongshuAdapter(WebSourceAdapter):
    """Xiaohongshu (小红书) adapter — extends WebSourceAdapter with platform defaults.

    Recipe config keys:
        query: Search query.
        url: Direct URL (overrides search).
    """

    _SEARCH_URL_TEMPLATE = "https://www.xiaohongshu.com/search_result?keyword={query}"

    @property
    def source_type(self) -> str:
        return "xiaohongshu"

    @staticmethod
    def _build_url(recipe: SourceRecipe) -> str:
        config = recipe.config or {}
        url = config.get("url", "")
        if url:
            return url
        query = config.get("query", "")
        if query:
            return XiaohongshuAdapter._SEARCH_URL_TEMPLATE.replace("{query}", query)
        return ""
