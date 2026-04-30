from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp('http://127.0.0.1:9222')
        context = browser.contexts[0]
        page = context.pages[0]
        
        # 不要重新導向，直接讀取目前的頁面，因為使用者已經登入
        # page.goto('https://app.houseflow.tw/HOUSE/ExploreCaseNew')
        
        try:
            page.wait_for_selector('.brandA', timeout=3000)
            htmls = page.evaluate('() => Array.from(document.querySelectorAll(".brandA")).map(e => e.outerHTML)')
            with open('scratch_brand_html.txt', 'w', encoding='utf-8') as f:
                f.write('\n\n=====\n\n'.join(htmls))
            print("成功寫入 scratch_brand_html.txt")
        except Exception as e:
            print("發生錯誤:", e)

if __name__ == '__main__':
    run()
