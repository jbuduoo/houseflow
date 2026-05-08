import os
import re
import time
import random
import gspread
from playwright.sync_api import sync_playwright
from oauth2client.service_account import ServiceAccountCredentials

# --- 設定 ---
_base_dir = os.path.dirname(os.path.abspath(__file__))
CREDS_FILE = os.path.join(_base_dir, "houseflow_gheet_key.json.json")
if not os.path.exists(CREDS_FILE):
    CREDS_FILE = os.path.join(_base_dir, "..", "houseflow_gheet_key.json.json")

SHEET_KEY = "1bU4BKbjQgnoNqSK50G4vHgMGBFetHsBrbMyHv2Xc2k0"

def get_yungching_coords_via_browser(page, url):
    """
    透過已開啟的瀏覽器頁面擷取永慶座標。
    新策略：等待地圖按鈕渲染。
    """
    try:
        # 修正格式
        if url.startswith('ttps://'): url = 'h' + url
        elif not url.startswith('http'): url = 'https://' + url
        
        # 前往網頁
        page.goto(url, wait_until="load", timeout=45000)
        
        # 1. 嘗試捲動到地圖區塊以觸發載入 (永慶有時需要這個動作)
        page.evaluate("window.scrollTo(0, 1500)")
        time.sleep(1)
        
        # 2. 等待「街景與導航」按鈕出現 (最多等 10 秒)
        # 按鈕通常是 <a class="btn-street-view" ...>
        selector = ".btn-street-view"
        try:
            page.wait_for_selector(selector, timeout=10000)
        except:
            # 如果沒出現，再捲動多一點試試看
            page.evaluate("window.scrollTo(0, 2500)")
            time.sleep(2)

        # 3. 讀取按鈕的 href
        href = page.get_attribute(selector, "href")
        if href:
            # 格式範例: https://www.google.com/maps?q=25.0066213,121.5148936
            match = re.search(r'q=([\d.]+),([\d.]+)', href)
            if match:
                return f"{match.group(1)},{match.group(2)}", "Success"
            
        # 方法 2: 如果按鈕沒抓到，最後一搏找全頁 HTML 裡的 google maps 關鍵字
        html = page.content()
        match = re.search(r'https?://www\.google\.com(?:\.tw)?/maps[^\s"\']*q=([\d.]+),([\d.]+)', html)
        if match:
            return f"{match.group(1)},{match.group(2)}", "Success (HTML Fallback)"

        return None, "Coordinates not found (Timed out waiting for button)"
    except Exception as e:
        return None, f"Browser Error: {str(e)}"

def run_yungching_coords_task():
    print("\n" + "="*60, flush=True)
    print("【永慶座標擷取工具 - 5b_yungching.py v2.0 (瀏覽器連動版)】", flush=True)
    print("="*60, flush=True)

    try:
        # 1. 初始化 Sheets
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive'])
        client = gspread.authorize(creds)
        wks = client.open_by_key(SHEET_KEY).sheet1
        
        all_rows = wks.get_all_values()
        if len(all_rows) <= 1: return
        
        idx_url = 10 # K
        idx_broker = 21 # V
        idx_lat = 17 # R
        idx_lng = 18 # S
        idx_src = 25 # Z
        
        targets = []
        for i, r in enumerate(all_rows[1:]):
            broker = r[idx_broker] if len(r) > idx_broker else ""
            lat = r[idx_lat].strip() if len(r) > idx_lat else ""
            url = r[idx_url].strip() if len(r) > idx_url else ""
            if "永慶" in broker and not lat and url:
                targets.append((i + 2, url))

        if not targets:
            print("目前沒有需要處理的永慶物件。", flush=True)
            return
        
        print(f"[系統] 準備透過 Chrome 連動處理 {len(targets)} 筆永慶物件...", flush=True)
        print(f"⚠️  請確保 Chrome 已開啟並處於 9222 偵錯模式。\n", flush=True)

        success_count = 0
        update_queue = []
        
        with sync_playwright() as p:
            try:
                browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
                context = browser.contexts[0]
                page = context.new_page()
                
                for idx, (row_num, url) in enumerate(targets):
                    print(f"  ({idx+1}/{len(targets)}) 行號 {row_num}: {url}", flush=True)
                    
                    coords, msg = get_yungching_coords_via_browser(page, url)
                    
                    if coords:
                        lat_val, lng_val = coords.split(',')
                        update_queue.append(gspread.Cell(row=row_num, col=idx_lat + 1, value=lat_val))
                        update_queue.append(gspread.Cell(row=row_num, col=idx_lng + 1, value=lng_val))
                        update_queue.append(gspread.Cell(row=row_num, col=idx_src + 1, value="永慶瀏覽器擷取"))
                        print(f"    ✨ 取得座標: {coords}", flush=True)
                        success_count += 1
                    else:
                        print(f"    ❌ 失敗: {msg}", flush=True)
                    
                    # 每累積 20 筆寫入一次
                    if len(update_queue) >= 60:
                        print(f"\n[雲端] 正在同步 {len(update_queue)//3} 筆資料...", flush=True)
                        wks.update_cells(update_queue)
                        update_queue = []
                        time.sleep(1)

                # 最後寫入
                if update_queue:
                    wks.update_cells(update_queue)
                
                page.close()
                print(f"\n🎉 任務完成！成功補齊 {success_count} 筆永慶座標。", flush=True)

            except Exception as e:
                print(f"❌ 瀏覽器連線失敗: {e}", flush=True)
                print("   請確認 0_chrome.bat 已啟動且 Chrome 視窗未關閉。", flush=True)

    except Exception as e:
        print(f"❌ 發生錯誤: {e}", flush=True)

if __name__ == "__main__":
    run_yungching_coords_task()
