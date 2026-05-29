import requests
from bs4 import BeautifulSoup
from geopy.geocoders import Nominatim
import urllib3
import re
import time

# 忽略不安全的 SSL 連線警告
urllib3.disable_warnings()

# 設定 HTTP 請求標頭
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "zh-TW,zh;q=0.9"
}

# 目標抓取的展覽網站清單 (示範縮減版，可自行加回原本所有的網址)
URLS = [
    "https://www.tainex.com.tw/event",
    "https://www.huashan1914.com/w/huashan1914/exhibition",
    "https://www.songshanculturalpark.org/exhibition",
    "https://www.npm.gov.tw/Exhibition-Current.aspx?sno=03000060&l=1"
]

FILTER_WORDS = [
    "首頁", "找活動", "全球資訊網", "網站導覽", "最新消息", "最新展覽",
    "檔期表", "當期展覽", "自辦展覽", "展演計畫", "常設展"
]

# 宣告地圖 API
geolocator = Nominatim(user_agent="exhibition_project_v3")

def get_coordinates(location):
    """將地址轉為經緯度 (加上延時防封鎖)"""
    preset_locations = {
        "台北南港展覽館1館": (25.05696, 121.6167),
        "台北南港展覽館2館": (25.05904, 121.6142),
        "華山1914文化創意園區": (25.04416, 121.5294),
        "松山文創園區": (25.04375, 121.5606),
        "國立故宮博物院": (25.10231, 121.5485)
    }
    
    if location in preset_locations:
        return preset_locations[location]
        
    try:
        time.sleep(1) # 防封鎖機制
        result = geolocator.geocode(location)
        if result:
            return (result.latitude, result.longitude)
    except:
        pass
    return None, None

def get_location(title):
    if any(x in title for x in ["龍藏經", "乾隆", "紅樓夢"]):
        return "國立故宮博物院"
    elif "華山" in title:
        return "華山1914文化創意園區"
    elif "松山" in title or "松菸" in title:
        return "松山文創園區"
    elif "南港" in title:
        return "台北南港展覽館1館"
    return "台北市"

def get_dates(text):
    pattern = r'\d{4}[./-]\d{1,2}[./-]\d{1,2}'
    dates = re.findall(pattern, text)
    if len(dates) >= 2:
        return dates[0], dates[1]
    elif len(dates) == 1:
        return dates[0], None
    return None, None

def get_time(text):
    pattern = r'\d{1,2}:\d{2}\s*[-~]\s*\d{1,2}:\d{2}'
    result = re.search(pattern, text)
    if result:
        return result.group()
    return None

def valid_exhibition(name):
    if len(name) < 6: return False
    if any(x in name for x in FILTER_WORDS): return False
    keywords = ["展", "特展", "《", "》", "：", "－"]
    if not any(x in name for x in keywords): return False
    return True

def scrape(url):
    """抓取單一網址的展覽資訊"""
    print(f"📡 抓取中: {url}")
    data = []
    try:
        response = requests.get(url, headers=HEADERS, timeout=(5, 10), verify=False)
        soup = BeautifulSoup(response.text, "html.parser")
        titles = soup.find_all(["h1", "h2", "h3", "a"])
        for title in titles:
            name = title.text.strip()
            if not valid_exhibition(name): continue
            
            location = get_location(name)
            lat, lon = get_coordinates(location)
            start_date, end_date = get_dates(title.text)
            exhibition_time = get_time(title.text)
            
            # 💡 這裡回傳的欄位必須要跟 main.py 一模一樣
            data.append({
                "title": name,
                "location": location,
                "address": location, # 避免導航壞掉，加上地址
                "lat": lat,          # 修改點 1
                "lon": lon,          # 修改點 1
                "start_date": start_date,
                "end_date": end_date,
                "exhibition_time": exhibition_time,
                "description": f"本展覽在{location}展出，歡迎前往參觀！",
                "eta_car": 15,
                "eta_moto": 12,
                "eta_transit": 20,
                "rating_avg": 5.0,
                "reviews": []
            })
    except Exception as e:
        print(f"❌ 錯誤: {e}")
    return data

# ==========================================
# 🌟 核心修改：專為 main.py 開放的接口
# ==========================================
def start_crawling():
    """啟動爬蟲，並將資料回傳給 main.py 寫入資料庫"""
    print("🚀 爬蟲開始執行...")
    all_data = []
    for url in URLS:
        all_data.extend(scrape(url))
        
    # 去除重複資料
    unique = []
    seen = set()
    for item in all_data:
        if item["title"] not in seen:
            seen.add(item["title"])
            unique.append(item)
            
    print(f"✅ 爬取完畢，共獲取 {len(unique)} 筆不重複展覽！準備交給 main.py 寫入...")
    return unique

# 保留單獨測試功能（讓組員自己在終端機跑 py 檔測試時可以看印出結果）
if __name__ == "__main__":
    result = start_crawling()
    for r in result[:3]:
        print(r)