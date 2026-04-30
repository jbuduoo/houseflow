import os
from urllib.parse import urlparse

def get_company_name(domain):
    mapping = {
        'www.hbhousing.com.tw': '住商不動產',
        'hbhousing.com.tw': '住商不動產',
        'www.sinyi.com.tw': '信義房屋',
        'sinyi.com.tw': '信義房屋',
        'buy.yungching.com.tw': '永慶房屋',
        'yungching.com.tw': '永慶房屋',
        'www.yungching.com.tw': '永慶房屋',
        'sale.591.com.tw': '591房屋交易',
        'www.591.com.tw': '591房屋交易',
        '591.com.tw': '591房屋交易',
        'buy.houseprice.tw': '實價登錄比價王',
        'houseprice.tw': '實價登錄比價王',
        'buy.housefun.com.tw': '好房網',
        'housefun.com.tw': '好房網',
        'buy.u-trust.com.tw': '有巢氏房屋',
        'u-trust.com.tw': '有巢氏房屋',
        'www.rakuya.com.tw': '樂屋網',
        'rakuya.com.tw': '樂屋網',
        'www.pacific.com.tw': '太平洋房屋',
        'pacific.com.tw': '太平洋房屋',
        'www.cthouse.com.tw': '中信房屋',
        'cthouse.com.tw': '中信房屋',
        'www.greathome.com.tw': '大家房屋',
        'greathome.com.tw': '大家房屋',
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

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    # Candidate files, prioritizing the main one if it's not empty
    candidates = ["名單2.md", "名單2_recovered.md"]
    input_file = None
    
    for c in candidates:
        path = os.path.join(base_dir, c)
        if os.path.exists(path) and os.path.getsize(path) > 0:
            input_file = path
            break
            
    if not input_file:
        # If all are empty but exist, just take the first one to show the error
        input_file = os.path.join(base_dir, "名單2.md")
        if not os.path.exists(input_file):
            print(f"找不到檔案: {input_file}")
            return
            
    output_file = os.path.join(base_dir, "domain_mapping.txt")


        
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        with open(input_file, 'r', encoding='cp950') as f:
            lines = f.readlines()
            
    domains = set()
    for line in lines:
        line = line.strip()
        if not line or not line.startswith('http'):
            continue
            
        # Extract domain
        parsed = urlparse(line)
        if parsed.netloc:
            # Reconstruct domain with protocol
            domain_url = f"{parsed.scheme}://{parsed.netloc}/"
            domains.add(domain_url)
            
    results = []
    for domain_url in sorted(list(domains)):
        parsed = urlparse(domain_url)
        company = get_company_name(parsed.netloc)
        results.append(f"{domain_url} > {company}")
        
    with open(output_file, 'w', encoding='utf-8') as f:
        for res in results:
            f.write(res + "\n")
            print(res)
            
    print(f"\n整理完成，共 {len(results)} 個不重複網域。結果已存入 {output_file}")

if __name__ == "__main__":
    main()
