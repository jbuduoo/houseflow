import time
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from playwright.sync_api import sync_playwright

# 設定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDS_FILE = "houseflow_gheet_key.json.json"
SHEET_KEY = "1bU4BKbjQgnoNqSK50G4vHgMGBFetHsBrbMyHv2Xc2k0"

def fetch_coords():
    print("\n" + "="*60)
    print("【住通座標極速補完工具 v2.3 - 深度 DOM 解析版】")
    print("="*60)

    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive'])
        client = gspread.authorize(creds)
        wks = client.open_by_key(SHEET_KEY).sheet1
        all_rows = wks.get_all_values()
        target_ids = [row[0] for i, row in enumerate(all_rows) if i > 0 and row[0]]
        print(f"[1/4] 已連接試算表，清單內有 {len(target_ids)} 個待處理案件。")
    except Exception as e:
        print(f"❌ Google 授權失敗: {e}")
        return

    with sync_playwright() as p:
        try:
            print("[2/4] 正在搜尋 Chrome 分頁...")
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            target_page = next((page for page in browser.contexts[0].pages if "/HOUSE/" in page.url), None)
            
            if not target_page:
                print("❌ 找不到住通網頁。")
                return
            
            print(f"✅ 連線至：{target_page.url[:60]}")
            input(">>> [請確認內容已載入（例如：看到紅色 Pin），按 Enter 開始掃描]...")

            # 3. 深度 DOM 掃描 (特別針對「找房屋」頁面)
            print("[3/4] 正在進行深度掃描...")
            marker_data = target_page.evaluate(r"""() => {
                const results = [];
                
                // 掃描所有具有 onclick 的元素
                document.querySelectorAll('[onclick]').forEach(el => {
                    const attr = el.getAttribute('onclick');
                    // 偵測 showMap(3434859, 25.011, 121.522) 或類似數字對
                    const matches = [...attr.matchAll(/([\d.]{6,12})/g)];
                    if (matches.length >= 2) {
                        // 嘗試尋找 ID (通常在附近的 tr 或父層)
                        let id = null;
                        const tr = el.closest('tr');
                        if (tr) id = tr.getAttribute('data-id');
                        
                        // 如果沒 data-id，從 onclick 的第一個長整數抓
                        const idMatch = attr.match(/(\d{7,8})/);
                        if (!id && idMatch) id = idMatch[1];
                        
                        // 座標判斷 (緯度 22~26, 經度 119~122)
                        let lat = null, lng = null;
                        matches.forEach(m => {
                            const val = parseFloat(m[0]);
                            if (val > 21 && val < 26) lat = val;
                            if (val > 118 && val < 123) lng = val;
                        });

                        if (id && lat && lng) {
                            results.push({ id: String(id), lat: lat, lng: lng });
                        }
                    }
                });

                // 備援：掃描全局資料
                if (window.jData) results.push(...window.jData.map(d => ({id: String(d.id || d.Id || d.A10OnLineId), lat: d.lat||d.Lat, lng: d.lng||d.Lng})));

                return results;
            }""")

            # 4. 比對與更新
            update_cells = []
            count = 0
            unique_results = {r['id']: r for r in marker_data if r['id']}
            
            print(f"🔍 網頁分析完畢，共找到 {len(unique_results)} 個潛在座標物件。")
            if len(unique_results) > 0:
                print(f"   挖到的 ID 如下: {', '.join(unique_results.keys())}")

            for i, row in enumerate(all_rows):
                if i == 0: continue
                tid = row[0]
                if tid in unique_results:
                    # N 欄(14), O 欄(15) 為空才補
                    if len(row) <= 13 or not row[13]:
                        update_cells.append(gspread.Cell(row=i+1, col=14, value=str(unique_results[tid]['lat'])))
                        update_cells.append(gspread.Cell(row=i+1, col=15, value=str(unique_results[tid]['lng'])))
                        count += 1
                        print(f"   ✨ 成功比對 ID {tid}，準備寫入座標。")

            if update_cells:
                print(f"[4/4] 正在寫入 {count} 筆座標資料...")
                wks.update_cells(update_cells)
                print("🎉 大補帖同步大成功！")
            else:
                print("⚠️ 比對結果 0。建議：請回到【大地圖模式】，資料量會比較多。")

        except Exception as e:
            print(f"💥 發生錯誤: {e}")

if __name__ == "__main__":
    fetch_coords()
