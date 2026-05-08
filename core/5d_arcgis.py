import os
import gspread
import urllib.request
import urllib.parse
import json
import time
import re
from oauth2client.service_account import ServiceAccountCredentials

# --- 設定 ---
_base_dir = os.path.dirname(os.path.abspath(__file__))
CREDS_FILE = os.path.join(_base_dir, "houseflow_gheet_key.json.json")
if not os.path.exists(CREDS_FILE):
    CREDS_FILE = os.path.join(_base_dir, "..", "houseflow_gheet_key.json.json")

SHEET_KEY = "1bU4BKbjQgnoNqSK50G4vHgMGBFetHsBrbMyHv2Xc2k0"

def clean_address(raw_addr):
    """去除干擾 ArcGIS 定位的字元，保留核心門牌"""
    addr = str(raw_addr).strip()
    if not addr or "http" in addr: return ""
    if "號" not in addr: return ""
    # 移除括號、鄰里、樓層
    addr = addr.split('(')[0]
    addr = re.sub(r'(?<=[區鄉鎮市])[^區鄉鎮市里]+里', '', addr)
    addr = re.sub(r'[0-9０-９]{1,3}鄰', '', addr)
    addr = re.sub(r'號.*', '號', addr)
    return addr.replace(' ', '').strip()

def get_arcgis_coordinates(address):
    """透過地址查詢 ArcGIS 座標"""
    if not address: return None, None
    url = f"https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates?f=json&singleLine={urllib.parse.quote(address)}&outFields=Match_addr"
    req = urllib.request.Request(url, headers={'User-Agent': 'HouseFlowApp/5.0'})
    try:
        time.sleep(0.2) # 防擋
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            if "candidates" in data and len(data["candidates"]) > 0:
                loc = data["candidates"][0]["location"]
                return str(loc["y"]), str(loc["x"]) # y=lat, x=lon
    except:
        pass
    return None, None

def run_arcgis_task():
    print("\n" + "="*60)
    print("【ArcGIS 座標補救工具 - 5d_arcgis.py v1.1】")
    print("="*60)

    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive'])
        client = gspread.authorize(creds)
        wks = client.open_by_key(SHEET_KEY).sheet1
        
        all_rows = wks.get_all_values()
        if len(all_rows) <= 1: return
        header = all_rows[0]
        
        # 欄位索引：M(12, 查地址), R(17, 物件緯度), S(18, 物件經度), V(21, 來源仲介), Z(25, 座標來源)
        idx_addr = 12
        idx_lat = 17
        idx_lng = 18
        idx_broker = 21
        idx_src = 25
        
        rows_to_update = []
        for i, r in enumerate(all_rows[1:]):
            row_num = i + 2
            addr = r[idx_addr].strip() if len(r) > idx_addr else ""
            lat = r[idx_lat].strip() if len(r) > idx_lat else ""
            broker = r[idx_broker].strip() if len(r) > idx_broker else ""
            
            # 條件：有地址 且 沒座標 (R 欄為空) 且 不是信義或永慶
            if addr and not lat and broker not in ["信義", "永慶"]:
                clean_addr = clean_address(addr)
                if clean_addr:
                    rows_to_update.append((row_num, clean_addr))

        if not rows_to_update:
            print("目前沒有需要補救的座標。")
            return

        print(f"預計處理 {len(rows_to_update)} 筆補救任務...")
        
        success_count = 0
        for row_num, addr in rows_to_update:
            lat, lng = get_arcgis_coordinates(addr)
            if lat and lng:
                wks.update_cell(row_num, idx_lat + 1, lat)
                wks.update_cell(row_num, idx_lng + 1, lng)
                wks.update_cell(row_num, idx_src + 1, "ArcGIS")
                print(f"  [成功] 行號 {row_num}: {addr} ➔ ({lat}, {lng})")
                success_count += 1
            else:
                print(f"  [失敗] 行號 {row_num}: {addr}")

        print(f"\n[任務結束] 成功補救 {success_count} 筆座標。")

    except Exception as e:
        print(f"❌ 錯誤: {e}")

if __name__ == "__main__":
    run_arcgis_task()
