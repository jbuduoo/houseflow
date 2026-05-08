import os
import gspread
import json
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd

# --- 設定 ---
_base_dir = os.path.dirname(os.path.abspath(__file__))
CREDS_FILE = os.path.join(_base_dir, "..", "houseflow_gheet_key.json.json")
SHEET_KEY = "1bU4BKbjQgnoNqSK50G4vHgMGBFetHsBrbMyHv2Xc2k0"

BROKER_PRIORITY = {
    '信義': 1, '永慶': 2, '好房網': 3, '住商': 4,
    '大家': 5, '591': 6, '21世紀': 7, 
    '太平洋': 8, '樂屋網': 9
}

def get_priority(broker_name):
    broker_name = str(broker_name).replace('\u3000', '').replace(' ', '').strip()
    priority = 100
    for key, val in BROKER_PRIORITY.items():
        if key in broker_name:
            if val < priority:
                priority = val
    return priority

def run_test_report():
    print("="*60)
    print("【數據整合實驗室 - 地址合併模擬報告】")
    print("="*60)

    # 1. 連接
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive'])
    client = gspread.authorize(creds)
    wks = client.open_by_key(SHEET_KEY).sheet1
    all_values = wks.get_all_values()
    
    if len(all_values) <= 1:
        print("資料量不足，無法測試。")
        return

    header = all_values[0]
    data = all_values[1:]
    df = pd.DataFrame(data, columns=header)

    print(f"原始資料筆數: {len(df)}")

    # 2. 定義合併 Key: 地址(D, index 3) + 樓層現(H, index 7) + 坪數(F, index 5)
    def make_key(row):
        try:
            addr = str(row[3]).strip()
            size = str(row[5]).strip()
            floor = str(row[7]).strip()
            if not addr or addr == "" or addr == "地址": return None
            return f"{addr}_{floor}_{size}"
        except:
            return None

    # 3. 模擬合併
    masters = {} 
    merges_log = [] 
    
    for idx, row in df.iterrows():
        key = make_key(row.tolist())
        if not key: continue
        
        if key not in masters:
            masters[key] = idx
        else:
            m_idx = masters[key]
            master_row = df.iloc[m_idx].tolist()
            current_row = row.tolist()
            
            p_master = get_priority(master_row[21] if len(master_row)>21 else "")
            p_current = get_priority(current_row[21] if len(current_row)>21 else "")
            
            if p_current < p_master:
                masters[key] = idx
            
            merges_log.append(key)

    # 4. 準備導出資料
    report_rows = []
    unique_keys_with_merges = [k for k, v in masters.items() if any(make_key(df.iloc[idx].tolist()) == k for idx in range(len(df)) if idx != masters[k])]
    
    # 我們只導出那些有發生「重複」的群組，方便檢視
    print(f"[系統] 正在整理重複物件清單...")
    for target_key in unique_keys_with_merges:
        cluster_indices = []
        for idx, row in df.iterrows():
            if make_key(row.tolist()) == target_key:
                cluster_indices.append(idx)
        
        if len(cluster_indices) > 1:
            for idx in cluster_indices:
                row_data = df.iloc[idx].tolist()
                status = "🏆 主紀錄(保留)" if idx == masters[target_key] else "🔗 從屬(預計合併)"
                # 在原本的資料列最後面加上合併狀態與指紋
                extended_row = row_data + [status, target_key]
                report_rows.append(extended_row)

    # 5. 寫入 CSV
    report_header = header + ["合併狀態", "地址指紋"]
    report_df = pd.DataFrame(report_rows, columns=report_header)
    
    output_path = os.path.join(_base_dir, "..", "duplicate_analysis.csv")
    report_df.to_csv(output_path, index=False, encoding='utf-8-sig')
    
    print("-" * 60)
    print(f"報告產出成功！")
    print(f"檔案路徑: {os.path.abspath(output_path)}")
    print(f"共列出 {len(report_rows)} 筆涉及重複的物件。")
    print("-" * 60)

if __name__ == "__main__":
    run_test_report()
