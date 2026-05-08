import os
import gspread
import requests
import re
import time
from oauth2client.service_account import ServiceAccountCredentials

# --- 設定 ---
_base_dir = os.path.dirname(os.path.abspath(__file__))
CREDS_FILE = os.path.join(_base_dir, "houseflow_gheet_key.json.json")
if not os.path.exists(CREDS_FILE):
    CREDS_FILE = os.path.join(_base_dir, "..", "houseflow_gheet_key.json.json")

SHEET_KEY = "1bU4BKbjQgnoNqSK50G4vHgMGBFetHsBrbMyHv2Xc2k0"

def get_generic_coordinates(url, source):
    """【通用防線】直接爬取仲介網頁原始碼中的經緯度關鍵字"""
    if not url or not url.startswith('http'):
        return None, "Invalid URL"
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        # 增加超時時間，因為有些網站比較慢
        resp = requests.get(url, headers=headers, timeout=10)
        html = resp.text
        
        # 使用通用正則尋找潛在的經緯度 (通常藏在 JS 變數、Meta 標籤或 Google Maps 連結中)
        # 支援格式如: lat: 25.123, lng: 121.456 或 "latitude": "25.123"
        lat_match = re.search(r'(?:lat|latitude)["\']?\s*[:=]\s*["\']?(2[2-5]\.\d+)', html, re.IGNORECASE)
        lon_match = re.search(r'(?:lng|lon|longitude)["\']?\s*[:=]\s*["\']?(12[0-2]\.\d+)', html, re.IGNORECASE)
        
        if lat_match and lon_match:
            return f"{lat_match.group(1)},{lon_match.group(1)}", "Success"
            
        # 嘗試找 Google Maps 連結備援
        map_match = re.search(r'google\.com(?:\.tw)?/maps/place/([\d.]+,[\d.]+)', html)
        if map_match:
            return map_match.group(1), "Success (Maps Link)"
            
    except Exception as e:
        return None, f"Scrape Error: {str(e)}"
    
    return None, "No coordinates found in HTML"

def run_others_task():
    print("\n" + "="*60)
    print("【其他仲介座標擷取工具 - 5c_others.py v1.0】")
    print("="*60)

    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive'])
        client = gspread.authorize(creds)
        wks = client.open_by_key(SHEET_KEY).sheet1
        
        all_rows = wks.get_all_values()
        if len(all_rows) <= 1: return
        
        # 索引：K(10, 網址), V(21, 來源), R(17, 物件緯度), S(18, 物件經度), Z(25, 來源標註)
        idx_url = 10
        idx_broker = 21
        idx_lat = 17
        idx_lng = 18
        idx_src = 25
        
        targets = []
        for i, r in enumerate(all_rows[1:]):
            broker = r[idx_broker] if len(r) > idx_broker else ""
            lat = r[idx_lat] if len(r) > idx_lat else ""
            url = r[idx_url] if len(r) > idx_url else ""
            
            # 排除已處理過的信義與永慶，只抓「其餘」仲介 且 沒座標的
            if broker and broker not in ["信義", "永慶"] and not lat and url:
                targets.append((i + 2, broker, url))

        if not targets:
            print("目前沒有需要處理的其他仲介物件。")
            return

        print(f"預計掃描 {len(targets)} 筆其他仲介物件...")
        
        success_count = 0
        for row_num, broker, url in targets:
            print(f"  [掃描] 行號 {row_num} ({broker}): {url[:40]}...")
            
            # 通用爬取通常不需要休息太久，但還是加一點緩衝
            time.sleep(0.5)
            
            coords, msg = get_generic_coordinates(url, broker)
            if coords:
                lat_val, lng_val = coords.split(',')
                wks.update_cell(row_num, idx_lat + 1, lat_val)
                wks.update_cell(row_num, idx_lng + 1, lng_val)
                wks.update_cell(row_num, idx_src + 1, f"{broker}爬取")
                print(f"    ✅ 取得座標: {coords}")
                success_count += 1
            else:
                # 紀錄失敗，方便 5d 辨識
                wks.update_cell(row_num, idx_src + 1, f"爬取失敗({broker})")
                print(f"    ⚠️  失敗: {msg}")

        print(f"\n[任務結束] 成功從其他仲介原始碼補齊 {success_count} 筆座標。")

    except Exception as e:
        print(f"❌ 錯誤: {e}")

if __name__ == "__main__":
    run_others_task()
