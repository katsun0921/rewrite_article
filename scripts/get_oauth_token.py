"""
OAuth 2.0 リフレッシュトークンを取得する（ローカルで一度だけ実行する）。

使い方:
  pip install google-auth-oauthlib
  python scripts/get_oauth_token.py

取得した refresh_token を GitHub Secrets の GOOGLE_OAUTH_REFRESH_TOKEN に登録する。
"""

import json

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive"]

CLIENT_ID = input("GCP の OAuth クライアント ID を入力: ").strip()
CLIENT_SECRET = input("GCP の OAuth クライアントシークレットを入力: ").strip()

client_config = {
    "installed": {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}

flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
creds = flow.run_local_server(port=0)

print("\n===== GitHub Secrets に登録する値 =====")
print(f"GOOGLE_OAUTH_CLIENT_ID:      {CLIENT_ID}")
print(f"GOOGLE_OAUTH_CLIENT_SECRET:  {CLIENT_SECRET}")
print(f"GOOGLE_OAUTH_REFRESH_TOKEN:  {creds.refresh_token}")
print("=======================================")
print("\n※ GOOGLE_SERVICE_ACCOUNT_JSON は不要になります（削除しても構いません）")
