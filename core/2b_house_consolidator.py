import os
import gspread
import json
import re
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials

# --- 設定 ---
_base_dir = os.path.dirname(os.path.abspath(__file__))
CREDS_FILE = os.path.join(_base_dir, "houseflow_gheet_key.json.json")
if not os.path.exists(CREDS_FILE):
    CREDS_FILE = os.path.join(_base_dir, "..", "houseflow_gheet_key.json.json")

SHEET_KEY = "1bU4BKbjQgnoNqSK50G4vHgMGBFetHsBrbMyHv2Xc2k0"

# 仲介優先序 (數字越小越優先)
BROKER_PRIORITY = {
    '信義': 1, '永慶': 2, '好房網': 3, '住商': 4,
    '大家': 5, '591': 6, '21世紀': 7, 
    '太平洋': 8, '樂屋網': 9
}

def get_priority(broker_name):
    if not broker_name: return 100
    src = str(broker_name).replace('\u3000', '').replace(' ', '').strip()
    priority = 100
    for key, val in BROKER_PRIORITY.items():
        if key in src:
            if val < priority: priority = val
    return priority

def parse_json_safely(json_str):
    if not json_str or json_str.strip() == "": return []
    try:
        return json.loads(json_str)
    except:
        return []

def run_consolidator():
    print("\n" + "="*60)
    print("【住通數據整合中心 - 2b_house_consolidator v1.0】")
    print("="*60)

    try:
        # 1. 連接
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive'])
        client = gspread.authorize(creds)
        sh = client.open_by_key(SHEET_KEY)
        wks = sh.sheet1
        
        print(f"[系統] 正在讀取試算表資料...")
        all_rows = wks.get_all_values()
        if len(all_rows) <= 1:
            print("資料量不足，無需處理。")
            return

        header = all_rows[0]
        rows = all_rows[1:]
        total_initial = len(rows)
        print(f"原始總筆數: {total_initial}")

        # --- 第一階段：網址去重 (URL Dedupe) ---
        unique_urls = {} 
        url_dedupe_count = 0
        
        for r in rows:
            url = r[10].strip() if len(r) > 10 else ""
            if not url:
                unique_urls[f"no_url_{id(r)}"] = r
                continue
            
            if url not in unique_urls:
                unique_urls[url] = r
            else:
                url_dedupe_count += 1
                try:
                    old_time = unique_urls[url][16]
                    new_time = r[16]
                    if new_time > old_time: unique_urls[url] = r
                except:
                    pass
        
        cleaned_rows = list(unique_urls.values())
        print(f"階段 1: 網址去重完成，減少了 {url_dedupe_count} 筆。")

        # --- 第二階段：地址指紋合併 (Address Merge) ---
        clusters = {} 
        for r in cleaned_rows:
            addr = r[3].strip()
            floor = r[7].strip()
            size = r[5].strip()
            if not addr: continue
            fp = f"{addr}_{floor}_{size}"
            if fp not in clusters: clusters[fp] = []
            clusters[fp].append(r)

        final_rows = []
        merge_count = 0
        
        for fp, group in clusters.items():
            if len(group) == 1:
                final_rows.append(group[0])
                continue
            
            merge_count += (len(group) - 1)
            # 挑選 Master (依優先序)
            best_row = min(group, key=lambda x: get_priority(x[21] if len(x)>21 else ""))
            # 建立 Master 的複本，準備吸收情報
            final_row = list(best_row)
            if len(final_row) < 28: final_row += [""] * (28 - len(final_row))

            # 桶子：{ agent_name: { url_set: set(), listings: [] } }
            bucket = {}
            
            for r in group:
                # --- A. 情報大豐收：繼承重要的補完資訊 (M, O, W, X, AA) ---
                # 欄位索引：M(12), O(14), W(22), X(23), AA(26)
                for col_idx in [12, 14, 22, 23, 26]:
                    if len(r) > col_idx and r[col_idx].strip():
                        # 如果 Master 該欄位是空的，但這筆有資料，就繼承過來
                        if not final_row[col_idx].strip():
                            final_row[col_idx] = r[col_idx]

                # --- B. 整合 JSON ---
                agent_name = (r[21] if len(r)>21 else "未知").strip() or "未知"
                if agent_name not in bucket: bucket[agent_name] = {"urls": set(), "list": []}
                
                m_url = r[10] if len(r)>10 else ""
                if m_url and m_url not in bucket[agent_name]["urls"]:
                    bucket[agent_name]["urls"].add(m_url)
                    bucket[agent_name]["list"].append({
                        "title": r[1] if len(r)>1 else "",
                        "price": r[4] if len(r)>4 else "",
                        "time": r[16] if len(r)>16 else "",
                        "url": m_url
                    })
                
                old_json = parse_json_safely(r[27] if len(r)>27 else "")
                for agent_entry in old_json:
                    a_name = agent_entry.get("name", "未知")
                    if a_name not in bucket: bucket[a_name] = {"urls": set(), "list": []}
                    for l in agent_entry.get("listings", []):
                        l_url = l.get("url", "")
                        if l_url and l_url not in bucket[a_name]["urls"]:
                            bucket[a_name]["urls"].add(l_url)
                            bucket[a_name]["list"].append(l)
            
            # 重新封裝為最終 JSON 並寫回 final_row
            final_json_list = []
            for a_name, data in bucket.items():
                final_json_list.append({"name": a_name, "listings": data["list"]})
            
            final_row[27] = json.dumps(final_json_list, ensure_ascii=False)
            final_rows.append(final_row)

        print(f"階段 2: 地址指紋合併完成，縮減了 {merge_count} 筆重複物件。")

        # --- 第三階段：結案與無效清理 (Final Filter) ---
        fully_cleaned = []
        p_y_count = 0
        no_addr_count = 0
        
        for r in final_rows:
            is_dlg = r[15].upper() if len(r)>15 else ""
            if is_dlg in ['Y', 'YES', '是']:
                p_y_count += 1
                continue
            
            # 無效清理：地址(3) 為空 且 座標(22, 23) 也為空時才刪除
            addr = r[3].strip()
            lat = r[22].strip() if len(r)>22 else ""
            lng = r[23].strip() if len(r)>23 else ""
            
            if not addr and not lat and not lng:
                no_addr_count += 1
                continue
                
            fully_cleaned.append(r)
            
        print(f"階段 3: 清理完成。刪除已委託(Y) {p_y_count} 筆，刪除無效地址 {no_addr_count} 筆。")

        # --- 4. 寫回試算表 ---
        print(f"\n[系統] 正在執行最後更新，目前剩餘 {len(fully_cleaned)} 筆精華物件...")
        wks.clear()
        wks.update('A1', [header] + fully_cleaned)
        
        print(f"\n🎉 整合任務大功告成！")
        print(f"📊 終極統計：")
        print(f"   - 原始資料: {total_initial} 筆")
        print(f"   - 最終留存: {len(fully_cleaned)} 筆")
        print(f"   - 總體壓縮率: {((total_initial-len(fully_cleaned))/total_initial)*100:.1f}%")

    except Exception as e:
        print(f"❌ 發生錯誤: {e}")

if __name__ == "__main__":
    run_consolidator()
