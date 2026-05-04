
from geopy.geocoders import Nominatim
import time

UA = "HouseFlow_Taiwan_Scraper_9e46e488"
geolocator = Nominatim(user_agent=UA)

def reverse_geocode(lat, lng):
    try:
        location = geolocator.reverse(f"{lat}, {lng}", language="zh-TW", timeout=10)
        if location:
            return location.address
    except Exception as e:
        return str(e)
    return "Not found"

# ArcGIS coords
lat, lng = 25.000293983612, 121.508823987799
print(f"Coords: {lat}, {lng}")
print(f"OSM Reverse: {reverse_geocode(lat, lng)}")
