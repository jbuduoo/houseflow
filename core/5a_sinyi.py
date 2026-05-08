import requests
import re
import os
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 設定 ---
_base_dir = os.path.dirname(os.path.abspath(__file__))
CREDS_FILE = os.path.join(_base_dir, "houseflow_gheet_key.json.json")
if not os.path.exists(CREDS_FILE):
    CREDS_FILE = os.path.join(_base_dir, "..", "houseflow_gheet_key.json.json")

SHEET_KEY = "1bU4BKbjQgnoNqSK50G4vHgMGBFetHsBrbMyHv2Xc2k0"

def scrape_sinyi_coordinates(url):
    """爬取信義房屋網址的經緯度"""
    if not url or "sinyi" not in url: return None, "Invalid URL"
    if url.startswith('ttps://'): url = 'h' + url
    elif not url.startswith('http'): url = 'https://' + url
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200: return None, f"Status {response.status_code}"
        
        # Method 1: Google Maps place link
        map_match = re.search(r'https?://www\.google\.com(?:\.tw)?/maps/place/([\d.]+,[\d.]+)', response.text)
        if map_match: return map_match.group(1), "Success"
            
        # Method 2: script tags
        scripts = re.findall(r'<script[^>]*>(.*?)</script>', response.text, re.DOTALL)
        for script in scripts:
            if '"lat"' in script and '"lng"' in script:
                lats = re.findall(r'"lat"\s*:\s*(\d+\.\d+)', script)
                lngs = re.findall(r'"lng"\s*:\s*(\d+\.\d+)', script)
                if lats and lngs: return f"{lats[0]},{lngs[0]}", "Success"
        
        return None, "Not found"
    except Exception as e:
        return None, str(e)

def run_sinyi_task():
    print("\n" + "="*60)
    print("【信義座標擷取工具 - 5a_sinyi.py v2.1】")
    print("="*60)
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive'])
        client = gspread.authorize(creds)
        wks = client.open_by_key(SHEET_KEY).sheet1
        all_rows = wks.get_all_values()
        if len(all_rows) <= 1: return
        
        # 索引：K(10, 網址), V(21, 來源), R(17, 物件緯度), S(18, 物件經度), Z(25, 來源標註)
        for i, r in enumerate(all_rows[1:]):
            row_num = i + 2
            broker = r[21] if len(r) > 21 else ""
            lat = r[17] if len(r) > 17 else "" # 檢查 R 欄
            url = r[10] if len(r) > 10 else ""
            
            if "信義" in broker and not lat and url:
                print(f"  [處理] 行號 {row_num}: {url[:40]}...")
                coords, msg = scrape_sinyi_coordinates(url)
                if coords:
                    lat_val, lng_val = coords.split(',')
                    wks.update_cell(row_num, 18, lat_val) # R 欄
                    wks.update_cell(row_num, 19, lng_val) # S 欄
                    wks.update_cell(row_num, 26, "信義爬取") # Z 欄
                    print(f"    ✅ 取得座標: {coords}")
                else:
                    print(f"    ⚠️ 失敗: {msg}")
                time.sleep(1)
        print("\n[信義任務完成]")
    except Exception as e:
        print(f"❌ 錯誤: {e}")

if __name__ == "__main__":
    run_sinyi_task()
