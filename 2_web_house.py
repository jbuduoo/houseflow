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
    
    /* 標籤按鈕頁籤系統 */
    .agent-tabs {
        position: relative;
        margin-top: 10px;
        border-top: 1px dashed #eee;
        padding-top: 8px;
    }
    .pill-row {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin-bottom: 5px;
    }
    .tab-input {
        display: none;
    }
    .agent-pill {
        background: #f0f2f6;
        border: 1px solid #d1d5db;
        border-radius: 4px;
        padding: 2px 8px;
        font-size: 11px;
        color: #31333f;
        cursor: pointer;
        display: inline-flex;
        align-items: center;
        white-space: nowrap;
        transition: all 0.2s;
    }
    .agent-pill:hover {
        background: #e0e4e9;
    }
    /* 選中標籤時的樣式 */
    .tab-input:checked + .tab-content-trigger .agent-pill {
        background: #1a73e8;
        color: white;
        border-color: #1a73e8;
        font-weight: bold;
    }
    /* 內容區塊樣式 */
    .tab-content {
        display: none;
        background: #ffffff;
        border: 1px solid #d1d5db;
        border-radius: 4px;
        padding: 5px 10px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        margin-top: 5px;
        width: 100%;
        box-sizing: border-box;
    }
    /* 選中時顯示內容 */
    .tab-input:checked + .tab-content-trigger + .tab-content {
        display: block !important;
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
        import json
        creds_dict = json.loads(st.secrets["google_credentials_json"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, scope)
    return gspread.authorize(creds)

@st.cache_data(ttl=300)
def load_data_from_gsheet():
    client = get_gspread_client()
    sheet = client.open_by_key(SHEET_KEY).sheet1
    all_values = sheet.get_all_values()
    if not all_values:
        return pd.DataFrame()
    headers = all_values[0]
    data = all_values[1:]
    clean_headers = []
    seen = {}
    for i, h in enumerate(headers):
        h = h.strip()
        if not h: h = f"Unnamed_{i}"
        if h in seen:
            seen[h] += 1
            clean_headers.append(f"{h}_{seen[h]}")
        else:
            seen[h] = 0
            clean_headers.append(h)
    return pd.DataFrame(data, columns=clean_headers)

def log_to_gsheet(user_device, house_url, status):
    try:
        client = get_gspread_client()
        spreadsheet = client.open_by_key(SHEET_KEY)
        try:
            log_sheet = spreadsheet.worksheet("Logs")
        except:
            log_sheet = spreadsheet.add_worksheet(title="Logs", rows=1000, cols=4)
            log_sheet.insert_row(["時間", "使用者", "物件網址", "連結狀態"], 1)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_sheet.insert_row([now_str, user_device, house_url, status], 2)
    except: pass

def get_device_name():
    ua = ""
    try: ua = st.context.headers.get("User-Agent", "")
    except: pass
    device = "Unknown"
    if "iPhone" in ua: device = "iPhone"
    elif "Android" in ua: device = "Android"
    if 'device_id' not in st.session_state:
        import random
        st.session_state['device_id'] = random.randint(1000, 9999)
    return f"{device}-{st.session_state['device_id']}"

# --- 1.5 輔助工具：解析同行 JSON (按鈕頁籤版) ---
def parse_agent_info(json_str, row_idx):
    if not json_str or str(json_str).strip() == "": return ""
    try:
        import json
        data = json.loads(json_str)
        if not data or not isinstance(data, list): return ""
        
        final_html = '<div class="agent-tabs"><div class="pill-row">'
        
        for a_idx, item in enumerate(data):
            name = item.get("name", "未知")
            listings = item.get("listings", [])
            if not listings: continue
            
            tab_id = f"tab_{row_idx}_{a_idx}"
            summary_text = name if len(listings) == 1 else f"{name}({len(listings)})"
            
            # 內容區塊生成
            links_html = ""
            for l in listings:
                l_title = l.get("title", "物件網頁")
                l_price = l.get("price", "")
                l_time = l.get("time", "")
                l_url = l.get("url", "#")
                
                price_tag = f'<span style="color:#d32f2f; font-weight:bold; font-size:10px;">{l_price}</span>' if l_price else ""
                time_tag = f'<span style="color:#666; font-size:9px; border:1px solid #ddd; padding:0 2px; border-radius:2px; white-space:nowrap;">{l_time}</span>' if l_time else ""
                
                links_html += f'''
                <div style="border-bottom:1px solid #eee; padding:3px 0; display: grid; grid-template-columns: 1fr 65px 70px; align-items: center; gap: 5px;">
                    <a href="{l_url}" target="_blank" style="color:#1a73e8; font-size:11px; text-decoration:none; font-weight:bold; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">🔗 {l_title}</a>
                    <div style="text-align: right;">{price_tag}</div>
                    <div style="text-align: right;">{time_tag}</div>
                </div>
                '''
            
            # 拼接 HTML：Radio + Label + Content
            final_html += f'''
            <input type="radio" name="agent_group_{row_idx}" id="{tab_id}" class="tab-input">
            <label for="{tab_id}" class="tab-content-trigger">
                <span class="agent-pill">{summary_text}</span>
            </label>
            <div class="tab-content">{links_html}</div>
            '''
            
        final_html += '</div></div>'
        return final_html
    except:
        return ""

# --- 2. 主程式流程 ---
df_raw = load_data_from_gsheet()
df = df_raw[~df_raw['是否已委託'].astype(str).str.upper().isin(['Y', 'YES', '是', 'TRUE'])]

visit_counts = {}
log_path = os.path.join(os.path.dirname(__file__), "houseflow_visit_logs.csv")
if os.path.exists(log_path):
    logs_all = pd.read_csv(log_path)
    visit_counts = logs_all['物件ID'].astype(str).value_counts().to_dict()

if 'init_done' not in st.session_state:
    st.session_state['init_done'] = False

if st.query_params.get("jump") == "test":
    st.session_state['map_center'] = [25.0001, 121.5065]
    st.session_state['init_done'] = True
    st.query_params.clear()
    st.rerun()

if not st.session_state['init_done']:
    _, col_mid, _ = st.columns([1, 2, 1])
    with col_mid:
        st.markdown("<div style='text-align:center; margin-top: 30vh;'><h2>請點選 ⌖ 以開啟定位服務。</h2></div>", unsafe_allow_html=True)
        _, col_gps_btn, _ = st.columns([1, 1, 1])
        with col_gps_btn:
            from streamlit_geolocation import streamlit_geolocation
            loc = streamlit_geolocation()
        if loc and loc.get('latitude'):
            st.session_state['map_center'] = [loc['latitude'], loc['longitude']]
            st.session_state['init_done'] = True
            st.rerun()
    st.stop()

c_lat, c_lng = st.session_state['map_center']
m = folium.Map(location=[c_lat, c_lng], zoom_start=17, min_zoom=17, max_zoom=19, tiles="OpenStreetMap")
m.get_root().html.add_child(folium.Element('<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">'))

# 中心標記
folium.Marker(location=[c_lat, c_lng], icon=folium.DivIcon(html="<div style='background-color:#333;width:40px;height:40px;border-radius:50%;border:3px solid white;display:flex;align-items:center;justify-content:center;font-size:22px;'><i class='fa-solid fa-cat' style='color:#ffd43b;'></i></div>", icon_anchor=(20, 20))).add_to(m)
folium.Circle(location=[c_lat, c_lng], radius=500, color="#3186cc", fill=True, fill_opacity=0.1).add_to(m)

# 隱藏預設關閉按鈕
m.get_root().header.add_child(folium.Element("<style>.leaflet-popup-close-button { display: none !important; }</style>"))

from collections import defaultdict
grouped_houses = defaultdict(list)
for index, row in df.iterrows():
    try:
        h_lat, h_lng = float(row.get('物件緯度', '')), float(row.get('物件經度', ''))
        if (((h_lat - c_lat) * 111)**2 + ((h_lng - c_lng) * 100)**2)**0.5 <= 0.5:
            grouped_houses[(h_lat, h_lng)].append(row)
    except: continue

marker_group = folium.FeatureGroup(name="物件點位").add_to(m)
count_rendered = 0

for (h_lat, h_lng), rows in grouped_houses.items():
    count_rendered += len(rows)
    combined_html = "<div style='max-height: 350px; overflow-y: auto; padding-right: 10px;'>"
    
    for i, row in enumerate(rows):
        img_url = str(row.get('案件首圖', ''))
        web_link = str(row.get('網頁連結', ''))
        transcript_url = str(row.get('比對地址', ''))
        
        # 同行資訊解析
        other_agents_raw = row.get('其他同行資訊', '')
        if not other_agents_raw and i == 0: # 測試用 mock 資料
            mock_data = [
                {"name": "591", "listings": [{"title": "永和商辦/馬上收租", "price": "1488萬", "time": "4小時前", "url": "#1"}, {"title": "永和美業金店面", "price": "1488萬", "time": "1天前", "url": "#2"}]},
                {"name": "台屋", "listings": [{"title": "四號公園超值公寓", "price": "1450萬", "time": "2天前", "url": "#A"}]},
                {"name": "住商", "listings": [{"title": "保健路店辦", "price": "1500萬", "time": "剛剛", "url": "#X"}]}
            ]
            import json
            other_agents_raw = json.dumps(mock_data, ensure_ascii=False)
        
        agent_pills_html = parse_agent_info(other_agents_raw, f"{int(h_lat*10000)}_{i}")
        
        display_text = re.sub(r'[\s,，]+', '<br>', str(row.get('AI 結論', '') or row.get('物件地址', '')).replace('新北市',''))
        layout_display = f"{row.get('類型','')} | {row.get('格局','')}"
        
        img_tag = f"<img src='{img_url}' style='width:100%; height:120px; object-fit:cover; border-radius:8px; margin-bottom:8px;'>" if len(img_url) > 10 else ""
        
        item_html = f"""
            {img_tag}
            <a href='{web_link}' target='_blank' style='text-decoration:none;'>
                <span style='font-size:17px; font-weight:bold; color:#1a73e8; display:block; margin-bottom:5px;'>{row['案件名稱']} 🔗</span>
            </a>
            <div style='font-size:14px; color:#333; line-height:1.5;'>
                📍 地址：{display_text}<br>
                🏠 房型：{layout_display}<br>
                💰 <strong style='font-size:15px; color:#d32f2f;'>{row.get('售價(萬)','')} 萬</strong> | {row.get('總坪數','')}坪
            </div>
            {agent_pills_html}
            <div style='margin-top:10px; border-top:1px solid #eee; padding-top:8px;'>
                <a href='{transcript_url}' target='_blank' style='font-size:14px; font-weight:bold; color:#d32f2f; text-decoration:none;'>📑 謄本連結</a>
            </div>
        """
        combined_html += item_html
        if i < len(rows)-1: combined_html += "<hr style='margin:15px 0; border-top:1px solid #ddd;'>"
        
    combined_html += "</div>"
    
    # 畫標記
    marker_text = str(len(rows)) if len(rows) > 1 else ("🏠" if visit_counts.get(str(rows[0]['ID']),0)==0 else str(visit_counts.get(str(rows[0]['ID']),0)))
    marker_icon = f"""
    <div style="display:flex; flex-direction:column; align-items:center;">
        <div style="background-color:red; width:36px; height:36px; border-radius:50%; border:3px solid white; display:flex; align-items:center; justify-content:center; color:white; font-weight:bold; box-shadow:0 0 10px rgba(0,0,0,0.3);">{marker_text}</div>
        <div style="width:0; height:0; border-left:8px solid transparent; border-right:8px solid transparent; border-top:10px solid white; margin-top:-3px;"></div>
    </div>
    """
    folium.Marker(location=[h_lat, h_lng], popup=folium.Popup(combined_html, max_width=380), icon=folium.DivIcon(html=marker_icon, icon_anchor=(18, 43))).add_to(marker_group)

st_folium(m, width="stretch", height=700, key="main_map", returned_objects=[])

st.markdown(f"<div style='position:fixed; top:15px; right:15px; background:rgba(0,0,0,0.7); color:white; padding:8px 15px; border-radius:8px; z-index:9999;'>⏱️ 載入時間：{time.time()-start_time:.2f}s<br>📍 物件：{count_rendered} 筆</div>", unsafe_allow_html=True)
