import re
import urllib.request
import urllib.parse
import json

def clean_address(raw_addr):
    addr = str(raw_addr).strip()
    if not addr or addr in ["", "查無", "解析失敗", "待查閱"]:
        return ""
    addr = addr.split('(')[0]
    addr = re.sub(r'(?<=[區鄉鎮市])[^區鄉鎮市里]+里', '', addr)
    addr = re.sub(r'[0-9０-９]{1,3}鄰', '', addr)
    addr = re.sub(r'號.*', '號', addr)
    addr = re.sub(r'[0-9０-９一二三四五六七八九十百]+樓.*', '', addr)
    return addr.replace(' ', '')

def test_geocode(address):
    if not address: return "N/A"
    url = f"https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates?f=json&singleLine={urllib.parse.quote(address)}&outFields=Match_addr"
    req = urllib.request.Request(url, headers={'User-Agent': 'HouseFlow/4.0'})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            if "candidates" in data and len(data["candidates"]) > 0:
                score = data["candidates"][0]["score"]
                match_addr = data["candidates"][0]["address"]
                return f"[成功] 分數:{score} -> 判定:{match_addr}"
            return "[失敗] 找不到座標"
    except Exception as e:
        return f"[錯誤] {e}"

test_cases = [
    "新北市永和區中山路一段１０６號四樓之二(多筆)",
    "新北市永和區前溪里12鄰中山路一段133號四樓之二", 
    "台北市信義區信義路五段7號89樓", 
    "新北市中和區景平路258號(多筆)",
    "新北市新店區安康里1鄰安康路二段159巷2號5樓", 
    "新北市永和區得和里成功路二段100號",
    "桃園市桃園區同安街336巷(疑似)"
]

lines = []
lines.append("="*90)
lines.append(f"{'原始複雜地址':<30} | {'正規化推算地址':<25} | {'ArcGIS 衛星回報結果'}")
lines.append("="*90)

for raw in test_cases:
    cleaned = clean_address(raw)
    result = test_geocode(cleaned)
    raw_pad = raw + " "*(35 - len(raw.encode('big5', 'ignore')))
    cln_pad = cleaned + " "*(28 - len(cleaned.encode('big5', 'ignore')))
    lines.append(f"{raw_pad} | {cln_pad} | {result}")

with open('test_address_result.txt', 'w', encoding='utf-8') as f:
    f.write("\n".join(lines))
