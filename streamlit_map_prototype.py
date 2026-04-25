import streamlit as st
import pandas as pd
import folium
from folium import plugins
from streamlit_folium import st_folium
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# --- 設定頁面資訊 ---
st.set_page_config(page_title="房仲攻堅地圖 (實景排版版)", layout="wide")

# --- 0. 注入自定義 CSS ---
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
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
        max-height: 150px;
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
    </style>
""", unsafe_allow_html=True)

# --- 1. Google Sheets 連線 ---
SHEET_KEY = "1bU4BKbjQgnoNqSK50G4vHgMGBFetHsBrbMyHv2Xc2k0"
CREDS_FILE = "houseflow_gheet_key.json.json"

@st.cache_resource
def get_gspread_client():
    scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, scope)
    return gspread.authorize(creds)

def load_data_from_gsheet():
    client = get_gspread_client()
    sheet = client.open_by_key(SHEET_KEY).sheet1
    data = sheet.get_all_records()
    return pd.DataFrame(data), sheet

# --- 2. 主程式流程 ---
df_raw, sheet_obj = load_data_from_gsheet()
df = df_raw.copy()

visit_counts = {}
log_path = os.path.join(os.path.dirname(__file__), "houseflow_visit_logs.csv")
if os.path.exists(log_path):
    logs_all = pd.read_csv(log_path)
    visit_counts = logs_all['物件ID'].astype(str).value_counts().to_dict()

tab1, tab2 = st.tabs(["📍 攻堅地圖", "📋 全員工作清單"])

with tab1:
    m = folium.Map(location=[25.006, 121.520], zoom_start=16, tiles="OpenStreetMap")
    plugins.LocateControl(auto_start=False).add_to(m)

    map_id = m.get_name()
    jump_script = f"<script>function jumpTo(lat, lon) {{ var map = {map_id}; map.flyTo([lat, lon], 18); }}</script>"
    m.get_root().html.add_child(folium.Element(jump_script))

    for index, row in df.iterrows():
        try:
            house_loc = [float(row['物件緯度']), float(row['物件經度'])]
            res_loc = [float(row['戶籍緯度']), float(row['戶籍經度'])]
        except: continue
        
        count = visit_counts.get(str(row['ID']), 0)
        is_overlap = (abs(house_loc[0] - res_loc[0]) < 0.0001 and abs(house_loc[1] - res_loc[1]) < 0.0001)

        display_obj_addr = str(row['物件地址']) if str(row['物件地址']) != '' else str(row['比對地址'])
        display_res_addr = str(row['戶籍地址']) if str(row['戶籍地址']) != '' else "待查閱"
        img_url = str(row.get('案件首圖', ''))
        transcript_url = str(row.get('騰本連結', ''))
        history_url = str(row.get('刊登歷史', ''))
        web_link = str(row['網頁連結'])
        
        suffix = " (多筆)" if int(row.get('案件數量', 1)) > 1 else ""
        display_text = f"{display_obj_addr.replace('新北市','')}{suffix}"
        
        # --- 構建彈窗 HTML ---
        img_tag = f"<img src='{img_url}' class='popup-img'>" if len(img_url) > 10 else ""
        links_block = f"""
            <div class='popup-links'>
                <a href='{web_link}' target='_blank'>🏠 同行網頁</a>
                <a href='{history_url}' target='_blank'>⏳ 歷史紀錄</a>
                <a href='{transcript_url}' target='_blank'>📄 騰本連結</a>
            </div>
        """
        
        popup_html = f"""
            {img_tag}
            <span class='popup-title'>{row['案件名稱']} (ID:{row['ID']})</span>
            <div style='font-size:13px; color:#555;'>
                📍 物件：{display_text}<br>
                👤 戶籍：{display_res_addr}<br>
                💰 {row['售價(萬)']}萬 | {row['總坪數']}坪 | {row['樓層']}/{row['總樓層']}F<br>
                🕒 更新：{str(row['更新時間'])}
            </div>
            {links_block}
        """

        base_style = "display:flex;align-items:center;justify-content:center;border-radius:50%;border:3px solid white;box-shadow:0 0 10px rgba(0,0,0,0.5);color:white;font-weight:bold;"
        
        # 紅點
        folium.Marker(
            location=house_loc,
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"{row['案件名稱']}",
            icon=folium.DivIcon(html=f'<div style="{base_style}background-color:red;width:42px;height:42px;font-size:18px;">{"🏠" if count==0 else count}</div>', icon_anchor=(21, 21))
        ).add_to(m)

        # 綠點
        if not is_overlap and display_res_addr != "待查閱":
            folium.Marker(
                location=res_loc,
                popup=folium.Popup(f"{img_tag}<b class='popup-title'>👤 屋主戶籍地</b>📍 物件：{display_text}<br>👤 戶籍：{display_res_addr}<br><a href='javascript:void(0);' onclick='parent.jumpTo({house_loc[0]}, {house_loc[1]})' class='jump-btn'>🏠 回物件位置</a>", max_width=300),
                tooltip=f"屋主戶籍 (ID:{row['ID']})",
                icon=folium.DivIcon(html=f'<div style="{base_style}background-color:#28a745;width:38px;height:38px;font-size:18px;"><i class="fa fa-user"></i></div>', icon_anchor=(19, 19))
            ).add_to(m)
            folium.PolyLine([house_loc, res_loc], color="gray", weight=2, opacity=0.5, dash_array='8').add_to(m)

    st_folium(m, width="100%", height=700, use_container_width=True, key="image_map")

with st.sidebar:
    st.header("📲 實戰回報")
    target_id = st.text_input("輸入 ID 進度更新")
    if target_id:
        row_idx = df_raw.index[df_raw['ID'].astype(str) == str(target_id)].tolist()
        if row_idx:
            idx = row_idx[0]; tr = df_raw.iloc[idx]
            st.info(f"📍 {tr['案件名稱']}")
            with st.form("r"):
                note = st.text_area("本次回報內容")
                if st.form_submit_button("同步雲端"):
                    # 修整欄位：拜訪紀錄位於第 22 欄 (23 cols total)
                    sheet_obj.update_cell(idx + 2, 22, note) 
                    st.success("同步成功！")
                    st.rerun()

with tab2:
    st.dataframe(df_raw, use_container_width=True, height=600)
