"""ai_newsletter.sources.reddit の integration test (respx で Reddit API mock)。"""
from __future__ import annotations

import base64

import httpx
import pytest
import respx

from ai_newsletter.sources.reddit import (
    REDDIT_API_BASE,
    REDDIT_TOKEN_URL,
    RedditError,
    fetch,
)


def _post(post_id: str, title: str, score: int, **extra) -> dict:
    return {
        "kind": "t3",
        "data": {
            "id": post_id,
            "title": title,
            "score": score,
            "url": extra.get("url", f"https://example.com/{post_id}"),
            "permalink": extra.get("permalink", f"/r/test/comments/{post_id}/x/"),
            "is_self": extra.get("is_self", False),
            "selftext": extra.get("selftext", ""),
            "num_comments": extra.get("num_comments", 10),
            "upvote_ratio": extra.get("upvote_ratio", 0.95),
            "created_utc": extra.get("created_utc", 1700000000),
        },
    }


def _listing(*posts: dict) -> dict:
    return {"data": {"children": list(posts)}}


@respx.mock
def test_fetch_returns_items_per_subreddit() -> None:
    respx.post(REDDIT_TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "tk", "token_type": "bearer"})
    )
    respx.get(f"{REDDIT_API_BASE}/r/LocalLLaMA/top").mock(
        return_value=httpx.Response(200, json=_listing(_post("a1", "LLM news", 300)))
    )
    respx.get(f"{REDDIT_API_BASE}/r/ClaudeAI/top").mock(
        return_value=httpx.Response(200, json=_listing(_post("b1", "Claude tips", 150)))
    )

    items = fetch(
        subreddits=["LocalLLaMA", "ClaudeAI"],
        limit=5,
        client_id="cid",
        client_secret="cs",
        user_agent="ai-newsletter/0.1 by tester",
    )

    assert [it.id for it in items] == ["LocalLLaMA:a1", "ClaudeAI:b1"]
    assert items[0].source == "reddit"
    assert items[0].score_raw == 300.0
    assert items[0].extra["subreddit"] == "LocalLLaMA"
    assert items[0].extra["num_comments"] == 10
    assert items[0].published_at is not None


@respx.mock
def test_fetch_uses_basic_auth_for_token_and_bearer_for_listing() -> None:
    token_route = respx.post(REDDIT_TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "tk-dummy"})
    )
    listing_route = respx.get(f"{REDDIT_API_BASE}/r/LocalLLaMA/top").mock(
        return_value=httpx.Response(200, json=_listing())
    )

    fetch(
        subreddits=["LocalLLaMA"],
        client_id="cid-x",
        client_secret="csk-x",
        user_agent="ai-newsletter/0.1 by tester",
    )

    token_req = token_route.calls.last.request
    expected = "Basic " + base64.b64encode(b"cid-x:csk-x").decode()
    assert token_req.headers["authorization"] == expected
    assert token_req.headers["user-agent"] == "ai-newsletter/0.1 by tester"
    assert b"grant_type=client_credentials" in token_req.read()

    listing_req = listing_route.calls.last.request
    assert listing_req.headers["authorization"] == "Bearer tk-dummy"
    assert listing_req.headers["user-agent"] == "ai-newsletter/0.1 by tester"
    assert "t=day" in str(listing_req.url)
    assert "limit=25" in str(listing_req.url)


@respx.mock
def test_fetch_resolves_url_for_self_post() -> None:
    """is_self=True の self post は permalink を返す (data.url は reddit 内 URL なので)。"""
    respx.post(REDDIT_TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "tk"})
    )
    respx.get(f"{REDDIT_API_BASE}/r/ClaudeAI/top").mock(
        return_value=httpx.Response(
            200,
            json=_listing(
                _post(
                    "self1",
                    "What's your favorite Claude trick?",
                    50,
                    is_self=True,
                    selftext="long body here",
                    permalink="/r/ClaudeAI/comments/self1/x/",
                )
            ),
        )
    )

    items = fetch(
        subreddits=["ClaudeAI"],
        client_id="cid",
        client_secret="cs",
        user_agent="ai-newsletter/0.1 by tester",
    )

    assert items[0].url == "https://www.reddit.com/r/ClaudeAI/comments/self1/x/"
    assert items[0].summary_raw == "long body here"
    assert items[0].extra["is_self"] is True


def test_fetch_raises_when_credentials_empty() -> None:
    with pytest.raises(RedditError, match="REDDIT_CLIENT_ID"):
        fetch(
            client_id="",
            client_secret="cs",
            user_agent="ua",
        )


def test_fetch_raises_when_user_agent_empty() -> None:
    with pytest.raises(RedditError, match="REDDIT_USER_AGENT"):
        fetch(
            client_id="cid",
            client_secret="cs",
            user_agent="",
        )


@respx.mock
def test_fetch_raises_when_token_missing_in_response() -> None:
    respx.post(REDDIT_TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"error": "invalid_grant"})
    )

    with pytest.raises(RedditError, match="missing access_token"):
        fetch(
            subreddits=["LocalLLaMA"],
            client_id="cid",
            client_secret="cs",
            user_agent="ai-newsletter/0.1 by tester",
        )
