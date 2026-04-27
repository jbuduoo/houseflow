import time
from playwright.sync_api import sync_playwright

def diagnose():
    with sync_playwright() as p:
        try:
            print("正在進行【全元素深度採樣 v3.1】...")
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            page = browser.contexts[0].pages[0]
            
            # 抓取所有可能是按鈕、連結、或圖片的東西
            info = page.evaluate(r"""() => {
                const samples = [];
                // 擴大搜索至 iframe
                const scan = (doc) => {
                    doc.querySelectorAll('a, button, img, area, td, span').forEach(el => {
                        const html = el.outerHTML;
                        if (html.includes('Map') || html.includes('house') || html.match(/\d{2,3}\.\d{4,}/)) {
                            samples.push({
                                tag: el.tagName,
                                html: html.substring(0, 300) 
                            });
                        }
                    });
                };

                scan(document);
                document.querySelectorAll('iframe').forEach(f => {
                    try { scan(f.contentDocument); } catch(e) {}
                });

                return samples;
            }""")
            
            print(f"\n🔍 採樣報告 (共抓到 {len(info)} 個疑似組件)：")
            for i, s in enumerate(info[:15]): 
                print(f"{i+1}. [{s['tag']}] HTML: {s['html']}")
                print("-" * 30)
            
        except Exception as e:
            print(f"診斷失敗: {e}")

if __name__ == "__main__":
    diagnose()
