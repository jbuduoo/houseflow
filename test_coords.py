import requests
import re

def test_sinyi():
    url = 'https://www.sinyi.com.tw/buy/house/0951DT'
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    r = requests.get(url, headers=headers)
    html = r.text
    print('Sinyi length:', len(html))
    
    # regex to find coordinate near something meaningful or just all lats
    lats = re.findall(r'2[2-5]\.\d{4,}', html)
    lons = re.findall(r'12[0-2]\.\d{4,}', html)
    
    print('Sinyi lats:', set(lats))
    print('Sinyi lons:', set(lons))

def test_yungching():
    url = 'https://buy.yungching.com.tw/house/5607834'
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    r = requests.get(url, headers=headers)
    html = r.text
    print('Yungching length:', len(html))
    
    lats = re.findall(r'2[2-5]\.\d{4,}', html)
    lons = re.findall(r'12[0-2]\.\d{4,}', html)
    
    print('Yungching lats:', set(lats))
    print('Yungching lons:', set(lons))

if __name__ == '__main__':
    test_sinyi()
    test_yungching()
