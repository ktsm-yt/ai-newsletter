"""ai_newsletter.sources.github_trending の integration test (respx で GitHub API mock)。"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from ai_newsletter.sources.github_trending import (
    GITHUB_API_BASE,
    GitHubError,
    fetch,
)

SEARCH_URL = f"{GITHUB_API_BASE}/search/repositories"


def _repo(full_name: str, stars: int, **extra) -> dict:
    name = full_name.split("/", 1)[1]
    return {
        "full_name": full_name,
        "name": name,
        "html_url": f"https://github.com/{full_name}",
        "description": extra.get("description", f"desc of {name}"),
        "stargazers_count": stars,
        "language": extra.get("language", "Python"),
        "topics": extra.get("topics", []),
    }


@respx.mock
def test_fetch_baseline_writes_snapshot_and_returns_empty(tmp_path: Path) -> None:
    snapshot = tmp_path / "stars.json"
    respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(
            200, json={"items": [_repo("a/foo", 100), _repo("b/bar", 50)]}
        )
    )

    items = fetch(
        snapshot_path=snapshot,
        topics=["llm"],
        token="ghp-test",
    )

    assert items == []
    assert json.loads(snapshot.read_text()) == {"a/foo": 100, "b/bar": 50}


@respx.mock
def test_fetch_returns_only_positive_delta(tmp_path: Path) -> None:
    snapshot = tmp_path / "stars.json"
    snapshot.write_text(json.dumps({"a/foo": 100, "b/bar": 50, "c/baz": 200}))

    respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    _repo("a/foo", 130),  # +30
                    _repo("b/bar", 50),  # 0 → excluded
                    _repo("c/baz", 190),  # -10 → excluded
                ]
            },
        )
    )

    items = fetch(snapshot_path=snapshot, topics=["llm"], token="ghp-test")

    assert [it.id for it in items] == ["a/foo"]
    assert items[0].score_raw == 30.0
    assert items[0].extra["stars_now"] == 130
    assert items[0].extra["stars_delta"] == 30
    assert items[0].url == "https://github.com/a/foo"
    # snapshot は最新値で上書き
    assert json.loads(snapshot.read_text()) == {"a/foo": 130, "b/bar": 50, "c/baz": 190}


@respx.mock
def test_fetch_dedupes_across_topics(tmp_path: Path) -> None:
    snapshot = tmp_path / "stars.json"
    snapshot.write_text(json.dumps({"a/foo": 100, "b/bar": 50}))

    # Both topic queries return overlapping repos
    route = respx.get(SEARCH_URL).mock(
        side_effect=[
            httpx.Response(200, json={"items": [_repo("a/foo", 110), _repo("b/bar", 60)]}),
            httpx.Response(200, json={"items": [_repo("a/foo", 110), _repo("c/baz", 70)]}),
        ]
    )

    items = fetch(
        snapshot_path=snapshot,
        topics=["llm", "rag"],
        token="ghp-test",
    )

    assert route.call_count == 2
    ids = sorted(it.id for it in items)
    # a/foo: +10, b/bar: +10 (c/baz is new → delta 0 by design)
    assert ids == ["a/foo", "b/bar"]


@respx.mock
def test_fetch_new_repos_have_zero_delta_until_next_run(tmp_path: Path) -> None:
    """前回 snapshot に居ない repo は差分 0 扱い、次回 cron 以降に評価される。"""
    snapshot = tmp_path / "stars.json"
    snapshot.write_text(json.dumps({"a/foo": 100}))

    respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(
            200, json={"items": [_repo("a/foo", 105), _repo("new/repo", 999)]}
        )
    )

    items = fetch(snapshot_path=snapshot, topics=["llm"], token="ghp-test")

    assert [it.id for it in items] == ["a/foo"]
    # snapshot には新規 repo も書き込まれる (次回からの evaluation 対象)
    assert json.loads(snapshot.read_text()) == {"a/foo": 105, "new/repo": 999}


@respx.mock
def test_fetch_sends_auth_and_query(tmp_path: Path) -> None:
    snapshot = tmp_path / "stars.json"
    snapshot.write_text(json.dumps({"placeholder": 0}))  # avoid baseline path

    route = respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(200, json={"items": []})
    )

    fetch(
        snapshot_path=snapshot,
        topics=["ai-agent"],
        days=30,
        per_page=10,
        token="ghp-secret",
    )

    sent = route.calls.last.request
    assert sent.headers["authorization"] == "Bearer ghp-secret"
    assert sent.headers["accept"] == "application/vnd.github+json"
    # q=topic:ai-agent created:>YYYY-MM-DD / sort=stars / per_page=10
    assert "topic%3Aai-agent" in str(sent.url) or "topic:ai-agent" in str(sent.url)
    assert "sort=stars" in str(sent.url)
    assert "per_page=10" in str(sent.url)


def test_fetch_raises_when_token_is_empty(tmp_path: Path) -> None:
    with pytest.raises(GitHubError, match="GH_TOKEN is empty"):
        fetch(snapshot_path=tmp_path / "x.json", token="")


@respx.mock
def test_fetch_creates_parent_dir_for_snapshot(tmp_path: Path) -> None:
    snapshot = tmp_path / "nested" / "deep" / "stars.json"
    respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(200, json={"items": [_repo("a/foo", 1)]})
    )

    fetch(snapshot_path=snapshot, topics=["llm"], token="ghp-test")

    assert snapshot.exists()
    assert json.loads(snapshot.read_text()) == {"a/foo": 1}
