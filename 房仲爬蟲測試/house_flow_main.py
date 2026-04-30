import os
import time
import re
from core.sinyi import scrape_sinyi_coordinates
from core.geocoder import reverse_geocode
from core.utils import get_company_name, extract_domain

def main():
    print("=== HouseFlow Property Data Automation ===")
    
    # 1. 讀取名單
    input_file = "名單.md"
    if not os.path.exists(input_file):
        # 嘗試找不同副檔名
        for ext in [".md", ".txt", ""]:
            if os.path.exists("名單" + ext):
                input_file = "名單" + ext
                break
    
    if not os.path.exists(input_file):
        print(f"錯誤：找不到名單檔案")
        return

    print(f"正在讀取名單：{input_file}")
    urls = []
    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # 提取網址部分
            url_match = re.search(r'https?://[^\s]+', line)
            if url_match:
                url = url_match.group(0)
                # 檢查是否在支援的網域中
                domain = extract_domain(url)
                if get_company_name(domain) != "未知公司":
                    urls.append(url)

    if not urls:
        print("未在檔案中找到任何有效的信義網址。")
        print("未在檔案中找到任何有效的網址。")
        return

    final_results = []

    # 2. 開始處理流程 (組合工具)
    for i, url in enumerate(urls, 1):
        domain = extract_domain(url)
        company = get_company_name(domain)
        
        print(f"\n[{i}/{len(urls)}] 處理中: {company} ({url})")
        
        # 目前僅支援信義的座標爬取
        if company != "信義":
            print(f"  [Skip] 目前尚未支援 {company} 的座標爬取。")
            continue
            
        # --- 工具 1: 爬取經緯度 (來自 sinyi) ---
        _, coords = scrape_sinyi_coordinates(url)
        
        if "Error" in coords or "not found" in coords:
            print(f"  [Error] Failed to scrape: {coords}")
            continue
        
        print(f"  [Location] Coordinates: {coords}")
        
        # --- 工具 2: 反查地址 (來自 reverse_geocode_test) ---
        try:
            lat, lng = map(float, coords.split(","))
            address, was_cached = reverse_geocode(lat, lng)
            
            source = "[快取]" if was_cached else "[API]"
            print(f"  [Address] {source}: {address}")
            
            final_results.append({
                "url": url,
                "company": company,
                "coords": coords,
                "address": address
            })
            
            # 禮貌延遲 (只有真正請求 API 時才等待)
            if not was_cached:
                time.sleep(1.2)
        except Exception as e:
            print(f"  [Error] Geocoding error: {e}")

    # 3. 輸出整合報表
    output_report = "最終整合報表.md"
    with open(output_report, "w", encoding="utf-8") as f:
        f.write("# 🏠 房仲資料整合執行報表 (自動化產出)\n\n")
        f.write(f"- **產出時間**：{time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"- **處理數量**：{len(final_results)} 筆\n\n")
        f.write("| 序號 | 來源公司 | 原始網址 | 經緯度 | 反查物理地址 |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- |\n")
        for i, item in enumerate(final_results, 1):
            f.write(f"| {i} | {item['company']} | [連結]({item['url']}) | `{item['coords']}` | {item['address']} |\n")
    
    print(f"\n" + "="*30)
    print(f"DONE! Process completed.")
    print(f"Report generated: {output_report}")
    print("="*30)

if __name__ == "__main__":
    main()
