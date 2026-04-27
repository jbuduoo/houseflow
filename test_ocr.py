import base64
import io
import time
from playwright.sync_api import sync_playwright
from houseflow_registry_fetcher import get_ocr_reader, EXTRACT_JS

def test_ocr():
    print("啟動測試...")
    url = "https://app.houseflow.tw/HOUSE/Transcript/BuildingDialog/F33184602501000?HostId=2&A10OnLineId=2412717"
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        context = browser.contexts[0]
        page = context.new_page()
        
        try:
            page.goto(url, wait_until="load", timeout=45000)
            time.sleep(3)
            
            res = None
            for frame in page.frames:
                try:
                    res = frame.evaluate(EXTRACT_JS)
                    if res and (res.get("inputValue") or res.get("imgSrc")):
                        break
                except:
                    pass
            
            if res and res.get("imgSrc"):
                img_src = res["imgSrc"]
                print("成功擷取到 Base64 圖片。長度:", len(img_src))
                
                import numpy as np
                from PIL import Image, ImageEnhance, ImageOps

                _, b64 = img_src.split(",", 1)
                img_bytes = base64.b64decode(b64)
                img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
                
                # 儲存原始圖片
                img.save("ocr_sample_raw.png")
                print("已儲存原始圖片 ocr_sample_raw.png")
                
                # 進行影像前處理：灰階、放大、二值化或提升對比
                w, h = img.size
                # 放大倍率從 3 改為 4，並用更平滑的 LANCZOS
                img = img.resize((w * 4, h * 4), Image.LANCZOS)
                
                # 轉灰階
                img = ImageOps.grayscale(img)
                
                # 提升對比度
                enhancer = ImageEnhance.Contrast(img)
                img = enhancer.enhance(3.0)
                
                # 銳化
                enhancer = ImageEnhance.Sharpness(img)
                img = enhancer.enhance(2.0)
                
                img.save("ocr_sample_processed.png")
                print("已儲存處理後圖片 ocr_sample_processed.png")
                
                img_np = np.array(img)
                reader = get_ocr_reader()
                results = reader.readtext(
                    img_np,
                    detail=0,
                    paragraph=True
                )
                print("OCR 結果:", "".join(results))
            else:
                print("找不到該網址的圖片。")
        except Exception as e:
            print("錯誤:", e)
        finally:
            page.close()

if __name__ == "__main__":
    test_ocr()
