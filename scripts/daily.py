"""毎朝 JST 07:00 (UTC 22:00) に GitHub Actions から呼ぶ entrypoint。

3 source を並列 fetch → pipeline で 10 件抽出 → Gemini 要約 → Slack 投稿。
失敗時は Actions log にスタックトレースが残るのみ (要件 §8 Slack エラー通知なし)。
"""
from __future__ import annotations

import logging
import sys
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv

from ai_newsletter.llm import summarize_all
from ai_newsletter.models import RawItem
from ai_newsletter.pipeline import select_top10
from ai_newsletter.render import post_newsletter
from ai_newsletter.sources import github_trending, hackernews, reddit

logger = logging.getLogger("ai_newsletter.daily")


def _safe_fetch(name: str, fn) -> list[RawItem]:
    """1 source の失敗が全体配信を止めないようにラップする。"""
    try:
        items = fn()
        logger.info("%s: %d items fetched", name, len(items))
        return items
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s: fetch failed — %s", name, exc)
        return []


def main() -> int:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    with ThreadPoolExecutor(max_workers=3) as ex:
        fut_hn = ex.submit(_safe_fetch, "hackernews", hackernews.fetch)
        fut_gh = ex.submit(_safe_fetch, "github", github_trending.fetch)
        fut_rd = ex.submit(_safe_fetch, "reddit", reddit.fetch)
        all_items = fut_hn.result() + fut_gh.result() + fut_rd.result()

    logger.info("total candidates: %d", len(all_items))

    selected = select_top10(all_items)
    if not selected:
        logger.warning("no items selected after pipeline — skipping Slack post")
        return 0

    pairs = summarize_all(selected)
    if not pairs:
        logger.warning("all summaries failed — skipping Slack post")
        return 0

    sent = post_newsletter(pairs)
    logger.info("posted %d Slack message(s) with %d article(s)", sent, len(pairs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
