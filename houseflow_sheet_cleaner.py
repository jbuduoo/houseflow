import gspread
from oauth2client.service_account import ServiceAccountCredentials

# 設定
CREDS_FILE = "houseflow_gheet_key.json.json"
SHEET_KEY = "1bU4BKbjQgnoNqSK50G4vHgMGBFetHsBrbMyHv2Xc2k0"

def clean_sheet():
    print("\n" + "="*60)
    print("【住通試算表淨化工具 - 座標/紀錄清除版】")
    print("="*60)

    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive'])
        client = gspread.authorize(creds)
        wks = client.open_by_key(SHEET_KEY).sheet1
        
        # 取得總列數
        all_rows = wks.get_all_values()
        total_rows = len(all_rows)
        
        if total_rows < 2:
            print("✨ 試算表目前是空的，不需清理。")
            return

        print(f"[步驟] 正在清除 N、O、P 欄位 (2 ~ {total_rows} 列)...")
        
        # 準備空值矩陣 (N, O, P 三欄)
        empty_data = [["", "", ""] for _ in range(total_rows - 1)]
        
        # 大批量更新 N2:P (節省 API 次數)
        wks.update(f"N2:P{total_rows}", empty_data)
        
        print("   ✅ 清除成功！經緯度與拜訪紀錄已移除。")
        print("   💡 現在您可以放心使用新版地址抓取程式了。")

    except Exception as e:
        print(f"❌ 清除失敗: {e}")

if __name__ == "__main__":
    clean_sheet()
