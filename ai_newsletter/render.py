"""採用記事 + Gemini 要約を Slack Block Kit に整形し、必要なら投稿まで行う。

要求定義 §2.72 / §5: 1 投稿に 10 件、各件は固定レイアウト、末尾にフィードバックボタン。
v0.1 ではフィードバック URL は placeholder (M2 で Apps Script Web App URL に差し替え)。
"""
from __future__ import annotations

from typing import Any

from ai_newsletter.llm import Summary
from ai_newsletter.models import RawItem
from ai_newsletter.slack import post_message

# Slack chat.postMessage の blocks 配列上限 (公式仕様)
SLACK_BLOCKS_LIMIT = 50

CATEGORY_LABELS = {
    "devtool": "AI開発ツール",
    "tips": "AIエージェント実装Tips",
    "service": "新サービス",
}

DEFAULT_FEEDBACK_URL_BASE = "https://example.com/feedback"  # v0.2 M2 で差し替え


def _format_quant(item: RawItem) -> str:
    """source ごとに「定量情報」行を組み立てる。"""
    if item.source == "github":
        stars = item.extra.get("stars_now", 0)
        delta = item.extra.get("stars_delta", 0)
        return f"GitHub: {stars} stars (+{delta} / 24h)"
    if item.source == "hackernews":
        comments = item.extra.get("descendants") or 0
        return f"HN: {int(item.score_raw)} points / {comments} comments"
    if item.source == "reddit":
        sub = item.extra.get("subreddit", "?")
        comments = item.extra.get("num_comments") or 0
        return f"r/{sub}: {int(item.score_raw)} upvotes / {comments} comments"
    return f"score: {item.score_raw}"


def _article_blocks(
    index: int,
    item: RawItem,
    summary: Summary,
    *,
    feedback_url_base: str,
) -> list[dict[str, Any]]:
    category_key = item.extra.get("category", "?")
    category_label = CATEGORY_LABELS.get(category_key, category_key)

    body = (
        f"*{index}. <{item.url}|{item.title}>*\n"
        f"カテゴリ: {category_label}  /  信頼度: {summary['trust']}  /  優先度: {summary['priority']}\n"
        f"要約:\n{summary['summary_3lines']}\n"
        f"なぜ注目か: {summary['why_notable']}\n"
        f"使いどころ: {summary['dev_use_case']}\n"
        f"採用理由: {summary['reason']}\n"
        f"定量: {_format_quant(item)}"
    )

    def fb(reaction: str, label: str) -> dict[str, Any]:
        return {
            "type": "button",
            "text": {"type": "plain_text", "text": label, "emoji": True},
            "url": f"{feedback_url_base}?id={item.source}:{item.id}&r={reaction}",
            "action_id": f"fb_{reaction}_{item.source}_{item.id}",
        }

    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": body}},
        {
            "type": "actions",
            "elements": [
                fb("like", "興味あり"),
                fb("dislike", "不要"),
                fb("later", "あとで読む"),
            ],
        },
        {"type": "divider"},
    ]


def render_blocks(
    pairs: list[tuple[RawItem, Summary]],
    *,
    feedback_url_base: str = DEFAULT_FEEDBACK_URL_BASE,
) -> list[list[dict[str, Any]]]:
    """Block Kit JSON を組み立て、Slack の 50 blocks/message 上限を超えそうなら分割。

    戻り値: 1 つの Slack 投稿 = 1 つの blocks 配列 で、複数投稿になる場合は list が伸びる。
    """
    header = {
        "type": "header",
        "text": {"type": "plain_text", "text": f"本日のAI開発ニュース {len(pairs)}件", "emoji": True},
    }

    messages: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = [header]
    index = 0
    for item, summary in pairs:
        index += 1
        article = _article_blocks(index, item, summary, feedback_url_base=feedback_url_base)
        # ヘッダー + 既存 + 今回追加が 50 を超えるなら、現在の message を確定して新規開始
        if len(current) + len(article) > SLACK_BLOCKS_LIMIT:
            messages.append(current)
            current = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"本日のAI開発ニュース (続き) — 第 {index} 件〜",
                        "emoji": True,
                    },
                }
            ]
        current.extend(article)
    if len(current) > 1:  # header だけの空メッセージは投稿しない
        messages.append(current)
    return messages


def post_newsletter(
    pairs: list[tuple[RawItem, Summary]],
    *,
    feedback_url_base: str = DEFAULT_FEEDBACK_URL_BASE,
    fallback_text: str = "本日のAI開発ニュース",
) -> int:
    """整形して Slack に投稿。投稿数 (1 or 2+) を返す。"""
    messages = render_blocks(pairs, feedback_url_base=feedback_url_base)
    for blocks in messages:
        post_message(fallback_text, blocks=blocks)
    return len(messages)
