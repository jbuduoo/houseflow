import time
import os
import re
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from playwright.sync_api import sync_playwright
from datetime import datetime
import importlib.util

# 動態載入 1a_broker.py (因為檔名開頭為數字)
_base_dir = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("1a_broker", os.path.join(_base_dir, "1a_broker.py"))
_broker_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_broker_module)
get_company_name = _broker_module.get_company_name
extract_domain = _broker_module.extract_domain

# 設定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 取得金鑰檔案的絕對路徑 (支援從根目錄或 core 執行)
_base_dir = os.path.dirname(os.path.abspath(__file__))
CREDS_FILE = os.path.join(_base_dir, "houseflow_gheet_key.json.json")
if not os.path.exists(CREDS_FILE):
    CREDS_FILE = os.path.join(_base_dir, "..", "houseflow_gheet_key.json.json")
SHEET_KEY = "1bU4BKbjQgnoNqSK50G4vHgMGBFetHsBrbMyHv2Xc2k0"

# 仲介可靠性優先序（數字越小越優先）
# data-id 中有全形空格，統一去除空白後比對
BROKER_PRIORITY = {
    '信義': 1, '永慶': 2, '好房網': 3, '住商': 4,
    '大家': 5, '591': 6, '21世紀': 7, 
    '太平洋': 8, '樂屋網': 9
}

def select_best_peer(peer_links_data):
    """從多個仲介連結中，依可靠性優先序選出最佳一筆，回傳 (url, 來源仲介名稱)"""
    best_priority = 999
    best_url = ""
    best_source = ""
    for item in peer_links_data:
        url = item.get('url', '')
        # 若有 URL，優先以網域辨識真實仲介名稱
        if url:
            domain = extract_domain(url)
            real_source = get_company_name(domain)
            if real_source != "未知公司":
                src = real_source
            else:
                src = item.get('source', '').replace('\u3000', '').replace(' ', '').strip()
        else:
            src = item.get('source', '').replace('\u3000', '').replace(' ', '').strip()
            
        priority = 100
        matched_key = src  # 預設為原名稱
        for key, val in BROKER_PRIORITY.items():
            if key in src:
                if val < priority:
                    priority = val
                    matched_key = key  # 如果有配對到，就把寫入的名稱強制改為標準化的短名（例如 '信義'）

        if priority < best_priority:
            best_priority = priority
            best_url = url
            best_source = matched_key
    return best_url, best_source


def run_map_scraper():
    with sync_playwright() as p:
        session_dir = os.path.join(BASE_DIR, "browser_session")
        browser_context = p.chromium.launch_persistent_context(
            session_dir, headless=False, viewport={'width': 1280, 'height': 800}
        )
        page = browser_context.pages[0]

        print("\n" + "="*60)
        print("【住通地圖攻堅 - 類型數據採集版 v64 (來源仲介版)】")
        print("="*60)

        page.goto("https://app.houseflow.tw/HOUSE/ExploreCaseNew")
        input(">>> [請再次搜尋區域，按 Enter 啟動]...")

        all_data = []
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        last_first_id = "" 
        p_idx = 1
        interrupted = False
        try:
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
                            
                                // 蒐集 .brandA 各仲介的詳細資訊
                                const peerLinksData = [];
                                const brandA = row.querySelector('.brandA');
                                if (brandA) {
                                    const brandDivs = brandA.querySelectorAll(':scope > div[data-id]');
                                    brandDivs.forEach(div => {
                                        const agentNameRaw = div.getAttribute('data-id') || '';
                                        const agentName = agentNameRaw.replace(/\s/g, ''); // 去除全形半形空白
                                        
                                        const listings = [];
                                        const listingBlocks = div.children;
                                        for (let block of listingBlocks) {
                                            const linkEl = block.querySelector('a[href]');
                                            if (linkEl) {
                                                // 尋找價格：包含「萬」或顏色為紅色的 span
                                                const spans = Array.from(block.querySelectorAll('span'));
                                                const priceEl = spans.find(s => s.innerText.includes('萬') || s.style.color.includes('df4041'));
                                                // 尋找時間：包含「前」或「刊登」的 span
                                                const timeEl = spans.find(s => s.innerText.includes('前') || s.innerText.includes('刊登'));
                                                
                                                listings.push({
                                                    title: linkEl.innerText.trim(),
                                                    price: priceEl ? priceEl.innerText.replace(/-/g, '').trim() : "",
                                                    time: timeEl ? timeEl.innerText.trim() : "",
                                                    url: linkEl.href
                                                });
                                            }
                                        }

                                        if (listings.length > 0) {
                                            peerLinksData.push({
                                                name: agentName,
                                                listings: listings
                                            });
                                        }
                                    });
                                }
        
                                results.push({
                                    id: aid,
                                    name: titleEl.title || titleEl.innerText.trim(),
                                    img: row.querySelector('img')?.src || "",
                                    peerLinksData: peerLinksData,
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
                        print(f"  [系統] 頁面解析錯誤: {e}, 等待重試...")
                        time.sleep(1.5)

                if raw_items: last_first_id = raw_items[0]['id']

                for item in raw_items:
                    txt = item['fullText']
                    addr_match = re.search(r'((?:新北|台北|桃園|台中)[市][^ \n\r\t]*?[區市鄉鎮][^ \n\r\t]*?[路街巷][^ \n\r\t]*)', txt)
                    clean_addr = addr_match.group(1).strip() if addr_match else ""
                    price = (re.search(r'(\d+)\s*萬', txt) or re.search(r'萬\s*(\d+)', txt)).group(1) if re.search(r'\d+', txt) else ""
                    size = (re.search(r'(\d+\.?\d*)\s*坪', txt) or re.search(r'坪\s*(\d+\.?\d*)', txt)).group(1) if re.search(r'\d+', txt) else ""
                
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

                    # 整理同行 JSON 格式
                    import json
                    from datetime import timedelta
                    
                    def parse_relative_time(time_str):
                        """將 '4小時前刊登', '1天前' 等轉換為具體日期 MM-DD"""
                        if not time_str: return ""
                        now = datetime.now()
                        try:
                            # 提取數字
                            num = int(re.search(r'\d+', time_str).group())
                            if '小時' in time_str:
                                target_date = now - timedelta(hours=num)
                            elif '天' in time_str:
                                target_date = now - timedelta(days=num)
                            elif '個月' in time_str:
                                target_date = now - timedelta(days=num * 30)
                            elif '週' in time_str or '周' in time_str:
                                target_date = now - timedelta(weeks=num)
                            else:
                                target_date = now
                            return target_date.strftime("%Y-%m-%d")
                        except:
                            if '剛剛' in time_str: return now.strftime("%Y-%m-%d")
                            return time_str # 若無法解析則傳回原字串
                    
                    # 處理並轉換時間
                    enriched_peer_data = item.get('peerLinksData', [])
                    for agent in enriched_peer_data:
                        for lst in agent.get('listings', []):
                            lst['time'] = parse_relative_time(lst['time'])

                    peer_json_str = json.dumps(enriched_peer_data, ensure_ascii=False)
                    
                    # 舊有的 select_best_peer 邏輯保留
                    legacy_peer_data = []
                    for agent in enriched_peer_data:
                        for lst in agent.get('listings', []):
                            legacy_peer_data.append({'source': agent['name'], 'url': lst['url']})
                    
                    peer_link, source_broker = select_best_peer(legacy_peer_data)
                
                    row_data = [
                        item['id'],    # A (0) 物件ID
                        item['name'],  # B (1) 物件名稱
                        item['img'],   # C (2) 圖片
                        clean_addr,    # D (3) 地址
                        price,         # E (4) 價格
                        size,          # F (5) 坪數
                        h_type,        # G (6) 類型
                        f_cur,         # H (7) 樓層(現)
                        f_total,       # I (8) 樓層(總)
                        pattern,       # J (9) 格局
                        peer_link,     # K (10) 仲介外部連結
                        f"https://app.houseflow.tw/HOUSE/ExploreHouseNew?A10OnLineId={item['id']}",  # L (11)
                        "", "", "",    # M N O (12-14)
                        is_dlg,        # P (15) 委託狀態
                        current_time,  # Q (16) 更新時間
                        "", "", "", "",# R S T U (17-20)
                        source_broker, # V (21) 來源仲介
                        item['lat'],   # W (22) HF緯度
                        item['lng'],   # X (23) HF經度
                        "",            # Y (24) 反查地址
                        "",            # Z (25) 座標來源
                        "",            # AA (26) AI 結論
                        peer_json_str  # AB (27) 同行資訊 JSON 格式
                    ]
                    all_data.append({"id": item['id'], "row_data": row_data})
                    print(f"  √ [{item['id']}] {item['name']} | 類型: {h_type} | 來源: {source_broker or '未知'} | 地址: {clean_addr} | HF緯: {item['lat']}")



                has_next = page.evaluate(f"() => {{ const btns = Array.from(document.querySelectorAll('.pagination a')); let clicked = false; for(let b of btns) {{ if(b.innerText.trim() == '{p_idx+1}') {{ b.click(); clicked = true; break; }} }} return clicked; }}")
                if has_next:
                    time.sleep(2)
                    p_idx += 1
                else:
                    print(f"✅ 已探索到底部，共掃描了 {p_idx} 頁！")
                    break

        except KeyboardInterrupt:
            print("\n🛑 收到強制中斷訊號 (Ctrl+C)，準備儲存已採集資料...")
            interrupted = True

        if all_data:
            creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive'])
            client = gspread.authorize(creds)
            wks = client.open_by_key(SHEET_KEY).sheet1
            all_rows = wks.get_all_values()
            existing_ids = {row[0]: i+1 for i, row in enumerate(all_rows) if row}
            
            new_rows, update_cells = [], []
            seen_in_this_run = set() # 用來防止本次抓取的資料中包含重複 ID
            
            for item in all_data:
                tid = item['id']; d = item['row_data']
                
                # 1. 檢查本次執行是否已經處理過這筆 ID
                if tid in seen_in_this_run:
                    continue
                seen_in_this_run.add(tid)
                
                # 2. 檢查試算表是否已存在
                if tid in existing_ids:
                    row_idx = existing_ids[tid]
                    # 更新基礎欄位：地址(4)、類型(7)、網址(11,12)、來源仲介(22)、同行資訊 JSON(28)
                    for col_idx in [4, 7, 11, 12, 28]:
                        val = d[col_idx-1]
                        if val: update_cells.append(gspread.Cell(row=row_idx, col=col_idx, value=val))

                    # 來源仲介（V欄=22）：有值才更新
                    if d[21]:  # index 21 = V欄
                        update_cells.append(gspread.Cell(row=row_idx, col=22, value=d[21]))
                        
                    # 委託狀態與時間：只有在網頁上看到「委託=Y」時才蓋掉舊紀錄，避免把本來的 Y 洗成 N
                    # 現在 is_dlg 在索引 15 (P欄)，current_time 在索引 16 (Q欄)
                    if d[15] == 'Y':
                        update_cells.append(gspread.Cell(row=row_idx, col=16, value='Y'))
                        update_cells.append(gspread.Cell(row=row_idx, col=17, value=d[16]))
                        
                    # HF座標 (W欄=23, X欄=24)：強制更新
                    if len(d) > 23:
                        update_cells.append(gspread.Cell(row=row_idx, col=23, value=d[22]))
                        update_cells.append(gspread.Cell(row=row_idx, col=24, value=d[23]))
                else:
                    new_rows.append(d)
            
            if update_cells: 
                print(f"  ...正在更新 {len(update_cells)} 個儲存格...")
                wks.update_cells(update_cells)
            if new_rows: 
                old_count = len(wks.get_all_values())
                print(f"  ...正在插入 {len(new_rows)} 筆新物件至「{wks.title}」最上方...")
                wks.insert_rows(new_rows, 2)
                new_count = len(wks.get_all_values())
                print(f"  ...寫入完成。列數變化: {old_count} -> {new_count}")
                print(f"  ...首筆新增 ID: {new_rows[0][0]}")
            
            print(f"\n🎉 採集任務完成！")
            print(f"📊 統計報告：")
            print(f"   - 工作表分頁: {wks.title}")
            print(f"   - 掃描總數: {len(seen_in_this_run)} 筆")
            print(f"   - 新增資料: {len(new_rows)} 筆")
            print(f"   - 更新資料: {len(all_data) - len(new_rows)} 筆")
        browser_context.close()

        if interrupted:
            raise KeyboardInterrupt

if __name__ == "__main__":
    run_map_scraper()
