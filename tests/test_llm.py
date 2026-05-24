"""ai_newsletter.llm の unit test。SDK は generate_fn 注入で bypass する。"""
from __future__ import annotations

import json
import logging

from ai_newsletter.llm import (
    DEFAULT_MODEL,
    RESPONSE_SCHEMA,
    summarize,
    summarize_all,
)
from ai_newsletter.models import RawItem


def _item(item_id: str = "x1") -> RawItem:
    return RawItem(
        source="hackernews",
        id=item_id,
        title="Show HN: a new RAG framework",
        url="https://example.com/x",
        summary_raw="brief description",
        score_raw=300.0,
        extra={"category": "devtool"},
    )


def _valid_payload() -> dict:
    return {
        "summary_3lines": "1行目\n2行目\n3行目",
        "why_notable": "新しい RAG framework が出た",
        "dev_use_case": "自分の検索基盤に組み込める",
        "trust": "中",
        "reason": "Star 急増 + AI 関連",
        "priority": "中",
    }


def test_summarize_returns_parsed_payload() -> None:
    captured: dict = {}

    def fake(prompt: str, model: str) -> str:
        captured["prompt"] = prompt
        captured["model"] = model
        return json.dumps(_valid_payload())

    result = summarize(_item(), generate_fn=fake)

    assert result == _valid_payload()
    # prompt にカテゴリと title が含まれる
    assert "devtool" in captured["prompt"]
    assert "RAG framework" in captured["prompt"]
    # model default
    assert captured["model"] == DEFAULT_MODEL


def test_summarize_uses_passed_model_over_default() -> None:
    captured: dict = {}

    def fake(prompt: str, model: str) -> str:
        captured["model"] = model
        return json.dumps(_valid_payload())

    summarize(_item(), model="gemini-3.1-flash-lite", generate_fn=fake)

    assert captured["model"] == "gemini-3.1-flash-lite"


def test_summarize_uses_env_model_when_no_arg(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_MODEL", "gemini-from-env")
    captured: dict = {}

    def fake(prompt: str, model: str) -> str:
        captured["model"] = model
        return json.dumps(_valid_payload())

    summarize(_item(), generate_fn=fake)

    assert captured["model"] == "gemini-from-env"


def test_summarize_returns_none_on_invalid_json(caplog) -> None:
    def fake(prompt: str, model: str) -> str:
        return "not a json {{{"

    with caplog.at_level(logging.WARNING, logger="ai_newsletter.llm"):
        result = summarize(_item("bad1"), generate_fn=fake)

    assert result is None
    assert any("summarize failed" in r.message for r in caplog.records)


def test_summarize_returns_none_when_required_key_missing(caplog) -> None:
    incomplete = _valid_payload()
    del incomplete["trust"]

    def fake(prompt: str, model: str) -> str:
        return json.dumps(incomplete)

    with caplog.at_level(logging.WARNING, logger="ai_newsletter.llm"):
        result = summarize(_item("miss1"), generate_fn=fake)

    assert result is None
    assert any("missing keys" in r.message for r in caplog.records)


def test_summarize_returns_none_when_generate_raises(caplog) -> None:
    def fake(prompt: str, model: str) -> str:
        raise RuntimeError("upstream API down")

    with caplog.at_level(logging.WARNING, logger="ai_newsletter.llm"):
        result = summarize(_item("err1"), generate_fn=fake)

    assert result is None


def test_summarize_all_skips_failures_and_keeps_successes() -> None:
    items = [_item("ok1"), _item("ok2"), _item("ok3")]
    calls = {"n": 0}

    def fake(prompt: str, model: str) -> str:
        calls["n"] += 1
        # 2 回目だけ JSON parse 失敗を返す
        if calls["n"] == 2:
            return "not json"
        return json.dumps(_valid_payload())

    results = summarize_all(items, generate_fn=fake)

    assert len(results) == 2
    assert [it.id for it, _ in results] == ["ok1", "ok3"]


def test_response_schema_lists_all_required_keys() -> None:
    # スキーマと TypedDict が乖離しないことの最低保証
    assert set(RESPONSE_SCHEMA["required"]) == {
        "summary_3lines",
        "why_notable",
        "dev_use_case",
        "trust",
        "reason",
        "priority",
    }
