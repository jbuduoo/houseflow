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

def normalize_fullwidth(text):
    """將全形數字 ０-９ 轉換為半形 0-9，以利後續 Regex 比對"""
    return text.translate(str.maketrans('０１２３４５６７８９', '0123456789'))

def strip_floor(address):
    """移除號碼之後的樓層資訊，保留到號為止（用於比對）"""
    normalized = normalize_fullwidth(address)
    result = re.sub(r'號.*', '號', normalized)
    return result.strip()

def get_last_door_num(address):
    """取出地址中最後一個號碼前的數字（門牌號），供比對用"""
    normalized = normalize_fullwidth(address)
    matches = re.findall(r'(\d+)號', normalized)
    return matches[-1] if matches else None

def is_gps_match(m_addr, y_addr):
    """
    判斷 M 欄某一筆地址是否與 Y 欄反查地址吻合
    比對邏輯：提取最後的門牌號，若相同視為命中
    """
    if not m_addr or not y_addr:
        return False
    m_num = get_last_door_num(m_addr)
    y_num = get_last_door_num(y_addr)
    return m_num and y_num and m_num == y_num

def build_conclusion(m_val, y_val, z_val):
    """
    依照業務邏輯建立 AA 欄的輸出文字：
    - GPS 命中：地址(星號)
    - 多筆含命中：命中地址(星號) + 其他地址
    - GPS 不吻合：住通：M地址 + 定位：Y地址
    - 查無 + 有 GPS：定位：Y地址
    - 查無 + 無 GPS：查無
    """
    m_val = normalize_fullwidth(str(m_val).strip())
    y_val = normalize_fullwidth(str(y_val).strip())
    z_val = str(z_val).strip()

    # 若座標來源是 ArcGIS（系統自算），Y 欄不視為有效 GPS 驗證
    if z_val == "ArcGIS":
        y_val = ""

    is_not_found = (m_val == "查無" or m_val == "")
    has_gps = y_val != ""

    # ── 情況一：查無 ──────────────────────────────────
    if is_not_found:
        if has_gps:
            return f"定位：{y_val}"
        else:
            return "查無"

    # ── 情況二：有產權資料 ────────────────────────────
    # 分割多筆地址（以逗號分隔）
    addrs = [a.strip() for a in m_val.split(',') if a.strip()]
    if not addrs:
        return m_val

    if not has_gps:
        # 無 GPS，直接列出所有產權地址
        return "\n".join(addrs)

    # 找出哪一筆 M 地址與 GPS 命中
    matched_idx = None
    for i, addr in enumerate(addrs):
        if is_gps_match(addr, y_val):
            matched_idx = i
            break

    if matched_idx is not None:
        # GPS 命中！命中的那筆加(星號)，其他保留
        lines = []
        for i, addr in enumerate(addrs):
            if i == matched_idx:
                lines.append(f"{addr}(星號)")
            else:
                lines.append(addr)
        return "\n".join(lines)
    else:
        # GPS 不吻合：顯示住通地址 + 定位地址
        m_lines = "\n".join([f"住通：{addr}" for addr in addrs])
        return f"{m_lines}\n定位：{y_val}"


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
            conclusion = build_conclusion(m_val, y_val, z_val)
            
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
