"""GitHub Search API で AI 系 topic の Star 急増 repo を抽出する client。

API: https://docs.github.com/en/rest/search/search#search-repositories
- 各 topic で個別 search (GitHub Search の qualifier は AND 結合のため、topic OR は別 search で表現)
- created:>YYYY-MM-DD で 30 日以内に作られた repo を sort=stars で取得
- 前回スナップショット (data/github_stars.json) との差分で「24h Star 増加数」を算出
- snapshot は Actions cache で永続化する想定 (logノイズ回避、D.1 で workflow 統合)
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import httpx

from ai_newsletter.models import RawItem

GITHUB_API_BASE = "https://api.github.com"

# 初期案 (Plans.md L62 で user 確定済、2026-05-24): AI 系トピック横断
DEFAULT_TOPICS: tuple[str, ...] = ("llm", "ai-agent", "rag")
DEFAULT_DAYS = 30
DEFAULT_PER_PAGE = 50
DEFAULT_SNAPSHOT_PATH = Path("data/github_stars.json")


class GitHubError(RuntimeError):
    """GitHub API 呼び出し失敗時の例外。"""


def _search_one_topic(
    client: httpx.Client,
    topic: str,
    *,
    days: int,
    per_page: int,
    token: str,
) -> list[dict[str, Any]]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    q = f"topic:{topic} created:>{cutoff}"
    resp = client.get(
        f"{GITHUB_API_BASE}/search/repositories",
        params={"q": q, "sort": "stars", "order": "desc", "per_page": per_page},
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    resp.raise_for_status()
    return resp.json().get("items", [])


def _load_snapshot(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return {k: int(v) for k, v in data.items() if isinstance(k, str)}


def _save_snapshot(path: Path, snapshot: dict[str, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2, sort_keys=True))


def fetch(
    *,
    snapshot_path: Path = DEFAULT_SNAPSHOT_PATH,
    topics: Iterable[str] = DEFAULT_TOPICS,
    days: int = DEFAULT_DAYS,
    per_page: int = DEFAULT_PER_PAGE,
    token: str | None = None,
    client: httpx.Client | None = None,
) -> list[RawItem]:
    """topic × created window で repo を集め、Star 増分が正のものを返す。

    初回 (snapshot 未存在) は snapshot を書き出すだけで [] を返す (baseline)。
    """
    token = (token if token is not None else os.environ.get("GH_TOKEN", "")).strip()
    if not token:
        raise GitHubError("GH_TOKEN is empty (set the env var or pass token=)")

    owns_client = client is None
    if client is None:
        client = httpx.Client(timeout=15.0)
    try:
        all_repos: dict[str, dict[str, Any]] = {}
        for topic in topics:
            for repo in _search_one_topic(
                client, topic, days=days, per_page=per_page, token=token
            ):
                full_name = repo.get("full_name")
                if isinstance(full_name, str) and full_name not in all_repos:
                    all_repos[full_name] = repo
    finally:
        if owns_client:
            client.close()

    prev_snapshot = _load_snapshot(snapshot_path)
    is_baseline = not prev_snapshot
    new_snapshot: dict[str, int] = {}
    items: list[RawItem] = []

    for full_name, repo in all_repos.items():
        stars_now = int(repo.get("stargazers_count") or 0)
        new_snapshot[full_name] = stars_now
        if is_baseline:
            continue
        # 新規 repo (前回 snapshot 未掲載) は差分 0 扱い → 次回から評価対象
        prev = prev_snapshot.get(full_name, stars_now)
        delta = stars_now - prev
        if delta <= 0:
            continue
        items.append(
            RawItem(
                source="github",
                id=full_name,
                title=repo.get("name") or full_name,
                url=repo.get("html_url") or f"https://github.com/{full_name}",
                summary_raw=(repo.get("description") or "")[:500],
                score_raw=float(delta),
                published_at=None,
                extra={
                    "full_name": full_name,
                    "stars_now": stars_now,
                    "stars_delta": delta,
                    "language": repo.get("language"),
                    "topics": repo.get("topics") or [],
                },
            )
        )

    _save_snapshot(snapshot_path, new_snapshot)
    return items
