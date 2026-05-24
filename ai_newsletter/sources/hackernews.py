"""Hacker News topstories から AI 関連を抽出する client。

API: https://github.com/HackerNews/API
- topstories.json: 上位 500 件の ID list
- item/{id}.json: 個別記事の score / title / url / by / time
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

import httpx

from ai_newsletter.models import RawItem

HN_API_BASE = "https://hacker-news.firebaseio.com/v0"

# 初期案 (Plans.md L55 で user 確定済、2026-05-24):
# ai|llm|gpt|claude|gemini|agent|copilot|anthropic|openai|huggingface|rag|fine-tuning
# - word boundary でマッチさせ "main" の "ai" 等を弾く
# - case-insensitive
AI_KEYWORDS = (
    "ai",
    "llm",
    "gpt",
    "claude",
    "gemini",
    "agent",
    "copilot",
    "anthropic",
    "openai",
    "huggingface",
    "rag",
    "fine-tuning",
)
_AI_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(k) for k in AI_KEYWORDS) + r")\b",
    re.IGNORECASE,
)


def _is_ai_related(title: str) -> bool:
    return bool(_AI_PATTERN.search(title))


def fetch(
    *,
    top_n: int = 200,
    client: httpx.Client | None = None,
) -> list[RawItem]:
    """topstories 上位 top_n から AI 関連 title だけ RawItem で返す。

    client を渡せばその httpx.Client を使う (test や接続再利用向け)。
    """
    owns_client = client is None
    if client is None:
        client = httpx.Client(timeout=10.0)
    try:
        ids_resp = client.get(f"{HN_API_BASE}/topstories.json")
        ids_resp.raise_for_status()
        ids: list[int] = ids_resp.json()[:top_n]

        items: list[RawItem] = []
        for item_id in ids:
            r = client.get(f"{HN_API_BASE}/item/{item_id}.json")
            r.raise_for_status()
            data = r.json()
            if not data:
                continue
            title = data.get("title") or ""
            if not _is_ai_related(title):
                continue
            url = data.get("url") or f"https://news.ycombinator.com/item?id={item_id}"
            ts = data.get("time")
            published = (
                datetime.fromtimestamp(ts, tz=timezone.utc) if isinstance(ts, int) else None
            )
            items.append(
                RawItem(
                    source="hackernews",
                    id=str(item_id),
                    title=title,
                    url=url,
                    summary_raw="",
                    score_raw=float(data.get("score") or 0),
                    published_at=published,
                    extra={
                        "by": data.get("by"),
                        "descendants": data.get("descendants"),
                    },
                )
            )
    finally:
        if owns_client:
            client.close()
    return items
