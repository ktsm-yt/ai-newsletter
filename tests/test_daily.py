"""scripts/daily.py の smoke test。

外部 I/O (Slack / Gemini / HN / GitHub / Reddit) は monkeypatch で fake に差し替える。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from ai_newsletter.models import RawItem

REPO_ROOT = Path(__file__).resolve().parent.parent
DAILY_PATH = REPO_ROOT / "scripts" / "daily.py"


def _load_daily() -> ModuleType:
    spec = importlib.util.spec_from_file_location("daily_under_test", DAILY_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _item(source: str, item_id: str, title: str, *, score: float = 100.0) -> RawItem:
    return RawItem(
        source=source,
        id=item_id,
        title=title,
        url=f"https://example.com/{source}/{item_id}",
        score_raw=score,
        extra={},
    )


def test_main_runs_full_pipeline_when_items_available(monkeypatch) -> None:
    daily = _load_daily()
    posted: list[list] = []

    monkeypatch.setattr(
        daily.hackernews,
        "fetch",
        lambda: [
            _item("hackernews", "1", "A new SDK release", score=1000),
            _item("hackernews", "2", "Tutorial: building agents", score=900),
            _item("hackernews", "3", "Acme launches AI platform", score=800),
        ],
    )
    monkeypatch.setattr(
        daily.github_trending,
        "fetch",
        lambda: [_item("github", "a/b", "agentic-toolkit", score=300)],
    )
    monkeypatch.setattr(
        daily.reddit,
        "fetch",
        lambda: [_item("reddit", "r1", "Best practice for agent design", score=200)],
    )

    def fake_summarize_all(items, **kwargs):
        return [
            (
                it,
                {
                    "summary_3lines": "x",
                    "why_notable": "x",
                    "dev_use_case": "x",
                    "trust": "中",
                    "reason": "x",
                    "priority": "中",
                },
            )
            for it in items
        ]

    monkeypatch.setattr(daily, "summarize_all", fake_summarize_all)

    def fake_post(pairs, **kwargs):
        posted.append(pairs)
        return 1

    monkeypatch.setattr(daily, "post_newsletter", fake_post)

    rc = daily.main()

    assert rc == 0
    assert len(posted) == 1
    assert len(posted[0]) >= 1  # 1 件以上配信されている


def test_main_skips_slack_when_no_candidates(monkeypatch, caplog) -> None:
    daily = _load_daily()
    posted: list = []

    monkeypatch.setattr(daily.hackernews, "fetch", lambda: [])
    monkeypatch.setattr(daily.github_trending, "fetch", lambda: [])
    monkeypatch.setattr(daily.reddit, "fetch", lambda: [])
    monkeypatch.setattr(
        daily, "post_newsletter", lambda pairs, **kw: posted.append(pairs) or 0
    )

    rc = daily.main()

    assert rc == 0
    assert posted == []


def test_main_continues_when_one_source_raises(monkeypatch) -> None:
    daily = _load_daily()
    posted: list[list] = []

    def boom():
        raise RuntimeError("github API down")

    monkeypatch.setattr(
        daily.hackernews,
        "fetch",
        lambda: [
            _item("hackernews", str(i), f"A new SDK release v{i}", score=1000 - i * 10)
            for i in range(8)
        ],
    )
    monkeypatch.setattr(daily.github_trending, "fetch", boom)
    monkeypatch.setattr(daily.reddit, "fetch", lambda: [])

    monkeypatch.setattr(
        daily,
        "summarize_all",
        lambda items, **kw: [
            (
                it,
                {
                    "summary_3lines": "x",
                    "why_notable": "x",
                    "dev_use_case": "x",
                    "trust": "中",
                    "reason": "x",
                    "priority": "中",
                },
            )
            for it in items
        ],
    )
    monkeypatch.setattr(
        daily,
        "post_newsletter",
        lambda pairs, **kw: posted.append(pairs) or 1,
    )

    rc = daily.main()

    assert rc == 0
    # github が落ちても HN 由来で配信は走る
    assert len(posted) == 1
    assert len(posted[0]) >= 1


def test_main_skips_slack_when_all_summaries_fail(monkeypatch) -> None:
    daily = _load_daily()
    posted: list = []

    monkeypatch.setattr(
        daily.hackernews,
        "fetch",
        lambda: [_item("hackernews", "1", "A new SDK release", score=1000)],
    )
    monkeypatch.setattr(daily.github_trending, "fetch", lambda: [])
    monkeypatch.setattr(daily.reddit, "fetch", lambda: [])
    monkeypatch.setattr(daily, "summarize_all", lambda items, **kw: [])
    monkeypatch.setattr(
        daily, "post_newsletter", lambda pairs, **kw: posted.append(pairs) or 1
    )

    rc = daily.main()

    assert rc == 0
    assert posted == []
