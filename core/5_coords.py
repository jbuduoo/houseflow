import gspread
from oauth2client.service_account import ServiceAccountCredentials
import urllib.request
import urllib.parse
import json
import time
import re
import os
import requests
import importlib.util

# 動態載入 5a_sinyi.py
_base_dir = os.path.dirname(os.path.abspath(__file__))
_spec_sinyi = importlib.util.spec_from_file_location("5a_sinyi", os.path.join(_base_dir, "5a_sinyi.py"))
_sinyi_module = importlib.util.module_from_spec(_spec_sinyi)
_spec_sinyi.loader.exec_module(_sinyi_module)
scrape_sinyi_coordinates = _sinyi_module.scrape_sinyi_coordinates

# 取得金鑰檔案的絕對路徑 (支援從根目錄或 core 執行)
_base_dir = os.path.dirname(os.path.abspath(__file__))
CREDS_FILE = os.path.join(_base_dir, "houseflow_gheet_key.json.json")
if not os.path.exists(CREDS_FILE):
    CREDS_FILE = os.path.join(_base_dir, "..", "houseflow_gheet_key.json.json")
SHEET_KEY  = "1bU4BKbjQgnoNqSK50G4vHgMGBFetHsBrbMyHv2Xc2k0"

# R, S, T, U 欄的動態名稱定義，幫助後續取得 Index
HEAD_OBJ_ADDR = "查地址"
HEAD_RES_ADDR = "戶籍地址"
HEAD_OBJ_LAT = "物件緯度"
HEAD_OBJ_LON = "物件經度"
HEAD_RES_LAT = "戶籍緯度"
HEAD_RES_LON = "戶籍經度"

def clean_address(raw_addr):
    """去除會干擾 ArcGIS 定位的里、鄰、樓層與室別，但保留完整的門牌"""
    addr = str(raw_addr).strip()
    if not addr or addr in ["", "查無", "解析失敗", "待查閱"] or "http" in addr:
        return ""
        
    # 如果地址有屏蔽字元或標註不完整，或是根本沒有「號」，則拒絕轉換座標
    if "***" in addr or "＊＊＊" in addr or "不完整" in addr:
        return ""
    if "號" not in addr:
        return ""
    
    # 切掉括號(多筆、疑似等)
    addr = addr.split('(')[0]
    
    # 移除「XX里」、「XX鄰」，避免誤殺「XX區」，故限定前面要是區鄉鎮市結尾
    addr = re.sub(r'(?<=[區鄉鎮市])[^區鄉鎮市里]+里', '', addr)
    addr = re.sub(r'[0-9０-９]{1,3}鄰', '', addr)
    
    # 移除號後面的樓層，保留「號」
    addr = re.sub(r'號.*', '號', addr)
    
    # 如果地址內沒有號，但有樓層 (例如 重慶北路三段5樓)，則剝除樓層
    # 但若裡面本身就沒有號也沒有樓，就不會有動作
    addr = re.sub(r'[0-9０-９一二三四五六七八九十百]+樓.*', '', addr)
    
    return addr.replace(' ', '').strip()

def get_broker_coordinates(url, source):
    """【第一防線】直接爬取仲介網頁的經緯度"""
    if not url or not url.startswith('http'):
        return "", ""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        resp = requests.get(url, headers=headers, timeout=5)
        html = resp.text
        
        # 使用通用正則尋找潛在的經緯度 (通常藏在 JS 變數或 HTML 屬性中)
        lat_match = re.search(r'(?:lat|latitude)["\']?\s*[:=]\s*["\']?(2[2-5]\.\d+)', html, re.IGNORECASE)
        lon_match = re.search(r'(?:lng|lon|longitude)["\']?\s*[:=]\s*["\']?(12[0-2]\.\d+)', html, re.IGNORECASE)
        
        if lat_match and lon_match:
            return lat_match.group(1), lon_match.group(1)
    except Exception as e:
        print(f"    [爬蟲失敗] {source} 網頁請求錯誤或超時")
    return "", ""

def get_arcgis_coordinates(address):
    """【第二防線】透過地址查詢 ArcGIS"""
    if not address or address in ["", "查無", "待查閱", "解析失敗"]:
        return "", ""
        
    url = f"https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates?f=json&singleLine={urllib.parse.quote(address)}&outFields=Match_addr"
    req = urllib.request.Request(url, headers={'User-Agent': 'HouseFlowApp/5.0'})
    
    try:
        time.sleep(0.12) # 適度休息防擋
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            if "candidates" in data and len(data["candidates"]) > 0:
                loc = data["candidates"][0]["location"]
                return str(loc["y"]), str(loc["x"]) # y=lat, x=lon
    except Exception as e:
        pass
    
    return "", ""

def run_coords_enricher():
    print("\n" + "="*60)
    print("【住通地理圖資補完管線 v2.0 — 多層防護降級版】")
    print("="*60)

    try:
        creds  = ServiceAccountCredentials.from_json_keyfile_name(
            CREDS_FILE,
            ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        )
        client = gspread.authorize(creds)
        wks    = client.open_by_key(SHEET_KEY).sheet1
        all_rows = wks.get_all_values()
        print(f"[系統] 成功連接試算表，共 {len(all_rows) - 1} 筆資料。")
    except Exception as e:
        print(f"❌ 雲端連線失敗: {e}")
        return

    update_cells = []
    
    # 進度計算用
    updated_obj = 0
    updated_res = 0

    print("[情報] 開始掃描並進行分層座標補齊...\n")

    if not all_rows:
        print("❌ 試算表沒有資料。")
        return
        
    headers = all_rows[0]
    try:
        IDX_M_ADDR = headers.index(HEAD_OBJ_ADDR)
        IDX_O_ADDR = headers.index(HEAD_RES_ADDR)
        IDX_OBJ_LAT = headers.index(HEAD_OBJ_LAT)
        IDX_OBJ_LON = headers.index(HEAD_OBJ_LON)
        IDX_RES_LAT = headers.index(HEAD_RES_LAT)
        IDX_RES_LON = headers.index(HEAD_RES_LON)
    except ValueError as e:
        print(f"❌ 找不到必要的標題欄位: {e}，請確認 A1 列的標題文字是否正確。")
        return

    # 動態尋找其他擴充欄位 (如果有標題就用標題，沒有就用預設 Index)
    try: IDX_K_URL = headers.index("仲介外部連結")
    except: IDX_K_URL = 10
    try: IDX_V_SOURCE = headers.index("來源仲介")
    except: IDX_V_SOURCE = 21
    try: IDX_W_HF_LAT = headers.index("HF緯度")
    except: IDX_W_HF_LAT = 22
    try: IDX_X_HF_LON = headers.index("HF經度")
    except: IDX_X_HF_LON = 23
    try: IDX_Z_COORD_SRC = headers.index("座標來源")
    except ValueError: IDX_Z_COORD_SRC = 25

    interrupted = False
    try:
        for i, row in enumerate(all_rows):
            if i == 0:
                continue
            
            row_num = i + 1
        
            # 為了安全取得欄位長度，避免 list index out of range
            def get_val(idx):
                return row[idx].strip() if len(row) > idx else ""

            obj_addr = get_val(IDX_M_ADDR)
            res_addr = get_val(IDX_O_ADDR)
        
            # 檢查是否已經有緯度
            has_obj_lat = get_val(IDX_OBJ_LAT) != ""
            has_res_lat = get_val(IDX_RES_LAT) != ""
        
            # --- A. 處理物件座標 (R, S) ---
            if not has_obj_lat:
                broker_url = get_val(IDX_K_URL)
                source = get_val(IDX_V_SOURCE)
            
                lat, lon = "", ""
                method_used = ""
            
                # [第一防線] 仲介精準座標
                if source == "信義" and broker_url:
                    _, coords = scrape_sinyi_coordinates(broker_url)
                    if "Error" not in coords and "not found" not in coords:
                        lat, lon = coords.split(",")
                        method_used = f"原生爬取({source})"
                elif source == "永慶" and broker_url:
                    lat, lon = get_broker_coordinates(broker_url, source)
                    if lat and lon:
                        method_used = f"原生爬取({source})"
            
                # [第二防線] ArcGIS
                if not lat and obj_addr:
                    clean_str = clean_address(obj_addr)
                    if clean_str:
                        lat, lon = get_arcgis_coordinates(clean_str)
                        if lat and lon:
                            method_used = "ArcGIS"
            

            
                if lat and lon:
                    update_cells.extend([
                        gspread.Cell(row=row_num, col=IDX_OBJ_LAT + 1, value=lat),
                        gspread.Cell(row=row_num, col=IDX_OBJ_LON + 1, value=lon),
                        gspread.Cell(row=row_num, col=IDX_Z_COORD_SRC + 1, value=method_used)
                    ])
                    updated_obj += 1
                    addr_display = obj_addr.split('(')[0] if obj_addr else "無地址"
                    print(f"  [物件] {addr_display:<18} ➔ ({lat}, {lon}) [{method_used}]")

            # --- B. 處理戶籍座標 (T, U) ---
            if res_addr and res_addr not in ["待查閱", "查無"] and not has_res_lat:
                clean_str = clean_address(res_addr)
                if clean_str:
                    lat, lon = get_arcgis_coordinates(clean_str)
                    if lat and lon:
                        update_cells.extend([
                            gspread.Cell(row=row_num, col=IDX_RES_LAT + 1, value=lat),
                            gspread.Cell(row=row_num, col=IDX_RES_LON + 1, value=lon)
                        ])
                        updated_res += 1
                        print(f"  [戶籍] {res_addr.split('(')[0]:<18} ➔ ({lat}, {lon}) [ArcGIS]")

            # 滿 50 個物件/戶籍 的座標 (即 100 個儲存格) 就提早存檔，避免中斷全失
            if len(update_cells) >= 100:
                print(f"\n[系統] 觸發分批備份：正在將剛才的 {len(update_cells)//2} 個新座標寫入 Google 雲端...")
                try:
                    wks.update_cells(update_cells)
                    update_cells.clear()
                except Exception as e:
                    print(f"💥 分批寫入失敗: {e}")
                    time.sleep(3) # 失敗稍微等一下

    except KeyboardInterrupt:
        print("\n🛑 收到強制中斷訊號 (Ctrl+C)，準備儲存已處理資料...")
        interrupted = True

    # 迴圈結束後，把剩下的尾數也存好
    if update_cells:
        print(f"\n[系統] 準備寫入最後剩下的 {len(update_cells)//2} 個座標...")
        try:
            wks.update_cells(update_cells)
            update_cells.clear()
        except: pass

    if updated_obj == 0 and updated_res == 0:
        print("\n✅ 所有案件的座標皆已存在，無需更新。")
    else:
        print(f"\n🎉 執行完畢！本次總共充填了 {updated_obj} 筆物件座標 以及 {updated_res} 筆戶籍座標！")

if __name__ == "__main__":
    run_coords_enricher()

    if interrupted:
        raise KeyboardInterrupt
