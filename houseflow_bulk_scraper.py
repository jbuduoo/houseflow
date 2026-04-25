import time
import json
import os
from playwright.sync_api import sync_playwright

# 設定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(BASE_DIR, "full_customer_skills.json")

def extract_details(page):
    """在詳細資訊頁面中抓取配對指標"""
    try:
        # 切換到「銷售配對」分頁
        # 根據觀察，可能需要等待該分頁標籤出現
        matching_tab = page.query_selector("text=銷售配對")
        if matching_tab:
            matching_tab.click()
        else:
            # 嘗試使用通用的配對 Tab 選擇器
            page.click(".nav-tabs a:has-text('配對')", timeout=3000)
            
        time.sleep(1.5)
        
        # 抓取數值 (根據 HouseFlow 系統常見 ID)
        details = {
            "budget_range": [
                page.input_value("#BudgetMin") if page.query_selector("#BudgetMin") else "0",
                page.input_value("#BudgetMax") if page.query_selector("#BudgetMax") else "99999"
            ],
            "rooms_range": [
                page.input_value("#RoomsMin") if page.query_selector("#RoomsMin") else "0",
                page.input_value("#RoomsMax") if page.query_selector("#RoomsMax") else "99"
            ],
            "floor_range": [
                page.input_value("#FloorMin") if page.query_selector("#FloorMin") else "0",
                page.input_value("#FloorMax") if page.query_selector("#FloorMax") else "99"
            ],
            "building_type": page.inner_text("#BuildingType") if page.query_selector("#BuildingType") else "不限",
            "region": page.inner_text("#RegionList") if page.query_selector("#RegionList") else "未指定"
        }
        return details
    except Exception as e:
        print(f"    [警告] 詳細資料抓取失敗: {e}")
        return {}

def run_scraper():
    with sync_playwright() as p:
        # 開啟有介面模式，以便使用者手動登入
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        print("\n" + "="*50)
        print("【住通 HouseFlow 批量抓取工具】啟動中...")
        print("請在彈出的瀏覽器中完成：\n1. 輸入帳號密碼\n2. 輸入圖形驗證碼\n3. 點擊進入系統")
        print("="*50 + "\n")

        page.goto("https://app.houseflow.tw/HOUSE/Customer")
        
        # 等待登入成功標誌 (例如客戶代碼欄位出現)
        try:
            page.wait_for_selector("td[data-title='客戶代碼']", timeout=300000) # 給予 5 分鐘登入時間
        except:
            print("等待登入超時，程式結束。")
            return

        print("--- 偵測到登入成功，開始自動流程 ---")

        all_customers = []
        current_page = 1

        while True:
            print(f"\n>>> 正在抓取第 {current_page} 頁...")
            page.wait_for_selector("tr[id^='tr_']")
            
            # 獲取當前頁面的客戶列
            rows_count = page.locator("tr[id^='tr_']").count()
            print(f"本頁偵測到 {rows_count} 位客戶。")
            
            for i in range(rows_count):
                try:
                    row = page.locator("tr[id^='tr_']").nth(i)
                    
                    # 抓取列表上的基本資訊
                    name = row.locator("td[data-title='客戶姓名']").inner_text().strip()
                    phone = row.locator("td[data-title='聯絡電話']").inner_text().strip()
                    
                    print(f"  [{i+1}/{rows_count}] 進入客戶: {name}")
                    
                    # 點擊進入詳情
                    row.click()
                    time.sleep(2)
                    
                    # 抓取詳細 Skill 指標
                    skill_data = extract_details(page)
                    
                    all_customers.append({
                        "customer_name": name,
                        "phone": phone,
                        "skills": skill_data,
                        "source": "HouseFlow",
                        "updated_at": time.strftime("%Y-%m-%d %H:%M")
                    })
                    
                    # 返回列表頁並等待加載
                    page.go_back()
                    page.wait_for_selector("tr[id^='tr_']", timeout=10000)
                    time.sleep(1)
                    
                except Exception as e:
                    print(f"  [錯誤] 處理第 {i+1} 筆客戶時發生異常: {e}")
                    # 嘗試強制返回列表頁
                    page.goto("https://app.houseflow.tw/HOUSE/Customer")
                    page.wait_for_selector("tr[id^='tr_']")

            # 儲存進度
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(all_customers, f, ensure_ascii=False, indent=2)

            # 翻頁邏輯 (假設翻頁按鈕有 .GotoPageButton)
            current_page += 1
            page_input = page.query_selector("#Page")
            if page_input:
                page.fill("#Page", str(current_page))
                page.press("#Page", "Enter")
                time.sleep(3) # 等待跳轉
            else:
                print("未偵測到翻頁控制項，抓取結束。")
                break

        print(f"\n恭喜！全部抓取任務完成。")
        print(f"總計獲取: {len(all_customers)} 位客戶 Skill 檔案。")
        print(f"存檔路徑: {OUTPUT_FILE}")
        browser.close()

if __name__ == "__main__":
    run_scraper()
