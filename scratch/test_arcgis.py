
import urllib.request
import urllib.parse
import json

def get_arcgis_coordinates(address):
    url = f"https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates?f=json&singleLine={urllib.parse.quote(address)}&outFields=Match_addr"
    req = urllib.request.Request(url, headers={'User-Agent': 'HouseFlowApp/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            if "candidates" in data and len(data["candidates"]) > 0:
                loc = data["candidates"][0]["location"]
                return str(loc["y"]), str(loc["x"]) # y=lat, x=lon
    except Exception as e:
        return str(e), ""
    return "Not found", ""

addr = "永和區中和路399號"
lat, lon = get_arcgis_coordinates(addr)
print(f"Address: {addr}")
print(f"ArcGIS Coords: {lat}, {lon}")
