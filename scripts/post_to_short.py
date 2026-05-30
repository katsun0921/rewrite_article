"""
S1 (PoC): WordPress 公開記事 → ショート動画 (9:16 MP4)

WP REST API で公開済み Post を取得し、本文を Gemini で台本に要約、
Google Cloud TTS で音声化、アイキャッチ画像を背景にした縦型動画を FFmpeg で生成する。

パイプライン:
  ① WP REST API で publish 記事を取得（draft_to_gdoc.py の仕組みを応用）
  ② Gemini Flash で本文 → 縦型動画用の台本（フック/本編/CTA）に要約
  ③ Google Cloud TTS (Neural2 ja-JP) で台本 → ナレーション音声
  ④ 台本を句読点で分割し音声長に比例配分 → ASS 字幕
  ⑤ アイキャッチ画像を Ken Burns(zoompan) で背景に、音声+字幕を合成 → 9:16 MP4

設計判断は docs/features/short_video_feasibility.md を参照。
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------

WP_BASE_URL = os.environ["WP_BASE_URL"].rstrip("/")
WP_USERNAME = os.environ["WP_USERNAME"]
WP_APP_PASSWORD = os.environ["WP_APP_PASSWORD"]

# Gemini Flash（台本要約）。Google AI Studio の API キー。
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")

# Google Cloud TTS（音声合成）。TTS API を有効化した GCP プロジェクトの API キー。
GOOGLE_TTS_API_KEY = os.environ.get("GOOGLE_TTS_API_KEY", "")
TTS_VOICE = os.environ.get("TTS_VOICE", "ja-JP-Neural2-B")
TTS_SPEAKING_RATE = float(os.environ.get("TTS_SPEAKING_RATE", "1.15"))

# 動画仕様（縦型ショート）
VIDEO_W, VIDEO_H = 1080, 1920
FPS = 30
# Noto Sans CJK（ワークフローで apt install fonts-noto-cjk 済みを想定）
SUBTITLE_FONT = os.environ.get("SUBTITLE_FONT", "Noto Sans CJK JP")


# ---------------------------------------------------------------------------
# ① WordPress API（draft_to_gdoc.py の仕組みを応用）
# ---------------------------------------------------------------------------

def _make_wp_session() -> requests.Session:
    """/wp-json/ 用セッションを生成する。WP Application Password で認証する。"""
    session = requests.Session()
    session.auth = (WP_USERNAME, WP_APP_PASSWORD)
    # .htaccess の User-Agent フィルタ（"python" を含む UA をブロック）を回避する
    session.headers.update({"User-Agent": "wp-short-bot/1.0"})
    return session


def fetch_post(post_id: str) -> dict:
    """WP REST API から公開済み記事を1件取得する。"""
    url = f"{WP_BASE_URL}/wp-json/wp/v2/posts/{post_id}"
    params = {"_fields": "id,title,excerpt,content,featured_media"}
    resp = _make_wp_session().get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_featured_image_url(media_id: int) -> Optional[str]:
    """featured_media ID からアイキャッチ画像の URL を取得する。"""
    if not media_id:
        return None
    url = f"{WP_BASE_URL}/wp-json/wp/v2/media/{media_id}"
    try:
        resp = _make_wp_session().get(url, params={"_fields": "source_url"}, timeout=30)
        if resp.status_code == 200:
            return resp.json().get("source_url")
    except Exception as e:
        print(f"  [WARN] アイキャッチ取得失敗 (media_id={media_id}): {e}", file=sys.stderr)
    return None


# ---------------------------------------------------------------------------
# ② Gemini Flash で台本生成
# ---------------------------------------------------------------------------

def _strip_html(text: str) -> str:
    """簡易 HTML タグ除去。"""
    return re.sub(r"<[^>]+>", "", text or "").strip()


def generate_script(title: str, content: str) -> str:
    """記事本文を縦型ショート動画用の台本に要約する。"""
    plain = _strip_html(content)[:6000]  # 入力トークン節約のため先頭を使用
    prompt = (
        "あなたは縦型ショート動画（TikTok / YouTube Shorts）の構成作家です。\n"
        "以下のブログ記事を、ナレーションとして読み上げる台本に要約してください。\n\n"
        "# 制約\n"
        "- 全体で300〜400字（30〜50秒で読める長さ）\n"
        "- 冒頭2秒で惹きつける『フック』→『本編（記事の要点）』→『CTA（続きはブログで等）』の構成\n"
        "- 話し言葉。視聴者に語りかける口調\n"
        "- 絵文字・記号・見出し・ナレーション以外の文字は出力しない（読み上げる文章のみ）\n\n"
        f"# 記事タイトル\n{title}\n\n"
        f"# 記事本文\n{plain}\n"
    )
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    resp = requests.post(url, json=body, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    return text


# ---------------------------------------------------------------------------
# ③ Google Cloud TTS で音声合成
# ---------------------------------------------------------------------------

def synthesize_speech(text: str, out_path: str) -> None:
    """台本テキストを Google Cloud TTS (Neural2 ja-JP) で音声化し mp3 で保存する。"""
    url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={GOOGLE_TTS_API_KEY}"
    body = {
        "input": {"text": text},
        "voice": {"languageCode": "ja-JP", "name": TTS_VOICE},
        "audioConfig": {"audioEncoding": "MP3", "speakingRate": TTS_SPEAKING_RATE},
    }
    resp = requests.post(url, json=body, timeout=60)
    resp.raise_for_status()
    import base64
    audio = base64.b64decode(resp.json()["audioContent"])
    with open(out_path, "wb") as f:
        f.write(audio)


def probe_duration(media_path: str) -> float:
    """ffprobe でメディアの長さ（秒）を取得する。"""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", media_path],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


# ---------------------------------------------------------------------------
# ④ 字幕生成（音声長に比例配分）
# ---------------------------------------------------------------------------

def _split_captions(text: str) -> list[str]:
    """台本を字幕1行ぶんのチャンクに分割する（句読点・改行区切り、約20字上限）。"""
    # 句点・改行で大きく分割
    segments = re.split(r"[。！？\n]", text)
    chunks: list[str] = []
    for seg in segments:
        seg = seg.strip("、 　")
        if not seg:
            continue
        # 長い場合は読点でさらに分割し、約20字以内に整える
        if len(seg) <= 22:
            chunks.append(seg)
            continue
        buf = ""
        for part in seg.split("、"):
            if buf and len(buf) + len(part) > 22:
                chunks.append(buf)
                buf = part
            else:
                buf = f"{buf}{part}" if buf else part
        if buf:
            chunks.append(buf)
    return chunks


def _ass_time(seconds: float) -> str:
    """秒を ASS のタイムコード (H:MM:SS.cc) に変換する。"""
    cs = int(round(seconds * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def build_ass(text: str, duration: float, out_path: str) -> None:
    """台本と音声長から ASS 字幕ファイルを生成する（文字数に比例して配分）。"""
    chunks = _split_captions(text)
    total_chars = sum(len(c) for c in chunks) or 1

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {VIDEO_W}
PlayResY: {VIDEO_H}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{SUBTITLE_FONT},72,&H00FFFFFF,&H00000000,&H80000000,-1,6,2,2,80,80,420,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    lines = [header]
    t = 0.0
    for chunk in chunks:
        dur = duration * (len(chunk) / total_chars)
        start, end = t, t + dur
        t = end
        text_esc = chunk.replace("\n", " ").strip()
        lines.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{text_esc}\n"
        )

    with open(out_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


# ---------------------------------------------------------------------------
# ⑤ 動画合成（FFmpeg）
# ---------------------------------------------------------------------------

def download_image(url: str, out_path: str) -> bool:
    """画像をダウンロードする。成功で True。"""
    try:
        resp = _make_wp_session().get(url, timeout=30)
        resp.raise_for_status()
        with open(out_path, "wb") as f:
            f.write(resp.content)
        return True
    except Exception as e:
        print(f"  [WARN] 画像ダウンロード失敗: {e}", file=sys.stderr)
        return False


def render_video(image_path: Optional[str], audio_path: str, ass_path: str,
                 duration: float, out_path: str) -> None:
    """アイキャッチ背景 + 音声 + 字幕を合成して 9:16 MP4 を生成する。"""
    total_frames = int(duration * FPS) + 1
    # 背景: 画像があれば Ken Burns(zoompan)、無ければ単色
    if image_path:
        bg_input = ["-loop", "1", "-i", image_path]
        vf = (
            f"scale={VIDEO_W}:{VIDEO_H}:force_original_aspect_ratio=increase,"
            f"crop={VIDEO_W}:{VIDEO_H},"
            f"zoompan=z='min(zoom+0.0004,1.25)':d={total_frames}:"
            f"s={VIDEO_W}x{VIDEO_H}:fps={FPS},"
            f"ass={ass_path}"
        )
    else:
        bg_input = ["-f", "lavfi", "-i",
                    f"color=c=0x1a1a2e:s={VIDEO_W}x{VIDEO_H}:r={FPS}"]
        vf = f"ass={ass_path}"

    cmd = [
        "ffmpeg", "-y",
        *bg_input,
        "-i", audio_path,
        "-vf", vf,
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "192k",
        "-t", f"{duration:.3f}",
        "-shortest",
        out_path,
    ]
    subprocess.run(cmd, check=True)


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="WP 公開記事 → ショート動画 (PoC)")
    parser.add_argument("--post-id", required=True, help="対象の公開 Post ID")
    parser.add_argument("--output", default="short.mp4", help="出力 MP4 パス")
    args = parser.parse_args()

    if not GEMINI_API_KEY:
        sys.exit("GEMINI_API_KEY が未設定です。")
    if not GOOGLE_TTS_API_KEY:
        sys.exit("GOOGLE_TTS_API_KEY が未設定です。")

    print(f"① 記事取得中... (post_id={args.post_id})")
    post = fetch_post(args.post_id)
    title = _strip_html(post["title"]["rendered"])
    content = post.get("content", {}).get("rendered", "")
    print(f"   タイトル: {title}")

    print("② Gemini で台本生成中...")
    script = generate_script(title, content)
    print(f"   台本({len(script)}字):\n{script}\n")

    with tempfile.TemporaryDirectory() as tmp:
        audio_path = os.path.join(tmp, "narration.mp3")
        ass_path = os.path.join(tmp, "subtitle.ass")
        image_path = os.path.join(tmp, "bg.jpg")

        print("③ Google TTS で音声合成中...")
        synthesize_speech(script, audio_path)
        duration = probe_duration(audio_path)
        print(f"   音声長: {duration:.1f}秒")

        print("④ 字幕生成中...")
        build_ass(script, duration, ass_path)

        print("⑤ 背景画像を取得中...")
        media_url = fetch_featured_image_url(post.get("featured_media", 0))
        bg = image_path if (media_url and download_image(media_url, image_path)) else None
        if not bg:
            print("   アイキャッチなし → 単色背景にフォールバック")

        print("   FFmpeg で動画合成中...")
        render_video(bg, audio_path, ass_path, duration, args.output)

    print(f"\n✅ 完了: {args.output} ({duration:.1f}秒, {VIDEO_W}x{VIDEO_H})")

    # GitHub Actions Step Summary
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write("## ショート動画生成結果\n\n")
            f.write(f"- **Post ID**: {args.post_id}\n")
            f.write(f"- **タイトル**: {title}\n")
            f.write(f"- **動画長**: {duration:.1f}秒\n")
            f.write(f"- **解像度**: {VIDEO_W}x{VIDEO_H} (9:16)\n\n")
            f.write("### 生成された台本\n\n")
            f.write(f"> {script}\n")


if __name__ == "__main__":
    main()
