from google.oauth2.service_account import Credentials
from google.cloud import vision
from googleapiclient.discovery import build
from PIL import Image
import pyheif
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

# サポートされている画像フォーマット
SUPPORTED_FORMATS = ["image/jpeg", "image/png", "image/gif", "image/bmp", "image/webp"]

# HEICをPNGに変換
def convert_to_png(file_data):
    try:
        heif_file = pyheif.read(file_data)
        image = Image.frombytes(
            heif_file.mode,
            heif_file.size,
            heif_file.data,
            "raw",
            heif_file.mode,
            heif_file.stride,
        )
        output = io.BytesIO()
        image.save(output, format="PNG")
        output.seek(0)
        return output.getvalue()
    except Exception as e:
        logger.error(f"Error converting to PNG: {e}")
        raise

# Google Driveから画像を取得
def get_image_files_from_drive(folder_id, max_files=10):
    try:
        results = drive_service.files().list(
            q=f"'{folder_id}' in parents and mimeType contains 'image/'",
            fields="files(id, name, mimeType)",
            pageSize=max_files
        ).execute()
        files = results.get('files', [])
        logger.info(f"Found {len(files)} files in folder ID {folder_id}")
        return files
    except Exception as e:
        logger.error(f"Error retrieving files from folder ID {folder_id}: {e}")
        raise

# Vision APIでテキストを抽出
def extract_text_from_image(file_data):
    try:
        image = vision.Image(content=file_data)
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
        logger.error(f"Error extracting text: {e}")
        raise

# オブジェクト認識
def detect_objects(file_data):
    try:
        image = vision.Image(content=file_data)
        response = client.object_localization(image=image)

        if response.error.message:
            raise Exception(f"Vision API error: {response.error.message}")

        objects = response.localized_object_annotations
        logger.info(f"Detected {len(objects)} objects.")
        return objects
    except Exception as e:
        logger.error(f"Error detecting objects: {e}")
        raise

# Google Docsにオブジェクトの詳細を追記
def append_objects_to_google_doc(doc_id, objects):
    try:
        doc = docs_service.documents().get(documentId=doc_id).execute()
        body_content = doc.get('body', {}).get('content', [])
        last_index = body_content[-1]['endIndex'] if body_content else 1

        content = "\nDetected Objects:\n"
        for obj in objects:
            content += f"- {obj.name} (Score: {obj.score:.2f})\n"

        requests = [
            {"insertText": {
                "location": {"index": last_index - 1},
                "text": content
            }}
        ]
        docs_service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()
        logger.info("Appended objects to Google Doc.")
    except Exception as e:
        logger.error(f"Error appending objects to Google Doc: {e}")
        raise

# Google Docsにテキストを追記
def append_text_to_google_doc(doc_id, text, file_name):
    try:
        doc = docs_service.documents().get(documentId=doc_id).execute()
        body_content = doc.get('body', {}).get('content', [])
        last_index = body_content[-1]['endIndex'] if body_content else 1

        content = f"\nExtracted Text from {file_name}:\n{text}\n"
        requests = [
            {"insertText": {
                "location": {"index": last_index - 1},
                "text": content
            }}
        ]
        docs_service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()
        logger.info("Appended text to Google Doc.")
    except Exception as e:
        logger.error(f"Error appending text to Google Doc: {e}")
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
        files = get_image_files_from_drive(SOURCE_FOLDER_ID, max_files=10)

        for file in files:
            logger.info(f"Processing file: {file['name']}")
            request = drive_service.files().get_media(fileId=file['id'])
            file_data = io.BytesIO(request.execute()).getvalue()

            # フォーマット変換
            if file['mimeType'] not in SUPPORTED_FORMATS:
                logger.info(f"Converting unsupported format: {file['mimeType']} to PNG.")
                file_data = convert_to_png(file_data)

            # オブジェクト認識
            objects = detect_objects(file_data)
            if objects:
                append_objects_to_google_doc(DOC_ID, objects)

            # テキスト認識
            text = extract_text_from_image(file_data)
            if text:
                append_text_to_google_doc(DOC_ID, text, file['name'])

            # ファイルを移動
            move_file_to_folder(file['id'], DONE_FOLDER_ID)

    except Exception as e:
        logger.error(f"An error occurred during processing: {e}")

if __name__ == "__main__":
    main()