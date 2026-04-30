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
    print("【住通自動化地產開發總管 - Master Pipeline v2】")
    print("★" * 60)

    print("  [1] 🔍 採集物件 (1_house.py)")
    print("  [2] 🗑️ 去除重複 ID (2_deduplicate.py)")
    print("  [3] 📍 地址補完 (3_address.py)")
    print("  [4] 🏠 戶籍/座標擷取 (4_registry.py)")
    print("  [5] 🗺️ 補齊座標 1.取得信義座標 2.取得的地址及戶籍地址沒有座標的物件 (5_coords.py)")
    print("  [6] 📍 地址補完 (座標反查) (6_reverse_geocode.py)")
    print("  [7] 🤖 AI 綜合研判 (7_smart_analysis.py)")
    print("  [0] ⚡ 全部依序執行 (1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7)")

    try:
        user_input = input("\n請輸入功能編號: ").strip()
        if not user_input:
            print("❌ 未輸入任何選項，程式結束。")
            return

        # 處理輸入選項
        if "0" in user_input.split():
            selected_tasks = ["1", "2", "3", "4", "5", "6", "7"]
        else:
            selected_tasks = user_input.split()

        total_start_time = time.time()

        for task in selected_tasks:
            task_start = time.time()
            if task == "1":
                print("\n>>> [執行功能 1] 啟動地圖採集程式 (1_house.py)...")
                house_module = import_script("core/1_house.py")
                house_module.run_map_scraper()

            elif task == "2":
                print("\n>>> [執行功能 2] 啟動去除重複 ID 程式 (2_deduplicate.py)...")
                dedup_module = import_script("core/2_deduplicate.py")
                # utils_deduplicate.py 執行時不跳過確認，依原設計
                try:
                    dedup_module.run_deduplicator()
                except TypeError:
                    # 如果 run_deduplicator 沒有參數
                    dedup_module.run_deduplicator()

            elif task == "3":
                print("\n>>> [執行功能 3] 啟動地址補完程序 (3_address.py)...")
                addr_module = import_script("core/3_address.py")
                addr_module.run_enricher()

            elif task == "4":
                print("\n>>> [執行功能 4] 啟動戶籍與座標補完 (4_registry.py)...")
                reg_module = import_script("core/4_registry.py")
                reg_module.run_fetcher()

            elif task == "5":
                print("\n>>> [執行功能 5] 啟動純補座標 (5_coords.py)...")
                coords_module = import_script("core/5_coords.py")
                coords_module.run_coords_enricher()

            elif task == "6":
                print("\n>>> [執行功能 6] 啟動座標反查地址 (6_reverse_geocode.py)...")
                rev_geo_module = import_script("core/6_reverse_geocode.py")
                rev_geo_module.run_reverse_geocoder()

            elif task == "7":
                print("\n>>> [執行功能 7] 啟動 AI 綜合研判 (7_smart_analysis.py)...")
                analysis_module = import_script("core/7_smart_analysis.py")
                analysis_module.run_smart_analysis()

            else:
                print(f"\n⚠️ 未知的功能編號 '{task}'，已跳過。")
                continue
            
            task_end = time.time()
            print(f"✅ 功能 {task} 執行完畢，耗時: {task_end - task_start:.1f} 秒")
            time.sleep(1)

        total_end_time = time.time()
        print("\n" + "★" * 60)
        print(f"🎉 恭喜！選定任務全部執行完畢！總耗時: {total_end_time - total_start_time:.1f} 秒")
        print("★" * 60)

    except KeyboardInterrupt:
        print("\n\n🛑 使用者中斷任務。")
    except Exception as e:
        print(f"\n\n❌ 執行過程中發生錯誤: {e}")

if __name__ == "__main__":
    main()
