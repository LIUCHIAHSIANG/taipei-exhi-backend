import requests
from bs4 import BeautifulSoup
from geopy.geocoders import Nominatim
import urllib3
import re
import time
import random
from urllib.parse import urljoin

# 忽略不安全的 SSL 連線警告
urllib3.disable_warnings()

# 設定 HTTP 請求標頭
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "zh-TW,zh;q=0.9"
}

# 🌟 完整 23 個展覽網站清單
URLS = [
    "https://www.tainex.com.tw/event",
    "https://www.huashan1914.com/w/huashan1914/exhibition",
    "https://www.songshanculturalpark.org/exhibition",
    "https://www.npm.gov.tw/Exhibition-Current.aspx?sno=03000060&l=1",
    "https://www.tfam.museum/Exhibition/Exhibition.aspx?ddlLang=zh-tw",
    "https://www.ntsec.gov.tw/article/list.aspx?a=27",
    "https://www.ntsec.gov.tw/article/list.aspx?a=25",
    "https://www.ntsec.gov.tw/article/list.aspx?a=5904",
    "https://www.ntsec.gov.tw/article/list.aspx?a=30",
    "https://www.cksmh.gov.tw/News_Actives_photo.aspx?n=6067&sms=14954",
    "https://www.cksmh.gov.tw/News_card.aspx?n=8909&sms=16036",
    "https://ntcart.museum/exhibition.aspx?kind=today",
    "https://www.farglorydome.com.tw/news/",
    "https://www.nhrm.gov.tw/w/nhrm/ExhibitionA",
    "https://www.artmuse.ntnu.edu.tw/index.php/current_exhibit/",
    "https://montue.ntue.edu.tw/exhibitions/",
    "https://montue.ntue.edu.tw/exhibitions-upcoming/",
    "https://kdmofa.tnua.edu.tw/mod/exhibition/index.php",
    "https://kdmofa.tnua.edu.tw/mod/course/index.php",
    "https://museum.org.tw/exhibitions.php",
    "https://www.mwr.org.tw/xcpmtexhi?xsmsid=0H305740978429024070",
    "https://www.mwr.org.tw/xcspecexhi?xsmsid=0H305741810776620070",
    "https://museum.post.gov.tw/post/Postal_Museum/museum/north/Museum_Activities_index.jsp"
]

FILTER_WORDS = [
    "首頁", "找活動", "全球資訊網", "網站導覽", "最新消息", "最新展覽",
    "檔期表", "當期展覽", "自辦展覽", "展演計畫", "常設展",
    "展區詳細敘述", "官方商品", "賽程表", "dotDefender", "Blocked",
    "遠雄集團", "預告展覽", "交通指南", "參觀資訊", "線上預約"
]

geolocator = Nominatim(user_agent="exhibition_project_v5")

def get_coordinates(location):
    """將地址轉為經緯度 (擴充版精準字典，避免 Geopy 當機)"""
    preset_locations = {
        "台北南港展覽館1館": (25.05696, 121.6167),
        "華山1914文化創意園區": (25.04416, 121.5294),
        "松山文創園區": (25.04375, 121.5606),
        "國立故宮博物院": (25.10231, 121.5485),
        "臺北市立美術館": (25.0725, 121.5248),
        "國立臺灣科學教育館": (25.0958, 121.5165),
        "國立中正紀念堂": (25.0347, 121.5218),
        "臺北當代工藝設計分館": (25.0325, 121.5126),
        "臺北大巨蛋": (25.0416, 121.5582),
        "國家人權博物館": (24.9856, 121.5317),
        "師大美術館": (25.0271, 121.5284),
        "北師美術館": (25.0243, 121.5435),
        "關渡美術館": (25.1326, 121.4697),
        "世界宗教博物館": (25.0084, 121.5054),
        "郵政博物館": (25.0315, 121.5146)
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

def get_location(title, url):
    """雙重智能判斷：看標題也看網址"""
    if any(x in title for x in ["龍藏經", "乾隆", "紅樓夢"]): return "國立故宮博物院"
    if "棒球" in title: return "臺北大巨蛋"
    if "郵票" in title: return "郵政博物館"
    if "華山" in title: return "華山1914文化創意園區"
    if "松山" in title or "松菸" in title: return "松山文創園區"
    if "南港" in title: return "台北南港展覽館1館"
    
    url_lower = url.lower()
    if "tainex" in url_lower: return "台北南港展覽館1館"
    if "huashan" in url_lower: return "華山1914文化創意園區"
    if "songshanculturalpark" in url_lower: return "松山文創園區"
    if "npm" in url_lower: return "國立故宮博物院"
    if "tfam" in url_lower: return "臺北市立美術館"
    if "ntsec" in url_lower: return "國立臺灣科學教育館"
    if "cksmh" in url_lower: return "國立中正紀念堂"
    if "ntcart" in url_lower: return "臺北當代工藝設計分館"
    if "farglorydome" in url_lower: return "臺北大巨蛋"
    if "nhrm" in url_lower: return "國家人權博物館"
    if "artmuse.ntnu" in url_lower: return "師大美術館"
    if "montue.ntue" in url_lower: return "北師美術館"
    if "kdmofa.tnua" in url_lower: return "關渡美術館"
    if "mwr" in url_lower: return "世界宗教博物館"
    if "museum.post" in url_lower: return "郵政博物館"
    
    return "台北市"

def get_dates(text):
    pattern = r'\d{4}[./-]\d{1,2}[./-]\d{1,2}'
    dates = re.findall(pattern, text)
    if len(dates) >= 2: return dates[0], dates[1]
    elif len(dates) == 1: return dates[0], None
    return None, None

def get_time(text):
    pattern = r'\d{1,2}:\d{2}\s*[-~]\s*\d{1,2}:\d{2}'
    result = re.search(pattern, text)
    if result: return result.group()
    return None

def valid_exhibition(name):
    if len(name) < 6: return False
    if any(x in name for x in FILTER_WORDS): return False
    keywords = ["展", "特展", "《", "》", "：", "－"]
    if not any(x in name for x in keywords): return False
    return True

def scrape(url):
    print(f"📡 抓取中: {url}")
    data = []
    try:
        # 加入 Timeout 與連線錯誤防護，防止抓23個網站時卡死
        response = requests.get(url, headers=HEADERS, timeout=(5, 10), verify=False)
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
        print(f"⚠️ 跳過(連線失敗或逾時): {url}")
        return []
    except Exception as e:
        print(f"⚠️ 請求錯誤: {e}")
        return []

    try:
        soup = BeautifulSoup(response.text, "html.parser")
        titles = soup.find_all(["h1", "h2", "h3", "a"])
        for title in titles:
            name = title.text.strip()
            if not valid_exhibition(name): continue
            
            location = get_location(name, url)
            lat, lon = get_coordinates(location)
            start_date, end_date = get_dates(title.text)
            exhibition_time = get_time(title.text)
            
            # 🌟 爬蟲新增：往上找 3 層，去抓取展覽圖片
            img_url = ""
            parent = title.parent
            for _ in range(3):
                if parent:
                    img = parent.find("img")
                    if img and img.get("src"):
                        img_url = urljoin(url, img.get("src"))
                        break
                    parent = parent.parent

            # 🌟 爬蟲新增：自動分析展覽分類與模擬票價
            category = "綜合"
            if any(kw in name for kw in ["畫", "藝術", "故宮", "設計"]): category = "藝文歷史"
            elif any(kw in name for kw in ["AI", "科技", "數位"]): category = "科技趨勢"
            elif any(kw in name for kw in ["動漫", "玩具", "市集"]): category = "娛樂動漫"

            price = random.choice([0, 0, 100, 150, 200, 250, 300])
            if "免費" in name or "市集" in name: price = 0
            elif "故宮" in name: price = 350
            elif "棒球" in name: price = 800
            
            # 💡 回傳字典完美對接前端需求
            data.append({
                "title": name,
                "location": location,
                "address": location,
                "lat": lat,
                "lon": lon,
                "start_date": start_date,
                "end_date": end_date,
                "exhibition_time": exhibition_time,
                "description": f"本展覽在{location}展出，歡迎前往參觀！",
                "image_url": img_url,  # 解決圖片消失問題
                "category": category,  # 解決分類問題
                "price": price,        # 解決 undefined 元問題
                "eta_car": 15,
                "eta_moto": 12,
                "eta_transit": 20,
                "rating_avg": 5.0,
                "reviews": []
            })
    except Exception as e:
        print(f"❌ 錯誤: {e}")
    return data

def start_crawling():
    print("🚀 爬蟲開始執行...")
    all_data = []
    for url in URLS:
        all_data.extend(scrape(url))
        
    unique = []
    seen = set()
    for item in all_data:
        if item["title"] not in seen:
            seen.add(item["title"])
            unique.append(item)
            
    print(f"✅ 爬取完畢，共獲取 {len(unique)} 筆不重複展覽！準備交給 main.py 寫入...")
    return unique

if __name__ == "__main__":
    result = start_crawling()
    for r in result[:3]:
        print(r)