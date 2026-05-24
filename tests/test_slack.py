"""ai_newsletter.slack の unit test (respx で Slack API を mock)。"""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from ai_newsletter.slack import SlackError, post_message

SLACK_URL = "https://slack.com/api/chat.postMessage"


@respx.mock
def test_post_message_sends_channel_text_and_bearer() -> None:
    route = respx.post(SLACK_URL).mock(
        return_value=httpx.Response(
            200, json={"ok": True, "ts": "1700000000.0001", "channel": "C123"}
        )
    )

    result = post_message("hello", channel="C123", token="xoxb-test")

    assert route.called
    sent = route.calls.last.request
    body = json.loads(sent.read())
    assert body == {"channel": "C123", "text": "hello"}
    assert sent.headers["authorization"] == "Bearer xoxb-test"
    assert result["ok"] is True


@respx.mock
def test_post_message_includes_blocks_when_provided() -> None:
    respx.post(SLACK_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "*hi*"}}]

    post_message("hi", blocks=blocks, channel="C123", token="xoxb-test")

    body = json.loads(respx.calls.last.request.read())
    assert body["blocks"] == blocks


@respx.mock
def test_post_message_raises_on_api_error() -> None:
    respx.post(SLACK_URL).mock(
        return_value=httpx.Response(200, json={"ok": False, "error": "not_in_channel"})
    )

    with pytest.raises(SlackError, match="not_in_channel"):
        post_message("hello", channel="C123", token="xoxb-test")


def test_post_message_raises_when_token_is_empty() -> None:
    with pytest.raises(SlackError, match="SLACK_BOT_TOKEN is empty"):
        post_message("hello", channel="C123", token="")


def test_post_message_raises_when_channel_is_empty() -> None:
    with pytest.raises(SlackError, match="SLACK_CHANNEL_ID is empty"):
        post_message("hello", channel="", token="xoxb-test")


@respx.mock
def test_post_message_strips_whitespace_from_token_and_channel() -> None:
    # GitHub Secrets / .env からの値に紛れ込んだ改行や空白を吸収する
    respx.post(SLACK_URL).mock(return_value=httpx.Response(200, json={"ok": True}))

    post_message("hi", channel="  C123\n", token="\txoxb-test\n")

    sent = respx.calls.last.request
    assert sent.headers["authorization"] == "Bearer xoxb-test"
    body = json.loads(sent.read())
    assert body["channel"] == "C123"
