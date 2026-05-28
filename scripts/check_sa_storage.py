"""
サービスアカウントの Drive ストレージ使用量を確認するユーティリティ。
"""

import json
import os

from google.oauth2 import service_account
from googleapiclient.discovery import build

GOOGLE_SERVICE_ACCOUNT_JSON = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]


def main() -> None:
    sa_info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    creds = service_account.Credentials.from_service_account_info(
        sa_info, scopes=DRIVE_SCOPES
    )
    drive = build("drive", "v3", credentials=creds)

    # ストレージ使用量を取得
    about = drive.about().get(fields="storageQuota,user").execute()
    user = about.get("user", {})
    quota = about.get("storageQuota", {})

    used = int(quota.get("usage", 0))
    total = int(quota.get("limit", 0))
    used_in_drive = int(quota.get("usageInDrive", 0))
    used_in_trash = int(quota.get("usageInDriveTrash", 0))

    def mb(b: int) -> str:
        return f"{b / 1024 / 1024:.1f} MB" if b < 1024 ** 3 else f"{b / 1024 / 1024 / 1024:.2f} GB"

    print(f"サービスアカウント: {user.get('emailAddress', '不明')}")
    print(f"表示名:             {user.get('displayName', '不明')}")
    print("---")
    print(f"Drive 使用量:       {mb(used_in_drive)}")
    print(f"ゴミ箱:             {mb(used_in_trash)}")
    print(f"合計使用量:         {mb(used)}")
    print(f"上限:               {mb(total) if total else '無制限'}")

    if total:
        pct = used / total * 100
        print(f"使用率:             {pct:.1f}%")
        if pct >= 90:
            print("⚠️  ストレージがほぼ満杯です。不要なファイルを削除してください。")

    # 所有ファイルの上位10件を表示
    print("\n--- 所有ファイル（新しい順・最大10件）---")
    result = drive.files().list(
        q="'me' in owners and trashed=false",
        fields="files(id,name,size,createdTime,mimeType)",
        orderBy="createdTime desc",
        pageSize=10,
    ).execute()
    files = result.get("files", [])
    if not files:
        print("（ファイルなし）")
    for f in files:
        size = int(f.get("size", 0))
        print(f"  [{f['createdTime'][:10]}] {mb(size):>10}  {f['name']}  ({f['id']})")


if __name__ == "__main__":
    main()
