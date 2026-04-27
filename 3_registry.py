"""
houseflow_registry_fetcher.py
正式版 v3.0 — 找「建築物所有權部」底下的住址欄位。
若 input 有值 → 直接寫入；若為空 → OCR 讀取住址圖片。
"""

import time
import os
import base64
import io
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from playwright.sync_api import sync_playwright

os.environ["NODE_OPTIONS"] = "--no-deprecation"

CREDS_FILE = "houseflow_gheet_key.json.json"
SHEET_KEY  = "1bU4BKbjQgnoNqSK50G4vHgMGBFetHsBrbMyHv2Xc2k0"

IDX_N = 13   # N: 查戶籍 URL (輸入)
IDX_O = 14   # O: 戶籍地址  (輸出)

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
        text = text.replace("耋", "臺").replace("0號", "號")
        
        return text
    except Exception as e:
        print(f"  [OCR錯誤] {e}")
        return ""


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

    # 2. 篩選：N 有 URL，O 為空
    target_rows = []
    for i, row in enumerate(all_rows):
        if i == 0:
            continue
        n_val = (row[IDX_N] if len(row) > IDX_N else "").strip()
        o_val = (row[IDX_O] if len(row) > IDX_O else "").strip()
        if n_val and "houseflow" in n_val and (not o_val or "失敗" in o_val):
            target_rows.append({"row_num": i + 1, "url": n_val, "id": row[0]})

    if not target_rows:
        print("✅ 沒有待處理資料（O 欄已填，或 N 欄無連結）。")
        return

    print(f"[情報] 找到 {len(target_rows)} 筆待查詢，開始處理...\n")

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
            
            # 安全模式：每次跑任務建一個新分頁，跑完關閉
            page = context.new_page()

            try:
                page.goto(url, wait_until="load", timeout=45000)
                time.sleep(3)

                res = scan_all_frames(page)

                if res is None:
                    # 連 section 都找不到
                    wks.update_cell(row_num, IDX_O + 1, "解析失敗")
                    print("[警告] 頁面無法解析建物所有權部")

                elif res.get("inputValue"):
                    # 住址 input 有值 → 直接寫入
                    addr = res["inputValue"]
                    wks.update_cell(row_num, IDX_O + 1, addr)
                    print(f"[OK] {addr}")

                elif res.get("imgSrc"):
                    # 住址 input 空白 → OCR 圖片
                    w, h = res.get("imgW", 0), res.get("imgH", 0)
                    print(f"[圖片] 住址為空，OCR ({w}×{h}px)...", end=" ")
                    ocr_text = ocr_from_img_src(res["imgSrc"])
                    if ocr_text:
                        wks.update_cell(row_num, IDX_O + 1, ocr_text)
                        print(f"[OK] {ocr_text}")
                    else:
                        wks.update_cell(row_num, IDX_O + 1, "OCR失敗")
                        print("[失敗] 無法識別")

                else:
                    # section 找到但住址欄空且無圖片
                    wks.update_cell(row_num, IDX_O + 1, "住址空白")
                    print("[未找到] 住址欄空且無圖片")

            except Exception as e:
                print(f"[錯誤] {e}")
            finally:
                page.close()

            time.sleep(1.5)

    print("\n[完工] 全部任務完成！")


if __name__ == "__main__":
    run_fetcher()
