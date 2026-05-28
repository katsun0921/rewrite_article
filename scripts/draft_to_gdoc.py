"""
Phase 1: WordPress ドラフト → Google Doc

WP REST API でドラフト記事を取得し、Google Drive に Google Doc として保存する。
"""

import argparse
import base64
import json
import os
import sys
from typing import Optional

import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------

WP_BASE_URL = os.environ["WP_BASE_URL"].rstrip("/")
WP_USERNAME = os.environ["WP_USERNAME"]
WP_APP_PASSWORD = os.environ["WP_APP_PASSWORD"]
GDOC_FOLDER_ID = os.environ["GDOC_FOLDER_ID"]
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]

# サーバーレベルの HTTP Basic 認証（任意）
# WP_BASIC_USER が設定されている場合、全リクエストにサーバー Basic 認証を付与する。
# WP REST API (/wp-json/) が Basic 認証対象外の場合は不要。
# 対象の場合、サーバーは WP_USERNAME/WP_APP_PASSWORD と同じ認証情報を受け入れる必要がある。
WP_BASIC_USER = os.environ.get("WP_BASIC_USER", "")
WP_BASIC_PASSWORD = os.environ.get("WP_BASIC_PASSWORD", "")

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]

MAX_LIMIT = 20

# フィールドごとの目安文字数
FIELD_HINTS = {
    "excerpt_ja": "140〜150字",
    "excerpt_en": "70〜80 words",
    "seo_desc_ja": "120字前後",
    "seo_desc_en": "160 chars",
    "tagline": "自由",
}


# ---------------------------------------------------------------------------
# WordPress API
# ---------------------------------------------------------------------------

def _make_wp_session(auth: tuple[str, str]) -> requests.Session:
    """指定した認証情報でセッションを生成する。"""
    session = requests.Session()
    session.auth = auth
    # .htaccess の User-Agent フィルタ（"python" を含む UA をブロック）を回避する
    session.headers.update({"User-Agent": "wp-rewrite-bot/1.0"})
    return session


def _request_with_fallback(method: str, url: str, **kwargs) -> requests.Response:
    """
    WP REST API リクエストを実行する。

    WP_BASIC_USER が設定されている場合、サーバー Basic 認証（WP_BASIC_USER/WP_BASIC_PASSWORD）
    と WP Application Password（WP_USERNAME/WP_APP_PASSWORD）の両方を順に試みる。
    サーバー Basic 認証と WP REST API 認証は同一の Authorization ヘッダーを使用するため、
    どちらの認証情報が有効かをフォールバックで判定する。
    """
    credentials = []
    if WP_BASIC_USER:
        credentials.append(("server-basic", WP_BASIC_USER, WP_BASIC_PASSWORD))
    credentials.append(("wp-app-password", WP_USERNAME, WP_APP_PASSWORD))

    last_resp = None
    for label, user, passwd in credentials:
        resp = _make_wp_session((user, passwd)).request(method, url, **kwargs)
        if resp.status_code < 400:
            return resp
        print(
            f"  [AUTH] {label} で失敗 ({resp.status_code}): {resp.text[:500]}",
            file=sys.stderr,
        )
        last_resp = resp

    last_resp.raise_for_status()
    return last_resp  # unreachable


def fetch_drafts(post_id: Optional[str], limit: int) -> list[dict]:
    """WP REST API からドラフト記事を取得する。"""
    url = f"{WP_BASE_URL}/wp-json/wp/v2/posts"
    params: dict = {
        "status": "draft",
        "per_page": min(limit, MAX_LIMIT),
        "_fields": "id,title,excerpt,content,acf",
    }
    if post_id:
        params["include"] = post_id
        params["per_page"] = 1

    resp = _request_with_fallback("GET", url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_aioseo_meta(post_id: int) -> dict:
    """AIOSEO REST API から SEO メタを取得する。失敗時は空辞書を返す。"""
    url = f"{WP_BASE_URL}/wp-json/aioseo/v1/posts/{post_id}"
    try:
        resp = _request_with_fallback("GET", url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "seo_desc_ja": data.get("description", ""),
            }
    except Exception as e:
        print(f"  [WARN] AIOSEO API 取得失敗 (post_id={post_id}): {e}", file=sys.stderr)
    return {}


# ---------------------------------------------------------------------------
# Google Drive API
# ---------------------------------------------------------------------------

def _drive_service():
    sa_info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    creds = service_account.Credentials.from_service_account_info(
        sa_info, scopes=DRIVE_SCOPES
    )
    return build("drive", "v3", credentials=creds)


def check_existing_doc(drive, doc_title: str) -> Optional[str]:
    """同名 Doc が既に存在する場合は webViewLink を返す。"""
    q = (
        f"name='{doc_title}' "
        f"and '{GDOC_FOLDER_ID}' in parents "
        f"and trashed=false"
    )
    result = drive.files().list(q=q, fields="files(id,webViewLink)").execute()
    files = result.get("files", [])
    return files[0]["webViewLink"] if files else None


def upload_gdoc(drive, doc_title: str, html_content: str) -> str:
    """HTML コンテンツを Google Doc としてアップロードし webViewLink を返す。"""
    file_metadata = {
        "name": doc_title,
        "mimeType": "application/vnd.google-apps.document",
        "parents": [GDOC_FOLDER_ID],
    }
    from googleapiclient.http import MediaInMemoryUpload

    media = MediaInMemoryUpload(
        html_content.encode("utf-8"),
        mimetype="text/html",
        resumable=False,
    )
    file = (
        drive.files()
        .create(body=file_metadata, media_body=media, fields="id,webViewLink")
        .execute()
    )
    return file["webViewLink"]


# ---------------------------------------------------------------------------
# Doc コンテンツ生成
# ---------------------------------------------------------------------------

def _strip_html(text: str) -> str:
    """簡易 HTML タグ除去。"""
    import re
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _char_count(text: str) -> int:
    return len(text.strip())


def _word_count(text: str) -> int:
    return len(text.strip().split())


def build_html(post: dict, aioseo: dict) -> str:
    """Google Doc にアップロードする HTML を生成する。"""
    post_id = post["id"]
    title = _strip_html(post["title"]["rendered"])
    acf = post.get("acf") or {}

    excerpt_ja = _strip_html(post.get("excerpt", {}).get("rendered", ""))
    excerpt_en = acf.get("excerpt_en", "")
    seo_desc_ja = aioseo.get("seo_desc_ja") or acf.get("seo_description", "")
    seo_desc_en = acf.get("seo_description_en", "")
    tagline = acf.get("tagline", "")

    def section(label: str, current: str, field_key: str, count_fn=_char_count, unit="字") -> str:
        count = count_fn(current)
        hint = FIELD_HINTS.get(field_key, "")
        return f"""<h3>{label}</h3>
<p>▼ 現在値　（現在 {count}{unit}）</p>
<p>{current or "（未入力）"}</p>
<p></p>
<p>▼ リライト後　目安: {hint}</p>
<p></p>
"""

    body = f"""<h1>[リライト] {title} (ID:{post_id})</h1>
<p>Post ID: {post_id}</p>
<p>元記事URL: {WP_BASE_URL}/?p={post_id}</p>
<hr>

{section("抜粋（excerpt）— 日本語", excerpt_ja, "excerpt_ja")}
{section("抜粋（excerpt）— 英語", excerpt_en, "excerpt_en", _word_count, "words")}
{section("SEO Description — 日本語", seo_desc_ja, "seo_desc_ja")}
{section("SEO Description — 英語", seo_desc_en, "seo_desc_en", _char_count, "chars")}
{section("Tagline", tagline, "tagline")}
"""
    return f"<!DOCTYPE html><html><body>{body}</body></html>"


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="WP Draft → Google Doc")
    parser.add_argument("--post-id", default="", help="特定の Post ID（省略時は全 draft）")
    parser.add_argument("--limit", type=int, default=5, help="最大処理件数（最大20）")
    args = parser.parse_args()

    limit = min(max(args.limit, 1), MAX_LIMIT)
    post_id = args.post_id.strip() or None

    print(f"WP ドラフト取得中... (post_id={post_id or '全件'}, limit={limit})")
    posts = fetch_drafts(post_id, limit)
    if not posts:
        print("対象のドラフトが見つかりませんでした。")
        return

    print(f"{len(posts)} 件取得。Drive API に接続中...")
    drive = _drive_service()

    summary_lines: list[str] = []
    for post in posts:
        pid = post["id"]
        title = _strip_html(post["title"]["rendered"])
        doc_title = f"[リライト] {title} (ID:{pid})"

        existing_link = check_existing_doc(drive, doc_title)
        if existing_link:
            print(f"  [SKIP] 既存 Doc あり (ID:{pid}): {existing_link}")
            summary_lines.append(f"| {pid} | {title} | スキップ（既存） | {existing_link} |")
            continue

        print(f"  [処理中] ID:{pid} {title}")
        aioseo = fetch_aioseo_meta(pid)
        html = build_html(post, aioseo)

        try:
            link = upload_gdoc(drive, doc_title, html)
            print(f"  [完了] {link}")
            summary_lines.append(f"| {pid} | {title} | 作成済み | {link} |")
        except HttpError as e:
            print(f"  [ERROR] Drive API エラー (ID:{pid}): {e}", file=sys.stderr)
            summary_lines.append(f"| {pid} | {title} | エラー | - |")

    # GitHub Actions Step Summary
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write("## WP Draft → Google Doc 結果\n\n")
            f.write("| Post ID | タイトル | ステータス | リンク |\n")
            f.write("|---------|--------|--------|------|\n")
            for line in summary_lines:
                f.write(line + "\n")

    print(f"\n完了: {len(summary_lines)} 件処理")


if __name__ == "__main__":
    main()
