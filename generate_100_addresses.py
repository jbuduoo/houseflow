import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re

def clean_address(raw_addr):
    addr = str(raw_addr).strip()
    if not addr or addr in ["", "查無", "解析失敗", "待查閱"]:
        return ""
    addr = addr.split('(')[0]
    
    # 移除里、鄰 (避免切到「區」或「鄉鎮」的特殊處理)
    addr = re.sub(r'(?<=[區鄉鎮市])[^區鄉鎮市里]+里', '', addr)
    addr = re.sub(r'[0-9０-９]{1,3}鄰', '', addr)
    
    # 保留到「號」
    addr = re.sub(r'號.*', '號', addr)
    
    # 如果沒有號但有樓層，則去除樓層
    addr = re.sub(r'[0-9０-９一二三四五六七八九十百]+樓.*', '', addr)
    
    return addr.replace(' ', '')

try:
    print("Connecting to Google Sheets...")
    creds = ServiceAccountCredentials.from_json_keyfile_name('houseflow_gheet_key.json.json', ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive'])
    client = gspread.authorize(creds)
    sheet = client.open_by_key("1bU4BKbjQgnoNqSK50G4vHgMGBFetHsBrbMyHv2Xc2k0").sheet1
    all_rows = sheet.get_all_values()
    
    idx_obj = 12 # M欄: 物件地址 (0-indexed = 12, wait, check_cols said Col M = 13. So index 12 is M. Wait, M is 物件地址?)
    idx_res = 14 # O欄: 戶籍地址
    
    results = []
    count = 0
    for row in all_rows[1:]:
        if len(row) > 12:
            obj_addr = row[12].strip()
            if obj_addr and obj_addr not in ["查無", "解析失敗", "待查閱"]:
                cln = clean_address(obj_addr)
                if obj_addr != cln: # 只顯示有變動的，或是全部顯示？全部顯示好了
                    results.append((obj_addr, cln))
                    count += 1
        if len(row) > 14:
            res_addr = row[14].strip()
            if res_addr and res_addr not in ["查無", "解析失敗", "待查閱"]:
                cln = clean_address(res_addr)
                results.append((res_addr, cln))
                count += 1
                
        if count >= 100:
            break

    # 取前 100 筆不重複的地址
    unique_results = []
    seen = set()
    for raw, cln in results:
        if raw not in seen:
            unique_results.append((raw, cln))
            seen.add(raw)
        if len(unique_results) == 100:
            break

    with open("address_100_comparison.md", "w", encoding="utf-8") as f:
        f.write("| 原始地址 (Google試算表) | 正規化後 (準備丟給衛星) |\n")
        f.write("| :--- | :--- |\n")
        for raw, cln in unique_results:
            f.write(f"| `{raw}` | `{cln}` |\n")
            
    print("Done generating address_100_comparison.md")

except Exception as e:
    print(f"Error: {e}")
