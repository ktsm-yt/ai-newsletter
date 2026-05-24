"""ai_newsletter.pipeline の unit test。"""
from __future__ import annotations

import logging

from ai_newsletter.models import RawItem
from ai_newsletter.pipeline import (
    classify,
    is_excluded,
    select_top10,
)


def _item(
    source: str,
    item_id: str,
    title: str,
    *,
    score: float = 100.0,
    url: str = "",
    summary: str = "",
) -> RawItem:
    return RawItem(
        source=source,
        id=item_id,
        title=title,
        url=url or f"https://example.com/{item_id}",
        summary_raw=summary,
        score_raw=score,
    )


def test_is_excluded_drops_funding_only_items() -> None:
    assert is_excluded(_item("hackernews", "1", "Acme raises $50M Series B"))
    assert is_excluded(_item("hackernews", "2", "Foo valued at $10B in latest round"))


def test_is_excluded_drops_gadget_reviews() -> None:
    assert is_excluded(_item("reddit", "1", "Review: the new iPhone camera"))
    assert is_excluded(_item("reddit", "2", "Best gadget of 2026"))


def test_is_excluded_keeps_normal_dev_topics() -> None:
    assert not is_excluded(_item("hackernews", "1", "Show HN: a new RAG framework"))
    assert not is_excluded(_item("github", "1", "claude/agents — agentic toolkit"))


def test_classify_tips_wins_over_devtool() -> None:
    """tips キーワードが優先 (Tutorial in a framework discussion → tips 寄りに分類)。"""
    assert (
        classify(_item("hackernews", "1", "Tutorial: building an LLM framework"))
        == "tips"
    )


def test_classify_devtool_by_keyword() -> None:
    assert classify(_item("hackernews", "1", "New CLI for LLM evals")) == "devtool"
    assert classify(_item("hackernews", "2", "A new SDK for LLM apps")) == "devtool"


def test_classify_service_by_keyword() -> None:
    assert (
        classify(_item("hackernews", "1", "Acme launches AI assistant platform"))
        == "service"
    )


def test_classify_falls_back_to_source_bias() -> None:
    # GitHub source の repo は keyword に当たらなければ devtool 既定
    assert classify(_item("github", "1", "claude/agents")) == "devtool"
    # Reddit source は tips 既定
    assert classify(_item("reddit", "1", "What's your favorite Claude trick?")) == "tips"
    # HN は other に落ちる
    assert classify(_item("hackernews", "1", "Random non-AI title")) == "other"


def test_select_top10_respects_quota_and_normalizes_per_source() -> None:
    items = [
        # devtool 候補 (HN: max 1000, GitHub: max 500)
        _item("hackernews", "h1", "A new SDK release", score=1000),  # devtool, score=1.0
        _item("hackernews", "h2", "Another framework debut", score=500),  # devtool, 0.5
        _item("hackernews", "h3", "A library for prompts", score=400),  # devtool, 0.4
        _item("hackernews", "h4", "Tiny CLI for LLMs", score=300),  # devtool, 0.3
        _item("hackernews", "h5", "Yet another SDK update", score=200),  # devtool, 0.2 (drop)
        _item("github", "g1", "agentic-toolkit", score=500),  # devtool (source bias), 1.0
        # tips 候補
        _item("reddit", "r1", "RAG tutorial", score=300),  # tips, 1.0
        _item("reddit", "r2", "How-to: fine-tuning small models", score=200),  # tips, 0.66
        _item("reddit", "r3", "Best practice for agent design", score=150),  # tips, 0.5
        _item("reddit", "r4", "Prompt engineering tips", score=100),  # tips, 0.33
        # service 候補
        _item("hackernews", "h6", "Acme launches new AI platform", score=800),  # service, 0.8
        _item("hackernews", "h7", "Beta unveils chat product", score=600),  # service, 0.6
    ]

    selected = select_top10(items)

    # 配分通り 10 件 (4 devtool + 4 tips + 2 service)
    assert len(selected) == 10
    cats = [it.extra["category"] for it in selected]
    assert cats.count("devtool") == 4
    assert cats.count("tips") == 4
    assert cats.count("service") == 2

    # devtool は score 上位 4 (g1=1.0, h1=1.0, h2=0.5, h3=0.4) — h4/h5 落ち
    devtool_ids = {it.id for it in selected if it.extra["category"] == "devtool"}
    assert devtool_ids == {"g1", "h1", "h2", "h3"}

    # final_score が埋まっていること
    h1 = next(it for it in selected if it.id == "h1")
    assert h1.extra["final_score"] == 1.0


def test_select_top10_under_quota_logs_warning(caplog) -> None:
    items = [
        _item("hackernews", "h1", "A new SDK release", score=100),  # devtool only
        _item("hackernews", "h2", "Another framework debut", score=50),
    ]

    with caplog.at_level(logging.WARNING, logger="ai_newsletter.pipeline"):
        selected = select_top10(items)

    assert len(selected) == 2
    # tips / service が枠不足の log
    warnings = [r.message for r in caplog.records]
    assert any("category tips under quota" in m for m in warnings)
    assert any("category service under quota" in m for m in warnings)


def test_select_top10_drops_excluded_before_classify() -> None:
    items = [
        _item("hackernews", "h1", "Acme raises $50M Series B"),  # excluded
        _item("hackernews", "h2", "A new SDK release", score=100),  # devtool
    ]
    selected = select_top10(items)
    assert [it.id for it in selected] == ["h2"]


def test_select_top10_drops_other_category() -> None:
    items = [
        _item("hackernews", "h1", "Random unrelated news"),  # other → drop
    ]
    selected = select_top10(items)
    assert selected == []
