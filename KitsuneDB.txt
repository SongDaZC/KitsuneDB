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

# Google Docsにテキストを保存
def create_google_doc(title, content):
    document = docs_service.documents().create(body={"title": title}).execute()
    doc_id = document.get('documentId')

    requests = [
        {"insertText": {"location": {"index": 1}, "text": content}}
    ]
    docs_service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()

    return f"https://docs.google.com/document/d/{doc_id}"

# 実行
def main():
    folder_id = "your_drive_folder_id"  # Google DriveフォルダID
    files = get_image_files_from_drive(folder_id)

    for file in files:
        print(f"Processing file: {file['name']}")
        text = extract_text_from_image(file['id'])
        doc_url = create_google_doc(file['name'], text)
        print(f"Google Doc created: {doc_url}")

if __name__ == "__main__":
    main()
