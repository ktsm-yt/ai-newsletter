# ai-newsletter

毎朝 7:00 (JST) に、海外中心の AI 開発情報を 10 件に絞って Slack に日本語配信する個人用ニュースレター。

- 重点: AI 開発ツール / AI エージェント実装 Tips / 新サービス
- 除外: 投資・資金調達ニュース、一般向け AI ニュース、宣伝色の強い記事
- 構成: GitHub Actions (日次) + Python + Gemini 3.5 Flash + Slack Bot (chat.postMessage) + Google Apps Script + Sheets (フィードバック保存)

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

| サービス | 取得手順 | 使うタスク |
|---|---|---|
| Slack Bot Token | [docs/setup-slack-app.md](docs/setup-slack-app.md) | A.1 (MVP に必須) |
| Gemini API Key  | https://aistudio.google.com/apikey | C.2 |
| GitHub Token    | https://github.com/settings/tokens (fine-grained, `public_repo` 読み取り) | B.2 |
| Reddit OAuth    | https://www.reddit.com/prefs/apps で script app 作成 | B.3 |

取得した値は `.env` に記入する。GitHub Actions で動かすには、同じ値を repo の `Settings → Secrets and variables → Actions` にも登録する。

### 3. 動作確認 (各 task 完了時に追記される)

- A.2 完了: `uv run python scripts/send_hello.py` で Slack に hello 投稿
- D.1 完了: 毎朝 07:00 JST に Slack 配信

## 開発フロー

進捗管理は [Plans.md](Plans.md) を SSOT として `cc:TODO` / `cc:WIP` / `cc:完了` マーカーで追跡する。
要求定義 §13 成功条件の達成状況も Plans.md の E.1 で README にチェックリスト化予定。
