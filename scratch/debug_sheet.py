import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials

_base_dir = os.path.dirname(os.path.abspath(__file__))
CREDS_FILE = os.path.join(_base_dir, "houseflow_gheet_key.json.json")
if not os.path.exists(CREDS_FILE):
    CREDS_FILE = os.path.join(_base_dir, "..", "houseflow_gheet_key.json.json")

SHEET_KEY = "1bU4BKbjQgnoNqSK50G4vHgMGBFetHsBrbMyHv2Xc2k0"

def debug_check():
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive'])
    client = gspread.authorize(creds)
    wks = client.open_by_key(SHEET_KEY).sheet1
    all_rows = wks.get_all_values()
    
    # R(17, 物件緯度), V(21, 來源仲介)
    count = 0
    print(f"總行數: {len(all_rows)}")
    for i, r in enumerate(all_rows[1:100]): # 先看前 100 行
        row_num = i + 2
        lat = r[17] if len(r) > 17 else ""
        broker = r[21] if len(r) > 21 else ""
        addr = r[12] if len(r) > 12 else ""
        
        if not lat.strip() and broker not in ["信義", "永慶"]:
            print(f"行號 {row_num}: 來源={broker}, 座標='{lat}', 原始地址='{addr}'")
            count += 1
            if count >= 10: break

if __name__ == "__main__":
    debug_check()
