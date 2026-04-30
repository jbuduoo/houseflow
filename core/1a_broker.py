import os
from urllib.parse import urlparse

def get_company_name(domain):
    """
    根據網域識別房仲公司名稱。
    """
    mapping = {
        'www.hbhousing.com.tw': '住商',
        'hbhousing.com.tw': '住商',
        'www.sinyi.com.tw': '信義',
        'sinyi.com.tw': '信義',
        'buy.yungching.com.tw': '永慶',
        'yungching.com.tw': '永慶',
        'www.yungching.com.tw': '永慶',
        'sale.591.com.tw': '591',
        'www.591.com.tw': '591',
        '591.com.tw': '591',
        'buy.houseprice.tw': '比價王',
        'houseprice.tw': '比價王',
        'buy.housefun.com.tw': '好房網',
        'housefun.com.tw': '好房網',
        'buy.u-trust.com.tw': '有巢氏',
        'u-trust.com.tw': '有巢氏',
        'www.rakuya.com.tw': '樂屋網',
        'rakuya.com.tw': '樂屋網',
        'www.pacific.com.tw': '太平洋',
        'pacific.com.tw': '太平洋',
        'www.cthouse.com.tw': '中信',
        'cthouse.com.tw': '中信',
        'www.greathome.com.tw': '大家',
        'greathome.com.tw': '大家',
        'www.twhg.com.tw': '台灣房屋',
        'twhg.com.tw': '台灣房屋',
    }
    
    # Try exact match
    if domain in mapping:
        return mapping[domain]
    
    # Try subdomains match
    for k, v in mapping.items():
        if domain.endswith(k):
            return v
            
    return "未知公司"

def extract_domain(url):
    """
    從網址中提取網域。
    """
    parsed = urlparse(url)
    return parsed.netloc
