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
    print("\n" + "="*60, flush=True)
    print("【其他仲介座標擷取工具 - 5c_others.py v1.1】", flush=True)
    print("="*60, flush=True)

    try:
        print("[1/4] 正在初始化 Google Sheets 連線...", flush=True)
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive'])
        client = gspread.authorize(creds)
        
        print("[2/4] 正在開啟試算表並讀取所有資料 (請稍候)...", flush=True)
        wks = client.open_by_key(SHEET_KEY).sheet1
        all_rows = wks.get_all_values()
        if len(all_rows) <= 1: 
            print("! 試算表為空，任務取消。", flush=True)
            return
        
        print(f"[3/4] 讀取完成，共 {len(all_rows)} 行。正在篩選需要爬取的案件...", flush=True)
        
        # 索引：K(10,網址), V(21,來源), R(17,物件緯度), S(18,物件經度), Z(25,來源標註)
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
            
            # 再次縮小範圍：僅針對 [中信, 住商] 進行爬取
            if broker and any(k in broker for k in ["中信", "住商"]) and not lat.strip() and url:
                targets.append((i + 2, broker, url))

        if not targets:
            print("目前沒有需要處理的其他仲介物件。", flush=True)
            return

        print(f"[4/4] 篩選完成，預計掃描 {len(targets)} 筆其他仲介物件...", flush=True)
        
        success_count = 0
        update_queue = []
        
        for row_num, broker, url in targets:
            print(f"  [掃描] 行號 {row_num} ({broker}): {url[:40]}...", flush=True)
            
            time.sleep(0.5) # 通用爬取稍快一點
            
            coords, msg = get_generic_coordinates(url, broker)
            if coords:
                lat_val, lng_val = coords.split(',')
                # 加入隊列
                update_queue.append(gspread.Cell(row=row_num, col=idx_lat + 1, value=lat_val))
                update_queue.append(gspread.Cell(row=row_num, col=idx_lng + 1, value=lng_val))
                update_queue.append(gspread.Cell(row=row_num, col=idx_src + 1, value=f"{broker}爬取"))
                print(f"    [SUCCESS] 取得座標: {coords}", flush=True)
                success_count += 1
            else:
                # 紀錄失敗
                update_queue.append(gspread.Cell(row=row_num, col=idx_src + 1, value=f"爬取失敗({broker})"))
                print(f"    [FAILED] {msg}", flush=True)

            # 每累積 30 筆寫入一次
            if len(update_queue) >= 90: # 30 筆 * 3 個儲存格
                print(f"\n[系統] 正在將累積的 {len(update_queue)//3} 筆資料寫入雲端...", flush=True)
                wks.update_cells(update_queue)
                update_queue = []
                time.sleep(1) # 寫入後小休，防 API 限制

        # 寫入最後剩餘的資料
        if update_queue:
            print(f"\n[系統] 正在寫入最後 {len(update_queue)//3} 筆資料...", flush=True)
            wks.update_cells(update_queue)
        
        print(f"\n[任務結束] 成功補齊 {success_count} 筆座標。", flush=True)

    except Exception as e:
        print(f"ERROR: {e}", flush=True)

if __name__ == "__main__":
    run_others_task()
