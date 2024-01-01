import os
from io import BytesIO

import gspread
import pandas as pd
import gspread_dataframe as gd

from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload


BASE_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).split('objects')[0]


def send_data(col: int, sheet_name: str, data: [list]) -> None:
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

    creds = ServiceAccountCredentials.from_json_keyfile_name(f'{BASE_PATH}/Credentials/client_secret.json', scope)
    client = gspread.authorize(creds)

    url = "https://docs.google.com/spreadsheets/d/1Kw8t5Cdfi4zhw8JbBOE6wNyYfgxvoQDXAcQxsguLMu4/edit#gid=0"
    spread_sheet = client.open_by_url(url)
    sheet = spread_sheet.worksheet(sheet_name)

    if sheet_name == "Tasks":
        spread_sheet.values_clear("Tasks!A2:D")

    table = pd.DataFrame(data)
    res = gd.set_with_dataframe(sheet, table, include_column_header=False, row=len(sheet.col_values(col)) + 1,
                                col=col, include_index=False, resize=False, allow_formulas=True,
                                string_escaping="default")


def get_drive_service():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(f'{BASE_PATH}/Credentials/client_secret.json', scope)

    return build('drive', 'v3', credentials=creds)


def upload_file(origin_file: BytesIO, mime_type='image/png') -> str:
    service = get_drive_service()

    file_metadata = {'name': origin_file.name, 'parents': ['1rGIhCL-HC0908p22d_XitafWNlCTn3oB']}
    media = MediaIoBaseUpload(origin_file, mimetype=mime_type)
    file = service.files().create(body=file_metadata, media_body=media, fields='id,webViewLink').execute()

    return file.get('webViewLink')


def get_available_space() -> float:
    service = get_drive_service()

    about = service.about().get(fields='storageQuota').execute()
    quota = about['storageQuota']
    used_space = int(quota['usage'])
    total_space = int(quota['limit'])
    available_space = total_space - used_space

    return available_space / (1024 * 1024)
