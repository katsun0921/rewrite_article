# Post → ショート動画自動化 実現可能性調査

**対象サイト**: katsumascore.blog
**作成日**: 2026-05-30
**ステータス**: 調査フェーズ（実装前）
**結論**: ✅ 技術的に実現可能。既存の WP 取得基盤をそのまま流用できる。

-----

## 目次

1. [背景・ゴール](#背景ゴール)
2. [結論サマリ](#結論サマリ)
3. [既存資産の再利用](#既存資産の再利用)
4. [パイプライン全体像](#パイプライン全体像)
5. [構成要素ごとの実現性調査](#構成要素ごとの実現性調査)
6. [プラットフォーム別 自動投稿の壁](#プラットフォーム別-自動投稿の壁)
7. [コスト試算](#コスト試算)
8. [想定リスク・制約](#想定リスク制約)
9. [推奨フェーズ計画](#推奨フェーズ計画)
10. [判断待ち事項](#判断待ち事項)
11. [参考リンク](#参考リンク)

-----

## 背景・ゴール

既存の「ブログリライト仕組み」(`scripts/draft_to_gdoc.py`) は WP REST API から
Post を取得して Google Doc を生成している。この **「WP から Post を取得する仕組み」を応用**し、
Post の内容を素材として **TikTok / YouTube Shorts 向けの縦型ショート動画 (9:16, 60秒以内)** を
自動生成するパイプラインを構築したい。

まず本書で「実現可能か」を技術的に検証する。

-----

## 結論サマリ

| 観点 | 判定 | 補足 |
|------|------|------|
| Post の取得 | ✅ 実装済み | `fetch_drafts()` をほぼそのまま流用可能 |
| 台本(スクリプト)生成 | ✅ 可能 | LLM API で記事本文 → 縦型動画用の短い台本へ要約 |
| 音声合成 (TTS) | ✅ 可能 | 日本語対応の TTS が複数あり（VOICEVOX / Google / Azure / OpenAI） |
| 字幕生成 | ✅ 可能 | Whisper で音声→単語レベルのタイムスタンプ→ASS/SRT |
| 動画合成 | ✅ 可能 | FFmpeg / MoviePy で背景 + 音声 + 字幕を 9:16 で合成 |
| 成果物の保管 | ✅ 可能 | 既存の Google Drive 連携を流用 |
| YouTube Shorts へ自動投稿 | ⚠️ 条件付き可 | Data API v3 で可能。ただし**1日約6本**のクォータ制限 |
| TikTok へ自動投稿 | ⚠️ 審査必須 | Content Posting API の**アプリ審査通過まで非公開限定** |

→ **動画生成までは完全自動化が現実的**。自動「投稿」はプラットフォーム規約・審査・クォータが
ネックになるため、初期は「**動画ファイル生成 + Drive保管 → 手動アップロード**」が安全。

-----

## 既存資産の再利用

新機能は既存パイプラインの基盤をほぼそのまま流用できる。これが「実現可能」の最大の根拠。

| 既存の仕組み | 場所 | 動画機能での再利用 |
|------------|------|------------------|
| WP REST API 認証セッション | `draft_to_gdoc.py: _make_wp_session()` | そのまま流用 |
| Post 取得 | `draft_to_gdoc.py: fetch_drafts()` | `status` を `publish` 等に変えて流用 |
| HTML タグ除去 | `draft_to_gdoc.py: _strip_html()` | 本文クリーニングに流用 |
| Google Drive 認証 (OAuth/SA) | `draft_to_gdoc.py: _drive_service()` | 動画ファイルの保管先として流用 |
| GitHub Actions 実行基盤 | `.github/workflows/draft_to_gdoc.yml` | 同じ手動トリガー構成を流用 |
| Step Summary 出力 | `draft_to_gdoc.py: main()` | 生成結果リンクの出力に流用 |

差分として新たに必要なのは **台本生成・TTS・動画合成・(任意で)投稿** の各ステップのみ。

-----

## パイプライン全体像

```
┌──────────────────────────────────────────────────────────────┐
│  GitHub Actions (post_to_short.yml)                          │
│                                                              │
│  scripts/post_to_short.py                                    │
└──────────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────┐   ① WP REST API で Post を取得（既存 fetch を流用）
│  WordPress   │      GET /wp-json/wp/v2/posts?include={id}
│  REST API    │      → title / content / excerpt
└──────────────┘
        │
        ▼
┌──────────────┐   ② 台本生成（LLM）
│  LLM API     │      記事本文 → 30〜50秒で読める縦型動画用の台本
│ (任意)        │      フック / 本編 / CTA の構成に要約
└──────────────┘
        │
        ▼
┌──────────────┐   ③ 音声合成（TTS）
│  TTS API     │      台本テキスト → ナレーション音声 (mp3/wav)
└──────────────┘
        │
        ▼
┌──────────────┐   ④ 字幕生成（Whisper）
│  Whisper     │      音声 → 単語レベルのタイムスタンプ → ASS/SRT
└──────────────┘
        │
        ▼
┌──────────────┐   ⑤ 動画合成（FFmpeg / MoviePy）
│  FFmpeg      │      背景(画像/動画/アイキャッチ) + 音声 + 字幕
│              │      → 9:16 縦型 MP4 (60秒以内)
└──────────────┘
        │
        ├─────────────▶ ⑥ Google Drive に保管（既存連携を流用）
        │
        └─────────────▶ ⑦ (任意) YouTube / TikTok へ投稿
                          ※ 初期は手動アップロード推奨
```

-----

## 構成要素ごとの実現性調査

### ① Post 取得 — ✅ 実装済み

`fetch_drafts()` の `status` を `publish` に変える、あるいは引数化するだけ。
`_fields` に `id,title,content,excerpt,featured_media` を指定すれば動画素材として十分。
アイキャッチ画像は `featured_media` → `/wp-json/wp/v2/media/{id}` で URL を取得できる。

### ② 台本生成 — ✅ 可能（任意）

記事本文は長すぎるため、そのまま読み上げると動画が長くなる。LLM で
「冒頭2秒のフック → 本編 → CTA」の縦型動画フォーマットに要約するのが定石。
本リポジトリは既に Claude/LLM 連携の文脈があるため、Anthropic API 等で実装可能。
※ LLM を使わず「`excerpt` をそのまま読み上げる」最小構成も可能。

### ③ 音声合成 (TTS) — ✅ 可能

日本語対応の主要 TTS を調査。品質評価では概ね **Azure ≳ Amazon Polly ≳ Google ＞ VOICEVOX**。

| サービス | 日本語品質 | コスト | 備考 |
|---------|----------|--------|------|
| **VOICEVOX** | 中（やや不自然な場合あり） | 基本無料 | ローカル/自前ホスト。キャラ音声豊富。**商用は音声ごとにライセンス確認必須** |
| **Google Cloud TTS** | 高 | 従量（無料枠あり） | アジア言語に強い。既存の Google 連携と相性◎ |
| **Azure TTS** | 最高クラス | 従量 | カスタムニューラル音声が強力 |
| **Amazon Polly** | 高 | 従量 | 安定 |
| **OpenAI TTS** | 高 | 従量 | API がシンプル |

→ **既に Google 認証基盤がある**ため、初手は **Google Cloud TTS** が導入コスト最小。
コストゼロ重視なら VOICEVOX（商用ライセンス要確認）。

### ④ 字幕生成 — ✅ 可能

ショート動画は字幕がほぼ必須。OpenAI **Whisper**（または faster-whisper）で
TTS 音声を文字起こしし、**単語レベルのタイムスタンプ**を取得 → カラオケ風字幕 (ASS) を生成する
構成が一般的。台本テキストが手元にあるので、強制アラインメントで精度を上げることも可能。

### ⑤ 動画合成 — ✅ 可能

**FFmpeg** が事実上の標準。Python からは **MoviePy** 経由か FFmpeg 直叩き。
- 背景: アイキャッチ画像のズーム(Ken Burns) / 単色 + テキスト / ストック動画(Pexels API 等)
- 音声トラック + 字幕焼き込み (ASS) を合成し **9:16 / 1080×1920 / 60秒以内**の MP4 を出力
- GitHub Actions の ubuntu ランナーには FFmpeg がプリインストール済みで追加導入容易

OSS の先行事例が多数あり（short-maker, Viral-Faceless-Shorts-Generator,
youtube-shorts-pipeline 等）、設計の参考にできる。

### ⑥ 保管 — ✅ 可能

生成 MP4 を既存の `_drive_service()` で Drive にアップロード（`upload_gdoc` を
動画 MIME 用に一般化するだけ）。GitHub Actions の artifact としても残せる。

-----

## プラットフォーム別 自動投稿の壁

ここが「完全自動化」の最大の論点。**動画生成は容易だが、自動投稿は規約・審査・クォータが壁**。

### YouTube Shorts — ⚠️ 条件付きで自動投稿可

- 専用の Shorts API は無い。**Data API v3 の `videos.insert`** で通常動画として投稿し、
  9:16・60秒以内・タイトル/説明に `#Shorts` を付ければ Shorts 扱いになる。
- **OAuth 2.0**（`youtube.upload` スコープ）が必要 → 既存の Google OAuth 基盤を拡張可能。
- **クォータ制約が厳しい**: デフォルト 1日 10,000 ユニット。`videos.insert` は **1回1,600ユニット**
  → **実質 1日約6本まで**。増枠は無料申請可能だが審査あり。
- レジューマブルアップロードでリトライ対応すれば自動化に向く。

### TikTok — ⚠️ アプリ審査が必須

- **Content Posting API** の Direct Post で投稿可能だが、`video.publish` スコープの**アプリ審査が必須**。
- **審査通過まで投稿は「非公開(private)」限定**。一般公開にはコンプライアンス監査が必要（数日〜2週間）。
- 投稿前に**ユーザーの明示同意・プレビュー表示・音源利用規約への同意**が UI 要件として求められる
  → 完全無人での自動公開は規約上ハードルが高い。
- レート上限: Direct Post で **1アカウント24時間あたり約15本**まで。

→ **推奨**: 初期は自動投稿を組み込まず、**MP4 を生成して Drive/artifact に保管 → 人間が確認して手動アップロード**。
投稿自動化は需要が固まってから Phase 化する。

-----

## コスト試算（1本あたり、目安）

| 項目 | 構成A（コスト最小） | 構成B（品質重視） |
|------|-------------------|------------------|
| 台本生成 | excerpt 流用（0円） | LLM 要約（数円） |
| TTS | VOICEVOX 自前（0円） | Google/Azure TTS（数円〜） |
| 字幕 | faster-whisper ローカル（0円） | 同左 |
| 動画合成 | FFmpeg（0円） | 同左 + ストック素材 API |
| 実行環境 | GitHub Actions 無料枠 | 同左 |
| **概算** | **ほぼ 0円** | **1本あたり 数円〜十数円** |

→ 金銭コストは小さい。**ボトルネックは費用より「投稿クォータ/審査」と「動画の質(視聴維持)」**。

-----

## 想定リスク・制約

1. **GitHub Actions の実行時間/リソース**: FFmpeg レンダリングは CPU 負荷が高い。
   60秒動画なら無料ランナーで処理可能だが、本数が増えると実行時間に注意。
2. **TTS 商用ライセンス**: VOICEVOX は音声キャラごとに商用条件が異なる。要個別確認。
3. **著作権/素材**: 背景動画・BGM・画像の権利処理。ストック素材は API のライセンス遵守。
4. **プラットフォーム規約**: 自動生成・自動投稿コンテンツへの各社ポリシー。スパム判定リスク。
5. **品質担保**: 機械生成のイントネーション・字幕ズレ。公開前レビュー工程を推奨。
6. **依存追加**: `ffmpeg`/`moviepy`/`openai-whisper` 等で `requirements.txt` が肥大化。

-----

## 推奨フェーズ計画

実現可能性は確認済み。リスクの低い順に段階導入する。

| フェーズ | 内容 | 成果物 | 自動化度 |
|---------|------|--------|---------|
| **S1: 検証 PoC** | 1記事 → 台本 → TTS → 字幕 → MP4 をローカル/Actions で生成 | `scripts/post_to_short.py`（最小版） | 動画生成のみ |
| **S2: Drive 連携** | 生成 MP4 を Drive に保管・Step Summary にリンク出力 | 既存 `_drive_service` 流用 | 生成+保管 |
| **S3: 品質向上** | LLM 台本最適化・背景/BGM・字幕スタイル | テンプレート整備 | 生成+保管 |
| **S4: 投稿(任意)** | YouTube 自動投稿（クォータ内）／TikTok は審査後 | OAuth 拡張・投稿スクリプト | 投稿まで |

まずは **S1（PoC）** を 1 本作り、生成された動画の質を目視確認するのが次の一手。

-----

## 判断待ち事項

| # | 事項 | 影響 | 推奨 |
|---|------|------|------|
| 1 | **入力 Post の対象**（公開記事 / 特定ID / カテゴリ） | S1 | 特定 ID で PoC |
| 2 | **台本生成に LLM を使うか**（excerpt 流用 vs LLM 要約） | S1/S3 | PoC は excerpt、後で LLM |
| 3 | **TTS の選定**（VOICEVOX 無料 vs Google/Azure 有料高品質） | S1 | 既存基盤の Google から試す |
| 4 | **自動投稿まで踏み込むか**（生成のみ vs 投稿まで） | S4 | 初期は生成のみ（手動投稿） |
| 5 | **背景素材の方針**（アイキャッチ流用 vs ストック動画 vs 単色） | S3 | PoC はアイキャッチ流用 |

-----

## 参考リンク

- [AI-Driven Automated Short-Form Video Generation using Python (SSRN, 2025)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5755703)
- [short-maker (FFmpeg + gTTS で縦型動画自動生成)](https://github.com/Hukasx0/short-maker)
- [Viral-Faceless-Shorts-Generator](https://github.com/Dark2C/Viral-Faceless-Shorts-Generator)
- [youtube-shorts-pipeline (script→broll→TTS→captions→upload)](https://github.com/rushindrasinha/youtube-shorts-pipeline)
- [How to generate and add subtitles using Python, Whisper, FFmpeg (DigitalOcean)](https://www.digitalocean.com/community/tutorials/how-to-generate-and-add-subtitles-to-videos-using-python-openai-whisper-and-ffmpeg)
- [YouTube Data API: Quota and Compliance Audits](https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits)
- [YouTube 経由のアップロード手順 (2025, Medium)](https://medium.com/@dorangao/from-zero-to-first-upload-a-from-scratch-guide-to-publishing-videos-to-youtube-via-api-2025-73251a9324bd)
- [TikTok Content Posting API - Direct Post Reference](https://developers.tiktok.com/doc/content-posting-api-reference-direct-post)
- [TikTok Content Posting API - Get Started](https://developers.tiktok.com/doc/content-posting-api-get-started)
- [音声合成サービス比較検証 (Future 技術ブログ)](https://future-architect.github.io/articles/20230620a/)
- [Best TTS APIs in 2026 (Speechmatics)](https://www.speechmatics.com/company/articles-and-news/best-tts-apis-in-2025-top-12-text-to-speech-services-for-developers)

-----

*本書は調査フェーズの記録。実装方針が固まり次第、`spec.md` と同様の実装仕様へ展開する。*
