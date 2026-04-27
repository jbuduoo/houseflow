import urllib.request, json, urllib.parse
url = 'https://nominatim.openstreetmap.org/search?q=' + urllib.parse.quote('新北市永和區中山路一段') + '&format=json&limit=1'
req = urllib.request.Request(url, headers={'User-Agent': 'HouseFlowApp/1.0'})
try:
    resp = urllib.request.urlopen(req)
    data = json.loads(resp.read().decode())
    with open('nom_result.txt', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
except Exception as e:
    with open('nom_result.txt', 'w') as f:
        f.write(str(e))
