import sys
import time
import importlib.util
import os

def import_script(file_path):
    """特殊的 import 方法，支援以數字開頭的檔案名"""
    module_name = os.path.basename(file_path).replace(".py", "")
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def main():
    print("\n" + "★" * 60)
    print("【住通自動化地產開發總管 - Master Pipeline】")
    print("★" * 60)

    try:
        # 1. 執行採集
        print("\n>>> [階段 1/3] 啟動地圖採集程式 (1_house.py)...")
        house_module = import_script("core/1_house.py")
        house_module.run_map_scraper()
        
        # 2. 執行地址補完
        print("\n>>> [階段 2/3] 採集完成，正在自動啟動地址補完程序 (2_address.py)...")
        time.sleep(2)
        addr_module = import_script("core/2_address.py")
        addr_module.run_enricher()
        
        # 3. 執行戶籍與座標補完
        print("\n>>> [階段 3/3] 地址補完完成，正在啟動最終戶籍與座標補完 (3_registry.py)...")
        time.sleep(2)
        reg_module = import_script("core/3_registry.py")
        reg_module.run_fetcher()

        print("\n" + "★" * 60)
        print("🎉 恭喜！流水線任務全部執行完畢！資料已完美填充。")
        print("★" * 60)

    except KeyboardInterrupt:
        print("\n\n🛑 使用者中斷任務。")
    except Exception as e:
        print(f"\n\n❌ 執行過程中發生錯誤: {e}")

if __name__ == "__main__":
    main()
