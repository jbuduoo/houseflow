"""
debug_registry.py
針對「頁面無法解析」的案例， Dump 出 iframe 的 DOM 結構，
同時改用「每次新建分頁再關閉」以避開 TargetClosedError
"""

import time
import os
from playwright.sync_api import sync_playwright

os.environ["NODE_OPTIONS"] = "--no-deprecation"

TARGETS = [
    # 這是剛才報錯的 4 個 URL
    "https://app.houseflow.tw/HOUSE/Transcript/BuildingDialog/F33185204593000?HostId=2&A10OnLineId=2642156",
    "https://app.houseflow.tw/HOUSE/Transcript/BuildingDialog/F33184904450000?HostId=2&A10OnLineId=3434661",
    "https://app.houseflow.tw/HOUSE/Transcript/BuildingDialog/F33185603365000?HostId=2&A10OnLineId=3434504",
    "https://app.houseflow.tw/HOUSE/Transcript/BuildingDialog/F33182404127000?HostId=2&A10OnLineId=3434698",
]

DEBUG_JS = r"""() => {
    // 找出頁面裡所有包含「所有權部」或「住址」的元素，觀察它們所在的標籤位置
    const results = [];
    const elements = document.querySelectorAll('td, th, div, span, p');
    let sectionFound = false;
    
    for (let el of elements) {
        let text = (el.innerText || '').trim();
        // 為了避免印太多太長，只過濾短字串
        if (text.includes('建築物所有權部') || text.includes('建物所有權部')) {
            sectionFound = true;
            results.push(`[標題] <${el.tagName.toLowerCase()}> ${text}`);
        } else if (sectionFound && (text.includes('住址') || text.includes('住所') || text.includes('住　址'))) {
            // 找到標題後遇到的住址標籤，把整列的 tagName 印出來
            const parentHTML = el.parentElement ? el.parentElement.innerHTML.substring(0, 150) : '';
            results.push(`[標籤] <${el.tagName.toLowerCase()}> ${text}`);
            
            // 往上找 input 或 img
            const wrap = el.closest('tr') || el.closest('table') || document;
            const input = wrap.querySelector('input[type="text"]');
            if (input) {
                results.push(`  → 找到 input: value="${input.value}"`);
            }
            const img = wrap.querySelector('img');
            if (img) {
                results.push(`  → 找到 img: src=${img.src.substring(0, 40)}...`);
            }
        }
    }
    
    // 如果找不到，就把所有的 input 列出來
    if (results.length === 0) {
        const inputs = Array.from(document.querySelectorAll('input'));
        inputs.forEach(i => results.push(`[迷失的 input] value="${i.value}"`));
    }
    return results;
}"""

def run_debug():
    print("="*60)
    print("【DOM 結構診斷工具】")
    print("="*60)

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            context = browser.contexts[0]
        except Exception as e:
            print(f"❌ 瀏覽器連線失敗: {e}")
            return

        with open("debug_output.txt", "w", encoding="utf-8") as f:
            for idx, url in enumerate(TARGETS):
                f.write(f"\n({idx+1}/{len(TARGETS)}) 測試 URL: {url}\n")
                print(f"處理中: {idx+1}/{len(TARGETS)}")
                
                # 安全模式：每次跑任務建一個新分頁，跑完關閉
                page = context.new_page()
                
                try:
                    page.goto(url, wait_until="load", timeout=45000)
                    time.sleep(3)
                    
                    found_any = False
                    for f_idx, frame in enumerate(page.frames):
                        try:
                            res = frame.evaluate(DEBUG_JS)
                            if res and len(res) > 0:
                                found_any = True
                                f.write(f"  [Frame {f_idx}] 萃取結果:\n")
                                for line in res:
                                    f.write(f"    {line}\n")
                        except Exception:
                            pass
                    
                    if not found_any:
                        f.write("  ⚠️ Frame 裡找不到對應文字，或頁面尚未載入\n")
                        
                except Exception as e:
                    f.write(f"  💥 執行時錯誤: {e}\n")
                finally:
                    page.close()  # 確實關閉分頁釋放記憶體
                    time.sleep(1)

        print("輸出已寫入 debug_output.txt")

if __name__ == "__main__":
    run_debug()
