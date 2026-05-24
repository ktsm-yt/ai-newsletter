"""Reddit OAuth2 (application-only) client。各 subreddit の day top を取得する。

API:
- POST https://www.reddit.com/api/v1/access_token (Basic auth, grant_type=client_credentials)
- GET  https://oauth.reddit.com/r/{sub}/top?t=day&limit=N
Reddit は User-Agent header 必須 (空 / 既定だと 429 を返す)。
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Iterable

import httpx

from ai_newsletter.models import RawItem

REDDIT_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
REDDIT_API_BASE = "https://oauth.reddit.com"

# 初期案 (Plans.md L70 で user 確定済、2026-05-24)
DEFAULT_SUBREDDITS: tuple[str, ...] = (
    "LocalLLaMA",
    "MachineLearning",
    "singularity",
    "OpenAI",
    "ClaudeAI",
)
DEFAULT_LIMIT = 25


class RedditError(RuntimeError):
    """Reddit API 呼び出し失敗時の例外。"""


def _get_token(
    client: httpx.Client,
    *,
    client_id: str,
    client_secret: str,
    user_agent: str,
) -> str:
    resp = client.post(
        REDDIT_TOKEN_URL,
        auth=(client_id, client_secret),
        data={"grant_type": "client_credentials"},
        headers={"User-Agent": user_agent},
    )
    resp.raise_for_status()
    data = resp.json()
    token = data.get("access_token")
    if not isinstance(token, str) or not token:
        raise RedditError(f"reddit token response missing access_token: {data}")
    return token


def _resolve_url(post: dict) -> str:
    permalink = post.get("permalink") or ""
    full_permalink = f"https://www.reddit.com{permalink}" if permalink else ""
    if post.get("is_self"):
        return full_permalink
    return post.get("url") or full_permalink


def fetch(
    *,
    subreddits: Iterable[str] = DEFAULT_SUBREDDITS,
    limit: int = DEFAULT_LIMIT,
    client_id: str | None = None,
    client_secret: str | None = None,
    user_agent: str | None = None,
    client: httpx.Client | None = None,
) -> list[RawItem]:
    client_id = (
        client_id if client_id is not None else os.environ.get("REDDIT_CLIENT_ID", "")
    ).strip()
    client_secret = (
        client_secret
        if client_secret is not None
        else os.environ.get("REDDIT_CLIENT_SECRET", "")
    ).strip()
    user_agent = (
        user_agent if user_agent is not None else os.environ.get("REDDIT_USER_AGENT", "")
    ).strip()
    if not client_id or not client_secret:
        raise RedditError(
            "REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET is empty (set env vars or pass args)"
        )
    if not user_agent:
        raise RedditError(
            "REDDIT_USER_AGENT is empty — Reddit 429s requests with default UA"
        )

    owns_client = client is None
    if client is None:
        client = httpx.Client(timeout=15.0)
    try:
        token = _get_token(
            client,
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": user_agent,
        }

        items: list[RawItem] = []
        for sub in subreddits:
            resp = client.get(
                f"{REDDIT_API_BASE}/r/{sub}/top",
                params={"t": "day", "limit": limit},
                headers=headers,
            )
            resp.raise_for_status()
            children = resp.json().get("data", {}).get("children", []) or []
            for child in children:
                post = child.get("data") or {}
                post_id = post.get("id")
                if not post_id:
                    continue
                ts = post.get("created_utc")
                published = (
                    datetime.fromtimestamp(int(ts), tz=timezone.utc)
                    if isinstance(ts, (int, float))
                    else None
                )
                items.append(
                    RawItem(
                        source="reddit",
                        id=f"{sub}:{post_id}",
                        title=post.get("title") or "",
                        url=_resolve_url(post),
                        summary_raw=(post.get("selftext") or "")[:500],
                        score_raw=float(post.get("score") or 0),
                        published_at=published,
                        extra={
                            "subreddit": sub,
                            "num_comments": post.get("num_comments"),
                            "upvote_ratio": post.get("upvote_ratio"),
                            "is_self": bool(post.get("is_self")),
                        },
                    )
                )
    finally:
        if owns_client:
            client.close()
    return items
