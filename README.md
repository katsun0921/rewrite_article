# rewrite_article

WordPress ドラフト記事を Google Doc に書き出し、リライト後に書き戻すワークフロー。

## フェーズ構成

WordPress ドラフト記事を Google Doc に書き出し、リライト後に書き戻すワークフロー。

| フェーズ    | 内容                             | ステータス     |
|---------|--------------------------------|-----------|
| Phase 1 | WP Draft → Google Doc           | ✅ 実装済み    |
| Phase 2 | Google Doc でリライト（手動）            | 手動作業      |
| Phase 3 | Google Doc → WP 書き戻し            | 未実装       |
| Phase 4 | 運用安定化・改善（Slack通知・重複ガード等）        | 未実装       |

## ショート動画自動化（応用機能）

WP 公開記事から TikTok / YouTube Shorts 向けの縦型ショート動画を自動生成する応用機能。
詳細は [実現可能性調査](docs/features/short_video_feasibility.md) を参照。

| フェーズ    | 内容                                         | ステータス     |
|---------|--------------------------------------------|-----------|
| S1      | WP公開記事 → 要約(Gemini) → 音声(Google TTS) → 字幕 → MP4 | ✅ PoC実装済み |
| S2〜S3   | Drive保管・品質向上                              | 未実装       |
| S4      | YouTube / TikTok 投稿自動化                      | 将来対応      |

## セットアップ

詳細は [仕様書](docs/features/spec.md) を参照。

### 必要な GitHub Secrets

| Secret 名                      | 説明                     |
|-------------------------------|------------------------|
| `WP_BASE_URL`                 | WordPress サイトURL                        |
| `WP_USERNAME`                 | WP管理ユーザー名                               |
| `WP_APP_PASSWORD`             | WPアプリパスワード（Application Password）        |
| `WP_BASIC_USER`               | サーバーレベル HTTP Basic 認証ユーザー名（任意）          |
| `WP_BASIC_PASSWORD`           | サーバーレベル HTTP Basic 認証パスワード（任意）          |
| `GDOC_FOLDER_ID`              | Google DriveフォルダID                      |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | GCPサービスアカウントJSONの中身                     |
| `GEMINI_API_KEY`              | ショート動画: 台本要約用 Gemini API キー（任意）         |
| `GOOGLE_TTS_API_KEY`          | ショート動画: Google Cloud TTS API キー（任意）      |

## ワークフロー

### Phase 1: WP Draft → Google Doc

```
GitHub Actions > WP Draft → Google Doc > Run workflow
```

| パラメータ     | 説明                      | デフォルト   |
|-----------|-------------------------|---------|
| `post_id` | 特定のPost IDを指定（空で全draft）   | 空       |
| `limit`   | 最大処理件数（最大20）              | `5`     |

### Phase 3: Google Doc → WP 書き戻し（未実装）

```
GitHub Actions > Google Doc → WP 書き戻し > Run workflow
```

## ディレクトリ構成

```
.
├── .github/
│   └── workflows/
│       ├── draft_to_gdoc.yml     # Phase 1
│       ├── gdoc_to_wp.yml        # Phase 3
│       └── post_to_short.yml     # ショート動画 S1 (PoC)
├── docs/
│   ├── features/
│   │   ├── spec.md               # リライト仕様書
│   │   └── short_video_feasibility.md  # ショート動画 実現可能性調査
│   └── prompts/
│       └── short_video_script.md # ショート動画 台本生成プロンプト
├── scripts/
│   ├── draft_to_gdoc.py          # Phase 1 スクリプト
│   ├── gdoc_to_wp.py             # Phase 3 スクリプト（未実装）
│   └── post_to_short.py          # ショート動画 S1 スクリプト
├── .gitignore
├── README.md
└── requirements.txt
```
