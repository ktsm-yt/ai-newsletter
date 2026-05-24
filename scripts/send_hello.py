"""A.2 動作確認: 開発 channel に hello を投稿する。

実行: `uv run python scripts/send_hello.py`
"""
from __future__ import annotations

from dotenv import load_dotenv

from ai_newsletter.slack import post_message


def main() -> None:
    load_dotenv()
    result = post_message("hello from ai-newsletter")
    print(f"posted: ts={result.get('ts')}, channel={result.get('channel')}")


if __name__ == "__main__":
    main()
