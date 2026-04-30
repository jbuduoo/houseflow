"""
fix_fullwidth_m_col.py
一次性清理腳本：將試算表 M 欄（查地址）中的全形數字轉為半形。
"""
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import time

_base_dir = os.path.dirname(os.path.abspath(__file__))
CREDS_FILE = os.path.join(_base_dir, "core", "houseflow_gheet_key.json.json")
if not os.path.exists(CREDS_FILE):
    CREDS_FILE = os.path.join(_base_dir, "houseflow_gheet_key.json.json")
SHEET_KEY = "1bU4BKbjQgnoNqSK50G4vHgMGBFetHsBrbMyHv2Xc2k0"

def normalize_fullwidth(text):
    """將全形數字 ０-９ 轉換為半形 0-9"""
    return text.translate(str.maketrans('０１２３４５６７８９', '0123456789'))

def main():
    print("=" * 50)
    print("【M 欄全形→半形數字清理工具】")
    print("=" * 50)

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

    headers = all_rows[0]
    try:
        IDX_M = headers.index("查地址")
    except ValueError:
        IDX_M = 12  # 預設 M 欄

    update_cells = []
    changed = 0

    for i, row in enumerate(all_rows):
        if i == 0:
            continue
        m_val = row[IDX_M].strip() if len(row) > IDX_M else ""
        if not m_val:
            continue

        normalized = normalize_fullwidth(m_val)
        if normalized != m_val:
            update_cells.append(gspread.Cell(row=i+1, col=IDX_M+1, value=normalized))
            changed += 1
            print(f"  [修正] {m_val[:30]} → {normalized[:30]}")

    if not update_cells:
        print("\n✅ 所有 M 欄資料已是半形，無需修改。")
        return

    print(f"\n[系統] 共找到 {changed} 筆需要修正，正在寫入...")
    wks.update_cells(update_cells)
    print(f"[完成] 已修正 {changed} 筆 M 欄全形數字為半形！")

if __name__ == "__main__":
    main()
