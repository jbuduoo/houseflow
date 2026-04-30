import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 設定 ---
_base_dir = os.path.dirname(os.path.abspath(__file__))
CREDS_FILE = os.path.join(_base_dir, "houseflow_gheet_key.json.json")
if not os.path.exists(CREDS_FILE):
    CREDS_FILE = os.path.join(_base_dir, "..", "houseflow_gheet_key.json.json")

SHEET_KEY = "1bU4BKbjQgnoNqSK50G4vHgMGBFetHsBrbMyHv2Xc2k0"

# 仲介可靠性優先序（數字越小越優先，與 1_house.py 保持一致）
BROKER_PRIORITY = {
    '信義': 1, '永慶': 2, '好房網': 3, '住商': 4,
    '大家': 5, '591': 6, '21世紀': 7, 
    '太平洋': 8, '樂屋網': 9
}
# V欄在 row 中的索引（0-indexed）= 第 22 欄 → index 21
V_COL_INDEX = 21

def _broker_priority(row):
    """取得該列的來源仲介優先序數字（數字越小越優先）"""
    if len(row) <= V_COL_INDEX:
        return 999
    src = row[V_COL_INDEX].replace('\u3000', '').replace(' ', '').strip()
    
    priority = 100
    for key, val in BROKER_PRIORITY.items():
        if key in src:
            if val < priority:
                priority = val
    return priority

def run_deduplicator(auto_confirm=False):
    print("\n" + "="*60)
    print("【住通試算表維護 - 重覆資料清理工具（保留最佳來源版）】")
    print("="*60)

    try:
        # 1. 連接 Google 試算表
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            CREDS_FILE, 
            ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        )
        client = gspread.authorize(creds)
        sh = client.open_by_key(SHEET_KEY)
        wks = sh.sheet1
        
        print(f"[系統] 正在讀取試算表資料...")
        all_rows = wks.get_all_values()
        
        if len(all_rows) <= 1:
            print("✅ 試算表是空的或只有標題列，無需清理。")
            return

        header = all_rows[0]
        data_rows = all_rows[1:]
        total_before = len(data_rows)
        
        # 2. 進行去重：以第一欄 ID 為 key，遇重複時保留來源仲介等級最高的那筆
        best_rows = {}   # {tid: row}  只保留目前最佳的一列
        order = []       # 保留原始出現順序
        replaced_count = 0
        duplicate_count = 0

        for row in data_rows:
            if not row: continue
            tid = row[0].strip()
            if tid == "":
                continue

            if tid not in best_rows:
                best_rows[tid] = row
                order.append(tid)
            else:
                duplicate_count += 1
                # 比較 V 欄仲介等級，數字越小越優先
                current_priority = _broker_priority(best_rows[tid])
                new_priority     = _broker_priority(row)
                if new_priority < current_priority:
                    old_src = best_rows[tid][V_COL_INDEX] if len(best_rows[tid]) > V_COL_INDEX else ''
                    new_src = row[V_COL_INDEX] if len(row) > V_COL_INDEX else ''
                    print(f"  [替換] ID={tid}：{old_src.strip() or '無來源'}(優先序{current_priority}) → {new_src.strip() or '無來源'}(優先序{new_priority})")
                    best_rows[tid] = row
                    replaced_count += 1

        unique_rows = [best_rows[tid] for tid in order]

        print(f"[統計] 掃描完畢：總列數 {total_before}，發現 {duplicate_count} 筆重覆，其中 {replaced_count} 筆被更高等級來源取代。")

        if duplicate_count == 0:
            print("[訊息] 試算表目前沒有發現重覆 ID。")
            return

        # 3. 確認是否寫回
        if not auto_confirm:
            confirm = input(f"[注意] 即將刪除 {duplicate_count} 筆重複資料，保留 {len(unique_rows)} 筆（每個 ID 保留來源仲介等級最高的）。是否繼續？(y/n): ").lower()
            if confirm != 'y':
                print("[訊息] 操作已取消。")
                return
        else:
            print(f"[系統] 自動模式啟動，正在清理 {duplicate_count} 筆重覆資料...")

        # 4. 寫回試算表
        print(f"[系統] 正在清理並重寫試算表...")
        wks.clear()

        # 準備完整的新資料 (標題 + 唯一資料)
        new_content = [header] + unique_rows

        # 使用 update 批次寫入
        wks.update('A1', new_content)

        print(f"[完成] 清理完成！目前剩餘 {len(unique_rows)} 筆資料。")

    except Exception as e:
        print(f"[錯誤] 發生錯誤: {e}")

if __name__ == "__main__":
    # 手動執行時預設需要確認
    run_deduplicator(auto_confirm=False)
