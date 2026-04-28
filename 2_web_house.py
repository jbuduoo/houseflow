import streamlit as st
import pandas as pd
import folium
from folium import plugins
from streamlit_folium import st_folium
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import random
from collections import defaultdict

start_time = time.time()

# --- 設定頁面資訊 ---
st.set_page_config(page_title="房仲攻堅地圖", layout="wide", initial_sidebar_state="expanded")

# --- 0. 注入自定義 CSS ---
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 0rem !important;
    }
    section[data-testid="stSidebar"] { width: 340px !important; }
    .st_folium { border: none; border-radius: 0px; }
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
    data = sheet.get_all_records()
    return pd.DataFrame(data)

# --- 2. 初始歡迎與定位詢問 ---
if 'init_done' not in st.session_state:
    st.session_state.init_done = False
if 'map_center' not in st.session_state:
    st.session_state['map_center'] = [25.00393, 121.51231]

if not st.session_state.init_done:
    _, col_mid, _ = st.columns([1, 2, 1])
    with col_mid:
        st.write("") 
        st.subheader("📍 請選擇搜尋中心：")
        
        c1, c2 = st.columns(2)
        btn_gps = c1.button("🛰️ 我的位置", use_container_width=True)
        btn_default = c2.button("🏠 預設位置", use_container_width=True)
        
        # 隱藏的定位組件 (利用 streamlit-geolocation 的穩定性)
        from streamlit_geolocation import streamlit_geolocation
        if btn_gps or st.session_state.get('waiting_gps', False):
            st.session_state.waiting_gps = True
            st.info("⌛ 正在抓取您的 GPS 座標，請按下方標靶並允許權限...")
            loc = streamlit_geolocation()
            if loc and loc.get('latitude'):
                st.session_state['map_center'] = [loc['latitude'], loc['longitude']]
                st.session_state.init_done = True
                st.session_state.waiting_gps = False
                st.rerun()
        
        if btn_default:
            st.session_state['map_center'] = [25.00393, 121.51231]
            st.session_state.init_done = True
            st.rerun()
    st.stop()

# --- 3. 主程式流程 ---
df_raw = load_data_from_gsheet()
df = df_raw[~df_raw['是否已委託'].astype(str).str.upper().isin(['Y', 'YES', '是', 'TRUE'])]

if 'pending_center' not in st.session_state:
    st.session_state['pending_center'] = None
if 'last_processed_click' not in st.session_state:
    st.session_state['last_processed_click'] = None

c_lat, c_lng = st.session_state['map_center']

# 處理地圖點擊移動
if "main_map" in st.session_state and st.session_state["main_map"]:
    map_state = st.session_state["main_map"]
    if map_state.get("last_clicked"):
        click_lat = map_state["last_clicked"]["lat"]
        click_lng = map_state["last_clicked"]["lng"]
        current_click = [click_lat, click_lng]
        if st.session_state['last_processed_click'] != current_click:
            st.session_state['last_processed_click'] = current_click
            dist_from_center = (((click_lat - c_lat) * 111) ** 2 + ((click_lng - c_lng) * 100) ** 2) ** 0.5
            if dist_from_center > 0.3:
                st.session_state['pending_center'] = current_click

if st.session_state['pending_center']:
    @st.dialog("移動搜尋中心")
    def show_move_dialog():
        st.write("📍 偵測到點擊新位置，是否要將搜尋中心移動到該處？")
        col_btn1, col_btn2 = st.columns(2)
        if col_btn1.button("✅ 確認", use_container_width=True):
            st.session_state['map_center'] = st.session_state['pending_center']
            st.session_state['pending_center'] = None
            st.rerun()
        if col_btn2.button("❌ 取消", use_container_width=True):
            st.session_state['pending_center'] = None
            st.rerun()
    show_move_dialog()

# 建立地圖 - 鎖定 Zoom 18
c_lat, c_lng = st.session_state['map_center']
m = folium.Map(location=[c_lat, c_lng], zoom_start=18, min_zoom=18, max_zoom=18, tiles="OpenStreetMap")

# 定位控制 (手動點擊)
plugins.LocateControl(
    auto_start=False, 
    icon='fa-solid fa-location-arrow',
).add_to(m)

# 載入自定義樣式
from folium import Element
m.get_root().html.add_child(Element('''
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        .fa-location-arrow { color: rgb(116, 192, 252) !important; font-size: 24px !important; }
        .leaflet-popup-close-button { display: none !important; }
    </style>
'''))

# 中心標記 - 貓咪圖示
center_icon_html = "<div style='display:flex;align-items:center;justify-content:center;background-color:#333;width:40px;height:40px;border-radius:50%;border:3px solid white;box-shadow:0 0 10px rgba(0,0,0,0.5);font-size:22px;'><i class='fa-solid fa-cat' style='color: rgb(255, 212, 59);'></i></div>"
folium.Marker(location=[c_lat, c_lng], tooltip="📍 目前中心", icon=folium.DivIcon(html=center_icon_html, icon_anchor=(20, 20))).add_to(m)
folium.Circle(location=[c_lat, c_lng], radius=500, color="#3186cc", fill=True, fill_opacity=0.1).add_to(m)

# 物件點位 - 紅色數字樣式
marker_group = folium.FeatureGroup(name="物件點位").add_to(m)
base_style = "display:flex;align-items:center;justify-content:center;border-radius:50%;border:3px solid white;box-shadow:0 0 10px rgba(0,0,0,0.5);color:white;font-weight:bold;background-color:red;"

grouped_houses = defaultdict(list)
for index, row in df.iterrows():
    try:
        h_lat, h_lng = float(row.get('物件緯度', '')), float(row.get('物件經度', ''))
    except: continue
    dist_km = (((h_lat - c_lat) * 111) ** 2 + ((h_lng - c_lng) * 100) ** 2) ** 0.5
    if dist_km <= 0.5:
        grouped_houses[(h_lat, h_lng)].append(row)

count_rendered = 0
for (h_lat, h_lng), rows in grouped_houses.items():
    final_lat, final_lng = h_lat + random.uniform(-0.0001, 0.0001), h_lng + random.uniform(-0.0001, 0.0001)
    group_size = len(rows)
    count_rendered += group_size
    
    popup_html = "<div style='max-height: 350px; overflow-y: auto; padding-right: 10px;'>"
    for i, row in enumerate(rows):
        display_res_addr = str(row.get('戶籍地址', '')) if str(row.get('戶籍地址', '')) != '' else "待查閱"
        img_url = str(row.get('案件首圖', ''))
        img_tag = f"<img src='{img_url}' style='width:100%; height:120px; object-fit:cover; border-radius:8px;'>" if len(img_url) > 10 else ""
        popup_html += f"<div>{img_tag}<b>{row['案件名稱']}</b><br>📍 地址：{row.get('物件地址','')}<br>👤 戶籍：{display_res_addr}<br>💰 售價：{row.get('售價(萬)','')} 萬</div>"
        if i < group_size - 1: popup_html += "<hr>"
    popup_html += "</div>"
    
    folium.Marker(
        location=[final_lat, final_lng],
        popup=folium.Popup(popup_html, max_width=300),
        icon=folium.DivIcon(html=f'<div style="{base_style}width:38px;height:38px;">{group_size if group_size>1 else "🏠"}</div>', icon_anchor=(19, 19))
    ).add_to(marker_group)

# 渲染地圖
st_folium(m, width="stretch", height=700, key="main_map", returned_objects=["last_clicked"])

# 統計資訊
st.markdown(f"<div style='position: fixed; top: 15px; right: 15px; background: rgba(0,0,0,0.7); color: white; padding: 8px; border-radius: 8px;'>⏱️ {time.time()-start_time:.2f}s | 📍 {count_rendered} 筆</div>", unsafe_allow_html=True)
