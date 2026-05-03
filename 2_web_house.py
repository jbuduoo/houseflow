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
            st.rerun()

    st.stop()


if True:
    c_lat, c_lng = st.session_state['map_center']


    # 以 session_state 內的中心點建立地圖
    m = folium.Map(location=[c_lat, c_lng], zoom_start=18, min_zoom=18, max_zoom=18, tiles="OpenStreetMap")
    
    # 修改定位按鈕圖示與顏色
    plugins.LocateControl(
        auto_start=False, 
        icon='fa-solid fa-location-arrow',
        iconLoading='fa-solid fa-spinner fa-spin',
        flyTo=True,
        zoom=19
    ).add_to(m)
    
    # 載入 FontAwesome 6 且加上圖示的自訂顏色 CSS
    from folium import Element
    m.get_root().html.add_child(Element('''
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
        <style>
            .fa-location-arrow { color: rgb(116, 192, 252) !important; font-size: 24px !important; }
        </style>
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
        jitter_lat = random.uniform(-0.001, 0.001)
        jitter_lng = random.uniform(-0.001, 0.001)
        final_lat = h_lat + jitter_lat
        final_lng = h_lng + jitter_lng
        
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
                    {res_addr_html}🏠 房型：{layout_display}<br>
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
            
        # 畫出紅色物件標記
        folium.Marker(
            location=[final_lat, final_lng],
            popup=folium.Popup(combined_popup_html, max_width=320),
            icon=folium.DivIcon(html=f'<div style="{base_style}background-color:red;width:38px;height:38px;font-size:16px;">{marker_text}</div>', icon_anchor=(19, 19))
        ).add_to(marker_group)

        # 畫出綠色戶籍標記
        for res in res_locations:
            res_lat = res["loc"][0] + random.uniform(-0.001, 0.001)
            res_lng = res["loc"][1] + random.uniform(-0.001, 0.001)
            folium.Marker(
                location=[res_lat, res_lng],
                popup=folium.Popup(res["html"], max_width=300),
                icon=folium.DivIcon(html=f'<div style="{base_style}background-color:#28a745;width:38px;height:38px;font-size:16px;"><i class="fa fa-user"></i></div>', icon_anchor=(19, 19))
            ).add_to(marker_group)


    st_folium(m, width="stretch", height=700, key="image_map", returned_objects=[])

    end_time = time.time()
    st.markdown(f"""
    <div style='position: fixed; top: 15px; right: 15px; background-color: rgba(0,0,0,0.7); color: white; padding: 8px 15px; border-radius: 8px; z-index: 999999; font-weight: bold; font-size: 14px; box-shadow: 0 4px 6px rgba(0,0,0,0.3);'>
        ⏱️ 載入時間：{end_time - start_time:.2f} 秒<br>
        📍 顯示物件：{count_rendered} 筆<br>
        <span style="font-size:12px; color:#aaa;">💡 使用左上角 🎯 按鈕定位至當前位置</span>
    </div>
    """, unsafe_allow_html=True)

