import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd

SHEET_KEY = "1bU4BKbjQgnoNqSK50G4vHgMGBFetHsBrbMyHv2Xc2k0"
CREDS_FILE = "houseflow_gheet_key.json.json"

def debug_gsheet():
    scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, scope)
    client = gspread.authorize(creds)
    
    sheet = client.open_by_key(SHEET_KEY).sheet1
    all_values = sheet.get_all_values()
    if not all_values:
        print("Sheet is empty!")
        return
        
    headers = all_values[0]
    decoded_headers = []
    for h in headers:
        # Since gspread returns unicode, but the terminal might be mangling it,
        # let's try to see if it can be represented as Big5 or similar.
        # Actually, let's just print the hex for non-ascii characters.
        cleaned = "".join([c if ord(c) < 128 else f"\\u{ord(c):04x}" for c in h])
        decoded_headers.append(h)
        if h.strip():
            print(f"Col {headers.index(h)}: {cleaned} (Raw: {h})")
    
    clean_headers = []
    seen = {}
    for i, h in enumerate(headers):
        h = h.strip()
        if not h:
            h = f"Unnamed_{i}"
        
        if h in seen:
            seen[h] += 1
            new_h = f"{h}_{seen[h]}"
            clean_headers.append(new_h)
        else:
            seen[h] = 0
            clean_headers.append(h)
            
    print(f"Cleaned Headers (first 30): {clean_headers[:30]}")
    
    df = pd.DataFrame(all_values[1:], columns=clean_headers)
    print(f"DataFrame shape: {df.shape}")
    
    required_cols = [
        '是否已委託', '物件緯度', '物件經度', '查地址', '物件地址', 
        '戶籍地址', '案件首圖', '比對地址', '網頁連結', 
        '類型', '格局', '案件名稱', '售價(萬)', '總坪數', '樓層', 
        '總樓層', '戶籍緯度', '戶籍經度'
    ]
    
    for col in required_cols:
        if col in df.columns:
            print(f"OK: Column '{col}' found.")
        else:
            print(f"WARNING: Column '{col}' NOT found in DataFrame.")

    # Test the filtering logic from the app
    try:
        df_filtered = df[~df['是否已委託'].astype(str).str.upper().isin(['Y', 'YES', '是', 'TRUE'])]
        print(f"Filtered DataFrame shape: {df_filtered.shape}")
    except Exception as e:
        print(f"Filtering failed: {e}")

if __name__ == "__main__":
    debug_gsheet()
