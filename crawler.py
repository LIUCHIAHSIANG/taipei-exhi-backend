import requests
from bs4 import BeautifulSoup
import time

def start_crawling():
    print("🕸️ 爬蟲引擎啟動，正在前往藝文活動官網...")
    
    # 這裡以目標展覽網頁為例，實際 URL 請依據你的爬取目標更換
    target_url = "https://www.songshanculturalpark.org/exhibitions" 
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    scraped_data = []
    
    try:
        response = requests.get(target_url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"❌ 網頁請求失敗，狀態碼：{response.status_code}")
            return []
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 假設網頁上的展覽卡片外層標籤為 div.exhibition-item (請依據真實網頁結構調整 class)
        exhibition_cards = soup.select('.exhibition-item')
        
        if not exhibition_cards:
            # 備用防呆 mock 資料：確保如果官網改版沒抓到，至少有範例原料可以讓 Gemini 演示！
            print("⚠️ 未偵測到目標標籤，啟動擬真高品質活動原料進行動態展示...")
            return [
                {
                    "title": "100Y 山林有時",
                    "location": "台北松山文創園區",
                    "lat": 25.0438,
                    "lon": 121.5606,
                    "date": "2026/05/01 ~ 2026/06/30",
                    "full_text": "由農業部林業及自然保育署主辦。本展覽以時間之河為概念，全面梳理臺灣百年林業發展中經歷的四個關鍵『轉身』。現場不僅展示了珍貴的百年伐木老工具、歷史文獻紀錄，更引進了數位互動投影技術，重現臺灣山林從過去的資源開採到現代生態保育的演變歷程，帶領觀展民眾深刻反思下一個一百年，人類、科技與大自然之間該如何達成和諧共存的依存關係。"
                }
            ]

        for card in exhibition_cards:
            try:
                title = card.select_one('.title').text.strip() if card.select_one('.title') else "未命名展覽"
                location = card.select_one('.location').text.strip() if card.select_one('.location') else "雙北展覽館"
                
                # 🌟 重點：爬蟲必須把該活動頁面裡，所有介紹展覽細節的段落文字全部抓下來合併
                paragraphs = card.select('.description-p, p')
                full_text = " ".join([p.text.strip() for p in paragraphs if p.text.strip()])
                
                # 如果抓下來的內文太短，給個防呆字樣
                if len(full_text) < 20:
                    full_text = f"本展覽位於{location}展出，主題為{title}，歡迎民眾前往共襄盛舉。"

                item = {
                    "title": title,
                    "location": location,
                    "lat": 25.0438,  # 定位通常由各展場固定經緯度對照表提供，此處以松菸為例
                    "lon": 121.5606,
                    "date": "2026 展期",
                    "full_text": full_text  # 🌟 這個就是餵給 Gemini 吃的「純天然原料」
                }
                scraped_data.append(item)
                
            except Exception as card_err:
                print(f"⚠️ 單筆資料解析跳過: {str(card_err)}")
                continue
                
        return scraped_data

    except Exception as e:
        print(f"❌ 爬蟲核心發生崩潰: {str(e)}")
        return []

if __name__ == "__main__":
    # 本地測試用
    test_res = start_crawling()
    print(test_res)