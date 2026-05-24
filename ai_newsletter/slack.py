"""Slack chat.postMessage を httpx で薄く呼ぶ。"""
from __future__ import annotations

import os
from typing import Any

import httpx

SLACK_API_BASE = "https://slack.com/api"


class SlackError(RuntimeError):
    """Slack API が ok=false を返した時に投げる例外。"""


def post_message(
    text: str,
    blocks: list[dict[str, Any]] | None = None,
    *,
    channel: str | None = None,
    token: str | None = None,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """指定 channel にメッセージを投稿する。

    channel / token を省略した場合は環境変数 SLACK_CHANNEL_ID / SLACK_BOT_TOKEN を読む。
    client を渡せばその httpx.Client を使う (test や接続再利用向け)。
    """
    channel = channel if channel is not None else os.environ["SLACK_CHANNEL_ID"]
    token = token if token is not None else os.environ["SLACK_BOT_TOKEN"]

    payload: dict[str, Any] = {"channel": channel, "text": text}
    if blocks is not None:
        payload["blocks"] = blocks

    owns_client = client is None
    if client is None:
        client = httpx.Client(timeout=10.0)
    try:
        resp = client.post(
            f"{SLACK_API_BASE}/chat.postMessage",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
    finally:
        if owns_client:
            client.close()

    if not data.get("ok"):
        raise SlackError(f"Slack API error: {data.get('error', 'unknown')}")
    return data
