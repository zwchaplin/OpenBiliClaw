"""Tests for the xhs observed-URL ingestion endpoint.

POST /api/sources/xhs/observed-urls accepts a batch of xhs note URLs
that the extension passively collected and schedules enrichment via the
XiaohongshuAdapter.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Build a minimal TestClient with a real database but mocked adapter."""
    from types import SimpleNamespace

    from openbiliclaw.storage.database import Database

    db = Database(tmp_path / "test.db")
    db.initialize()

    fake_config = SimpleNamespace(
        data_path=tmp_path,
        bilibili=SimpleNamespace(cookie="", browser_executable="", browser_headed=False),
        sources=SimpleNamespace(
            browser_cdp_url="",
            browser_headed=False,
            xiaohongshu=SimpleNamespace(
                daily_search_budget=20,
                daily_creator_budget=10,
                task_interval_seconds=45,
            ),
        ),
        scheduler=SimpleNamespace(pool_target_count=300, account_sync_interval_hours=24),
    )

    monkeypatch.setattr("openbiliclaw.config.load_config", lambda: fake_config)
    monkeypatch.setattr("openbiliclaw.llm.build_llm_registry", lambda config: "registry")
    monkeypatch.setattr("openbiliclaw.bilibili.auth.resolve_runtime_cookie", lambda **_: "")

    from openbiliclaw.api.app import create_app

    app = create_app(database=db)
    return TestClient(app)


class TestXhsObservedUrls:
    def test_ingest_valid_urls(self, app_client: TestClient) -> None:
        response = app_client.post(
            "/api/sources/xhs/observed-urls",
            json={
                "urls": [
                    "https://www.xiaohongshu.com/explore/abc123?xsec_token=ZZZ",
                    "https://www.xiaohongshu.com/explore/def456?xsec_token=YYY",
                ],
                "page_type": "search",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["accepted"] == 2

    def test_rejects_empty_url_list(self, app_client: TestClient) -> None:
        response = app_client.post(
            "/api/sources/xhs/observed-urls",
            json={"urls": [], "page_type": "search"},
        )
        assert response.status_code == 422

    def test_rejects_too_many_urls(self, app_client: TestClient) -> None:
        urls = [f"https://www.xiaohongshu.com/explore/{i:024x}" for i in range(60)]
        response = app_client.post(
            "/api/sources/xhs/observed-urls",
            json={"urls": urls, "page_type": "search"},
        )
        assert response.status_code == 422

    def test_filters_invalid_url_shapes(self, app_client: TestClient) -> None:
        response = app_client.post(
            "/api/sources/xhs/observed-urls",
            json={
                "urls": [
                    "https://www.xiaohongshu.com/explore/abc123",
                    "https://example.com/bad",
                    "not-even-a-url",
                ],
                "page_type": "explore",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["accepted"] == 1  # only the valid xhs URL

    def test_stores_observations_in_db(
        self, app_client: TestClient, tmp_path: Path
    ) -> None:
        from openbiliclaw.storage.database import Database

        db = Database(tmp_path / "test.db")
        db.initialize()

        app_client.post(
            "/api/sources/xhs/observed-urls",
            json={
                "urls": ["https://www.xiaohongshu.com/explore/abc123"],
                "page_type": "search",
            },
        )

        rows = db.conn.execute("SELECT * FROM xhs_observed_urls").fetchall()
        assert len(rows) >= 1
        assert rows[0]["url"] == "https://www.xiaohongshu.com/explore/abc123"
        assert rows[0]["page_type"] == "search"

    def test_notes_cache_populates_source_and_platform(
        self, app_client: TestClient, tmp_path: Path
    ) -> None:
        """Regression: xhs note caches must tag `source` (strategy label)
        AND `source_platform='xiaohongshu'`.

        An earlier bug passed the wrong kwarg (`source_strategy=` instead of
        `source=`) to `cache_content`, silently dropping the label. Paired
        with the engine re-cache path that omitted `source_platform`, this
        let xhs rows end up with `source=''` and `source_platform='bilibili'`
        after the first rescore pass.
        """
        from openbiliclaw.storage.database import Database

        db = Database(tmp_path / "test.db")
        db.initialize()

        response = app_client.post(
            "/api/sources/xhs/observed-urls",
            json={
                "urls": ["https://www.xiaohongshu.com/explore/note-xyz-001"],
                "notes": [
                    {
                        "url": "https://www.xiaohongshu.com/explore/note-xyz-001",
                        "title": "手冲咖啡入门",
                        "author": "豆子老师",
                        "cover_url": "https://example.com/cover.jpg",
                    }
                ],
                "page_type": "search",
            },
        )
        assert response.status_code == 200

        row = db.conn.execute(
            "SELECT source, source_platform, content_id, content_url, title, up_name "
            "FROM content_cache WHERE bvid=?",
            ("note-xyz-001",),
        ).fetchone()
        assert row is not None, "xhs note was not cached"
        assert row["source"] == "xhs-extension-search"
        assert row["source_platform"] == "xiaohongshu"
        assert row["content_id"] == "note-xyz-001"
        assert row["content_url"].endswith("/note-xyz-001")
        assert row["title"] == "手冲咖啡入门"
        assert row["up_name"] == "豆子老师"

    def test_tokenized_url_upgrades_existing_bare_cache_row(
        self, app_client: TestClient, tmp_path: Path
    ) -> None:
        """Regression: when the extension reports a note URL *with*
        ``xsec_token`` after the same note was already cached from a
        search page *without* the token, the cache row must be upgraded.

        Without this backfill, users click recommendation cards and get
        dead-ended at xhs's login wall because the stored URL is missing
        the access token xhs requires for outbound sharing.
        """
        from openbiliclaw.storage.database import Database

        db = Database(tmp_path / "test.db")
        db.initialize()

        note_id = "note-upgrade-001"
        bare_url = f"https://www.xiaohongshu.com/explore/{note_id}"
        tokenized = f"{bare_url}?xsec_token=ABCXYZ123=&xsec_source=pc_feed"

        # First pass: search page sees the bare URL only
        resp1 = app_client.post(
            "/api/sources/xhs/observed-urls",
            json={
                "urls": [bare_url],
                "notes": [
                    {"url": bare_url, "title": "t", "author": "a", "cover_url": ""}
                ],
                "page_type": "search",
            },
        )
        assert resp1.status_code == 200

        row = db.conn.execute(
            "SELECT content_url FROM content_cache WHERE bvid=?", (note_id,)
        ).fetchone()
        assert row["content_url"] == bare_url  # bare URL cached

        # Second pass: explore feed observes the same note WITH a token.
        # No new `notes` payload — just the bare URL list carrying the token.
        resp2 = app_client.post(
            "/api/sources/xhs/observed-urls",
            json={"urls": [tokenized], "page_type": "explore"},
        )
        assert resp2.status_code == 200

        row = db.conn.execute(
            "SELECT content_url FROM content_cache WHERE bvid=?", (note_id,)
        ).fetchone()
        assert "xsec_token=ABCXYZ123" in row["content_url"], (
            f"token backfill failed: still cached as {row['content_url']!r}"
        )

    def test_cache_prefers_tokenized_url_from_prior_observation(
        self, app_client: TestClient, tmp_path: Path
    ) -> None:
        """Regression: if we previously observed a tokenized URL for a
        note (e.g. from the explore feed), and a later `notes` payload
        arrives with a bare URL for the same note (from search results),
        the cache must keep/write the tokenized URL rather than overwriting
        with the bare one.
        """
        from openbiliclaw.storage.database import Database

        db = Database(tmp_path / "test.db")
        db.initialize()

        note_id = "note-prefer-002"
        bare_url = f"https://www.xiaohongshu.com/explore/{note_id}"
        tokenized = f"{bare_url}?xsec_token=PRIOR456=&xsec_source="

        # Prime: explore feed observed a tokenized URL first (no notes yet).
        app_client.post(
            "/api/sources/xhs/observed-urls",
            json={"urls": [tokenized], "page_type": "explore"},
        )

        # Now search page reports `notes` with a bare URL for the same note.
        resp = app_client.post(
            "/api/sources/xhs/observed-urls",
            json={
                "urls": [bare_url],
                "notes": [
                    {"url": bare_url, "title": "t2", "author": "a2", "cover_url": ""}
                ],
                "page_type": "search",
            },
        )
        assert resp.status_code == 200

        row = db.conn.execute(
            "SELECT content_url FROM content_cache WHERE bvid=?", (note_id,)
        ).fetchone()
        assert "xsec_token=PRIOR456" in row["content_url"], (
            f"cache overwrote tokenized URL with bare: {row['content_url']!r}"
        )


class TestXhsTokens:
    """Regression tests for POST /api/sources/xhs/tokens.

    The MAIN-world sniffer discovers ``(note_id, xsec_token)`` pairs from
    xhs's own API responses and POSTs them here so cached bare URLs can
    be upgraded to tokenized URLs that xhs will accept for outbound
    sharing.
    """

    def test_backfills_token_onto_existing_bare_cache(
        self, app_client: TestClient, tmp_path: Path
    ) -> None:
        from openbiliclaw.storage.database import Database

        db = Database(tmp_path / "test.db")
        db.initialize()

        note_id = "note-sniffer-001"
        bare_url = f"https://www.xiaohongshu.com/explore/{note_id}"

        # Seed a bare-URL cache row as the search-page path would.
        app_client.post(
            "/api/sources/xhs/observed-urls",
            json={
                "urls": [bare_url],
                "notes": [
                    {"url": bare_url, "title": "t", "author": "a", "cover_url": ""}
                ],
                "page_type": "search",
            },
        )

        resp = app_client.post(
            "/api/sources/xhs/tokens",
            json={"pairs": [{"note_id": note_id, "xsec_token": "SNIFFED_TOKEN_42"}]},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert resp.json()["upgraded"] >= 1

        row = db.conn.execute(
            "SELECT content_url FROM content_cache WHERE bvid=?", (note_id,)
        ).fetchone()
        assert "xsec_token=SNIFFED_TOKEN_42" in row["content_url"], (
            f"token backfill failed: {row['content_url']!r}"
        )

    def test_empty_pairs_is_noop(self, app_client: TestClient) -> None:
        resp = app_client.post("/api/sources/xhs/tokens", json={"pairs": []})
        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "upgraded": 0}

    def test_skips_malformed_pairs(
        self, app_client: TestClient, tmp_path: Path
    ) -> None:
        resp = app_client.post(
            "/api/sources/xhs/tokens",
            json={
                "pairs": [
                    {"note_id": "", "xsec_token": "tok"},
                    {"note_id": "note-x", "xsec_token": ""},
                    "not-a-dict",
                    {"note_id": "note-y"},
                ]
            },
        )
        assert resp.status_code == 200
        assert resp.json()["upgraded"] == 0
