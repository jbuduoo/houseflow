from geopy.geocoders import Nominatim
from geopy.exc import GeocoderInsufficientPrivileges
import time

# 1. 複用 Nominatim 實體並使用更具唯一性的 User-Agent
UA = "HouseFlow_Taiwan_Scraper_9e46e488"
geolocator = Nominatim(user_agent=UA)

# 2. 實作座標快取，包含錯誤結果也進行短暫紀錄
address_cache = {}

def reverse_geocode(lat, lng):
    """
    將經緯度反查為地址，包含快取邏輯。
    回傳: (結果字串, 是否來自快取)
    """
    # 使用標準化的字串作為 key
    coord_key = f"{lat:.8f},{lng:.8f}"
    
    if coord_key in address_cache:
        return address_cache[coord_key], True
    
    try:
        # Nominatim reverse geocoding
        location = geolocator.reverse(f"{lat}, {lng}", language="zh-TW", timeout=10)
        if location:
            raw_addr = location.raw.get('address', {})
            
            # 依序精確挑選欄位
            district = raw_addr.get('town') or raw_addr.get('suburb') or raw_addr.get('city_district') or raw_addr.get('village') or ''
            road = raw_addr.get('road') or raw_addr.get('street') or ''
            house_number = raw_addr.get('house_number') or ''
            
            # 組合出標準的台灣地址格式 (不包含縣市)
            formatted_address = f"{district}{road}{house_number}"
            
            # 防呆機制：如果某些極端情況下抓不到詳細欄位，就退回使用系統預設的完整字串
            if len(formatted_address) < 4:
                formatted_address = location.address
                
            address_cache[coord_key] = formatted_address
            return formatted_address, False
        else:
            res = "Address not found"
            address_cache[coord_key] = res
            return res, False
            
    except GeocoderInsufficientPrivileges:
        res = "Error: 403 Forbidden"
        address_cache[coord_key] = res
        return res, False
    except Exception as e:
        res = f"Error: {str(e)}"
        address_cache[coord_key] = res
        return res, False
