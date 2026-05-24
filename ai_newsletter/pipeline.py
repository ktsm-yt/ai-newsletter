"""候補 RawItem を「分類 → 除外 → スコアリング → 10件抽出」する pipeline。

要件: docs/requirements.md §2.96 / §4 (10件中 devtool 4 + tips 4 + service 2)。
"""
from __future__ import annotations

import logging
import re
from collections.abc import Iterable

from ai_newsletter.models import RawItem

logger = logging.getLogger(__name__)

Category = str  # "devtool" | "tips" | "service" | "other"

# 配分制約 (要件 §4)
QUOTAS: dict[Category, int] = {"devtool": 4, "tips": 4, "service": 2}

# Source ごとのスコア重み (3 source 拮抗が初期値、運用しながら調整)
SOURCE_WEIGHTS: dict[str, float] = {
    "hackernews": 1.0,
    "github": 1.0,
    "reddit": 1.0,
}

# 分類用 keyword (title + url を対象、case-insensitive word boundary)
TIPS_KEYWORDS = (
    "tutorial",
    "guide",
    "how to",
    "how-to",
    "tips",
    "best practice",
    "workflow",
    "pattern",
    "prompt engineering",
    "prompting",
    "fine-tuning",
    "fine tuning",
    "rag",
    "evaluation",
    "benchmark",
    "agent design",
)
DEVTOOL_KEYWORDS = (
    "sdk",
    "cli",
    "library",
    "framework",
    "toolkit",
    "plugin",
    "extension",
    "ide",
    "editor",
    "debugger",
    "linter",
    "compiler",
    "runtime",
    "observability",
    "tracing",
    "deploy",
    "open source",
    "open-source",
)
SERVICE_KEYWORDS = (
    "launches",
    "launch",
    "announces",
    "announcement",
    "unveils",
    "introducing",
    "releases",
    "release",
    "ga released",
    "general availability",
    "platform",
    "saas",
    "startup",
    "new product",
)

# 除外: 宣伝色 / 資金調達のみ / ガジェットレビュー
EXCLUDE_PATTERNS = (
    re.compile(r"\b(?:raises|raised|series\s+[abcd]|seed\s+round|funding\s+round)\b", re.I),
    re.compile(r"\b(?:valuation|valued\s+at|ipo|acquires|acquisition)\b", re.I),
    re.compile(r"\b(?:gadget|smartphone|iphone|android\s+phone|laptop\s+review|review:)\b", re.I),
    re.compile(r"\b(?:sponsored|promoted|affiliate)\b", re.I),
)


def _haystack(item: RawItem) -> str:
    return f"{item.title}\n{item.url}\n{item.summary_raw}"


def _contains_any(text: str, keywords: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(kw in lowered for kw in keywords)


def is_excluded(item: RawItem) -> bool:
    text = _haystack(item)
    return any(p.search(text) for p in EXCLUDE_PATTERNS)


def classify(item: RawItem) -> Category:
    """title + url + summary を見て 4 カテゴリのいずれかに分類する。

    優先順位: tips > devtool > service > other。
    source-bias: GitHub は他カテゴリに該当しなければ devtool 既定、
    Reddit は同じく tips 既定 (コミュニティ議論の傾向)。
    """
    text = _haystack(item)
    if _contains_any(text, TIPS_KEYWORDS):
        return "tips"
    if _contains_any(text, DEVTOOL_KEYWORDS):
        return "devtool"
    if _contains_any(text, SERVICE_KEYWORDS):
        return "service"
    # source-bias fallback
    if item.source == "github":
        return "devtool"
    if item.source == "reddit":
        return "tips"
    return "other"


def _normalize_scores(items: list[RawItem]) -> dict[str, float]:
    """source 内 max-normalize した後、source 重みを乗じる。"""
    max_per_source: dict[str, float] = {}
    for it in items:
        if it.score_raw > max_per_source.get(it.source, 0.0):
            max_per_source[it.source] = it.score_raw

    normalized: dict[str, float] = {}
    for it in items:
        cap = max_per_source.get(it.source, 0.0)
        base = (it.score_raw / cap) if cap > 0 else 0.0
        weight = SOURCE_WEIGHTS.get(it.source, 1.0)
        normalized[it.id] = base * weight
    return normalized


def select_top10(
    items: Iterable[RawItem],
    *,
    quotas: dict[Category, int] | None = None,
) -> list[RawItem]:
    """除外 → 分類 → スコア → 配分通り 10 件抽出。

    各 item の `extra["category"]` と `extra["final_score"]` を埋めて返す。
    枠が埋まらない場合は log.warning し、埋まる分だけ返す (要件 §3 不足ログ)。
    """
    quotas = quotas or QUOTAS
    survivors: list[RawItem] = []
    for it in items:
        if is_excluded(it):
            continue
        cat = classify(it)
        if cat == "other":
            continue
        it.extra["category"] = cat
        survivors.append(it)

    scored = _normalize_scores(survivors)
    for it in survivors:
        it.extra["final_score"] = scored.get(it.id, 0.0)

    selected: list[RawItem] = []
    seen_ids: set[str] = set()
    for cat, quota in quotas.items():
        bucket = sorted(
            (it for it in survivors if it.extra["category"] == cat),
            key=lambda it: it.extra["final_score"],
            reverse=True,
        )
        taken = 0
        for it in bucket:
            if taken >= quota:
                break
            if it.id in seen_ids:
                continue
            selected.append(it)
            seen_ids.add(it.id)
            taken += 1
        if taken < quota:
            logger.warning(
                "category %s under quota: got %d / %d", cat, taken, quota
            )

    return selected
