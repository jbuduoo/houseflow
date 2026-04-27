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
    data = sheet.get_all_records()
    return pd.DataFrame(data)

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


if True:
    if 'map_center' not in st.session_state:
        st.session_state['map_center'] = [25.00393, 121.51231]
    if 'pending_center' not in st.session_state:
        st.session_state['pending_center'] = None
    if 'last_processed_click' not in st.session_state:
        st.session_state['last_processed_click'] = None

    c_lat, c_lng = st.session_state['map_center']

    # --- 極速攔截地圖點擊事件（從 session_state 直接讀取，省去一次 rerun 延遲） ---
    if "image_map" in st.session_state and st.session_state["image_map"]:
        map_state = st.session_state["image_map"]
        if map_state.get("last_clicked"):
            click_lat = map_state["last_clicked"]["lat"]
            click_lng = map_state["last_clicked"]["lng"]
            current_click = [click_lat, click_lng]
            
            # 確保同一個點擊事件只處理一次
            if st.session_state['last_processed_click'] != current_click:
                st.session_state['last_processed_click'] = current_click
                # 計算距離
                dist_from_center = (((click_lat - c_lat) * 111) ** 2 + ((click_lng - c_lng) * 100) ** 2) ** 0.5
                if dist_from_center > 0.5:
                    st.session_state['pending_center'] = current_click

    # 定義真正的彈出視窗 (Modal Dialog)
    if hasattr(st, "dialog"):
        @st.dialog("移動搜尋中心")
        def show_move_dialog():
            st.write("📍 偵測到點擊新位置，是否要將搜尋中心移動到該處並重新載入？")
            col_btn1, col_btn2 = st.columns(2)
            if col_btn1.button("✅ 確認移動", use_container_width=True):
                st.session_state['map_center'] = st.session_state['pending_center']
                st.session_state['pending_center'] = None
                st.rerun()
            if col_btn2.button("❌ 取消", use_container_width=True):
                st.session_state['pending_center'] = None
                st.rerun()
    else:
        # Fallback for older Streamlit versions
        def show_move_dialog():
            st.warning("📍 偵測到點擊新位置，是否要將搜尋中心移動到該處並重新載入？")
            col_btn1, col_btn2, _ = st.columns([1, 1, 3])
            if col_btn1.button("✅ 確認移動", use_container_width=True):
                st.session_state['map_center'] = st.session_state['pending_center']
                st.session_state['pending_center'] = None
                st.rerun()
            if col_btn2.button("❌ 取消", use_container_width=True):
                st.session_state['pending_center'] = None
                st.rerun()

    # --- 提示視窗：若有未確認的移動請求 ---
    if st.session_state['pending_center']:
        show_move_dialog()

    # 以 session_state 內的中心點建立地圖
    m = folium.Map(location=[c_lat, c_lng], zoom_start=18, min_zoom=18, max_zoom=18, tiles="OpenStreetMap")
    plugins.LocateControl(auto_start=False).add_to(m)
    
    # 載入 FontAwesome 6 的圖庫 (因為 fa-cat 是新版圖庫才有)
    from folium import Element
    m.get_root().html.add_child(Element('<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">'))

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
    </style>
    """
    m.get_root().header.add_child(folium.Element(mobile_css))
    
    # 叢集系統：設定 maxClusterRadius=50，讓彼此重疊 (小於 50px) 的標記會自動群集，點擊後以蜘蛛網狀 (spiderfy) 展開，方便手機點擊
    marker_cluster = MarkerCluster(options={'maxClusterRadius': 50}).add_to(m)

    count_rendered = 0
    for index, row in df.iterrows():
        try:
            house_loc = [float(row.get('物件緯度', '')), float(row.get('物件經度', ''))]
        except (ValueError, TypeError):
            house_loc = [None, None]
            
        try:
            res_loc = [float(row.get('戶籍緯度', '')), float(row.get('戶籍經度', ''))]
        except (ValueError, TypeError):
            res_loc = [None, None]

        # 地址優先取用「查地址」欄位，若空再退回「物件地址」
        display_obj_addr = str(row.get('查地址', '')).strip()
        if not display_obj_addr:
            display_obj_addr = str(row.get('物件地址', '')).strip()

        display_res_addr = str(row.get('戶籍地址', '')) if str(row.get('戶籍地址', '')) != '' else "待查閱"
        
        if house_loc[0] is None:
            continue
            
        # 距離過濾（寫死 0.5 公里以維持極速載入）
        dist_km = (((house_loc[0] - c_lat) * 111) ** 2 + ((house_loc[1] - c_lng) * 100) ** 2) ** 0.5
        if dist_km > 0.5:
            continue
            
        count = visit_counts.get(str(row['ID']), 0)
        
        is_overlap = False
        if res_loc[0] is not None:
            is_overlap = (abs(house_loc[0] - res_loc[0]) < 0.0001 and abs(house_loc[1] - res_loc[1]) < 0.0001)

        img_url = str(row.get('案件首圖', ''))
        transcript_url = str(row.get('比對地址', ''))
        web_link = str(row.get('網頁連結', ''))
        
        try:
            qty_val = str(row.get('案件數量', '1'))
            qty_is_multi = (qty_val == '多筆' or (qty_val.isdigit() and int(qty_val) > 1))
        except:
            qty_is_multi = False
            
        suffix = " (需比對：多筆)" if qty_is_multi else ""
        display_text = f"{display_obj_addr.replace('新北市','')}{suffix}".replace('(多筆)(需比對：多筆)', '(需比對：多筆)').replace('(多筆)', '(需比對：多筆)')
        
        type_str = str(row.get('類型', ''))
        layout_str = str(row.get('格局', ''))
        # 組合類型與格局顯示文字，若兩者都有則以 | 分隔
        layout_display = f"{type_str}" + (f" | {layout_str}" if layout_str else "") if type_str else layout_str
        
        img_tag = f"<img src='{img_url}' loading='lazy' style='width:100%; height:120px; object-fit:cover; border-radius:8px; margin-bottom:8px;'>" if len(img_url) > 10 else ""
        links_block = f"""
            <div style='margin-top:10px; border-top:1px solid #ccc; padding-top:10px; display:flex; gap:15px;'>
                <a href='{web_link}' target='_blank' style='font-size:15px; font-weight:bold; color:#1976d2; text-decoration:none;'>👉 同行網頁</a>
                <a href='{transcript_url}' target='_blank' style='font-size:15px; font-weight:bold; color:#1976d2; text-decoration:none;'>📑 騰本連結</a>
            </div>
        """
        
        res_addr_html = f"👤 研判戶籍：{display_res_addr}<br>\n                " if display_res_addr != "待查閱" else ""

        popup_html = f"""
            {img_tag}
            <span style='font-size:18px; font-weight:bold; color:#111; margin-bottom:8px; display:block; line-height:1.3;'>{row['案件名稱']}</span>
            <div style='font-size:15px; color:#333; line-height:1.6;'>
                📍 推估地址：{display_text}<br>
                {res_addr_html}🏠 房型：{layout_display}<br>
                💰 <strong style='font-size:16px; color:#d32f2f;'>{row.get('售價(萬)','')} 萬</strong> | {row.get('總坪數','')}坪 | {row.get('樓層','')}/{row.get('總樓層','')}F
            </div>
            {links_block}
        """

        base_style = "display:flex;align-items:center;justify-content:center;border-radius:50%;border:3px solid white;box-shadow:0 0 10px rgba(0,0,0,0.5);color:white;font-weight:bold;"

        # --- 紅色物件標記 ---
        folium.Marker(
            location=house_loc,
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=display_text,
            icon=folium.DivIcon(html=f'<div style="{base_style}background-color:red;width:38px;height:38px;font-size:16px;">{"🏠" if count==0 else count}</div>', icon_anchor=(19, 19))
        ).add_to(marker_cluster)

        # --- 綠色戶籍標記 ---
        if not is_overlap and display_res_addr != "待查閱" and res_loc and res_loc[0] is not None:
            # 戶籍彈窗 HTML: 直接顯示完整的物件資料，標題改為合併顯示
            res_popup_html = f"""
                {img_tag}
                <span style='font-size:18px; font-weight:bold; color:#111; margin-bottom:8px; display:block; line-height:1.3;'>{row['案件名稱']}<span style='color:#28a745; font-size:16px;'>(屋主戶籍地)</span></span>
                <div style='font-size:15px; color:#333; line-height:1.6;'>
                    📍 推估地址：{display_text}<br>
                    {res_addr_html}🏠 房型：{layout_display}<br>
                    💰 <strong style='font-size:16px; color:#d32f2f;'>{row.get('售價(萬)','')} 萬</strong> | {row.get('總坪數','')}坪 | {row.get('樓層','')}/{row.get('總樓層','')}F
                </div>
                {links_block}
            """
            
            folium.Marker(
                location=res_loc,
                popup=folium.Popup(res_popup_html, max_width=300),
                tooltip=display_res_addr,
                icon=folium.DivIcon(html=f'<div style="{base_style}background-color:#28a745;width:38px;height:38px;font-size:16px;"><i class="fa fa-user"></i></div>', icon_anchor=(19, 19))
            ).add_to(marker_cluster)
            
        count_rendered += 1
            
    map_result = st_folium(m, width="stretch", height=700, key="image_map", returned_objects=["last_clicked"])

    end_time = time.time()
    st.markdown(f"""
    <div style='position: fixed; top: 15px; right: 15px; background-color: rgba(0,0,0,0.7); color: white; padding: 8px 15px; border-radius: 8px; z-index: 999999; font-weight: bold; font-size: 14px; box-shadow: 0 4px 6px rgba(0,0,0,0.3);'>
        ⏱️ 載入時間：{end_time - start_time:.2f} 秒<br>
        📍 顯示物件：{count_rendered} 筆<br>
        <span style="font-size:12px; color:#aaa;">💡 點擊地圖空白處可重新定位</span>
    </div>
    """, unsafe_allow_html=True)

