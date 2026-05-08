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

def run_deduplicator(auto_confirm=True):
    """
    此函數已升級為鏈式執行：
    1. 2a_link_checker: 剔除 10 天未更新且已下架的物件。
    2. 2b_house_consolidator: 執行地址指紋大合併與 JSON 整合。
    """
    import importlib
    # 由於檔名以數字開頭，必須使用 importlib 動態載入
    try:
        module_2a = importlib.import_module("core.2a_link_checker")
        module_2b = importlib.import_module("core.2b_house_consolidator")
        
        # 執行清理
        module_2a.run_link_checker()
        
        # 執行整合
        module_2b.run_consolidator()
    except Exception as e:
        print(f"  [錯誤] 載入整合模組失敗: {e}")

if __name__ == "__main__":
    # 預設直接執行最強大的整合器
    run_deduplicator()
