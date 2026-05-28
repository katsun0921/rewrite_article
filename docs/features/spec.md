# ブログリライト仕組み 仕様書

**対象サイト**: katsumascore.blog  
**最終更新**: 2026-05-28  
**ステータス**: Phase 1 実装済み

-----

## 目次

1. [システム全体像](#システム全体像)
1. [フェーズ別 TODO](#フェーズ別-todo)
1. [Phase 1: WP Draft → Google Doc](#phase-1-wp-draft--google-doc)
1. [Phase 2: Google Doc でリライト（手動）](#phase-2-google-doc-でリライト手動)
1. [Phase 3: Google Doc → WP 書き戻し](#phase-3-google-doc--wp-書き戻し)
1. [Phase 4: 運用安定化・改善](#phase-4-運用安定化改善)
1. [データ仕様](#データ仕様)
1. [判断待ち事項](#判断待ち事項)

-----

## システム全体像

```
┌─────────────────────────────────────────────────────┐
│  GitHub Actions                                     │
│                                                     │
│  [Phase 1]                      [Phase 3]           │
│  draft_to_gdoc.py               gdoc_to_wp.py       │
│       │                               │             │
└───────┼───────────────────────────────┼─────────────┘
        │                               │
        ▼                               ▼
┌──────────────┐              ┌──────────────────────┐
│  WordPress   │              │  WordPress           │
│  REST API    │◄─────────────│  REST API (PATCH)    │
│  (GET draft) │              │  + AIOSEO API        │
└──────────────┘              └──────────────────────┘
        │                               ▲
        ▼                               │
┌──────────────────────────────────────┤
│  Google Drive                        │
│                                      │
│  [リライトフォルダ]                   │
│  [リライト] タイトル (ID:xxx).gdoc   │
│       │                              │
│       ▼                              │
│  [Phase 2: 手動記入]  ───────────────┘
└──────────────────────────────────────┘
```

**対象フィールド（WP標準 `post` タイプ）**

| フィールド                | 取得元                      | 書き戻し先                         |
|------------------------|--------------------------|-------------------------------|
| `excerpt`（日本語）        | WP REST API              | WP REST API PATCH             |
| `excerpt`（英語）         | ACF `excerpt_en`         | ACF `excerpt_en`              |
| SEO Description（日本語）  | AIOSEO API / ACF         | AIOSEO API or wp_aioseo_posts |
| SEO Description（英語）   | ACF `seo_description_en` | ACF `seo_description_en`      |
| `tagline`              | ACF `tagline`            | ACF `tagline`                 |

-----

## フェーズ別 TODO

### Phase 1: WP Draft → Google Doc ✅ 実装済み

- [x] WP REST API で `draft` を取得する
- [x] AIOSEO REST API でSEOメタを取得する（失敗時フォールバック）
- [x] HTML テンプレートを生成する
- [x] Drive API で Google Doc として保存する
- [x] GitHub Actions Step Summary にリンクを出力する
- [ ] **初回セットアップ**（→ [セットアップ手順](#セットアップ手順)）
  - [ ] GCPサービスアカウント作成・JSONキー発行
  - [ ] Drive APIを有効化
  - [ ] リライトフォルダにサービスアカウントを「編集者」で追加
  - [ ] GitHub Secrets 5件を登録
  - [ ] 動作確認（特定Post IDで1件テスト）

### Phase 2: Google Doc でリライト（手動）

- [ ] **Doc 記入ルールの確定**（→ [記入ルール仕様](#記入ルール仕様)）
  - [ ] 「▼ リライト後」の直後の段落が書き戻し対象と確定する
  - [ ] 完了マーカーの形式を決める（例: タイトルに `[完了]` プレフィックスを付ける）
- [ ] **フォルダ運用ルールの確定**
  - [ ] 未着手 / 作業中 / 完了 のサブフォルダ分けをするか決める
  - [ ] Doc の命名規則を確認・必要なら変更する

### Phase 3: Google Doc → WP 書き戻し

- [ ] `scripts/gdoc_to_wp.py` を実装する（→ [Phase 3 仕様](#phase-3-仕様)）
  - [ ] Drive API で Doc のテキストを取得する
  - [ ] フィールドをパースする（「▼ リライト後」の次の段落を抽出）
  - [ ] WP REST API PATCH で `excerpt` を更新する
  - [ ] ACF REST API で `excerpt_en` / `seo_description_en` / `tagline` を更新する
  - [ ] AIOSEO への書き戻し方法を決定・実装する（→ [判断待ち](#判断待ち事項)）
- [ ] `.github/workflows/gdoc_to_wp.yml` を実装する
- [ ] 書き戻し後に WP の post status を `draft` → `draft`（変更なし）とするか `pending` にするか決める
- [ ] 書き戻し済みの Doc にマーカーを付ける（タイトル変更 or Doc プロパティ）

### Phase 4: 運用安定化・改善

- [ ] 未完了フィールドがある場合のアラート（Step Summary への警告出力）
- [ ] Doc のフォルダ自動移動（完了後に「完了」フォルダへ移動）
- [ ] Slack 通知（Doc作成完了・書き戻し完了）
- [ ] エラー時の Retry ロジック（Drive API の一時エラー対策）
- [ ] 重複実行ガード（同じ Post ID の Doc が既に存在する場合はスキップ）

-----

## Phase 1: WP Draft → Google Doc

### セットアップ手順

**1. GCP サービスアカウント**

```
Google Cloud Console
→ IAM と管理 > サービス アカウント
→ 新しいサービスアカウントを作成
→ ロール: なし（Driveのみ使用するので不要）
→ キーを作成（JSON）→ ダウンロード
```

**2. Drive API を有効化**

```
Google Cloud Console
→ APIとサービス > ライブラリ
→ "Google Drive API" を検索して有効化
```

**3. リライトフォルダの共有設定**

```
Google Drive でリライトフォルダを作成
→ フォルダを右クリック > 共有
→ サービスアカウントのメール（xxx@xxx.iam.gserviceaccount.com）を追加
→ 権限: 編集者
```

**4. GitHub Secrets の登録**

| Secret 名                      | 値                           |
|-------------------------------|---------------------------|
| `WP_BASE_URL`                 | `https://katsumascore.blog` |
| `WP_USERNAME`                 | WP管理ユーザー名                   |
| `WP_APP_PASSWORD`             | WPアプリパスワード                  |
| `GDOC_FOLDER_ID`              | DriveフォルダのURL末尾のID          |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | サービスアカウントJSONの中身をそのままペースト   |

**5. 動作確認**

```
GitHub Actions > WP Draft → Google Doc > Run workflow
→ Post ID に既知の draft ID を入力
→ Step Summary に Doc リンクが出力されることを確認
→ Doc の内容・構造を目視確認
```

### GitHub Actions パラメータ

| パラメータ     | 型      | デフォルト     | 説明            |
|-----------|------|---------|-------------|
| `post_id` | string | 空（全draft） | 特定のPost IDを指定 |
| `limit`   | string | `5`     | 最大処理件数（最大20）  |

-----

## Phase 2: Google Doc でリライト（手動）

### 記入ルール仕様

Doc の各フィールドセクションは以下の構造になっている。

```
【見出し3】フィールド名
▼ 現在値  （現在 N 字）
[現在の本文]

▼ リライト後　目安: ○○字
[← ここに記入する段落]
```

**記入ルール（確定前の案）**

- `▼ リライト後` の直後の段落（空白段落は飛ばす）を書き戻し対象とする
- 記入しないフィールドは空白のままにする（書き戻しスクリプトはスキップ）
- 完了したら Doc タイトルの先頭に `[完了]` を付ける

> ⚠️ **判断待ち**: 記入ルールを変更する場合は Phase 3 のパーサーに影響する。Phase 3 実装前に確定すること。

### フォルダ運用（案）

```
リライト（ルートフォルダ）
├── 未着手/
├── 作業中/
└── 完了/
```

書き戻しスクリプトが完了フォルダへ自動移動する（Phase 4）。  
シンプルに1フォルダで運用する案もあり（Phase 3 実装後に判断）。

-----

## Phase 3: Google Doc → WP 書き戻し

### Phase 3 仕様

**スクリプト**: `scripts/gdoc_to_wp.py`  
**ワークフロー**: `.github/workflows/gdoc_to_wp.yml`

#### 入力

| パラメータ     | 説明                              |
|---------|-------------------------------|
| `doc_id`  | Google Doc の ID（URLの `/d/ここ/`）  |
| `post_id` | 書き戻し先の WP Post ID               |
| `dry_run` | `true` にすると WP への書き込みをスキップ（確認用） |

#### 処理フロー

```python
# 1. Doc のコンテンツを取得
#    Drive API: files().export(mimeType="text/plain")
#    または Docs API: documents().get()

# 2. フィールドをパース
#    「▼ リライト後」の次の空でない段落を抽出
#    フィールドごとに辞書化
#    {
#      "excerpt_ja":    "...",
#      "excerpt_en":    "...",
#      "seo_desc_ja":   "...",
#      "seo_desc_en":   "...",
#      "tagline":       "...",
#    }

# 3. バリデーション
#    excerpt_ja: 140〜150字チェック（警告のみ、エラーにはしない）
#    excerpt_en: 70〜80 words チェック（警告のみ）
#    空フィールドはスキップ（書き戻さない）

# 4. WP REST API PATCH
#    PATCH /wp-json/wp/v2/posts/{post_id}
#    body: { "excerpt": excerpt_ja }

# 5. ACF REST API PATCH
#    PATCH /wp-json/wp/v2/posts/{post_id}
#    body: { "acf": { "excerpt_en": ..., "seo_description_en": ..., "tagline": ... } }

# 6. AIOSEO 書き戻し（→ 判断待ち）

# 7. Doc タイトルを "[書き戻し済み]" に変更
#    Drive API: files().update(body={"name": "[書き戻し済み] ..."})
```

#### Docs API vs Drive export の選択

| 方法                                 | メリット             | デメリット          |
|------------------------------------|----------------|--------------|
| `Docs API documents().get()`       | 段落構造を正確に取得できる    | レスポンスが複雑（JSON） |
| `Drive files().export(text/plain)` | シンプルなテキストで処理しやすい | スタイル情報が失われる    |

→ **推奨**: `Drive files().export(text/plain)` でテキスト取得後、行単位でパース。  
Docの構造がシンプルなので十分。

#### AIOSEO 書き戻し方法（要調査）

| 方法                   | 概要                                        | 採用可否                |
|--------------------|-------------------------------------------|-------------------|
| AIOSEO REST API POST | `/wp-json/aioseo/v1/posts/{id}` への POST   | 要検証（Pro限定機能かも）      |
| WP REST API meta   | `meta: { _aioseo_description: "..." }`    | `register_meta` が必要 |
| 直接 SQL              | `wp_aioseo_posts` へ UPDATE                | 確実だがDB直アクセスが必要      |
| カスタムエンドポイント          | WP側に `wp-json/katsumascore/v1/aioseo` を追加 | 工数あるが最もクリーン         |

> ⚠️ **判断待ち**: どの方法で AIOSEO に書き戻すか。現在のパイプライン（`draft_to_gdoc.py` 前身）がSQLを使っているなら、同じアプローチでカスタムエンドポイントを作るのが最も一貫性がある。

-----

## Phase 4: 運用安定化・改善

### 重複実行ガード

```python
# Doc作成前に同名ファイルが存在するかチェック
existing = drive.files().list(
    q=f"name='{doc_title}' and '{GDOC_FOLDER_ID}' in parents and trashed=false",
    fields="files(id,webViewLink)"
).execute()

if existing["files"]:
    print(f"⚠️  既存のDocが見つかりました: {existing['files'][0]['webViewLink']}")
    # スキップ or 上書き or エラー（要判断）
```

### Slack 通知（案）

```yaml
- name: Slack通知
  if: always()
  uses: slackapi/slack-github-action@v1
  with:
    payload: |
      {
        "text": "📄 リライトDoc作成完了: ${{ steps.run.outputs.count }}件",
        "attachments": [{ "text": "${{ steps.run.outputs.links }}" }]
      }
  env:
    SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
```

-----

## データ仕様

### Google Doc 命名規則

```
[リライト] {post_title} (ID:{post_id})
例: [リライト] 映画「ドライブ・マイ・カー」感想 (ID:12345)
```

完了後:

```
[書き戻し済み] 映画「ドライブ・マイ・カー」感想 (ID:12345)
```

### WP REST API 認証

アプリパスワード（Application Password）を使用。  
`Authorization: Basic base64(username:app_password)` ヘッダーを付与。

`ACF REST API` は ACF Pro の「REST API」設定が ON の場合のみ有効。

### フィールドマッピング

| Google Doc セクション      | WP/ACFフィールド                   | バリデーション         |
|---------------------|------------------------------|---------------|
| 抜粋（excerpt）— 日本語     | `post.excerpt`               | 140〜150字（警告）    |
| 抜粋（excerpt）— 英語      | `acf.excerpt_en`             | 70〜80 words（警告） |
| SEO Description — 日本語 | `wp_aioseo_posts.description` | 120字前後（警告）      |
| SEO Description — 英語  | `acf.seo_description_en`     | 160 chars（警告）   |
| Tagline             | `acf.tagline`                | なし              |

-----

## 判断待ち事項

| # | 事項                                                     | 影響フェーズ     | 優先度 |
|---|------------------------------------------------------|----------|---|
| 1 | **AIOSEO 書き戻し方法**（REST API / meta / SQL / カスタムエンドポイント） | Phase 3  | 高   |
| 2 | **記入ルールの確定**（「▼ リライト後」の次の段落 = 書き戻し対象 でよいか）             | Phase 2, 3 | 高   |
| 3 | **書き戻し後の post_status**（`draft` のまま vs `pending`）       | Phase 3  | 中   |
| 4 | **フォルダ運用**（サブフォルダ分け vs 1フォルダ）                          | Phase 2, 4 | 低   |
| 5 | **重複実行時の挙動**（スキップ / 上書き / エラー）                         | Phase 1, 4 | 低   |

-----

*このドキュメントは実装進行に合わせて随時更新する。*
