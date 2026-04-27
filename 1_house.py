import time
import os
import re
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from playwright.sync_api import sync_playwright
from datetime import datetime

# 設定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDS_FILE = "houseflow_gheet_key.json.json"
SHEET_KEY = "1bU4BKbjQgnoNqSK50G4vHgMGBFetHsBrbMyHv2Xc2k0"

def run_map_scraper():
    with sync_playwright() as p:
        session_dir = os.path.join(BASE_DIR, "browser_session")
        browser_context = p.chromium.launch_persistent_context(
            session_dir, headless=False, viewport={'width': 1280, 'height': 800}
        )
        page = browser_context.pages[0]

        print("\n" + "="*60)
        print("【住通地圖攻堅 - 類型數據採集版 v63】")
        print("="*60)

        page.goto("https://app.houseflow.tw/HOUSE/ExploreCaseNew")
        input(">>> [請再次搜尋區域，按 Enter 啟動]...")

        all_data = []
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        last_first_id = "" 
        p_idx = 1
        while True:
            print(f"\n[進度] 正在解析第 {p_idx} 頁...")
            
            if p_idx > 1:
                for _ in range(20): 
                    cur_id = page.evaluate("() => document.querySelector('tr[data-id]')?.getAttribute('data-id')")
                    if cur_id and cur_id != last_first_id: break
                    time.sleep(0.5)
            
            raw_items = []
            for _retry in range(5):
                try:
                    page.wait_for_selector("tr[data-id]", timeout=5000)
                    raw_items = page.evaluate(r"""() => {
                        const results = [];
                        const rows = document.querySelectorAll('tr[data-id]'); 
                        rows.forEach(row => {
                            const aid = row.getAttribute('data-id');
                            const titleEl = row.querySelector('.objtitle a');
                            if (!titleEl) return;
                            
                            let peerLink = "";
                            const allLinks = row.querySelectorAll('a');
                            for(let a of allLinks) {
                                const h = a.href;
                                if (h && !h.includes('houseflow.tw') && h.startsWith('http')) {
                                    peerLink = h; break;
                                }
                            }
        
                            results.push({
                                id: aid,
                                name: titleEl.title || titleEl.innerText.trim(),
                                img: row.querySelector('img')?.src || "",
                                peerLink: peerLink,
                                fullText: row.innerText,
                                textContent: row.textContent,
                                lat: row.getAttribute('data-lat') || "",
                                lng: row.getAttribute('data-lng') || ""
                            });
                        });
                        return results;
                    }""")
                    break  # 成功取到資料跳出迴圈
                except Exception as e:
                    print("  [系統] 頁面載入/刷新中，等待重試...")
                    time.sleep(1.5)

            if raw_items: last_first_id = raw_items[0]['id']

            for item in raw_items:
                txt = item['fullText']
                addr_match = re.search(r'((?:新北|台北|桃園|台中)[市][^ \n\r\t]*?[區市鄉鎮][^ \n\r\t]*?[路街巷][^ \n\r\t]*)', txt)
                clean_addr = addr_match.group(1).strip() if addr_match else ""
                price = (re.search(r'(\d+)\s*萬', txt) or re.search(r'萬\s*(\d+)', txt)).group(1) if re.search(r'\d+', txt) else ""
                size = (re.search(r'(\d+\.?\d*)\s*坪', txt) or re.search(r'坪\s*(\d+\.?\d*)', txt)).group(1) if re.search(r'\d+', txt) else ""
                
                # --- [修正點] 型態抓取強化：加入「電梯」關鍵字，優先從「類型/格局」文字中尋找 ---
                h_type = (re.search(r'(電梯|公寓|大樓|店面|透天|套房|辦公|廠辦|土地|車位)', txt) or ["", ""])[0]
                if not h_type and "房" in txt: h_type = "大樓"

                f_cur, f_total = "", ""
                fp = re.search(r'(\d+)\s*[F層樓/]{1,3}\s*(\d+)\s*[F層樓]', txt)
                if fp: f_cur, f_total = fp.group(1), fp.group(2)
                else: 
                    sf = re.search(r'(\d+)\s*[F層樓]', txt.replace(price or 'XXXX', ''))
                    if sf: f_cur = sf.group(1)
                pattern = (re.search(r'(\d+房\d+廳\d+衛)', txt) or re.search(r'(\d+房)', txt) or ["", ""])[0]
                is_dlg = "Y" if ("委託" in item['textContent'] or "已接" in item['textContent']) else "N"
                
                row_data = [
                    item['id'], item['name'], item['img'], clean_addr, 
                    price, size, h_type, f_cur, f_total, pattern,
                    item['peerLink'], 
                    f"https://app.houseflow.tw/HOUSE/ExploreHouseNew?A10OnLineId={item['id']}", 
                    "", "", "", 
                    is_dlg, current_time
                ]
                all_data.append({"id": item['id'], "row_data": row_data})
                print(f"  √ [{item['id']}] {item['name']} | 類型: {h_type} | 地址: {clean_addr}")



            has_next = page.evaluate(f"() => {{ const btns = Array.from(document.querySelectorAll('.pagination a')); let clicked = false; for(let b of btns) {{ if(b.innerText.trim() == '{p_idx+1}') {{ b.click(); clicked = true; break; }} }} return clicked; }}")
            if has_next:
                time.sleep(2)
                p_idx += 1
            else:
                print(f"✅ 已探索到底部，共掃描了 {p_idx} 頁！")
                break

        if all_data:
            creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive'])
            client = gspread.authorize(creds)
            wks = client.open_by_key(SHEET_KEY).sheet1
            all_rows = wks.get_all_values()
            existing_ids = {row[0]: i+1 for i, row in enumerate(all_rows) if row}
            
            new_rows, update_cells = [], []
            for item in all_data:
                tid = item['id']; d = item['row_data']
                if tid in existing_ids:
                    row_idx = existing_ids[tid]
                    # 更新基礎欄位：地址(4)、類型(7)、網址(11,12) -- 取消對 14(N) 15(O)的污染
                    for col_idx in [4, 7, 11, 12]: 
                        val = d[col_idx-1]
                        if val: update_cells.append(gspread.Cell(row=row_idx, col=col_idx, value=val))
                        
                    # 委託狀態與時間：只有在網頁上看到「委託=Y」時才蓋掉舊紀錄，避免把本來的 Y 洗成 N
                    # 現在 is_dlg 在索引 15 (P欄)，current_time 在索引 16 (Q欄)
                    if d[15] == 'Y':
                        update_cells.append(gspread.Cell(row=row_idx, col=16, value='Y'))
                        update_cells.append(gspread.Cell(row=row_idx, col=17, value=d[16]))
                else:
                    new_rows.append(d)
            
            if update_cells: wks.update_cells(update_cells)
            if new_rows: wks.append_rows(new_rows)
            print("🎉 v63 類型採集成功！")
        browser_context.close()

if __name__ == "__main__":
    run_map_scraper()
