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

    # リライトフォルダの確認
    folder_id = os.environ.get("GDOC_FOLDER_ID", "")
    if folder_id:
        print(f"\n--- リライトフォルダの確認 (ID: {folder_id}) ---")
        try:
            folder = drive.files().get(
                fileId=folder_id,
                fields="id,name,mimeType,owners,capabilities,driveId",
                supportsAllDrives=True,
            ).execute()
            print(f"フォルダ名:     {folder.get('name')}")
            print(f"種別:           {folder.get('mimeType')}")
            owners = folder.get("owners", [])
            for o in owners:
                print(f"所有者:         {o.get('emailAddress')} (ストレージ満杯: {o.get('permissionDetails', '')})")
            caps = folder.get("capabilities", {})
            print(f"ファイル追加可: {caps.get('canAddChildren', '不明')}")
            print(f"書き込み可:     {caps.get('canEdit', '不明')}")
            if folder.get("driveId"):
                print(f"Shared Drive:   {folder['driveId']}")
        except Exception as e:
            print(f"⚠️  フォルダにアクセスできません: {e}")

        # テスト用の小さなファイルを作成して権限を確認
        print("\n--- テストファイル作成 ---")
        try:
            from googleapiclient.http import MediaInMemoryUpload
            test_meta = {"name": "_test_write.txt", "parents": [folder_id]}
            test_media = MediaInMemoryUpload(b"test", mimetype="text/plain", resumable=False)
            test_file = drive.files().create(
                body=test_meta, media_body=test_media, fields="id,webViewLink",
                supportsAllDrives=True,
            ).execute()
            print(f"✅ テストファイル作成成功: {test_file['webViewLink']}")
            # 作成したテストファイルを即削除
            drive.files().delete(fileId=test_file["id"], supportsAllDrives=True).execute()
            print("✅ テストファイル削除完了")
        except Exception as e:
            print(f"❌ テストファイル作成失敗: {e}")


if __name__ == "__main__":
    main()
