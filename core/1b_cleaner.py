import os
import gspread
import json
import re
import time
from oauth2client.service_account import ServiceAccountCredentials

# --- 設定 ---
_base_dir = os.path.dirname(os.path.abspath(__file__))
CREDS_FILE = os.path.join(_base_dir, "houseflow_gheet_key.json.json")
if not os.path.exists(CREDS_FILE):
    CREDS_FILE = os.path.join(_base_dir, "..", "houseflow_gheet_key.json.json")

SHEET_KEY = "1bU4BKbjQgnoNqSK50G4vHgMGBFetHsBrbMyHv2Xc2k0"

def remove_emojis(text):
    """移除字串中的 Emoji 與特殊行銷符號"""
    if not text: return ""
    # 移除 4 字節以上的 Unicode 字符 (大部分 Emoji)
    text = re.sub(r'[^\u0000-\uFFFF]', '', text)
    # 擴大過濾範圍：包含 BMP 內的特殊符號 (星星, 勾勾, 電話, 手寫等)
    # 加入：⭐(2b50), ☎(260e), ✅(2705), ☑(2611), ✍(270d)
    special_chars = r'[★☆☀☁⚡❄✨⭕❌❗❓➕➖🔥❤️👍🏠🏢📍🔔📢📣💥✨💎💰🚩⭐🌟✅☑✔☎📞📱✍✏✒➡⬅⬆⬇▶◀【】\[\]]'
    text = re.sub(special_chars, '', text)
    # 同時移除一些常見的標註符號，如單獨的波浪號或多餘空格
    text = re.sub(r'\s+', ' ', text) # 多個空格變一個
    return text.strip()

def clean_json_titles(json_str):
    """清理 JSON 格式內的所有 title 欄位"""
    if not json_str or json_str.strip() == "": return ""
    try:
        data = json.loads(json_str)
        for agent in data:
            for listing in agent.get("listings", []):
                if "title" in listing:
                    listing["title"] = remove_emojis(listing["title"])
        return json.dumps(data, ensure_ascii=False)
    except:
        return json_str

def run_emoji_cleaner():
    print("\n" + "="*60)
    print("【住通數據清洗中心 - 1b_cleaner.py (移除 Emoji)】")
    print("="*60)

    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive'])
        client = gspread.authorize(creds)
        wks = client.open_by_key(SHEET_KEY).sheet1
        
        print("[1/3] 正在讀取試算表資料...")
        all_rows = wks.get_all_values()
        if len(all_rows) <= 1:
            print("! 資料量不足，取消執行。")
            return

        print(f"[2/3] 正在掃描並清洗 B 欄(標題)與 AB 欄(JSON)...")
        
        # 索引：B(1, 標題), AB(27, 同行資訊 JSON)
        idx_title = 1
        idx_json = 27
        
        update_queue = []
        cleaned_count = 0
        
        for i, r in enumerate(all_rows[1:]):
            row_num = i + 2
            
            # A. 清洗標題
            orig_title = r[idx_title] if len(r) > idx_title else ""
            new_title = remove_emojis(orig_title)
            
            # B. 清洗 JSON
            orig_json = r[idx_json] if len(r) > idx_json else ""
            new_json = clean_json_titles(orig_json)
            
            # 如果有變動，加入更新隊列
            has_change = False
            if orig_title != new_title:
                update_queue.append(gspread.Cell(row=row_num, col=idx_title + 1, value=new_title))
                has_change = True
            
            if orig_json != new_json:
                update_queue.append(gspread.Cell(row=row_num, col=idx_json + 1, value=new_json))
                has_change = True
            
            if has_change:
                cleaned_count += 1

            # 每累積 100 個單元格更新一次
            if len(update_queue) >= 100:
                print(f"  - 正在寫入 {len(update_queue)//2} 筆異動至雲端...", flush=True)
                wks.update_cells(update_queue)
                update_queue = []
                time.sleep(1)

        # 寫入剩餘部分
        if update_queue:
            print(f"  - 正在寫入最後 {len(update_queue)//2} 筆異動...", flush=True)
            wks.update_cells(update_queue)

        print(f"\n[3/3] 清洗完成！本次共優化了 {cleaned_count} 筆物件的標題格式。")

    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    run_emoji_cleaner()
