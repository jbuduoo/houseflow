"""
houseflow_registry_fetcher.py
正式版 v3.0 — 找「建築物所有權部」底下的住址欄位。
若 input 有值 → 直接寫入；若為空 → OCR 讀取住址圖片。
"""

import time
import os
import re
import sys
import base64
import io
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from playwright.sync_api import sync_playwright
import urllib.request
import urllib.parse
import json

os.environ["NODE_OPTIONS"] = "--no-deprecation"

# 取得金鑰檔案的絕對路徑 (支援從根目錄或 core 執行)
_base_dir = os.path.dirname(os.path.abspath(__file__))
CREDS_FILE = os.path.join(_base_dir, "houseflow_gheet_key.json.json")
if not os.path.exists(CREDS_FILE):
    CREDS_FILE = os.path.join(_base_dir, "..", "houseflow_gheet_key.json.json")
SHEET_KEY  = "1bU4BKbjQgnoNqSK50G4vHgMGBFetHsBrbMyHv2Xc2k0"

IDX_N = 13   # N: 查戶籍 URL (輸入)
IDX_O = 14   # O: 戶籍地址  (輸出)

# 定義欄位名稱以便動態尋找
HEAD_OBJ_ADDR = "查地址"
HEAD_RES_ADDR = "戶籍地址"
HEAD_OBJ_LAT  = "物件緯度"
HEAD_OBJ_LON  = "物件經度"
HEAD_RES_LAT  = "戶籍緯度"
HEAD_RES_LON  = "戶籍經度"

# ── OCR 引擎（延遲初始化，只在需要時載入）────────────────
_ocr_reader = None

def get_ocr_reader():
    global _ocr_reader
    if _ocr_reader is None:
        try:
            import easyocr
            print("[系統] 初始化 OCR 引擎（首次需下載模型，請稍候）...")
            _ocr_reader = easyocr.Reader(['ch_tra', 'en'], gpu=False, verbose=False)
            print("[系統] OCR 引擎就緒。")
        except ImportError:
            print("[警告] 需要安裝 OCR 套件，請執行：\n"
                  "    pip install easyocr pillow numpy")
            return None
    return _ocr_reader


def ocr_from_img_src(img_src: str) -> str:
    """從 data:image base64 的 img src 讀取文字（繁體中文）"""
    if not img_src or not img_src.startswith("data:image"):
        return ""
    try:
        import numpy as np
        from PIL import Image, ImageOps, ImageEnhance

        _, b64 = img_src.split(",", 1)
        img_bytes = base64.b64decode(b64)
        img       = Image.open(io.BytesIO(img_bytes)).convert("RGB")

        # 放大 4 倍以提升 OCR 準確率（原圖約 24px 高，太小）
        w, h  = img.size
        img   = img.resize((w * 4, h * 4), Image.LANCZOS)
        
        # 影像前處理：灰階、高對比、銳化
        img = ImageOps.grayscale(img)
        img = ImageEnhance.Contrast(img).enhance(3.0)
        img = ImageEnhance.Sharpness(img).enhance(2.0)
        
        # 轉為 numpy array 方可正確餵給 easyocr
        img_np = np.array(img)

        reader  = get_ocr_reader()
        if reader is None:
            return ""
            
        results = reader.readtext(
            img_np,
            detail=0,
            paragraph=True
        )
        
        # 後處理：去除多餘空格，修正常見的 AI 辨識錯字
        text = "".join(results).strip()
        text = text.replace(" ", "").replace("　", "")
        
        # 常見 OCR 錯字校正
        text = text.replace("耋", "臺")
        text = text.replace("+", "十")   # 修正「十四樓」變「+四樓」
        text = text.replace("r", "「")   # 有時括號會辨識成英文字母
        text = text.replace("J", "」")
        
        return text
    except Exception as e:
        print(f"  [OCR錯誤] {e}")
        return ""


def clean_address_logic(addr):
    """移植自 4_apply_clean_o_col.py 的清理邏輯"""
    cleaned = str(addr).strip()
    if not cleaned or cleaned in ["", "查無", "解析失敗", "待查閱"]:
        return cleaned

    # 1. 抹除所有括號
    cleaned = cleaned.replace("(", "").replace(")", "").replace("（", "").replace("）", "")

    # 2. 全形數字轉半形數字
    trans_map = str.maketrans("０１２３４５６７８９", "0123456789")
    cleaned = cleaned.translate(trans_map)

    # 3. 統一「臺」為「台」
    cleaned = cleaned.replace("臺", "台")

    # 4. 縣市升格轉換
    cleaned = re.sub(r'台北縣', '新北市', cleaned)
    cleaned = re.sub(r'台中縣', '台中市', cleaned)
    cleaned = re.sub(r'台南縣', '台南市', cleaned)
    cleaned = re.sub(r'高雄縣', '高雄市', cleaned)
    cleaned = re.sub(r'桃園縣', '桃園市', cleaned)

    # 5. 鄉鎮市改制為「區」 (僅限五都與桃園)
    def replace_district(match):
        city = match.group(1)
        dist_name = match.group(2)
        return f"{city}{dist_name}區"
    cleaned = re.sub(r'(新北市|台中市|台南市|高雄市|桃園市)(.{1,3}?)[鄉鎮市]', replace_district, cleaned)

    # 6. 去除「里」或「村」
    cleaned = re.sub(r'(?<=[區鄉鎮市])[^區鄉鎮市里村]+[里村]', '', cleaned)
    
    # 7. 去除「鄰」
    cleaned = re.sub(r'[0-9]{1,3}鄰', '', cleaned)

    return cleaned


# ── JS：用 TreeWalker 依序掃描，最精準找建築物所有權部的住址 ─
EXTRACT_JS = r"""() => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ALL);
    let node;
    let section = 0; // 0=還沒到, 1=在所有權部內, 2=已離開
    let currentLabel = '';
    const R = { inputValue: '', imgSrc: '', imgW: 0, imgH: 0 };

    while ((node = walker.nextNode())) {
        if (node.nodeType === Node.TEXT_NODE) {
            // 洗掉所有空白與全形空白
            let t = node.textContent.replace(/[\s\u3000]/g, '');
            if (t.length === 0) continue;

            if (t.includes('建築物所有權部') || t.includes('建物所有權部')) {
                section = 1;
            } else if (section === 1 && t.includes('＊＊＊＊＊＊＊＊＊＊') && !t.includes('所有權部')) {
                // 遇到下一個區塊了
                section = 2; 
                break;
            } else if (section === 1) {
                // 記錄目前遇到什麼欄位標籤
                if (t.includes('住址') || t.includes('住所')) {
                    currentLabel = '住址';
                } else if (!t.includes('資料偵查') && !t.includes('異動索引') && t.length > 2) {
                    currentLabel = t; // 如果遇到像是「權利範圍」，就把記錄蓋掉
                }
            }
        } 
        else if (node.nodeType === Node.ELEMENT_NODE && section === 1) {
            // 如果我們現在的上下文是「住址」
            if (currentLabel === '住址') {
                if (node.tagName === 'INPUT' && (node.type === 'text' || !node.type)) {
                    let val = node.value.trim();
                    // 只抓第一個不是空的
                    if (!R.inputValue && val) {
                        R.inputValue = val;
                    }
                }
                else if (node.tagName === 'IMG') {
                    // 為了避免抓到小按鈕的圖片，過濾寬度太小的
                    if (!R.imgSrc && node.naturalWidth > 50) {
                        R.imgSrc = node.src;
                        R.imgW = node.naturalWidth;
                        R.imgH = node.naturalHeight;
                    }
                }
            }
        }
    }
    return R;
}"""


def scan_all_frames(page):
    """掃描所有 frame，回傳第一個有結果的 frame 資料"""
    for frame in page.frames:
        try:
            res = frame.evaluate(EXTRACT_JS)
            if res and (res.get("inputValue") or res.get("imgSrc")):
                return res
        except Exception:
            continue
    return None


def run_fetcher():
    print("\n" + "=" * 60)
    print("【住通戶籍地址擷取工具 v3.1 — 深度解析防當版】")
    print("=" * 60)

    # 1. 連接試算表
    try:
        creds  = ServiceAccountCredentials.from_json_keyfile_name(
            CREDS_FILE,
            ["https://spreadsheets.google.com/feeds",
             "https://www.googleapis.com/auth/drive"]
        )
        client   = gspread.authorize(creds)
        wks      = client.open_by_key(SHEET_KEY).sheet1
        all_rows = wks.get_all_values()
        print(f"[系統] 成功連接試算表，共 {len(all_rows)-1} 筆資料。")
    except Exception as e:
        print(f"❌ 雲端連線失敗: {e}")
        return

    # 1.1 動態尋找欄位 Index
    headers = all_rows[0]
    try:
        idx_m_addr = headers.index(HEAD_OBJ_ADDR)
        idx_o_addr = headers.index(HEAD_RES_ADDR)

        idx_n_url   = IDX_N # 直接使用預設的第 13 欄 (N)
    except ValueError as e:
        print(f"❌ 找不到必要的欄位: {e}")
        return

    # 2. 篩選需要處理的資料
    target_rows = []
    for i, row in enumerate(all_rows):
        if i == 0: continue
        row_num = i + 1
        
        # 取得關鍵欄位資料
        n_url = (row[idx_n_url] if len(row) > idx_n_url else "").strip()
        o_addr = (row[idx_o_addr] if len(row) > idx_o_addr else "").strip()
        m_addr = (row[idx_m_addr] if len(row) > idx_m_addr else "").strip()
        # A. 是否需要抓取戶籍地址 (N 有值，O 是空或失敗)
        need_fetch = n_url and "houseflow" in n_url and (not o_addr or "失敗" in o_addr)
        
        if need_fetch:
            target_rows.append({
                "row_num": row_num,
                "url": n_url,
                "id": row[0],
                "row_data": row
            })

    if not target_rows:
        print("✅ 目前資料都是齊全的（抓取、清理、座標皆已完成）。")
        return

    print(f"[情報] 找到 {len(target_rows)} 筆資料需要處理（抓取/補座標）...\n")

    # 3. 連接瀏覽器
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            context = browser.contexts[0]
            print("[系統] 成功連上瀏覽器。\n")
        except Exception as e:
            print(f"❌ 請確認【開路先鋒.bat】已啟動: {e}")
            return

        for idx, task in enumerate(target_rows):
            row_num = task["row_num"]
            case_id = task["id"]
            url     = task["url"]

            print(f"({idx+1}/{len(target_rows)}) ID:{case_id}", end=" → ")


            # --- 以下為需要開啟網頁抓取的情況 ---
            page = context.new_page()

            try:
                page.goto(url, wait_until="load", timeout=45000)

                # 如果是第一筆，先停下來讓使用者登入
                if idx == 0:
                    print(f"\n[提示] 正在開啟第一筆 URL。")
                    print("請在瀏覽器中完成帳密輸入與登入，確認進入系統後，再回到這裡按「Enter」繼續...")
                    input(" >>> 已完成登入，請按 Enter 開始執行抓取任務 <<<")
                    print("")

                time.sleep(3)
                res = scan_all_frames(page)

                row_updates = []
                final_cleaned_addr = ""

                if res is None:
                    row_updates.append(gspread.Cell(row=row_num, col=idx_o_addr + 1, value="解析失敗"))
                    print("[警告] 頁面無法解析", end="")

                elif res.get("inputValue"):
                    raw_addr = res["inputValue"]
                    final_cleaned_addr = clean_address_logic(raw_addr)
                    row_updates.append(gspread.Cell(row=row_num, col=idx_o_addr + 1, value=final_cleaned_addr))
                    print(f"[OK] {final_cleaned_addr}", end="")

                elif res.get("imgSrc"):
                    ocr_text = ocr_from_img_src(res["imgSrc"])
                    if ocr_text:
                        final_cleaned_addr = clean_address_logic(ocr_text)
                        display_addr = f"{final_cleaned_addr}(OCR)"
                        row_updates.append(gspread.Cell(row=row_num, col=idx_o_addr + 1, value=display_addr))
                        print(f"[OCR] {display_addr}", end="")
                        # 重點：OCR 辨識出的地址當下「不」進行座標查詢
                        final_cleaned_addr = "" 
                    else:
                        row_updates.append(gspread.Cell(row=row_num, col=idx_o_addr + 1, value="OCR失敗"))
                        print("[OCR失敗]", end="")

                # 一次寫回該列所有更新
                if row_updates:
                    wks.update_cells(row_updates)
                print("") # 換行

            except Exception as e:
                print(f"[錯誤] {e}")
            finally:
                page.close()

            time.sleep(1.5)

    print("\n[完工] 全部任務完成！")


if __name__ == "__main__":
    run_fetcher()
