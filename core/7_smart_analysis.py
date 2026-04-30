import os
import time
import re
import gspread
from oauth2client.service_account import ServiceAccountCredentials

_base_dir = os.path.dirname(os.path.abspath(__file__))
CREDS_FILE = os.path.join(_base_dir, "houseflow_gheet_key.json.json")
if not os.path.exists(CREDS_FILE):
    CREDS_FILE = os.path.join(_base_dir, "..", "houseflow_gheet_key.json.json")
SHEET_KEY  = "1bU4BKbjQgnoNqSK50G4vHgMGBFetHsBrbMyHv2Xc2k0"

def extract_street_numbers(address_text):
    """
    從字串中提取所有路/街及數字門牌
    例如: "中和路10號,12號" -> ["中和路10號", "12號", "10號"]
    回傳所有出現過的號碼數字 (以 list 儲存)
    """
    if not address_text: return []
    # 找尋所有數字+號
    matches = re.findall(r'(\d+)號', address_text)
    return matches

def smart_analyze(m_val, y_val, z_val):
    """
    根據 M(查地址), Y(反查地址), Z(座標來源) 進行 10 種情境研判
    """
    m_val = str(m_val).strip()
    y_val = str(y_val).strip()
    z_val = str(z_val).strip()

    # 1. 判斷 M 欄狀態
    is_perfect = "✨" in m_val
    is_suspect = "❓" in m_val
    is_multiple = "⚠️" in m_val
    is_not_found = "查無" in m_val or m_val == ""

    # 清理 M 欄文字作為顯示基底
    clean_m = re.sub(r'[✨❓⚠️]', '', m_val).strip()

    # 2. 判斷 Y 欄 (定位反查)
    has_rev = y_val != ""
    # 若來源是 ArcGIS，我們不視為有效驗證 (因為是自己推算的)
    if z_val == "ArcGIS":
        has_rev = False
        y_val = ""

    clean_y = y_val.replace("(座標反查)", "").strip()

    # 3. 判斷是否吻合 (交集比對)
    is_match = False
    if has_rev and not is_not_found:
        m_nums = extract_street_numbers(clean_m)
        y_nums = extract_street_numbers(clean_y)
        
        # 只要反查出來的號碼，存在於 M 欄的號碼清單中，就算吻合
        if y_nums and any(num in m_nums for num in y_nums):
            is_match = True
        elif not m_nums and not y_nums and clean_m and clean_y:
            # 兩邊都沒號碼，那就比對純文字路名
            if clean_y in clean_m or clean_m in clean_y:
                is_match = True

    # 4. 依照 10 種情境輸出
    if is_perfect:
        if has_rev and is_match:
            return f"🎯 雙重確認：【{clean_m}】 (備註：產權與網頁座標完美重合，請安心開發)"
        elif has_rev and not is_match:
            return f"🎯 真實門牌：【{clean_m}】 (⚠️ 注意：網頁座標刻意偏移至 {clean_y}，請忽略座標)"
        else:
            return f"🎯 系統推算：【{clean_m}】 (備註：無地圖定位可驗證，請依此門牌尋訪)"
            
    elif is_suspect:
        if has_rev and is_match:
            return f"🎯 雙重確認：推薦為【{clean_m}】 (備註：產權比對為疑似，但座標命中補足了信賴度)"
        elif has_rev and not is_match:
            return f"❓ 疑似門牌：【{clean_m}】 (⚠️ 注意：產權未100%吻合，且座標定於 {clean_y}，兩者皆需存疑)"
        else:
            return f"❓ 疑似門牌：【{clean_m}】 (備註：產權未100%吻合，且無地圖定位可驗證)"
            
    elif is_multiple:
        if has_rev and is_match:
            return f"🎯 座標助攻：推薦為【{clean_y}】 (備註：產權符合多筆，但座標精確命中 {clean_y})"
        elif has_rev and not is_match:
            return f"🔍 真實門牌應為：【{clean_m}】之一 (⚠️ 注意：座標定位於 {clean_y}，未命中產權清單，僅供參考)"
        else:
            return f"🔍 需實地確認：【{clean_m}】 (備註：產權符合多筆，無座標可輔助篩選)"
            
    else: # 查無
        if has_rev:
            return f"📍 地圖定位：疑似在【{clean_y}】附近 (備註：產權條件有誤導致查無資料，請至實地尋訪)"
        else:
            return f"❌ 查無有效開發資訊 (備註：產權與座標皆無法取得)"


def run_smart_analysis():
    print("\n" + "="*60)
    print("【住通 AI 綜合研判系統 v1.0】")
    print("="*60)

    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            CREDS_FILE,
            ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        )
        client = gspread.authorize(creds)
        wks = client.open_by_key(SHEET_KEY).sheet1
        all_rows = wks.get_all_values()
        print(f"[系統] 成功連接試算表，共 {len(all_rows) - 1} 筆資料。")
    except Exception as e:
        print(f"❌ 雲端連線失敗: {e}")
        return

    if not all_rows:
        return

    headers = all_rows[0]
    
    # 動態取得欄位 Index
    try: IDX_M_ADDR = headers.index("查地址")
    except ValueError: IDX_M_ADDR = 12

    try: IDX_Y_REV_ADDR = headers.index("反查地址")
    except ValueError: IDX_Y_REV_ADDR = 24

    try: IDX_Z_COORD_SRC = headers.index("座標來源")
    except ValueError: IDX_Z_COORD_SRC = 25
    
    # 嘗試尋找 AA 欄，沒有則寫入 26
    try: IDX_AA_ANALYSIS = headers.index("系統綜合研判")
    except ValueError: IDX_AA_ANALYSIS = 26

    update_cells = []
    
    print("[情報] 開始執行 10 項情境分析交叉比對...\n")
    
    try:
        for i, row in enumerate(all_rows):
            if i == 0: continue
            
            def get_val(idx):
                return row[idx].strip() if len(row) > idx else ""

            m_val = get_val(IDX_M_ADDR)
            y_val = get_val(IDX_Y_REV_ADDR)
            z_val = get_val(IDX_Z_COORD_SRC)
            aa_val = get_val(IDX_AA_ANALYSIS)
            
            # 若 M, Y 都有或查無，可以研判。如果有舊的，直接覆寫也無妨
            conclusion = smart_analyze(m_val, y_val, z_val)
            
            # 只有當算出來的結果跟原本不同才寫入，節省網路
            if conclusion != aa_val:
                update_cells.append(gspread.Cell(row=i+1, col=IDX_AA_ANALYSIS+1, value=conclusion))
                print(f"  [ID:{row[0]}] 產生研判：{conclusion}")

            # 批次備份
            if len(update_cells) >= 100:
                print(f"  ...寫入 100 筆資料至雲端...")
                wks.update_cells(update_cells)
                update_cells.clear()
                time.sleep(1)

    except KeyboardInterrupt:
        print("\n🛑 收到強制中斷訊號 (Ctrl+C)")

    # 寫回剩餘
    if update_cells:
        print(f"\n[系統] 寫入剩餘 {len(update_cells)} 筆研判結果...")
        wks.update_cells(update_cells)
        
    print("\n🎉 分析完畢！已將研判結果更新至 Google 試算表。")

if __name__ == "__main__":
    run_smart_analysis()
