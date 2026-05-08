import os
import gspread
import requests
import time
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials

# --- 設定 ---
_base_dir = os.path.dirname(os.path.abspath(__file__))
CREDS_FILE = os.path.join(_base_dir, "houseflow_gheet_key.json.json")
if not os.path.exists(CREDS_FILE):
    CREDS_FILE = os.path.join(_base_dir, "..", "houseflow_gheet_key.json.json")

SHEET_KEY = "1bU4BKbjQgnoNqSK50G4vHgMGBFetHsBrbMyHv2Xc2k0"

# 設定檢查門檻 (幾天沒更新才要檢查網址)
CHECK_THRESHOLD_DAYS = 10

def check_url_alive(url):
    """檢查網址是否仍有效"""
    if not url or not url.startswith('http'): return False
    try:
        # 使用瀏覽器 Header 避免被擋
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        
        if response.status_code == 404:
            return False
        
        # 針對常見仲介網站的「下架關鍵字」檢查
        content = response.text
        dead_keywords = ["此物件已下架", "此物件已成交", "找不到該網頁", "物件不存在", "已經結案", "頁面不存在"]
        for kw in dead_keywords:
            if kw in content:
                return False
                
        return True
    except Exception as e:
        print(f"  [警告] 網址檢查異常 ({url}): {e}")
        return True # 異常時先保守保留

def run_link_checker():
    print("\n" + "="*60)
    print("【住通數據維護 - 2a_link_checker 網址存活檢查器】")
    print("="*60)

    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive'])
        client = gspread.authorize(creds)
        sh = client.open_by_key(SHEET_KEY)
        wks = sh.sheet1
        
        print(f"[系統] 正在讀取資料...")
        all_rows = wks.get_all_values()
        if len(all_rows) <= 1: return

        header = all_rows[0]
        rows = all_rows[1:]
        
        now = datetime.now()
        alive_rows = []
        dead_count = 0
        skip_count = 0
        check_count = 0

        for r in rows:
            # Q 欄 (index 16) 更新時間
            update_time_str = r[16] if len(r) > 16 else ""
            should_check = False
            
            try:
                update_time = datetime.strptime(update_time_str, "%Y-%m-%d %H:%M:%S")
                if now - update_time > timedelta(days=CHECK_THRESHOLD_DAYS):
                    should_check = True
            except:
                # 時間格式錯誤或沒時間，保險起見不檢查
                should_check = False

            if should_check:
                check_count += 1
                url = r[10] if len(r) > 10 else ""
                print(f"  [檢查] {r[0]} ({r[21] if len(r)>21 else '未知'}) - {update_time_str}")
                
                if check_url_alive(url):
                    alive_rows.append(r)
                else:
                    print(f"  [!!!] 判定已下架，移除: {r[0]}")
                    dead_count += 1
                
                # 稍微延遲避免被封鎖
                time.sleep(0.5)
            else:
                skip_count += 1
                alive_rows.append(r)

        print(f"\n[完成] 檢查完畢：")
        print(f"  - 跳過檢查 (近期更新): {skip_count} 筆")
        print(f"  - 執行檢查: {check_count} 筆")
        print(f"  - 判定下架並移除: {dead_count} 筆")

        if dead_count > 0:
            print(f"[系統] 正在更新試算表...")
            wks.clear()
            wks.update('A1', [header] + alive_rows)
            print(f"已清理完畢。")
        else:
            print(f"沒有發現需要移除的下架案。")

    except Exception as e:
        print(f"❌ 錯誤: {e}")

if __name__ == "__main__":
    run_link_checker()
