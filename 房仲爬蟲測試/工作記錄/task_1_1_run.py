import requests
import re
import time
from geopy.geocoders import Nominatim

def scrape_sinyi_coordinates(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            return None
        
        scripts = re.findall(r'<script[^>]*>(.*?)</script>', response.text, re.DOTALL)
        for script in scripts:
            if '"lat"' in script and '"lng"' in script:
                lats = re.findall(r'"lat"\s*:\s*(\d+\.\d+)', script)
                lngs = re.findall(r'"lng"\s*:\s*(\d+\.\d+)', script)
                if lats and lngs:
                    return f"{lats[0]},{lngs[0]}"
        return None
    except Exception:
        return None

def reverse_geocode(lat, lng):
    geolocator = Nominatim(user_agent="house_scraper_task_1_1")
    try:
        location = geolocator.reverse(f"{lat}, {lng}", language="zh-TW", timeout=10)
        if location:
            return location.address
        return "Address not found"
    except Exception as e:
        return f"Error: {str(e)}"

def main():
    urls = [
        "https://www.sinyi.com.tw/buy/house/0951DT?breadcrumb=list",
        "https://www.sinyi.com.tw/buy/house/6294NF?breadcrumb=list",
        "https://www.sinyi.com.tw/buy/house/1459QF?breadcrumb=list",
        "https://www.sinyi.com.tw/buy/house/8089GW?breadcrumb=list",
        "https://www.sinyi.com.tw/buy/house/1629JZ?breadcrumb=list"
    ]
    
    print("正在執行工作內容1.1...")
    results = []
    
    for url in urls:
        print(f"正在爬取: {url}")
        coords = scrape_sinyi_coordinates(url)
        if coords:
            lat, lng = coords.split(',')
            print(f"找到座標: {coords}，正在反查地址...")
            address = reverse_geocode(lat, lng)
            results.append((url, coords, address))
        else:
            print(f"無法找到座標: {url}")
            results.append((url, "N/A", "N/A"))
        
        # 遵循 Nominatim 政策，間隔至少 1 秒
        time.sleep(1.5)
    
    print("\n--- 任務完成 ---")
    header = "| 網址 | 座標 | 地址 |"
    separator = "| :--- | :--- | :--- |"
    
    output_lines = [header, separator]
    for url, coords, addr in results:
        coord_display = f"`{coords}`" if coords != "N/A" else "N/A"
        output_lines.append(f"| {url} | {coord_display} | {addr} |")
    
    result_text = "\n".join(output_lines)
    # 這裡仍然會打印到終端，但在這之後我們寫入檔案
    try:
        print(result_text)
    except UnicodeEncodeError:
        print("終端不支援 UTF-8，跳過打印，請查看結果檔案。")
    
    with open("task_1_1_results.md", "w", encoding="utf-8") as f:
        f.write(result_text)
    print(f"\n結果已存入 task_1_1_results.md")

if __name__ == "__main__":
    main()
