import time
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from playwright.sync_api import sync_playwright

# 隱藏警告
os.environ["NODE_OPTIONS"] = "--no-deprecation"

# ── 設定 ──────────────────────────────────────────────
# 取得金鑰檔案的絕對路徑 (支援從根目錄或 core 執行)
_base_dir = os.path.dirname(os.path.abspath(__file__))
CREDS_FILE = os.path.join(_base_dir, "houseflow_gheet_key.json.json")
if not os.path.exists(CREDS_FILE):
    CREDS_FILE = os.path.join(_base_dir, "..", "houseflow_gheet_key.json.json")
SHEET_KEY  = "1bU4BKbjQgnoNqSK50G4vHgMGBFetHsBrbMyHv2Xc2k0"

# 欄位索引 (Python list, 0-based)
IDX_URL  = 11   # L欄: 查地址   (輸入 URL — ExploreHouseNew)
IDX_ADDR = 12   # M欄: 比對地址 (有資料則跳過；輸出地址)

# 欄位索引 (gspread, 1-based)
COL_URL  = 12   # L欄: 查地址
COL_ADDR = 13   # M欄: 比對地址 —— 寫入地址結果
COL_HIST = 14   # N欄: 查戶籍   —— 寫入 Transcript URL

# ── 頁面掃描 JS ───────────────────────────────────────
SCAN_JS = r"""() => {
    // 找到含有地籍資料的表格（標題含「區域」+「坪」）
    let resultTable = null;
    for (let t of document.querySelectorAll('table')) {
        const txt = t.innerText || '';
        if ((txt.includes('區域') || txt.includes('門牌')) && txt.includes('坪')) {
            resultTable = t;
            break;
        }
    }
    if (!resultTable) return null;

    // 取得資料列（至少含 3 個 td）
    const dataRows = Array.from(resultTable.querySelectorAll('tr')).filter(tr =>
        tr.querySelectorAll('td').length >= 3
    );
    if (dataRows.length === 0) return { count: 0 };

    // ── 黃色列偵測 ──────────────────────────────────
    const isYellow = (tr) => {
        const cls   = (tr.className || '').toLowerCase();
        const style = (tr.getAttribute('style') || '').toLowerCase();
        const bg    = window.getComputedStyle(tr).backgroundColor;

        // 以 class 判斷 (Bootstrap warning = 黃)
        if (cls.includes('warning') || cls.includes('yellow')) return true;
        // 以 inline style 判斷
        if (style.includes('yellow') || style.includes('gold') || style.includes('#ff')) return true;
        // 以計算後的 RGB 判斷 (R>200, G>180, B<150 ≈ 黃色系)
        const m = bg.match(/rgb[a]?\((\d+),\s*(\d+),\s*(\d+)/);
        if (m) {
            const r = parseInt(m[1]), g = parseInt(m[2]), b = parseInt(m[3]);
            if (r > 200 && g > 180 && b < 150) return true;
        }
        return false;
    };

    const yellowRows = dataRows.filter(tr => isYellow(tr));
    const hasYellow  = yellowRows.length > 0;
    const targetRow  = hasYellow ? yellowRows[0] : dataRows[0];
    const tds        = Array.from(targetRow.querySelectorAll('td'));

    // ── 地址提取：掃描所有 td 找「區」和「路/街+號」──
    let district = '';
    let street   = '';
    for (let td of tds) {
        // 改用 textContent，避免 innerText 遺漏隱藏元素
        const raw = td.textContent.replace(/\s+/g, '').trim();

        // 行政區：短文字含「區/鄉/鎮」
        if (!district) {
            const dm = raw.match(/[^\d,，]{1,5}[區鄉鎮]/);
            if (dm) district = dm[0];
        }
        // 門牌：直接 regex 抓「路/街」到「號」的完整門牌
        if (!street && (raw.includes('路') || raw.includes('街')) && raw.includes('號')) {
            const sm = raw.match(/[^\s,，]*[路街][^\s,，]*號[^\s,，]*/);
            if (sm) {
                street = sm[0]
                    // 移除開頭可能的 pin 圖示字元（非中文/數字）
                    .replace(/^[^一二三四五六七八九十百千萬\d\u4e00-\u9fa5]/, '')
                    // 移除含狀態關鍵字的括號整組，例如 (已接委託)
                    .replace(/\([^)]*(?:已接委託|已售|已下架|委託中|已租|結案)[^)]*\)/g, '')
                    // 移除剩下的狀態文字（不含括號的）
                    .replace(/已接委託|已售|已下架|委託中|已租|結案/g, '')
                    // 移除殘留的空括號 ()
                    .replace(/\(\s*\)/g, '')
                    .trim();
            }
        }
        if (district && street) break;
    }

    // ── 查閱連結提取（只在黃色列中取） ────────────────
    let transcriptUrl = '';
    if (hasYellow) {
        const links = Array.from(targetRow.querySelectorAll('a'));
        for (let a of links) {
            const href = a.href || '';
            // 優先抓 BuildingDialog / Transcript 格式
            if (href.includes('BuildingDialog') || href.includes('Transcript')) {
                transcriptUrl = href;
                break;
            }
            // 備援：按鈕文字為「查閱」
            if ((a.innerText || '').trim() === '查閱' && href) {
                transcriptUrl = href;
                break;
            }
        }
        // 最後備援：取該列第一個有效 <a>
        if (!transcriptUrl) {
            const firstA = targetRow.querySelector('a[href]');
            if (firstA) transcriptUrl = firstA.href;
        }
    }

    return {
        count        : dataRows.length,
        yellowCount  : yellowRows.length,   // 實際黃色列數
        hasYellow    : hasYellow,
        address      : district + street,
        transcriptUrl: transcriptUrl
    };
}"""


# ── 掃描所有 frames ────────────────────────────────────
def scan_all_frames(page):
    """逐一掃描所有 frame，回傳第一個有效結果"""
    for frame in page.frames:
        try:
            res = frame.evaluate(SCAN_JS)
            if res is None:
                continue
            if res.get('count', -1) == 0:
                return res          # 明確 0 筆，直接回傳
            if res.get('address'):
                return res          # 有解析到地址才算有效
        except Exception:
            continue
    return None


# ── 多執行緒防撞車機制 ──────────────────────────────────
import threading
import concurrent.futures

gspread_lock = threading.Lock()
login_lock = threading.Lock()
print_lock = threading.Lock()
stop_event = threading.Event() # 🚨 用來通知所有線程「馬上停止」

def safe_print(*args, **kwargs):
    with print_lock:
        print(*args, **kwargs)

# ── 單筆工作處理函數 ──────────────────────────────────────
def process_single_task(idx, task, total_tasks, wks):
    if stop_event.is_set(): return
    row_num  = task["row_num"]
    url      = task["url"]
    case_id  = task["id"]

    try:
        # 每個 thread 獨立建立 Playwright 連線與 context
        with sync_playwright() as p:
            if stop_event.is_set(): return
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            context = browser.contexts[0]
            page = context.new_page()

            safe_print(f"({idx+1}/{total_tasks}) ID:{case_id} → [處理中]...")

            try:
                page.goto(url, wait_until="load", timeout=45000)
                
                # 動態掃描：最多等 10 秒，只要一有資料就提早結束空等，全速前進下一筆！
                result = None
                for _ in range(10):
                    if stop_event.is_set(): return
                    try:
                        page.click('text=找房屋', timeout=1000)
                    except Exception:
                        pass
                    
                    result = scan_all_frames(page)
                    if result is not None:
                        break
                    time.sleep(1)

                # ── 找不到頁面：讓使用者手動確認登入 ──
                if result is None:
                    with login_lock:
                        # 進入 lock 後先重探一次，避免其他執行緒已經介入登入過了
                        result = scan_all_frames(page)
                        if result is None:
                            safe_print('\a\n⚠️ ====================================================')
                            safe_print(f"❌ 警告: ID:{case_id} 找不到資料表！可能是尚未登入！")
                            ans = input("    >>> [人工介入] 請處理好 Chrome 登入後按 Enter 重試 (或輸入 n 放棄此筆): ").strip().lower()
                            
                            if ans != 'n':
                                safe_print(f"    [系統] ID:{case_id} 重新載入頁面重試中...")
                                page.goto(url, wait_until="load", timeout=45000)
                                
                                result = None
                                for _ in range(10):
                                    if stop_event.is_set(): return
                                    try:
                                        page.click('text=找房屋', timeout=1000)
                                    except:
                                        pass
                                    result = scan_all_frames(page)
                                    if result is not None:
                                        break
                                    time.sleep(1)

                # ── 情況判斷與結果準備 ──────────────────────
                addr = ""
                t_url = ""
                status_symbol = ""

                if result is None:
                    addr = "查無"
                    status_symbol = "❌ 放棄或重試失敗 → 填「查無」"

                elif result.get('count', 0) == 0:
                    addr = "查無"
                    status_symbol = "🔍 查無結果 → 填「查無」"

                elif result.get('yellowCount', 0) == 1:
                    addr  = result.get('address', '解析失敗')
                    t_url = result.get('transcriptUrl', '')
                    status_symbol = f"✨ {addr}  🔗 查戶籍已填" if t_url else f"✨ {addr}  ⚠️ 無法取得查戶籍連結"

                elif result.get('yellowCount', 0) > 1:
                    addr = result.get('address', '解析失敗') + f"(需比對：{result['yellowCount']}筆)"
                    status_symbol = f"⚠️ {addr}  [黃色列有 {result['yellowCount']} 筆]"

                elif result.get('count', 0) == 1:
                    addr = result.get('address', '解析失敗') + "(疑似)"
                    status_symbol = f"❓ {addr}"

                else:
                    addr = result.get('address', '解析失敗') + f"(需比對：{result['count']}筆)"
                    status_symbol = f"⚠️ {addr}"

                # ── 排隊寫入試算表 ────────────────────────
                if stop_event.is_set(): return
                with gspread_lock:
                    wks.update_cell(row_num, COL_ADDR, addr)
                    if t_url:
                        wks.update_cell(row_num, COL_HIST, t_url)
                    safe_print(f"  └─ ({idx+1}/{total_tasks}) ID:{case_id} 完工: {status_symbol}")

            except Exception as e:
                safe_print(f"💥 ({idx+1}/{total_tasks}) ID:{case_id} 處理時發生錯誤: {e}")
            finally:
                page.close()

    except Exception as e:
        safe_print(f"❌ ({idx+1}/{total_tasks}) ID:{case_id} 腳本連線瀏覽器失敗: {e}")


# ── 主程式 ────────────────────────────────────────────
def run_enricher():
    print("\n" + "="*60)
    print("【住通地籍查閱補完工具 v4.0 — 多核併發極速版】")
    print("="*60)

    # 1. 連接 Google 試算表
    try:
        creds  = ServiceAccountCredentials.from_json_keyfile_name(
            CREDS_FILE,
            ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        )
        client   = gspread.authorize(creds)
        wks      = client.open_by_key(SHEET_KEY).sheet1
        all_rows = wks.get_all_values()
        print(f"[系統] 成功連接試算表，共 {len(all_rows) - 1} 筆資料。")
    except Exception as e:
        print(f"❌ 雲端連線失敗: {e}")
        return

    # 2. 篩選待處理列：L 有 URL 且 M 是空的
    target_rows = []
    for i, row in enumerate(all_rows):
        if i == 0:
            continue  # 跳過標題列
        url_val  = (row[IDX_URL]  if len(row) > IDX_URL  else "").strip()
        addr_val = (row[IDX_ADDR] if len(row) > IDX_ADDR else "").strip()
        dlg_val  = (row[15] if len(row) > 15 else "").strip() # P欄
        
        # 若已委託為 Y，就不掃描直接跳過
        if dlg_val == 'Y':
            continue
            
        if url_val and not addr_val:
            target_rows.append({
                "row_num": i + 1,
                "url"    : url_val,
                "id"     : row[0]
            })

    if not target_rows:
        print("✅ 目前沒有待處理的資料（M 欄已全部填寫或 L 欄無連結）。")
        return

    total_tasks = len(target_rows)
    print(f"[情報] 找到 {total_tasks} 筆待補完資料，準備同時開啟多個分頁...")
    print(f"⚠️  [注意] 避免登入狀態衝突，系統改為一次開啟 1 個案件循序處理。\n")

    # 3. 單線程依序處理 (支援 Ctrl+C 終止)
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    futures = []
    try:
        for idx, task in enumerate(target_rows):
            if stop_event.is_set(): break
            futures.append(executor.submit(process_single_task, idx, task, total_tasks, wks))
            time.sleep(0.3)  # 微幅錯開每條線程啟動時間，避免瞬間同時向 Chrome 狂轟濫炸
            
        # 主執行緒安靜等待結果，確保能在這裡截獲 Ctrl+C (KeyboardInterrupt)
        for f in concurrent.futures.as_completed(futures):
            f.result() 

    except KeyboardInterrupt:
        safe_print("\n🛑 收到強制中止訊號 (Ctrl+C)！正在緊急煞車...")
        stop_event.set()           # 通知所有在跑的任務放棄
        for f in futures:
            f.cancel()             # 取消還在排隊的任務
        executor.shutdown(wait=False) # 立刻關閉執行池，不等待
        import sys
        sys.exit(0)
    finally:
        executor.shutdown(wait=True)

    print("\n🎉 全部任務完成！")

if __name__ == "__main__":
    run_enricher()
