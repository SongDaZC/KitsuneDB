from google.cloud import vision
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
import io
import os

# 環境変数からサービスアカウントキーのパスを取得
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
if not SERVICE_ACCOUNT_FILE:
    raise EnvironmentError("GOOGLE_APPLICATION_CREDENTIALS environment variable not set.")

# Google DriveとDocs APIの認証
SCOPES = ["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/documents"]
credentials = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)

# Google Vision APIクライアントの作成
client = vision.ImageAnnotatorClient(credentials=credentials)

# Google Docs APIクライアントの作成
docs_service = build('docs', 'v1', credentials=credentials)
drive_service = build('drive', 'v3', credentials=credentials)

# フォルダIDの設定
SOURCE_FOLDER_ID = "1W1T256xpMY1axiBedwTDueitakp7S-19"  # 読み込み対象フォルダ
DESTINATION_FOLDER_ID = "1DNpth748BqhecbO_Ehux3aclHusexJFL"  # 処理後の移動先フォルダ
DOC_ID = "1j0NgJYwMoaiQ8GlgdaWteM7Bv1JAKnCJQzdkwsamdn0"  # テキストデータを書き込むGoogle DocのID

# Google Driveから画像を取得
def get_image_files_from_drive(folder_id):
    results = drive_service.files().list(
        q=f"'{folder_id}' in parents and mimeType contains 'image/'",
        fields="files(id, name)"
    ).execute()
    return results.get('files', [])

# 画像からテキストを抽出
def extract_text_from_image(image_id):
    request = drive_service.files().get_media(fileId=image_id)
    file_data = io.BytesIO(request.execute())
    image = vision.Image(content=file_data.getvalue())

    response = client.text_detection(image=image)
    if response.error.message:
        raise Exception(f"Vision API error: {response.error.message}")

    return response.text_annotations[0].description if response.text_annotations else ""

# Google Docsにテキストを追記
def append_text_to_google_doc(doc_id, content):
    requests = [
        {"insertText": {
            "location": {"index": 1},  # ドキュメントの先頭に追記
            "text": content + "\n"
        }}
    ]
    docs_service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()

# Google Driveでファイルを移動
def move_file_to_folder(file_id, destination_folder_id):
    file = drive_service.files().get(fileId=file_id, fields='parents').execute()
    previous_parents = ",".join(file.get('parents'))
    drive_service.files().update(
        fileId=file_id,
        addParents=destination_folder_id,
        removeParents=previous_parents,
        fields='id, parents'
    ).execute()

# 実行
def main():
    # 読み込み対象フォルダからファイルを取得
    files = get_image_files_from_drive(SOURCE_FOLDER_ID)

    for file in files:
        print(f"Processing file: {file['name']}")
        
        # テキストを抽出
        text = extract_text_from_image(file['id'])
        
        # Google Docに追記
        append_text_to_google_doc(DOC_ID, text)
        print(f"Appended text to Google Doc: {DOC_ID}")
        
        # ファイルを移動
        move_file_to_folder(file['id'], DESTINATION_FOLDER_ID)
        print(f"Moved file {file['name']} to folder ID: {DESTINATION_FOLDER_ID}")

if __name__ == "__main__":
    main()
