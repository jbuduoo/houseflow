import gspread
from oauth2client.service_account import ServiceAccountCredentials

def check():
    creds = ServiceAccountCredentials.from_json_keyfile_name(
        "houseflow_gheet_key.json.json",
        ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    )
    client = gspread.authorize(creds)
    wks = client.open_by_key("1bU4BKbjQgnoNqSK50G4vHgMGBFetHsBrbMyHv2Xc2k0").sheet1
    
    headers = wks.row_values(1)
    
    for row_num in [2, 9, 10]:
        row = wks.row_values(row_num)
        print(f"\n--- ROW {row_num} ---")
        for i in range(26):
            col_letter = chr(ord('A') + i)
            val = row[i] if i < len(row) else "(empty)"
            print(f"Col {col_letter} ({i+1}): {val}")

if __name__ == "__main__":
    check()
