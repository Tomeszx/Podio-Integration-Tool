import gspread
import pandas as pd
import gspread_dataframe as gd

from oauth2client.service_account import ServiceAccountCredentials


class GoogleSheet:
    def send_data(self, col: int, sheet_name: str, data: [list]) -> None:
        scope = ['https://spreadsheets.google.com/feeds',
                 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name('Credentials/client_secret.json', scope)
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
