import streamlit as st
import pandas as pd
import re
import folium
from folium import plugins
from streamlit_folium import st_folium
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import requests
import hashlib
import threading

start_time = time.time()

# --- 設定頁面資訊 ---
st.set_page_config(page_title="房仲攻堅地圖 (實景排版版)", layout="wide", initial_sidebar_state="expanded")

# --- 0. 注入自定義 CSS ---
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    /* 大幅緊縮頁面上方的黃金空白區塊 */
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 0rem !important;
    }
    section[data-testid="stSidebar"] { width: 340px !important; }
    .st_folium { border: none; border-radius: 0px; }
    .jump-btn {
        display: inline-block;
        margin-top: 8px;
        padding: 5px 15px;
        background-color: #ff4b4b;
        color: white !important;
        border-radius: 20px;
        text-decoration: none !important;
        font-size: 13px;
        font-weight: bold;
    }
    .popup-img {
        width: 100%;
        height: 85px;  /* 固定長寬，不讓它無限撐高 */
        object-fit: cover;
        border-radius: 8px;
        margin-bottom: 8px;
    }
    .popup-title {
        font-size: 16px;
        font-weight: bold;
        color: #333;
        margin-bottom: 4px;
        display: block;
    }
    .popup-links {
        margin-top: 10px;
        border-top: 1px solid #eee;
        padding-top: 8px;
        display: flex;
        gap: 10px;
    }
    .popup-links a {
        font-size: 13px;
        color: #1976d2 !important;
        text-decoration: underline !important;
    }
    /* 這裡加入閃爍跳動動畫 */
    @keyframes marker-flash {
        0%, 100% { transform: scale(1); filter: brightness(1); }
        50% { transform: scale(1.4); filter: brightness(1.2); }
    }
    .marker-flash {
        animation: marker-flash 0.5s ease-in-out 3;
        z-index: 9999 !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- 1. Google Sheets 連線 ---
SHEET_KEY = "1bU4BKbjQgnoNqSK50G4vHgMGBFetHsBrbMyHv2Xc2k0"
CREDS_FILE = "houseflow_gheet_key.json.json"

@st.cache_resource
def get_gspread_client():
    scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
    try:
        has_secret = "google_credentials_json" in st.secrets
    except Exception:
        has_secret = False

    if has_secret:
        # 供 Streamlit Cloud 雲端部署使用 (將 JSON 字串轉回字典)
        import json
        creds_dict = json.loads(st.secrets["google_credentials_json"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        # 供本地端開發使用
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, scope)
    return gspread.authorize(creds)

@st.cache_data(ttl=300)
def load_data_from_gsheet():
    client = get_gspread_client()
    sheet = client.open_by_key(SHEET_KEY).sheet1
    
    # get_all_records() 會在有重複或空欄位標題時報錯
    # 改用 get_all_values() 並手動處理標題
    all_values = sheet.get_all_values()
    if not all_values:
        return pd.DataFrame()
        
    headers = all_values[0]
    data = all_values[1:]
    
    # 清理標題：處理重複與空值
    clean_headers = []
    seen = {}
    for i, h in enumerate(headers):
        h = h.strip()
        if not h:
            h = f"Unnamed_{i}"
        
        if h in seen:
            seen[h] += 1
            new_h = f"{h}_{seen[h]}"
            clean_headers.append(new_h)
        else:
            seen[h] = 0
            clean_headers.append(h)
            
    return pd.DataFrame(data, columns=clean_headers)

@st.cache_data(ttl=86400)
def check_link_health(url):
    """檢查網址是否有效，24 小時內相同網址只查一次"""
    if not url or not url.startswith('http'):
        return "F"
    try:
        # 使用 HEAD 請求，只取標頭不下載網頁，速度極快
        res = requests.head(url, timeout=3, allow_redirects=True)
        return "T" if res.status_code == 200 else "F"
    except:
        return "F"

def log_to_gsheet(user_device, house_url, status):
    """將足跡紀錄寫回 Google Sheets 的 Logs 分頁 (由上而下插入)"""
    try:
        client = get_gspread_client()
        spreadsheet = client.open_by_key(SHEET_KEY)
        
        # 尋找或建立 Logs 工作表
        try:
            log_sheet = spreadsheet.worksheet("Logs")
        except:
            # 若不存在則建立，並加上標題列
            log_sheet = spreadsheet.add_worksheet(title="Logs", rows=1000, cols=4)
            log_sheet.insert_row(["時間", "使用者", "物件網址", "連結狀態"], 1)
        
        # 準備新資料
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_row = [now_str, user_device, house_url, status]
        
        # 插入在第 2 列 (標題下方)
        log_sheet.insert_row(new_row, 2)
    except Exception as e:
        print(f"Log Error: {e}")

def get_device_name():
    """從 User-Agent 嘗試辨識手機型號"""
    ua = ""
    try:
        # Streamlit 1.56.0 支援 st.context.headers
        ua = st.context.headers.get("User-Agent", "")
    except:
        pass
    
    device = "Unknown"
    if "iPhone" in ua:
        # 嘗試從 UA 抓取型號資訊 (簡化版)
        device = "iPhone"
    elif "Android" in ua:
        device = "Android"
        if "Samsung" in ua: device = "Samsung"
        elif "Pixel" in ua: device = "Pixel"
    
    # 產生一個 Session 級別的 ID (若要跨 Session 永久固定，需使用 Cookie)
    if 'device_id' not in st.session_state:
        import random
        st.session_state['device_id'] = random.randint(1000, 9999)
    
    return f"{device}-{st.session_state['device_id']}"

from folium.plugins import MarkerCluster

# --- 2. 主程式流程 ---
df_raw = load_data_from_gsheet()

# 硬性過濾已委託案件（保持地圖乾淨）
df = df_raw[~df_raw['是否已委託'].astype(str).str.upper().isin(['Y', 'YES', '是', 'TRUE'])]

visit_counts = {}
log_path = os.path.join(os.path.dirname(__file__), "houseflow_visit_logs.csv")
if os.path.exists(log_path):
    logs_all = pd.read_csv(log_path)
    visit_counts = logs_all['物件ID'].astype(str).value_counts().to_dict()



# --- 初始定位流程 ---
if 'init_done' not in st.session_state:
    st.session_state['init_done'] = False

# 處理測試跳轉請求
if st.query_params.get("jump") == "test":
    st.session_state['map_center'] = [25.0001, 121.5065] # 中和路 466 號
    st.session_state['init_done'] = True
    st.query_params.clear()
    st.rerun()


if not st.session_state['init_done']:
    _, col_mid, _ = st.columns([1, 2, 1])
    with col_mid:
        st.markdown("""
        <div style='text-align:center; margin-top: 30vh; margin-bottom: 1.5rem;'>
            <h2>為了精準推薦附近物件，請點選 ⌖ 以開啟定位服務。</h2>
        </div>
        """, unsafe_allow_html=True)

        # 使用內部欄位將定位按鈕置中
        _, col_gps_btn, _ = st.columns([1, 1, 1])
        with col_gps_btn:
            from streamlit_geolocation import streamlit_geolocation
            loc = streamlit_geolocation()
        if loc and loc.get('latitude'):
            st.session_state['map_center'] = [loc['latitude'], loc['longitude']]
            st.session_state['init_done'] = True
            
            # --- 新增：定位成功即紀錄足跡 (改為背景執行避免卡頓) ---
            try:
                device_info = get_device_name()
                threading.Thread(target=log_to_gsheet, args=(device_info, "定位成功 (使用者開啟地圖)", "T")).start()
            except:
                pass
                
            st.rerun()

    st.stop()


if True:
    c_lat, c_lng = st.session_state['map_center']


    # 以 session_state 內的中心點建立地圖
    m = folium.Map(location=[c_lat, c_lng], zoom_start=17, min_zoom=17, max_zoom=18, tiles="OpenStreetMap")
    
    # 載入 FontAwesome 6
    from folium import Element
    m.get_root().html.add_child(Element('''
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    '''))
    
    # --- 加入「目前位置」標記與搜尋半徑圈 ---
    center_icon_html = """
    <div style='display:flex;align-items:center;justify-content:center;background-color:#333;width:40px;height:40px;border-radius:50%;border:3px solid white;box-shadow:0 0 10px rgba(0,0,0,0.5);font-size:22px;'>
        <i class="fa-solid fa-cat" style="color: rgb(255, 212, 59);"></i>
    </div>
    """
    folium.Marker(
        location=[c_lat, c_lng],
        tooltip="📍 目前搜尋中心",
        icon=folium.DivIcon(html=center_icon_html, icon_anchor=(17, 17))
    ).add_to(m)

    folium.Circle(
        location=[c_lat, c_lng],
        radius=500,  # 0.5 公里 = 500 公尺
        color="#3186cc",
        fill=True,
        fill_color="#3186cc",
        fill_opacity=0.1,
        interactive=True
    ).add_to(m)

    map_id = m.get_name()
    # 升級版跳轉：飛過去 -> 找坐標 -> 開彈窗
    jump_script = f"""
    <script>
    function jumpTo(lat, lon) {{
        var m = window['{map_id}'];
        if(!m) return;
        m.flyTo([lat, lon], 18);
        m.once('moveend', function() {{
            m.eachLayer(function(layer) {{
                if (layer.getLatLng && 
                    Math.abs(layer.getLatLng().lat - lat) < 0.00001 && 
                    Math.abs(layer.getLatLng().lng - lon) < 0.00001) {{
                    if (layer.openPopup) layer.openPopup();
                }}
            }});
        }});
    }}
    </script>
    """
    m.get_root().html.add_child(folium.Element(jump_script))
    
    # 強制隱藏 Leaflet 預設的關閉按鈕
    mobile_css = """
    <style>
    .leaflet-popup-close-button {
        display: none !important;
    }
    .marker-cluster-small { background-color: rgba(220, 50, 50, 0.3) !important; }
    .marker-cluster-small div { background-color: rgba(200, 20, 20, 0.85) !important; color: white !important; font-weight: bold !important; }
    .marker-cluster-medium { background-color: rgba(220, 50, 50, 0.3) !important; }
    .marker-cluster-medium div { background-color: rgba(200, 20, 20, 0.85) !important; color: white !important; font-weight: bold !important; }
    .marker-cluster-large { background-color: rgba(220, 50, 50, 0.3) !important; }
    .marker-cluster-large div { background-color: rgba(200, 20, 20, 0.85) !important; color: white !important; font-weight: bold !important; }
    </style>
    """
    m.get_root().header.add_child(folium.Element(mobile_css))
    
    import random
    from collections import defaultdict
    
    # 使用 FeatureGroup，不合併內容
    marker_group = folium.FeatureGroup(name="物件點位").add_to(m)

    count_rendered = 0
    base_style = "display:flex;align-items:center;justify-content:center;border-radius:50%;border:3px solid white;box-shadow:0 0 10px rgba(0,0,0,0.5);color:white;font-weight:bold;"

    # 以精確座標分群（相同座標才合併）
    grouped_houses = defaultdict(list)
    for index, row in df.iterrows():
        try:
            h_lat = float(row.get('物件緯度', ''))
            h_lng = float(row.get('物件經度', ''))
        except (ValueError, TypeError):
            continue
        dist_km = (((h_lat - c_lat) * 111) ** 2 + ((h_lng - c_lng) * 100) ** 2) ** 0.5
        if dist_km > 0.5:
            continue
        grouped_houses[(h_lat, h_lng)].append(row)

    # 處理每一筆或分群
    for (h_lat, h_lng), rows in grouped_houses.items():
        # 取消位移邏輯，讓點位 100% 落在座標上
        final_lat = h_lat
        final_lng = h_lng
        
        group_size = len(rows)
        count_rendered += group_size
        
        combined_popup_html = "<div style='max-height: 350px; overflow-y: auto; padding-right: 10px;'>"
        first_display_text = ""
        res_locations = []
        
        for i, row in enumerate(rows):
            # --- 處理單筆物件的基礎資料 ---
            try:
                res_loc = [float(row.get('戶籍緯度', '')), float(row.get('戶籍經度', ''))]
            except (ValueError, TypeError):
                res_loc = [None, None]

            # 優先取得 AA 欄 (AI 結論) 的資料
            display_obj_addr = str(row.get('AI 結論', '')).strip()
            if not display_obj_addr:
                display_obj_addr = str(row.get('查地址', '')).strip()
            if not display_obj_addr:
                display_obj_addr = str(row.get('物件地址', '')).strip()

            display_res_addr = str(row.get('戶籍地址', '')) if str(row.get('戶籍地址', '')) != '' else "待查閱"
            
            img_url = str(row.get('案件首圖', ''))
            transcript_url = str(row.get('比對地址', ''))
            web_link = str(row.get('網頁連結', ''))
            
            try:
                qty_val = str(row.get('案件數量', '1'))
                qty_is_multi = (qty_val == '多筆' or (qty_val.isdigit() and int(qty_val) > 1))
            except:
                qty_is_multi = False
                
            suffix = " (需比對：多筆)" if qty_is_multi else ""
            # 強力分行邏輯：將各種空白與逗號轉為 <br>
            raw_addr_cleaned = f"{display_obj_addr.replace('新北市','').strip()}{suffix}"
            display_text = re.sub(r'[\s,，]+', '<br>', raw_addr_cleaned)
            display_text = display_text.replace('<br>⭐', ' ⭐') # 星號不換行
            display_text = display_text.replace('(多筆)(需比對：多筆)', '(需比對多筆)').replace('(多筆)', '(需比對多筆)')
            # 確保開頭與結尾沒有多餘的 <br>
            display_text = re.sub(r'^(<br>)+|(<br>)+$', '', display_text)
            # 自動放大地址中原有的 ⌖ 符號
            display_text = display_text.replace('⌖', '<span style="font-size:20px; vertical-align:middle;">⌖</span>')
            
            type_str = str(row.get('類型', ''))
            layout_str = str(row.get('格局', ''))
            layout_display = f"{type_str}" + (f" | {layout_str}" if layout_str else "") if type_str else layout_str
            
            img_tag = f"<img src='{img_url}' loading='lazy' style='width:100%; height:120px; object-fit:cover; border-radius:8px; margin-bottom:8px;'>" if len(img_url) > 10 else ""
            links_block = f"""
                <div style='margin-top:10px; border-top:1px solid #ccc; padding-top:10px; display:flex; gap:15px;'>
                    <a href='{web_link}' target='_blank' style='font-size:15px; font-weight:bold; color:#1976d2; text-decoration:none;'>👉 同行網頁</a>
                    <a href='{transcript_url}' target='_blank' style='font-size:15px; font-weight:bold; color:#1976d2; text-decoration:none;'>📑 騰本連結</a>
                </div>
            """
            
            res_addr_html = f"👤 戶籍：{display_res_addr}<br>\n                " if display_res_addr != "待查閱" else ""

            # --- 單筆物件 Popup HTML ---
            item_html = f"""
                {img_tag}
                <span style='font-size:18px; font-weight:bold; color:#111; margin-bottom:8px; display:block; line-height:1.3;'>{row['案件名稱']}</span>
                <div style='font-size:15px; color:#333; line-height:1.6;'>
                    📍 地址：{display_text}<br>
                    🏠 房型：{layout_display}<br>
                    💰 <strong style='font-size:16px; color:#d32f2f;'>{row.get('售價(萬)','')} 萬</strong> | {row.get('總坪數','')}坪 | {row.get('樓層','')}/{row.get('總樓層','')}F
                </div>
                {links_block}
            """
            
            if i == 0:
                first_display_text = display_text
                
            combined_popup_html += item_html
            if i < group_size - 1:
                combined_popup_html += "<hr style='margin: 15px 0; border: 0; border-top: 1px solid #ddd;'>"
                
            # --- 處理戶籍地 (過濾重疊與空值) ---
            is_overlap = False
            if res_loc[0] is not None:
                is_overlap = (abs(h_lat - res_loc[0]) < 0.0001 and abs(h_lng - res_loc[1]) < 0.0001)
                
            if not is_overlap and display_res_addr != "待查閱" and res_loc[0] is not None:
                res_popup_html = item_html.replace(
                    f"{row['案件名稱']}</span>",
                    f"{row['案件名稱']}<span style='color:#28a745; font-size:16px;'>(屋主戶籍地)</span></span>"
                ).replace(
                    "🏠 房型：",
                    f"👤 戶籍：{display_res_addr}<br>🏠 房型："
                )
                res_locations.append({
                    "loc": res_loc,
                    "html": res_popup_html,
                    "addr": display_res_addr
                })

        combined_popup_html += "</div>"
        
        # --- 決定合併標記外觀 (解法 B) ---
        if group_size > 1:
            marker_text = str(group_size)
            tooltip_text = f"{first_display_text} 等 (共 {group_size} 筆)"
        else:
            visit_count = visit_counts.get(str(rows[0]['ID']), 0)
            marker_text = "🏠" if visit_count == 0 else str(visit_count)
            tooltip_text = first_display_text
            
        # 畫出紅色物件標記 (升級為圖釘型)
        marker_html = f'''
        <div style="display: flex; flex-direction: column; align-items: center;">
            <div style="{base_style}background-color:red;width:38px;height:38px;font-size:16px;">{marker_text}</div>
            <div style="width: 0; height: 0; border-left: 9px solid transparent; border-right: 9px solid transparent; border-top: 12px solid white; margin-top: -4px; filter: drop-shadow(0 4px 4px rgba(0,0,0,0.3));"></div>
        </div>
        '''
        folium.Marker(
            location=[final_lat, final_lng],
            popup=folium.Popup(combined_popup_html, max_width=320),
            icon=folium.DivIcon(html=marker_html, icon_anchor=(19, 46))
        ).add_to(marker_group)

        # 畫出綠色戶籍標記 (升級為圖釘型)
        for res in res_locations:
            res_lat = res["loc"][0] + random.uniform(-0.001, 0.001)
            res_lng = res["loc"][1] + random.uniform(-0.001, 0.001)
            res_marker_html = f'''
            <div style="display: flex; flex-direction: column; align-items: center;">
                <div style="{base_style}background-color:#28a745;width:38px;height:38px;font-size:16px;"><i class="fa fa-user"></i></div>
                <div style="width: 0; height: 0; border-left: 9px solid transparent; border-right: 9px solid transparent; border-top: 12px solid white; margin-top: -4px; filter: drop-shadow(0 4px 4px rgba(0,0,0,0.3));"></div>
            </div>
            '''
            folium.Marker(
                location=[res_lat, res_lng],
                popup=folium.Popup(res["html"], max_width=300),
                icon=folium.DivIcon(html=res_marker_html, icon_anchor=(19, 46))
            ).add_to(marker_group)


    # --- 渲染地圖 (回歸順暢模式：不監聽點擊，避免重新整理) ---
    st_folium(m, width="stretch", height=700, key="image_map", returned_objects=[])

    end_time = time.time()
    st.markdown(f"""
    <div style='position: fixed; top: 15px; right: 15px; background-color: rgba(0,0,0,0.7); color: white; padding: 8px 15px; border-radius: 8px; z-index: 999999; font-weight: bold; font-size: 14px; box-shadow: 0 4px 6px rgba(0,0,0,0.3);'>
        ⏱️ 載入時間：{end_time - start_time:.2f} 秒<br>
        📍 顯示物件：{count_rendered} 筆<br>
        <a href="./?jump=test" target="_self" style="color: #ffeb3b; text-decoration: none; font-size: 12px; border: 1px solid #ffeb3b; padding: 2px 6px; border-radius: 4px; margin-top: 6px; display: inline-block;">🔍 跳轉至中和路 (測試用)</a>
    </div>
    """, unsafe_allow_html=True)

