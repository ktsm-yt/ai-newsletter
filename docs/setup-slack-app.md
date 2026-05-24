# Slack App セットアップ手順

ai-newsletter は Bot Token + `chat.postMessage` で Slack に投稿する。
個人用ワークスペースに Bot を 1 つ作って、配信先 channel に invite するだけ。

## 1. Slack App を作る

1. https://api.slack.com/apps → **Create New App** → **From scratch**
2. App Name: `ai-newsletter` / Workspace: 個人ワークスペースを選択
3. 左メニュー **OAuth & Permissions** → **Scopes** → **Bot Token Scopes** に以下を追加:
   - `chat:write` (必須: メッセージ投稿)
   - `chat:write.public` (推奨: invite なしで public channel に投稿可)
4. 同ページ上部 **Install to Workspace** → 承認
5. 表示された **Bot User OAuth Token** (`xoxb-...` で始まる) をコピー → `.env` の `SLACK_BOT_TOKEN` へ
   - `.env` がまだ無い場合: `cp env.example .env` してから埋める

> 後で scope を変えた時は再インストールが必要。

## 2. 配信先 channel を用意

1. Slack で配信先 channel を作る (例: `#ai-newsletter`、private でも public でも可)
2. private channel の場合 / `chat:write.public` を付けなかった場合:
   - channel 内で `/invite @ai-newsletter` を実行して Bot を招待
3. channel ID を控える:
   - Slack デスクトップで channel 名右クリック → **Copy link** → URL 末尾の `C` で始まる ID (例: `C0123ABCD45`)
   - `.env` の `SLACK_CHANNEL_ID` へ

## 3. 動作確認 (A.2 完了後に実行)

```bash
cd ~/Dev/ai-newsletter
uv sync
uv run python scripts/send_hello.py
```

設定した channel に `hello from ai-newsletter` が届けば OK。

## 4. GitHub Secrets 登録 (A.3 着手時)

`Settings → Secrets and variables → Actions → New repository secret` で以下を登録:

| Name | Value |
|---|---|
| `SLACK_BOT_TOKEN` | 手順 1 でコピーした `xoxb-...` |
| `SLACK_CHANNEL_ID` | 手順 2 で控えた `C...` |

## トラブルシュート

| エラー | 原因 / 対処 |
|---|---|
| `not_in_channel` | Bot が channel に invite されていない → `/invite @ai-newsletter` |
| `channel_not_found` | channel ID 間違い、または Bot から見えない private channel |
| `invalid_auth` | token が間違っているか revoke 済 → 再インストールして新 token を取得 |
| `missing_scope` | scope 不足 → OAuth ページで scope 追加 → 再インストール |
