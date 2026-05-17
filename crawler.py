import datetime
import time

def start_crawling():
    print("🤖 模擬爬蟲啟動：正在前往各大網站抓取資料...")
    time.sleep(2) # 假裝爬蟲運作花了 2 秒鐘
    
    # 抓取當下的時間，這樣你才知道是哪一次觸發的
    current_time = datetime.datetime.now().strftime('%m/%d %H:%M:%S')
    
    # 建立一筆「假」的展覽資料，完全符合你的前端規格
    fake_data = [
        {
            "title": f"⏱️ 自動化測試展覽 ({current_time})",
            "status": "現在",
            "category": "科技",
            "price": 0,
            "location": "雲端測試展館",
            "address": "台北市虛擬路1段1號",
            "lat": 25.0330,
            "lon": 121.5654,
            "description": f"如果你在網頁上看到這張卡片，代表你的 cron-job 排程與自動化更新已經完美運作！(更新時間: {current_time})"
        }
    ]
    
    print("✅ 模擬爬蟲抓取完畢！")
    return fake_data