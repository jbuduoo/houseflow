import time
import os
import gspread
import re
from oauth2client.service_account import ServiceAccountCredentials
from playwright.sync_api import sync_playwright

# 設定
CREDS_FILE = "houseflow_gheet_key.json.json"
SHEET_KEY = "1bU4BKbjQgnoNqSK50G4vHgMGBFetHsBrbMyHv2Xc2k0"

def run_enricher():
    print("\n" + "="*60)
    print("【住通地籍門牌 - 數據淨化版 v1.9】")
    print("="*60)

    # 1. 連接試算表
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive'])
        client = gspread.authorize(creds)
        wks = client.open_by_key(SHEET_KEY).sheet1
        all_rows = wks.get_all_values()
        print(f"[系統] 成功連接試算表。")
    except Exception as e:
        print(f"[錯誤] 無法連接試算表: {e}")
        return

    to_process = [r for r in [{"row_idx": i + 1, "id": row[0]} for i, row in enumerate(all_rows) if i > 0 and len(row) > 12 and row[12].strip() == ""]]
    if not to_process:
        print("✅ 目前沒有需要深挖地址的物件。")
        return

    to_process = to_process[:15]
    print(f"[情報] 即將接管網頁，對首批 {len(to_process)} 筆資料進行地址淨化採集...")

    # 2. 接管現有的 Chrome
    with sync_playwright() as p:
        browser = None
        try:
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            context = browser.contexts[0]
            
            # 尋找含有 houseflow 字眼的分頁
            page = None
            for p_obj in context.pages:
                if "houseflow" in p_obj.url:
                    page = p_obj
                    break
            if not page: page = context.new_page()
            
            print(f"[系統] 成功附身瀏覽器！目前頁面: {page.title()}")

            for i, task in enumerate(to_process):
                row_idx = task['row_idx']
                target_id = task['id']
                detail_url = f"https://app.houseflow.tw/HOUSE/ExploreHouseNew?A10OnLineId={target_id}"

                print(f"  ({i+1}/{len(to_process)}) 正在挖掘: {target_id}...")
                try:
                    page.goto(detail_url, timeout=30000)
                    page.wait_for_selector("td:has-text('區')", timeout=10000)
                    
                    addr_info = page.evaluate(r"""() => {
                        const tds = Array.from(document.querySelectorAll('td')).map(td => td.innerText.trim());
                        let district = "";
                        let houseNum = "";
                        
                        for(let j=0; j < tds.length; j++) {
                            const txt = tds[j];
                            if (txt.includes('區') && txt.length < 10) {
                                district = txt.split('\n')[0].trim();
                                if (tds[j+1] && (tds[j+1].includes('路') || tds[j+1].includes('街') || tds[j+1].includes('號'))) {
                                    houseNum = tds[j+1].split('\n')[0].trim();
                                    break;
                                }
                            }
                        }
                        
                        if (!district && !houseNum) return "探測失敗";
                        
                        // 初步清理：移除 9 這個圖標占位符以及多餘換行
                        let cleanHouse = houseNum.replace('9', '').split('\n')[0].trim();
                        // 移除所有 ( ) 號內的備註文字 (如 已接委託、已售)
                        cleanHouse = cleanHouse.replace(/\(已.*?\)/g, "").trim();
                        
                        let finalAddr = district + cleanHouse;
                        if (document.body.innerText.match(/共\s*[2-9]\s*筆/)) finalAddr += "(多筆)";
                        return finalAddr;
                    }""")
                    
                    wks.update_cell(row_idx, 13, addr_info)
                    print(f"    √ 淨化成功: {addr_info}")
                except Exception as e:
                    print(f"    x 跳過: {e}")
                
                time.sleep(1)

        except Exception as e:
            print(f"[錯誤] 瀏覽器連接失敗: {e}")
        finally:
            if browser:
                browser.disconnect()
                print("\n🎉 採集任務已安全結束。")

if __name__ == "__main__":
    run_enricher()

