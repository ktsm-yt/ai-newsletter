"""情報源横断で扱う共通データモデル。

B.1 (HN) / B.2 (GitHub) / B.3 (Reddit) は各 `fetch() -> list[RawItem]` を返す。
下流の pipeline (C.1) はこの型だけ見てカテゴリ分類・スコアリング・10件抽出を行う。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class RawItem:
    source: str
    id: str
    title: str
    url: str
    summary_raw: str = ""
    score_raw: float = 0.0
    published_at: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)
