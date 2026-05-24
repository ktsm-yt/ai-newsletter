# ai-newsletter

毎朝 7:00 (JST) に、海外中心の AI 開発情報を 10 件に絞って Slack に日本語配信する個人用ニュースレター。

- 重点: AI 開発ツール / AI エージェント実装 Tips / 新サービス
- 除外: 投資・資金調達ニュース、一般向け AI ニュース、宣伝色の強い記事
- 構成: GitHub Actions (日次 cron) + Python + Gemini (default `gemini-3.1-flash-lite`) + Slack Bot (chat.postMessage) + Google Apps Script + Sheets (フィードバック保存は v0.2 以降)

詳細な要求定義は [docs/requirements.md](docs/requirements.md) を参照。

## セットアップ

### 1. リポジトリと依存

```bash
git clone git@github.com:ktsm-yt/ai-newsletter.git
cd ai-newsletter
uv sync          # .venv 作成 + 依存 install
cp env.example .env
```

### 2. 各サービスの API キー

| サービス | 取得手順 | env 変数 |
|---|---|---|
| Slack Bot Token | [docs/setup-slack-app.md](docs/setup-slack-app.md) | `SLACK_BOT_TOKEN` / `SLACK_CHANNEL_ID` |
| Gemini API Key  | https://aistudio.google.com/apikey (無料枠で 1 日 10 件は余裕) | `GEMINI_API_KEY` (任意: `GEMINI_MODEL` で `gemini-2.5-flash` 等に切替可) |
| GitHub Token    | https://github.com/settings/tokens (fine-grained, `public_repo` 読み取り) | `GH_TOKEN` |
| Reddit OAuth    | https://www.reddit.com/prefs/apps で **script app** 作成 | `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` / `REDDIT_USER_AGENT` |

取得した値は `.env` に記入する。GitHub Actions で動かすには、同じ値を repo の `Settings → Secrets and variables → Actions → Secrets` にも登録する (Secrets 名は env 変数名と同じで OK)。

`GEMINI_MODEL` を `gemini-3.1-flash-lite` に切り替えたい場合は Secrets ではなく `Variables` 側に登録する (workflow が `vars.GEMINI_MODEL` を参照)。

### 3. ローカル動作確認

```bash
uv run python scripts/send_hello.py  # Slack に hello 投稿 (Slack token のみ必要)
uv run python scripts/daily.py        # 本番と同じパイプラインをローカルで走らせる
uv run pytest                          # 全 unit / integration test
```

## 運用

### スケジュール

`.github/workflows/daily.yml` が **UTC 22:00 = JST 07:00** に cron 起動して `scripts/daily.py` を走らせる。
手動再実行は `Actions` タブの `daily` workflow → `Run workflow`。

### 失敗時

- 取得・要約・配信のいずれかで例外が出ても、要件 §8 に従って Slack へのエラー通知はしない
- Actions の run ログにスタックトレースが残る → 失敗 run を開いて確認
- 1 source (HN/GitHub/Reddit) の fetch 失敗は warn log のみで、他 source からの配信は続行

### 状態保存

- GitHub trending の Star スナップショット (`data/github_stars.json`) は **Actions cache** に永続化される (git commit しない)
- 初回 run はベースライン化のみで配信 0 件、2 回目以降から Star 増分で評価
- 1 週間以上 run しないと cache が消えて再ベースライン

### フィードバック

v0.1 ではボタン URL が placeholder (`https://example.com/feedback?...`) で、押しても何も起きない。
v0.2 (M2) で Google Apps Script の Web App URL に差し替え、Sheets に記録するようになる。

## 要件 §13 成功条件チェックリスト

| 成功条件 | 状態 |
|---|---|
| 毎日 7:00 に Slack へ配信される | ⏳ D.1 完了、初回 cron 実行待ち |
| 10 件中 8 件が AI 開発ツールまたは AI エージェント実装 Tips | ✅ pipeline 配分制約 (devtool 4 + tips 4 + service 2) |
| 各ニュースに要約・注目理由・使いどころ・信頼度・採用理由・リンク | ✅ render.py で固定レイアウト |
| 投資・資金調達/一般 AI/宣伝が明確に減る | ✅ pipeline.is_excluded で除外、運用しながらキーワード調整 |
| 1 日の情報収集時間が 10 分以下 | ⏳ 3 日連続配信後に体感計測 (E.2) |
| フィードバックがスプレッドシートに残る | ❌ v0.2 (M2) で実装予定 |
| 1〜2 週間後に合う/合わない情報源が見える | ❌ v0.3 (M3) でフィードバック反映ロジック |

## 開発フロー

進捗管理は [Plans.md](Plans.md) を SSOT として `cc:TODO` / `cc:WIP` / `cc:完了` マーカーで追跡する。
