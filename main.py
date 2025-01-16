from google.oauth2.service_account import Credentials
from google.cloud import vision
from googleapiclient.discovery import build
import io
import logging
import os

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 環境変数からサービスアカウントキーを取得
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
if not SERVICE_ACCOUNT_FILE:
    raise EnvironmentError("Environment variable 'GOOGLE_APPLICATION_CREDENTIALS' is not set.")

# 認証情報の設定
SCOPES = ["https://www.googleapis.com/auth/cloud-platform",
          "https://www.googleapis.com/auth/drive",
          "https://www.googleapis.com/auth/documents"]
credentials = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)

# クライアントの作成
client = vision.ImageAnnotatorClient(credentials=credentials)
drive_service = build('drive', 'v3', credentials=credentials)
docs_service = build('docs', 'v1', credentials=credentials)

# Google DriveフォルダIDとGoogle Docs ID
SOURCE_FOLDER_ID = "1W1T256xpMY1axiBedwTDueitakp7S-19"  # Workフォルダ
DONE_FOLDER_ID = "1DNpth748BqhecbO_Ehux3aclHusexJFL"    # Doneフォルダ
DOC_ID = "1j0NgJYwMoaiQ8GlgdaWteM7Bv1JAKnCJQzdkwsamdn0"  # テキストを追記するGoogle DocsのID

# Google Driveから画像を取得
def get_image_files_from_drive(folder_id, max_files=10):
    try:
        results = drive_service.files().list(
            q=f"'{folder_id}' in parents and mimeType contains 'image/'",
            fields="files(id, name)",
            pageSize=max_files
        ).execute()
        files = results.get('files', [])
        logger.info(f"Found {len(files)} files in folder ID {folder_id}")
        return files
    except Exception as e:
        logger.error(f"Error retrieving files from folder ID {folder_id}: {e}")
        raise

# Vision APIでテキストを抽出
def extract_text_from_image(file_id):
    try:
        request = drive_service.files().get_media(fileId=file_id)
        file_data = io.BytesIO(request.execute())

        image = vision.Image(content=file_data.getvalue())
        response = client.text_detection(image=image)

        if response.error.message:
            raise Exception(f"Vision API error: {response.error.message}")

        if response.text_annotations:
            text = response.text_annotations[0].description
            logger.info(f"Extracted text: {text[:50]}...")
            return text
        else:
            logger.info("No text detected.")
            return ""
    except Exception as e:
        logger.error(f"Error extracting text from image ID {file_id}: {e}")
        raise

# Google Docsにテキストを追記
def append_text_to_google_doc(doc_id, content):
    try:
        requests = [
            {"insertText": {
                "location": {"index": 1},  # ドキュメントの先頭に追記
                "text": content + "\n"
            }}
        ]
        docs_service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()
        logger.info(f"Appended text to Google Doc ID {doc_id}")
    except Exception as e:
        logger.error(f"Error appending text to Google Doc ID {doc_id}: {e}")
        raise

# Google Driveでファイルを移動
def move_file_to_folder(file_id, destination_folder_id):
    try:
        file = drive_service.files().get(fileId=file_id, fields='parents').execute()
        previous_parents = ",".join(file.get('parents'))
        drive_service.files().update(
            fileId=file_id,
            addParents=destination_folder_id,
            removeParents=previous_parents,
            fields='id, parents'
        ).execute()
        logger.info(f"Moved file ID {file_id} to folder ID {destination_folder_id}")
    except Exception as e:
        logger.error(f"Error moving file ID {file_id} to folder ID {destination_folder_id}: {e}")
        raise

# 実行
def main():
    try:
        # Google Driveから画像を取得（最大10件）
        files = get_image_files_from_drive(SOURCE_FOLDER_ID, max_files=10)

        for file in files:
            logger.info(f"Processing file: {file['name']}")
            # Vision APIでテキストを抽出
            text = extract_text_from_image(file['id'])
            if text:
                # Google Docsに追記
                append_text_to_google_doc(DOC_ID, f"{file['name']}:\n{text}")
                # 処理済みファイルをDoneフォルダに移動
                move_file_to_folder(file['id'], DONE_FOLDER_ID)
    except Exception as e:
        logger.error(f"An error occurred during processing: {e}")

if __name__ == "__main__":
    main()
