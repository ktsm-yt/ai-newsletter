"""Gemini で 1 記事ずつ「要約3行 / 注目理由 / 使いどころ / 信頼度 / 採用理由 / 優先度」を生成する。

- model: 既定 gemini-3.0-flash (無料枠で運用可能、`GEMINI_MODEL` env で override)
- 構造化出力: response_mime_type=application/json + response_schema で固定 JSON を強制
- 失敗時: 該当件は None を返して呼び出し側で skip (要求定義 §8 配信は続行)
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable, TypedDict

from ai_newsletter.models import RawItem

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-3.0-flash"

# 信頼度・優先度の取りうる値 (Slack 投稿時の表示もこれに揃える)
TRUST_VALUES = ("高", "中", "低")
PRIORITY_VALUES = ("高", "中", "低")


class Summary(TypedDict):
    summary_3lines: str
    why_notable: str
    dev_use_case: str
    trust: str  # 高 / 中 / 低
    reason: str
    priority: str  # 高 / 中 / 低


RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary_3lines": {"type": "string"},
        "why_notable": {"type": "string"},
        "dev_use_case": {"type": "string"},
        "trust": {"type": "string", "enum": list(TRUST_VALUES)},
        "reason": {"type": "string"},
        "priority": {"type": "string", "enum": list(PRIORITY_VALUES)},
    },
    "required": [
        "summary_3lines",
        "why_notable",
        "dev_use_case",
        "trust",
        "reason",
        "priority",
    ],
}


def _build_prompt(item: RawItem) -> str:
    category = item.extra.get("category", "?")
    return (
        "あなたはAI開発者向けニュースレターの編集者です。\n"
        "下の海外記事/プロジェクトを日本語で要約してください。\n"
        "出力は指定された JSON schema に厳密に従い、装飾語は使わず簡潔に書いてください。\n"
        "\n"
        f"カテゴリ: {category}\n"
        f"ソース: {item.source}\n"
        f"タイトル: {item.title}\n"
        f"URL: {item.url}\n"
        f"スコア (生): {item.score_raw}\n"
        f"本文/概要: {item.summary_raw[:1500]}\n"
        "\n"
        "fields:\n"
        "- summary_3lines: 日本語の要約 (改行区切りで 3 行)\n"
        "- why_notable: なぜ AI 開発者にとって注目に値するか (1-2 文)\n"
        "- dev_use_case: 開発者が自分の作業にどう活かせるか具体例 (1-2 文)\n"
        "- trust: 高 / 中 / 低 のいずれか (公式発表・著名 OSS は高、匿名議論は低)\n"
        "- reason: なぜ今日の 10 件に採用したかの根拠 (1 文)\n"
        "- priority: 読む優先度 高 / 中 / 低 (使い回しできる Tips は高)\n"
    )


# Gemini SDK の generate_content をラップした callable。
# test では fake を注入できるように DI 形式にしておく。
GenerateFn = Callable[[str, str], str]


def _default_generate(prompt: str, model: str) -> str:
    """google-genai SDK で structured output を取得して JSON 文字列を返す。"""
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is empty")
    client = genai.Client(api_key=api_key)
    resp = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=RESPONSE_SCHEMA,
        ),
    )
    return resp.text or ""


def summarize(
    item: RawItem,
    *,
    model: str | None = None,
    generate_fn: GenerateFn | None = None,
) -> Summary | None:
    """1 件の RawItem を Gemini で要約。失敗時は None を返し log。

    generate_fn を渡すと SDK を bypass できる (test 用途)。
    """
    model = model or os.environ.get("GEMINI_MODEL", "").strip() or DEFAULT_MODEL
    fn = generate_fn or _default_generate
    prompt = _build_prompt(item)
    try:
        raw = fn(prompt, model)
        data = json.loads(raw)
    except Exception as exc:  # noqa: BLE001 — 1 件失敗は全体止めず skip
        logger.warning("gemini summarize failed for %s:%s — %s", item.source, item.id, exc)
        return None

    # schema 必須キーが揃っているかだけ最終 check (Gemini が破った場合の保険)
    missing = [k for k in RESPONSE_SCHEMA["required"] if k not in data]
    if missing:
        logger.warning(
            "gemini response missing keys %s for %s:%s", missing, item.source, item.id
        )
        return None
    return data  # type: ignore[return-value]


def summarize_all(
    items: list[RawItem],
    *,
    model: str | None = None,
    generate_fn: GenerateFn | None = None,
) -> list[tuple[RawItem, Summary]]:
    """配信対象を順に要約し、成功したものだけ (item, summary) のペアで返す。"""
    out: list[tuple[RawItem, Summary]] = []
    for it in items:
        summary = summarize(it, model=model, generate_fn=generate_fn)
        if summary is not None:
            out.append((it, summary))
    return out
