import requests
import re
import os
import time

def scrape_sinyi_coordinates(url):
    """
    爬取信義房屋網址的經緯度。
    優先使用 Google Maps 連結提取，備援使用 script 標籤提取。
    """
    # Fix malformed URLs (e.g., ttps instead of https)
    if url.startswith('ttps://'):
        url = 'h' + url
    elif not url.startswith('http'):
        url = 'https://' + url
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            return url, f"Error: Status Code {response.status_code}"
        
        # Method 1: Search for Google Maps place link (Task 1.2 method)
        # Pattern: https://www.google.com.tw/maps/place/25.002787,121.520065
        map_match = re.search(r'https?://www\.google\.com(?:\.tw)?/maps/place/([\d.]+,[\d.]+)', response.text)
        if map_match:
            return url, map_match.group(1)
            
        # Method 2 (Fallback): Search for coordinates in script tags
        scripts = re.findall(r'<script[^>]*>(.*?)</script>', response.text, re.DOTALL)
        for script in scripts:
            if '"lat"' in script and '"lng"' in script:
                lats = re.findall(r'"lat"\s*:\s*(\d+\.\d+)', script)
                lngs = re.findall(r'"lng"\s*:\s*(\d+\.\d+)', script)
                if lats and lngs:
                    return url, f"{lats[0]},{lngs[0]}"
        
        return url, "Coordinates not found"
    except Exception as e:
        return url, f"Error: {str(e)}"
