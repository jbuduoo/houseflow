import os
import importlib.util

_base_dir = os.path.dirname(os.path.abspath(__file__))

def run_coords_enricher():
    """
    座標補完四部曲指揮中心 (安全循序版)：
    依序執行 5a, 5b, 5c, 5d。
    """
    print("\n" + "★"*60)
    print("【座標補完四部曲 - 旗艦工作流啟動 🛡️】")
    print("★"*60)

    try:
        # 1. 執行信義爬取 (5a)
        print("\n>>> [第一階段] 啟動信義房屋座標特攻隊 (5a)...")
        spec_5a = importlib.util.spec_from_file_location("5a_sinyi", os.path.join(_base_dir, "5a_sinyi.py"))
        mod_5a = importlib.util.module_from_spec(spec_5a)
        spec_5a.loader.exec_module(mod_5a)
        mod_5a.run_sinyi_task()

        # 2. 執行永慶爬取 (5b)
        print("\n>>> [第二階段] 啟動永慶房屋座標特攻隊 (5b)...")
        spec_5b = importlib.util.spec_from_file_location("5b_yungching", os.path.join(_base_dir, "5b_yungching.py"))
        mod_5b = importlib.util.module_from_spec(spec_5b)
        spec_5b.loader.exec_module(mod_5b)
        is_blocked = mod_5b.run_yungching_coords_task()
        if is_blocked:
            print("\n⚠️ 偵測到永慶封鎖，已跳過剩餘永慶物件。繼續後續任務...")

        # 3. 執行其他仲介爬取 (5c)
        print("\n>>> [第三階段] 啟動其他仲介通用掃描 (5c)...")
        spec_5c = importlib.util.spec_from_file_location("5c_others", os.path.join(_base_dir, "5c_others.py"))
        mod_5c = importlib.util.module_from_spec(spec_5c)
        spec_5c.loader.exec_module(mod_5c)
        mod_5c.run_others_task()

        # 4. 執行 ArcGIS 補救 (5d)
        print("\n>>> [第四階段] 啟動 ArcGIS 門牌定位補救 (5d)...")
        spec_5d = importlib.util.spec_from_file_location("5d_arcgis", os.path.join(_base_dir, "5d_arcgis.py"))
        mod_5d = importlib.util.module_from_spec(spec_5d)
        spec_5d.loader.exec_module(mod_5d)
        mod_5d.run_arcgis_task()

        print("\n" + "★"*60)
        print("🎉 座標補完四部曲任務全部執行完畢！")
        print("★"*60)

    except KeyboardInterrupt:
        print("\n🛑 使用者中斷任務 (Ctrl+C)。")
    except Exception as e:
        print(f"❌ 執行任務時發生錯誤: {e}")

if __name__ == "__main__":
    run_coords_enricher()
