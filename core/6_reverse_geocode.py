import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import time
import importlib.util
import re

# 取得金鑰檔案的絕對路徑
_base_dir = os.path.dirname(os.path.abspath(__file__))
CREDS_FILE = os.path.join(_base_dir, "houseflow_gheet_key.json.json")
if not os.path.exists(CREDS_FILE):
    CREDS_FILE = os.path.join(_base_dir, "..", "houseflow_gheet_key.json.json")
SHEET_KEY  = "1bU4BKbjQgnoNqSK50G4vHgMGBFetHsBrbMyHv2Xc2k0"

# 動態載入 6a_geocoder.py
_spec_geocoder = importlib.util.spec_from_file_location("6a_geocoder", os.path.join(_base_dir, "6a_geocoder.py"))
_geocoder_module = importlib.util.module_from_spec(_spec_geocoder)
_spec_geocoder.loader.exec_module(_geocoder_module)
reverse_geocode = _geocoder_module.reverse_geocode

def run_reverse_geocoder():
    print("\n" + "="*60)
    print("【住通地址補完 - 座標反查工具 v1.0】")
    print("="*60)

    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            CREDS_FILE,
            ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        )
        client = gspread.authorize(creds)
        wks = client.open_by_key(SHEET_KEY).sheet1
        all_rows = wks.get_all_values()
        print(f"[系統] 成功連接試算表，共 {len(all_rows) - 1} 筆資料。", flush=True)
    except Exception as e:
        print(f"❌ 雲端連線失敗: {e}", flush=True)
        return

    if not all_rows:
        print("❌ 試算表沒有資料。", flush=True)
        return

    headers = all_rows[0]
    try:
        IDX_M_ADDR = headers.index("查地址")
        IDX_OBJ_LAT = headers.index("物件緯度")
        IDX_OBJ_LON = headers.index("物件經度")
    except ValueError as e:
        print(f"❌ 找不到必要的標題欄位: {e}，請確認 A1 列的標題文字是否正確。", flush=True)
        return

    try: IDX_V_SOURCE = headers.index("來源仲介")
    except: IDX_V_SOURCE = 21

    try: IDX_Y_REV_ADDR = headers.index("反查地址")
    except ValueError: IDX_Y_REV_ADDR = 24

    try: IDX_Z_COORD_SRC = headers.index("座標來源")
    except ValueError: IDX_Z_COORD_SRC = 25

    update_cells = []
    updated_count = 0

    print("[情報] 開始掃描並進行座標反查...\n", flush=True)

    interrupted = False
    try:
        for i, row in enumerate(all_rows):
            if i == 0:
                continue
            
            row_num = i + 1
        
            def get_val(idx):
                return row[idx].strip() if len(row) > idx else ""

            source = get_val(IDX_V_SOURCE)
            obj_addr = get_val(IDX_M_ADDR)
            lat_str = get_val(IDX_OBJ_LAT)
            lon_str = get_val(IDX_OBJ_LON)
        
            coord_src = get_val(IDX_Z_COORD_SRC)
            rev_addr = get_val(IDX_Y_REV_ADDR)
        
            # 條件：有經緯度、來源是信義或永慶 (模糊匹配)、且反查地址目前為空
            is_target = any(k in source for k in ["信義", "永慶"]) or any(k in coord_src for k in ["信義", "永慶"])
            
            if lat_str and lon_str and is_target and not rev_addr:
                try:
                    # 強效清理：只留下數字、點、負號
                    lat_clean = re.sub(r'[^0-9.-]', '', lat_str)
                    lon_clean = re.sub(r'[^0-9.-]', '', lon_str)
                    
                    if not lat_clean or not lon_clean:
                        print(f"  × [ID:{row[0]}] 座標無效: {lat_str}, {lon_str}", flush=True)
                        continue

                    lat = float(lat_clean)
                    lng = float(lon_clean)
                    address, was_cached = reverse_geocode(lat, lng)
                
                    if "Error" not in address and "not found" not in address:
                        # 寫入 Y 欄
                        update_cells.append(gspread.Cell(row=row_num, col=IDX_Y_REV_ADDR + 1, value=address))
                        updated_count += 1
                    
                        source_str = "[快取]" if was_cached else "[API]"
                        print(f"  OK [ID:{row[0]}] {source_str} 反查成功: {lat},{lng} ➔ {address}", flush=True)
                    else:
                        print(f"  FAILED [ID:{row[0]}] 反查失敗: {address}", flush=True)
                    
                    # 無論成功失敗，只要有呼叫 API 就必須休息
                    if not was_cached:
                        if "429" in address:
                            print("  WAIT [警告] 偵測到 429 流量管制，冷卻中 (10秒)...", flush=True)
                            time.sleep(10)
                        else:
                            time.sleep(1.5) # 遵守 Nominatim 1秒/筆 規定
                except Exception as e:
                    print(f"  ERROR [ID:{row[0]}] 發生錯誤: {str(e)[:50]} (lat='{lat_str}')", flush=True)

            # 批次寫入
            if len(update_cells) >= 50:
                print(f"\n[系統] 觸發分批備份：正在寫入 {len(update_cells)} 筆地址...", flush=True)
                try:
                    wks.update_cells(update_cells)
                    update_cells.clear()
                except Exception as e:
                    print(f"💥 分批寫入失敗: {e}", flush=True)
                    time.sleep(3)

    except KeyboardInterrupt:
        print("\n🛑 收到強制中斷訊號 (Ctrl+C)，準備儲存已處理資料...")
        interrupted = True

    # 寫入剩餘
    if update_cells:
        print(f"\n[系統] 準備寫入最後剩下的 {len(update_cells)} 筆地址...")
        try:
            wks.update_cells(update_cells)
        except Exception as e:
            print(f"💥 寫入失敗: {e}")

    if updated_count == 0:
        print("\n[OK] 沒有需要反查地址的資料。", flush=True)
    else:
        print(f"\n[DONE] 執行完畢！本次總共反查並填寫了 {updated_count} 筆地址！", flush=True)

if __name__ == "__main__":
    run_reverse_geocoder()

    if interrupted:
        raise KeyboardInterrupt
