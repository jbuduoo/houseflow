import os
import re
import time
import random
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 設定 ---
_base_dir = os.path.dirname(os.path.abspath(__file__))
CREDS_FILE = os.path.join(_base_dir, "houseflow_gheet_key.json.json")
if not os.path.exists(CREDS_FILE):
    CREDS_FILE = os.path.join(_base_dir, "..", "houseflow_gheet_key.json.json")

SHEET_KEY = "1bU4BKbjQgnoNqSK50G4vHgMGBFetHsBrbMyHv2Xc2k0"

# 反爬蟲標頭
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://buy.yungching.com.tw/"
}

def get_yungching_coords(url):
    """
    爬取永慶房屋網址的經緯度。
    從 '街景與導航' 按鈕 (class="btn-street-view") 提取 Google Maps 座標。
    """
    if not url or "yungching" not in url:
        return None, "Not a Yungching URL"
    
    # 修正可能的格式問題
    if url.startswith('ttps://'): url = 'h' + url
    elif not url.startswith('http'): url = 'https://' + url

    try:
        # 加入隨機延遲避免被抓
        time.sleep(random.uniform(2, 5))
        
        response = requests.get(url, headers=HEADERS, timeout=15)
        
        # 1. 偵測封鎖 (狀態碼)
        if response.status_code == 403:
            return None, "BLOCKED_403"
        
        if response.status_code != 200:
            return None, f"Error: {response.status_code}"
            
        # 2. 偵測封鎖 (關鍵字)
        content = response.text
        # 加入更多可能的封鎖關鍵字
        block_keywords = ["驗證碼", "訪問頻繁", "Access Denied", "安全驗證", "機器人", "行為異常", "請稍候再試", "偵測到異常行為"]
        for kw in block_keywords:
            if kw in content:
                return None, f"BLOCKED_KEYWORD({kw})"
        
        # 3. 偵測內容完整性 (通常正常物件頁面會很大)
        if len(content) < 10000:
            return None, "BLOCKED_SUSPICIOUS_SHORT_PAGE"

        # 3. 提取座標：尋找 btn-street-view 裡的 google maps 連結
        # 格式範例: href="https://www.google.com/maps?q=25.0066213,121.5148936"
        match = re.search(r'class="btn-street-view"[^>]*href="https?://www\.google\.com(?:\.tw)?/maps\?q=([\d.]+),([\d.]+)"', content)
        if match:
            lat, lng = match.groups()
            return f"{lat},{lng}", "Success"
        
        # 備選方案：直接搜尋 google maps 關鍵字
        alt_match = re.search(r'https?://www\.google\.com(?:\.tw)?/maps/place/([\d.]+,[\d.]+)', content)
        if alt_match:
            return alt_match.group(1), "Success"

        return None, "Coordinates not found"
        
    except Exception as e:
        return None, f"Error: {str(e)}"

def run_yungching_coords_task():
    print("\n" + "="*60)
    print("【永慶座標擷取工具 - 5b_yungching.py v1.0】")
    print("="*60)

    try:
        # 1. 連接試算表
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive'])
        client = gspread.authorize(creds)
        wks = client.open_by_key(SHEET_KEY).sheet1
        
        all_rows = wks.get_all_values()
        if len(all_rows) <= 1: return
        
        header = all_rows[0]
        rows = all_rows[1:]
        
        # 找到關鍵欄位索引
        idx_url = 10 # K
        idx_broker = 21 # V
        idx_lat = 17 # R (18th column)
        idx_lng = 18 # S (19th column)
        idx_src = 25 # Z (26th column)
        
        targets = []
        for i, r in enumerate(rows):
            broker = r[idx_broker] if len(r) > idx_broker else ""
            lat = r[idx_lat] if len(r) > idx_lat else ""
            url = r[idx_url] if len(r) > idx_url else ""
            
            # 條件：永慶物件 且 尚未有座標 且 有網址
            if "永慶" in broker and (not lat or lat.strip() == "") and url:
                targets.append((i + 2, url)) # i+2 是試算表行號

        if not targets:
            print("目前沒有需要處理的永慶物件。")
            return

        print(f"預計處理 {len(targets)} 筆永慶物件...")
        
        success_count = 0
        is_blocked = False
        for row_num, url in targets:
            print(f"  [執行] 行號 {row_num}: {url[:40]}...")
            
            # 安全延遲 5~10 秒
            time.sleep(random.uniform(5, 10))
            
            coords, msg = get_yungching_coords(url)
            
            if "BLOCKED" in msg:
                print("\n" + "!"*60)
                print(f"❌ 警告：偵測到永慶封鎖 ({msg})！為保護您的 IP，程式已自動終止。")
                print("!"*60 + "\n")
                is_blocked = True
                break
            
            if coords:
                lat, lng = coords.split(',')
                # 直接寫回試算表 (gspread 是 1-based)
                wks.update_cell(row_num, idx_lat + 1, lat)
                wks.update_cell(row_num, idx_lng + 1, lng)
                wks.update_cell(row_num, idx_src + 1, "永慶爬取")
                print(f"    ✅ 取得座標: {lat}, {lng}")
                success_count += 1
            else:
                print(f"    ⚠️  失敗: {msg}")

        print(f"\n[永慶任務結束] 成功補齊 {success_count} 筆座標。")
        return is_blocked

    except Exception as e:
        print(f"❌ 發生錯誤: {e}")
        return False

if __name__ == "__main__":
    run_yungching_coords_task()
