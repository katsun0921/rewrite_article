# Post → ショート動画自動化 実現可能性調査

**対象サイト**: katsumascore.blog
**作成日**: 2026-05-30
**最終更新**: 2026-05-30
**ステータス**: 調査フェーズ（実装前・方針確定済み）
**結論**: ✅ 技術的に実現可能。既存の WP 取得基盤をそのまま流用できる。

> **確定方針（2026-05-30）**
> 1. 入力は **公開済み(publish) の Post**。対象は **GitHub Actions の入力で指定**する。
> 2. 台本は **本文を LLM で要約**して生成する。
> 3. TTS は **予算重視で幅広く比較**（→ [コスト試算](#コスト試算)）。
> 4. スコープは **まず動画生成まで**。**将来的に投稿まで自動化**する（S4）。

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

**方針①により公開済み(publish)の Post を対象**とし、**GitHub Actions の入力(post_id)で指定**する。
`fetch_drafts()` を `fetch_posts(status="publish", post_id=...)` のように一般化するだけ。
`_fields` に `id,title,content,excerpt,featured_media` を指定すれば動画素材として十分。
アイキャッチ画像は `featured_media` → `/wp-json/wp/v2/media/{id}` で URL を取得できる。

### ② 台本生成 — ✅ 可能（任意）

**方針②により本文を LLM で要約して台本化する**。記事本文をそのまま読み上げると長すぎるため、
「冒頭2秒のフック → 本編 → CTA」の縦型動画フォーマット（約300〜400字／30〜50秒）に要約する。

要約用 LLM の料金比較（100万トークンあたり、入力/出力、2025〜2026時点）:

| モデル | 入力 | 出力 | 1本あたり概算 | 備考 |
|--------|------|------|--------------|------|
| **Gemini Flash** | $0.075 | $0.30 | **0.1円未満** | 最安クラス。要約に十分 |
| **GPT-4o mini** | $0.15 | $0.60 | 0.1円前後 | 安価・実績豊富 |
| **Claude Haiku 4.5** | $1 | $5 | 1円前後 | 日本語の質が高い |

1本の要約は入力 約3,000トークン（記事本文）+ 出力 約500トークン程度。
**どのモデルでも1本0.1〜1円**で、動画パイプライン全体のコストに対して誤差。

→ **推奨**: コスト最優先なら **Gemini Flash**、日本語の自然さ重視なら **Claude Haiku**。
プロンプトで「フック/本編/CTA」構成・文字数・口調を指定する。

### ③ 音声合成 (TTS) — ✅ 可能

日本語対応の主要 TTS を**料金込みで幅広く**比較（方針③に対応）。品質は概ね
**Azure ≳ Amazon Polly ≳ Google ＞ VOICEVOX**。料金は2025〜2026時点の公開情報。

| サービス | 日本語品質 | 料金（100万字あたり） | 無料枠 | 商用 | 備考 |
|---------|----------|---------------------|--------|------|------|
| **edge-tts**（非公式） | 高（Azure相当の音声） | **0円** | 実質無制限 | △グレー | Edge の TTS を叩く OSS。API キー不要。**規約上は個人利用想定**でレート制限あり |
| **VOICEVOX** | 中 | **0円**（自前ホスト） | 無制限 | ○ 要クレジット | キャラごとに規約差。**「VOICEVOX:ずんだもん」等のクレジット必須**。業務用途は VOICEVOX Nemo が無難 |
| **Google Cloud TTS (Neural2)** | 高 | **$16** | **月100万字無料** | ○ | アジア言語に強い。**既存 Google 連携と相性◎**。日本語は1文字=1カウント |
| **Google Cloud TTS (Standard)** | 中 | $4 | 月400万字無料 | ○ | 低コスト版 |
| **OpenAI TTS** | 高 | $15（HDは$30） | なし | ○ | API がシンプル |
| **Azure TTS (Neural)** | 最高クラス | $15（HDは$22） | あり（F0枠） | ○ | カスタムニューラル音声が強力 |
| **Amazon Polly (Neural)** | 高 | $16 | あり（12ヶ月） | ○ | 安定 |

**1本あたりの実コスト感**（台本 約300〜400字／本と仮定）:
- Google Neural2: 無料枠 **月100万字 ≒ 月2,500本**まで0円。超過後も1本 **約0.6円**。
- edge-tts / VOICEVOX: **0円**（ただし edge-tts は商用グレー、VOICEVOX はクレジット表記が必要）。

→ **推奨**:
- **PoC〜初期**: `edge-tts` または `VOICEVOX` で **0円検証**（個人利用・クレジット表記で運用）。
- **本番・商用が明確になったら**: **Google Cloud TTS (Neural2)** に切替。
  既存の Google 認証基盤を流用でき、月2,500本まで無料という圧倒的コスト効率。

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

確定方針（本文をLLM要約・publish記事・生成まで）を踏まえた実数ベースの試算。

| 項目 | 構成A（コスト最小） | 構成B（品質重視・商用） |
|------|-------------------|----------------------|
| 台本生成（LLM要約） | Gemini Flash（**0.1円未満**） | Claude Haiku（**約1円**） |
| TTS | edge-tts / VOICEVOX（**0円**） | Google Neural2（**月2,500本まで0円**／超過時1本約0.6円） |
| 字幕 | faster-whisper ローカル（0円） | 同左 |
| 動画合成 | FFmpeg（0円） | 同左 + ストック素材 API（任意） |
| 実行環境 | GitHub Actions 無料枠 | 同左 |
| **1本あたり概算** | **ほぼ 0円** | **約1〜2円** |

→ **金銭コストはほぼ無視できる**（月100本でも数百円以内）。
**真のボトルネックは費用ではなく「投稿クォータ/審査(将来のS4)」と「動画の質(視聴維持率)」**。

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

実現可能性は確認済み。確定方針に沿ってリスクの低い順に段階導入する。

| フェーズ | 内容 | 成果物 | 自動化度 |
|---------|------|--------|---------|
| **S1: 検証 PoC** | publish記事(指定ID) → LLM要約台本 → TTS → 字幕 → MP4 を Actions で生成 | `scripts/post_to_short.py`（最小版）+ `post_to_short.yml` | 動画生成のみ |
| **S2: Drive 連携** | 生成 MP4 を Drive に保管・Step Summary にリンク/プレビュー出力 | 既存 `_drive_service` 流用 | 生成+保管 |
| **S3: 品質向上** | LLM 台本プロンプト最適化・背景(アイキャッチ)・BGM・字幕スタイル | テンプレート整備 | 生成+保管 |
| **S4: 投稿自動化（将来）** | YouTube 自動投稿（クォータ内）→ TikTok（アプリ審査後） | OAuth(youtube.upload)拡張・投稿スクリプト | 投稿まで |

**方針④に従い S1〜S3（生成まで）を先に完成させ、S4（投稿）は将来対応**。
次の一手は **S1（PoC）**: GitHub Actions で post_id を渡し、要約→TTS→字幕→MP4 を1本生成して質を目視確認。

-----

## 判断待ち事項

基本方針は確定済み（冒頭参照）。残る詳細判断は以下。

| # | 事項 | 状態 | 結論/推奨 |
|---|------|------|----------|
| 1 | 入力 Post の対象 | ✅ 確定 | **公開(publish) + Actions入力でID指定** |
| 2 | 台本生成方式 | ✅ 確定 | **本文を LLM で要約** |
| 3 | 自動投稿の扱い | ✅ 確定 | **まず生成まで／将来 S4 で投稿** |
| 4 | **要約 LLM の選定**（Gemini Flash / GPT-4o mini / Claude Haiku） | ⏳ 未定 | PoC は Gemini Flash（最安）、質を見て Claude Haiku 検討 |
| 5 | **TTS の選定**（edge-tts/VOICEVOX 無料 vs Google Neural2） | ⏳ 未定 | PoC は無料(edge-tts/VOICEVOX)、商用化時に Google Neural2 |
| 6 | **背景素材の方針**（アイキャッチ流用 / ストック動画 / 単色） | ⏳ 未定 | PoC はアイキャッチ流用が最小 |
| 7 | **必要な API キーの追加**（LLM_API_KEY 等を GitHub Secrets へ） | ⏳ 未定 | 選定後に Secrets 登録 |

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
- [Google Cloud Text-to-Speech 料金](https://cloud.google.com/text-to-speech/pricing)
- [edge-tts (Microsoft Edge TTS の Python ラッパー)](https://github.com/rany2/edge-tts)
- [VOICEVOX は商用利用できるのか（利用規約解説）](https://blue-r.co.jp/blog-voicevox-commercial-use/)
- [LLM API Pricing Comparison 2025 (IntuitionLabs)](https://intuitionlabs.ai/articles/llm-api-pricing-comparison-2025)
- [OpenAI API Pricing](https://openai.com/api/pricing/)

-----

*本書は調査フェーズの記録。実装方針が固まり次第、`spec.md` と同様の実装仕様へ展開する。*
