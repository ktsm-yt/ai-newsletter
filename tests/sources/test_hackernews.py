"""ai_newsletter.sources.hackernews の integration test (respx で firebaseio mock)。"""
from __future__ import annotations

import httpx
import respx

from ai_newsletter.sources.hackernews import HN_API_BASE, _is_ai_related, fetch


def test_is_ai_related_matches_keywords() -> None:
    assert _is_ai_related("Show HN: a new LLM agent framework")
    assert _is_ai_related("Claude 4.7 is out")
    assert _is_ai_related("OpenAI launches something")
    # word boundary: "main" should not match "ai"
    assert not _is_ai_related("How to write maintainable code")
    # case-insensitive
    assert _is_ai_related("ANTHROPIC announces ...")
    # fine-tuning (hyphenated)
    assert _is_ai_related("Fine-tuning small models")


@respx.mock
def test_fetch_filters_ai_related_titles_only() -> None:
    respx.get(f"{HN_API_BASE}/topstories.json").mock(
        return_value=httpx.Response(200, json=[1, 2, 3])
    )
    respx.get(f"{HN_API_BASE}/item/1.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 1,
                "title": "Show HN: GPT-powered code reviewer",
                "url": "https://example.com/1",
                "score": 250,
                "time": 1700000000,
                "by": "alice",
                "descendants": 42,
            },
        )
    )
    respx.get(f"{HN_API_BASE}/item/2.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 2,
                "title": "Why I switched databases",
                "url": "https://example.com/2",
                "score": 180,
                "time": 1700000100,
            },
        )
    )
    respx.get(f"{HN_API_BASE}/item/3.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 3,
                "title": "Claude beats benchmark X",
                "url": "https://example.com/3",
                "score": 320,
                "time": 1700000200,
            },
        )
    )

    items = fetch(top_n=3)

    assert [it.id for it in items] == ["1", "3"]
    assert items[0].source == "hackernews"
    assert items[0].title.startswith("Show HN: GPT")
    assert items[0].url == "https://example.com/1"
    assert items[0].score_raw == 250.0
    assert items[0].extra == {"by": "alice", "descendants": 42}
    assert items[0].published_at is not None


@respx.mock
def test_fetch_respects_top_n() -> None:
    respx.get(f"{HN_API_BASE}/topstories.json").mock(
        return_value=httpx.Response(200, json=[10, 20, 30, 40, 50])
    )
    # Only the first 2 should be fetched
    respx.get(f"{HN_API_BASE}/item/10.json").mock(
        return_value=httpx.Response(
            200, json={"id": 10, "title": "LLM news", "url": "https://e.com/10", "score": 1, "time": 1}
        )
    )
    respx.get(f"{HN_API_BASE}/item/20.json").mock(
        return_value=httpx.Response(
            200, json={"id": 20, "title": "RAG news", "url": "https://e.com/20", "score": 2, "time": 2}
        )
    )

    items = fetch(top_n=2)

    assert [it.id for it in items] == ["10", "20"]


@respx.mock
def test_fetch_falls_back_to_hn_url_when_url_missing() -> None:
    """Ask HN / Tell HN は url フィールドが無い (本体テキストのみ)。HN 内部 URL に fallback する。"""
    respx.get(f"{HN_API_BASE}/topstories.json").mock(
        return_value=httpx.Response(200, json=[99])
    )
    respx.get(f"{HN_API_BASE}/item/99.json").mock(
        return_value=httpx.Response(
            200, json={"id": 99, "title": "Ask HN: best LLM for ...", "score": 5, "time": 1}
        )
    )

    items = fetch(top_n=1)

    assert len(items) == 1
    assert items[0].url == "https://news.ycombinator.com/item?id=99"


@respx.mock
def test_fetch_skips_deleted_items() -> None:
    respx.get(f"{HN_API_BASE}/topstories.json").mock(
        return_value=httpx.Response(200, json=[1, 2])
    )
    # HN API は deleted / dead を JSON null で返す
    respx.get(f"{HN_API_BASE}/item/1.json").mock(
        return_value=httpx.Response(200, content=b"null", headers={"content-type": "application/json"})
    )
    respx.get(f"{HN_API_BASE}/item/2.json").mock(
        return_value=httpx.Response(
            200, json={"id": 2, "title": "AI agent news", "url": "https://e.com/2", "score": 9, "time": 1}
        )
    )

    items = fetch(top_n=2)

    assert [it.id for it in items] == ["2"]
