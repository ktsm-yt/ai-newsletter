# Plans: ai-newsletter

Branch: feat/v0.1-scaffold
Base: main
Test policy: layered-lite
  - unit: 各 module の純粋ロジック (分類・スコアリング・整形) を pytest
  - integration: 外部 API (Slack / Gemini / HN / GitHub / Reddit) は httpx + respx で mock
  - 手動配信確認: 開発用 Slack channel への実投稿で MVP 動作確認 (e2e の代替)
関連 ADR: -
要件定義: docs/requirements.md (vault 由来、project ホーム化済)

---

## M1: v0.1 — Slack に固定→収集→要約→10件配信 MVP

目的: 「毎朝 7:00 JST に Slack へ AI 開発ニュース 10 件届く」を最小構成で実現する。
完了時点で、要求定義 §13 の成功条件のうち「配信が届く」「形式が揃う」「Actions ログに成功が残る」を満たす。

### A. Setup (Slack App + Secrets + Actions 雛形)

- cc:完了 1.1.A.1 Slack App 作成手順 doc と env テンプレ
  - DoD:
    - `docs/setup-slack-app.md` に手順 (App 作成 → Bot Token scope `chat:write` 付与 → channel invite)
    - `.env.example` に `SLACK_BOT_TOKEN` / `SLACK_CHANNEL_ID` を記載
    - README に「セットアップ」セクションを追加し doc へリンク
  - 完了確認: user が手順どおりに Slack App を作って channel ID を取得できた

- cc:完了 1.1.A.2 Slack 投稿の最小実装 (固定文字列を投稿できる)
  - DoD:
    - `src/ai_newsletter/slack.py` に `post_message(text: str, blocks: list | None) -> None`
    - `python-dotenv` で `.env` 読み、`httpx` で `chat.postMessage` 直叩き (SDK 入れずに薄く)
    - `scripts/send_hello.py` で実行: 開発 channel に "hello from ai-newsletter" が届く
    - unit: respx で `chat.postMessage` を mock、payload に channel/text が入ること
  - 依存: A.1 (token 取得済)

- cc:完了 1.1.A.3 GitHub Actions の手動実行 workflow (initial)
  - DoD:
    - `.github/workflows/daily.yml` に `workflow_dispatch` トリガと cron スタブ (cron はコメントアウト or `if: false` で M1 末まで休止)
    - job 内で `uv sync` → `python scripts/send_hello.py`
    - GitHub Secrets `SLACK_BOT_TOKEN` / `SLACK_CHANNEL_ID` を env 渡し
    - 手動実行 → Slack に hello が届く / Actions ログに緑
  - 完了確認: Actions 履歴に成功 run が 1 件残る

### B. 情報源クライアント (取得・正規化)

各 client は `fetch() -> list[RawItem]` の interface に揃える。
`RawItem` = `{source, id, title, url, summary_raw, score_raw, published_at, extra}`。

着手前に subreddit / GitHub 検索条件 / HN スコアしきい値の **具体リスト** を user と確定する (要求定義 §11 TBD の解消)。

- cc:TODO 1.1.B.1 Hacker News API client
  - DoD:
    - `src/ai_newsletter/sources/hackernews.py`
    - `https://hacker-news.firebaseio.com/v0/topstories.json` → 上位 N (e.g. 200) → 各 item の score / title / url を取得
    - AI 関連語 (要 user 確認、初期案: `ai|llm|gpt|claude|gemini|agent|copilot|anthropic|openai|huggingface|rag|fine-tuning`) で title フィルタ
    - integration: respx で firebaseio mock、フィルタ後に AI 関連だけ残ること

- cc:TODO 1.1.B.2 GitHub trending client (Star 急増)
  - DoD:
    - `src/ai_newsletter/sources/github_trending.py`
    - GitHub Search API で `language:Python topic:llm-agent created:>N-days` 等 (条件 user 確認)
    - `data/github_stars.json` に前回スナップショット保存 → 差分で「24h Star 増加数」算出
    - 初回実行 (snapshot 未存在) は差分 0 として全件 baseline 化
    - integration: GitHub API mock、snapshot 差分計算の unit
    - **設計判断**: rate limit (60 req/h 認証なし、5000 req/h with token) → 認証必須化、`GH_TOKEN` Secrets 追加

- cc:TODO 1.1.B.3 Reddit client
  - DoD:
    - `src/ai_newsletter/sources/reddit.py`
    - 対象 subreddit (要 user 確認、初期案: `LocalLLaMA, MachineLearning, singularity, OpenAI, ClaudeAI`)
    - 各 subreddit の `top?t=day` から N 件、score / num_comments / title / url 取得
    - 認証: OAuth2 (script app), `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` / `REDDIT_USER_AGENT` Secrets
    - integration: respx で Reddit API mock

### C. 加工と配信 (分類 → スコア → 抽出 → 要約 → 投稿)

- cc:TODO 1.1.C.1 カテゴリ分類 + 除外フィルタ + スコアリング → 10件抽出
  - DoD:
    - `src/ai_newsletter/pipeline.py`
    - 分類: title/url keyword で AI開発ツール / AIエージェントTips / 新サービス / その他 にラベル付け
    - 除外: 宣伝色キーワード / 資金調達のみ / ガジェットレビュー の正規表現セット
    - スコアリング: source 別正規化 (HN score / GitHub Star差分 / Reddit upvote) → 重み付き合算
    - 配分制約: AI開発ツール 4 / Tips 4 / 新サービス 2 を満たすよう枠ごとに上位選択
    - 不足時: 候補数分だけ採用し、不足理由を log
    - unit: 与えた `RawItem` リストから配分通りの 10 件が返ること、除外語が落ちること

- cc:TODO 1.1.C.2 Gemini 3.5 Flash 要約 + 採用理由 + 信頼度生成
  - DoD:
    - `src/ai_newsletter/llm.py`
    - `google-genai` SDK 利用、`GEMINI_API_KEY` Secrets
    - 1 件ずつ呼ぶ: 入力 = title/url/summary_raw/source/score、出力 = `{summary_3lines, why_notable, dev_use_case, trust, reason, priority}` の JSON
    - JSON schema response config で構造化応答 (Gemini の structured output 利用)
    - 失敗時: 該当件を skip して log、配信は続行
    - integration: Gemini API mock、JSON schema パース成功

- cc:TODO 1.1.C.3 Block Kit で 1 投稿に 10 件整形 + 投稿
  - DoD:
    - `src/ai_newsletter/render.py` で Block Kit JSON を組み立て
    - 1 件あたり: タイトル (リンク付き header) / カテゴリ / 要約3行 / 注目理由 / 使いどころ / 定量 / 信頼度 / 採用理由 / 優先度 / フィードバック URL ボタン (v0.2 までは placeholder URL)
    - 投稿 size 上限 (50 blocks / message) を超える場合は分割
    - integration: render output が valid Block Kit schema (blocks 配列の形)
    - 手動: 開発 channel に実投稿してレイアウト確認

### D. 統合 + cron 有効化

- cc:TODO 1.1.D.1 entrypoint `scripts/daily.py` と Actions cron 起動
  - DoD:
    - `scripts/daily.py` = B クライアント並列 fetch → C パイプライン → Slack 投稿
    - `.github/workflows/daily.yml` を `cron: '0 22 * * *'` (UTC 22:00 = JST 07:00) で有効化、`workflow_dispatch` も残す
    - 失敗時: Actions log にスタックトレース、Slack エラー通知はしない (要求定義 §8)
    - E2E (手動): cron 時刻を一時的に近未来に変えて 1 回成功確認 → 元に戻す
  - 完了確認: 翌朝 07:00 JST に Slack へ 10 件届く

### E. 仕上げ

- cc:TODO 1.1.E.1 README にセットアップ・運用手順を追記
  - DoD:
    - 必要な Secrets 一覧 / 初回 setup 手順 / 手動再実行コマンド / フィードバック確認方法 (v0.1 では URL placeholder と明記)
    - 要求定義 §13 成功条件の現状を README にチェックリスト化

- cc:TODO 1.1.E.2 v0.1 動作レビューと振り返り
  - DoD:
    - 3 日連続配信ログ確認、配分・除外・要約品質の所感を `docs/v0.1-retrospective.md` に
    - v0.2 (フィードバック保存) に進むかの判断ポイントを整理

---

## (v0.2 以降 — 本 milestone 範囲外、参考)

- M2: Google Apps Script + Sheets でフィードバック保存
- M3: フィードバックをランキングに反映 (要求定義 §11 「フィードバック反映ロジック」TBD 解消)
- M4: 情報源スコア調整 / 除外キーワード強化

---

## 進捗マーカー凡例

`cc` で始まるマーカーで管理 (harness-work が更新):

| マーカー | 意味 |
|---|---|
| TODO  | 未着手 |
| WIP   | 着手中 (1 タスクに 1 つだけ) |
| 完了  | 完了 |

(凡例行を grep に拾わせないため bullet/コードブロック表記は避けている)
