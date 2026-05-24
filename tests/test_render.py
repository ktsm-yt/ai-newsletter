"""ai_newsletter.render の unit test。"""
from __future__ import annotations

from typing import cast

import httpx
import respx

from ai_newsletter.llm import Summary
from ai_newsletter.models import RawItem
from ai_newsletter.render import (
    SLACK_BLOCKS_LIMIT,
    post_newsletter,
    render_blocks,
)


def _summary(**override) -> Summary:
    base = {
        "summary_3lines": "1行目\n2行目\n3行目",
        "why_notable": "面白い",
        "dev_use_case": "使える",
        "trust": "中",
        "reason": "score 高い",
        "priority": "中",
    }
    base.update(override)
    return cast(Summary, base)


def _hn(item_id: str = "1") -> RawItem:
    return RawItem(
        source="hackernews",
        id=item_id,
        title="GPT-powered code reviewer",
        url=f"https://example.com/hn/{item_id}",
        score_raw=250.0,
        extra={"category": "devtool", "descendants": 42},
    )


def _gh(item_id: str = "owner/repo") -> RawItem:
    return RawItem(
        source="github",
        id=item_id,
        title="agentic-toolkit",
        url=f"https://github.com/{item_id}",
        score_raw=30.0,
        extra={
            "category": "devtool",
            "stars_now": 1200,
            "stars_delta": 30,
        },
    )


def _reddit(item_id: str = "abc") -> RawItem:
    return RawItem(
        source="reddit",
        id=item_id,
        title="Best practice for agent design",
        url=f"https://www.reddit.com/r/ClaudeAI/comments/{item_id}/x/",
        score_raw=150.0,
        extra={"category": "tips", "subreddit": "ClaudeAI", "num_comments": 18},
    )


def test_render_blocks_single_message_for_10_items() -> None:
    pairs = [(_hn(str(i)), _summary()) for i in range(10)]

    messages = render_blocks(pairs)

    assert len(messages) == 1
    blocks = messages[0]
    # header + (section + actions + divider) * 10
    assert blocks[0]["type"] == "header"
    assert "10件" in blocks[0]["text"]["text"]
    assert len(blocks) == 1 + 3 * 10
    # 上限内
    assert len(blocks) <= SLACK_BLOCKS_LIMIT


def test_render_blocks_splits_when_over_limit() -> None:
    # 20 件で 1 + 60 blocks → 50 上限超 → 分割
    pairs = [(_hn(str(i)), _summary()) for i in range(20)]

    messages = render_blocks(pairs)

    assert len(messages) >= 2
    for blocks in messages:
        assert len(blocks) <= SLACK_BLOCKS_LIMIT
        assert blocks[0]["type"] == "header"


def test_render_blocks_includes_title_link_and_category_label() -> None:
    pairs = [(_hn(), _summary())]
    blocks = render_blocks(pairs)[0]
    body = blocks[1]["text"]["text"]
    assert "<https://example.com/hn/1|GPT-powered code reviewer>" in body
    # devtool は "AI開発ツール" に表示変換される
    assert "AI開発ツール" in body
    assert "信頼度: 中" in body
    assert "優先度: 中" in body


def test_render_blocks_quant_line_varies_by_source() -> None:
    blocks_hn = render_blocks([(_hn(), _summary())])[0][1]["text"]["text"]
    blocks_gh = render_blocks([(_gh(), _summary())])[0][1]["text"]["text"]
    blocks_rd = render_blocks([(_reddit(), _summary())])[0][1]["text"]["text"]

    assert "HN: 250 points / 42 comments" in blocks_hn
    assert "GitHub: 1200 stars (+30 / 24h)" in blocks_gh
    assert "r/ClaudeAI: 150 upvotes / 18 comments" in blocks_rd


def test_render_blocks_feedback_buttons_have_correct_urls() -> None:
    pairs = [(_hn("777"), _summary())]
    blocks = render_blocks(pairs, feedback_url_base="https://fb.example/in")[0]
    actions = blocks[2]
    assert actions["type"] == "actions"
    urls = [el["url"] for el in actions["elements"]]
    assert urls == [
        "https://fb.example/in?id=hackernews:777&r=like",
        "https://fb.example/in?id=hackernews:777&r=dislike",
        "https://fb.example/in?id=hackernews:777&r=later",
    ]


@respx.mock
def test_post_newsletter_posts_one_or_more_messages_to_slack() -> None:
    route = respx.post("https://slack.com/api/chat.postMessage").mock(
        return_value=httpx.Response(200, json={"ok": True, "ts": "1.0"})
    )
    pairs = [(_hn(str(i)), _summary()) for i in range(10)]

    # post_newsletter は slack.post_message を呼ぶ → token / channel が要る
    import os

    os.environ["SLACK_BOT_TOKEN"] = "xoxb-test"
    os.environ["SLACK_CHANNEL_ID"] = "C123"

    sent = post_newsletter(pairs)

    assert sent == 1
    assert route.call_count == 1
