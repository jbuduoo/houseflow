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
                            
                                // 蒐集 .brandA 各仲介的連結（依 data-id 分組）
                                const peerLinksData = [];
                                const brandA = row.querySelector('.brandA');
                                if (brandA) {
                                    const brandDivs = brandA.querySelectorAll(':scope > div[data-id]');
                                    brandDivs.forEach(div => {
                                        const dataId = div.getAttribute('data-id') || '';
                                        const text = div.innerText.trim();
                                        const img = div.querySelector('img');
                                        const alt = img ? (img.getAttribute('alt') || img.getAttribute('title') || '') : '';
                                    
                                        let sourceName = dataId;
                                        // 如果 data-id 是純數字且不是 591，代表它可能是系統內部的流水號
                                        // 這時我們優先拿裡面的文字或圖片標題來當作仲介名稱
                                        if (/^\\d+$/.test(dataId) && dataId !== '591') {
                                            if (alt) sourceName = alt;
                                            else if (text) sourceName = text;
                                        }
                                    
                                        const firstLink = div.querySelector('a[href]');
                                        if (firstLink && firstLink.href && firstLink.href.startsWith('http')) {
                                            peerLinksData.push({
                                                source: sourceName.trim(),
                                                url: firstLink.href
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

                    # 依優先序選出最佳仲介連結與來源名稱
                    peer_link, source_broker = select_best_peer(item.get('peerLinksData', []))
                
                    row_data = [
                        item['id'],    # A 物件ID
                        item['name'],  # B 物件名稱
                        item['img'],   # C 圖片
                        clean_addr,    # D 地址
                        price,         # E 價格
                        size,          # F 坪數
                        h_type,        # G 類型
                        f_cur,         # H 樓層(現)
                        f_total,       # I 樓層(總)
                        pattern,       # J 格局
                        peer_link,     # K 仲介外部連結（依優先序）
                        f"https://app.houseflow.tw/HOUSE/ExploreHouseNew?A10OnLineId={item['id']}",  # L houseflow連結
                        "", "", "",    # M N O 保留欄
                        is_dlg,        # P 委託狀態
                        current_time,  # Q 更新時間
                        "", "", "", "",# R S T U 保留欄
                        source_broker, # V 來源仲介
                        item['lat'],   # W HF緯度
                        item['lng']    # X HF經度
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
                    # 更新基礎欄位：地址(4)、類型(7)、網址(11,12)、來源仲介(22)
                    for col_idx in [4, 7, 11, 12]:
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
            
            if update_cells: wks.update_cells(update_cells)
            if new_rows: wks.append_rows(new_rows)
            print("🎉 v64 來源仲介採集成功！")
        browser_context.close()

        if interrupted:
            raise KeyboardInterrupt

if __name__ == "__main__":
    run_map_scraper()
