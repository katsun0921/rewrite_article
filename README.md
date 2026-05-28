# rewrite_article

WordPress ドラフト記事を Google Doc に書き出し、リライト後に書き戻すワークフロー。

## フェーズ構成

| フェーズ    | 内容                             | ステータス     |
|---------|--------------------------------|-----------|
| Phase 1 | WP Draft → Google Doc           | ✅ 実装済み    |
| Phase 2 | Google Doc でリライト（手動）            | 手動作業      |
| Phase 3 | Google Doc → WP 書き戻し            | 未実装       |
| Phase 4 | 運用安定化・改善（Slack通知・重複ガード等）        | 未実装       |

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
│       └── gdoc_to_wp.yml        # Phase 3
├── docs/
│   └── features/
│       └── spec.md               # 仕様書
├── scripts/
│   ├── draft_to_gdoc.py          # Phase 1 スクリプト
│   └── gdoc_to_wp.py             # Phase 3 スクリプト（未実装）
├── .gitignore
├── README.md
└── requirements.txt
```
