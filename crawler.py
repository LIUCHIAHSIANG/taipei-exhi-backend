import requests
from bs4 import BeautifulSoup
import urllib3
import re
import random
from urllib.parse import urljoin
from datetime import datetime

# 忽略不安全的 SSL 連線警告
urllib3.disable_warnings()

# 設定 HTTP 請求標頭
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "zh-TW,zh;q=0.9"
}

# 23 個展覽網站清單
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

def get_dates(text):
    pattern = r'(\d{2,4})\s*[\s./\-年]\s*(\d{1,2})\s*[\s./\-月]\s*(\d{1,2})\s*日?'
    matches = re.findall(pattern, text)
    cleaned_dates = []
    for y, m, d in matches:
        year = int(y)
        if year < 200: year += 1911
        cleaned_dates.append(f"{year}-{int(m):02d}-{int(d):02d}")
    if len(cleaned_dates) >= 2: return cleaned_dates[0], cleaned_dates[1]
    elif len(cleaned_dates) == 1: return cleaned_dates[0], None
    return None, None

def parse_date_string(date_str):
    if not date_str: return None
    try: return datetime.strptime(date_str, "%Y-%m-%d").date()
    except: return None

def get_coordinates(location):
    preset_locations = {
        "台北南港展覽館1館": (25.05696, 121.6167), "華山1914文化創意園區": (25.04416, 121.5294),
        "松山文創園區": (25.04375, 121.5606), "國立故宮博物院": (25.10231, 121.5485),
        "臺北市立美術館": (25.0725, 121.5248), "國立臺灣科學教育館": (25.0958, 121.5165),
        "國立中正紀念堂": (25.0347, 121.5218), "臺北當代工藝設計分館": (25.0325, 121.5126),
        "臺北大巨蛋": (25.0416, 121.5582), "國家人權博物館": (24.9856, 121.5317),
        "師大美術館": (25.0271, 121.5284), "北師美術館": (25.0243, 121.5435),
        "關渡美術館": (25.1326, 121.4697), "世界宗教博物館": (25.0084, 121.5054),
        "郵政博物館": (25.0315, 121.5146)
    }
    return preset_locations.get(location, (25.04416, 121.5294))

def get_location(title, url):
    url_lower = url.lower()
    if "tainex" in url_lower or "南港" in title: return "台北南港展覽館1館"
    if "huashan" in url_lower or "華山" in title: return "華山1914文化創意園區"
    if "songshanculturalpark" in url_lower or "松菸" in title or "松山" in title: return "松山文創園區"
    if "npm" in url_lower or any(x in title for x in ["龍藏經", "乾隆"]): return "國立故宮博物院"
    if "tfam" in url_lower: return "臺北市立美術館"
    if "ntsec" in url_lower: return "國立臺灣科學教育館"
    if "cksmh" in url_lower: return "國立中正紀念堂"
    if "ntcart" in url_lower: return "臺北當代工藝設計分館"
    if "farglorydome" in url_lower or "棒球" in title: return "臺北大巨蛋"
    if "nhrm" in url_lower: return "國家人權博物館"
    if "artmuse.ntnu" in url_lower: return "師大美術館"
    if "montue.ntue" in url_lower: return "北師美術館"
    if "kdmofa.tnua" in url_lower: return "關渡美術館"
    if "mwr" in url_lower: return "世界宗教博物館"
    if "museum.post" in url_lower or "郵票" in title: return "郵政博物館"
    return "台北市展覽館"

def valid_exhibition(name):
    if len(name) < 4: return False
    if any(x in name for x in FILTER_WORDS): return False
    keywords = ["展", "特展", "《", "》", "：", "－", "季", "藝術", "博覽會", "節", "大展", "聯展"]
    return any(x in name for x in keywords)

def scrape(url):
    print(f"📡 Fetching URL: {url}")
    data = []
    try:
        response = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, "html.parser")
        titles = soup.find_all(["h1", "h2", "h3", "a"])
    except Exception as e:
        print(f"❌ Connection Error: {str(e)}")
        return []

    today = datetime.today().date()
    current_year_ad = 2026
    current_year_roc = 115

    for title in titles:
        raw_name = title.text.strip()
        if not valid_exhibition(raw_name): continue
        
        ad_years = [int(y) for y in re.findall(r'(20\d{2})', raw_name)]
        if ad_years and all(y < current_year_ad for y in ad_years):
            continue  
            
        roc_years = [int(y) for y in re.findall(r'(1\d{2})[年\s]', raw_name)]
        if roc_years and all(y < current_year_roc for y in roc_years):
            continue  

        start_date, end_date = get_dates(raw_name)
        
        if end_date:
            end_dt = parse_date_string(end_date)
            if end_dt and end_dt < today:
                continue 
                
        if start_date:
            start_dt = parse_date_string(start_date)
            if start_dt and not end_date and (today - start_dt).days > 365:
                continue 

        clean_name = raw_name
        clean_name = re.sub(r'\d{2,4}\s*[\s./\-年]\s*\d{1,2}\s*[\s./\-月]\s*\d{1,2}\s*日?', '', clean_name)
        clean_name = re.sub(r'\d{1,2}\s*[\s./\-]\s*\d{1,2}', '', clean_name)
        clean_name = re.sub(r'[\s~至\-－—～：:\(\)（）\[\]【】\/]+', ' ', clean_name).strip()
        
        if len(clean_name) < 3: 
            continue

        location = get_location(clean_name, url)
        lat, lon = get_coordinates(location)
        
        img_url = ""
        full_text = ""
        
        parent = title.parent
        for _ in range(3):
            if parent:
                # 抓圖片
                if not img_url:
                    img = parent.find("img")
                    if img and img.get("src"):
                        img_url = urljoin(url, img.get("src"))
                
                # 🌟 擴大抓取範圍：將節點下的 p, div, span 內文字做深度地毯式搜索
                if not full_text:
                    text_elements = parent.find_all(["p", "div", "span"])
                    text_chunks = []
                    for el in text_elements:
                        if not el.find(["p", "div"]):  # 只抓最底層文字，避免重複疊加
                            txt = el.text.strip()
                            if txt and len(txt) > 6 and not any(fw in txt for fw in FILTER_WORDS):
                                text_chunks.append(txt)
                    if text_chunks:
                        seen_chunks = set()
                        unique_chunks = [x for x in text_chunks if not (x in seen_chunks or seen_chunks.add(x))]
                        full_text = " ".join(unique_chunks)
                
                parent = parent.parent

        category = "綜合"
        if any(kw in clean_name for kw in ["畫", "藝術", "故宮", "設計", "文物", "歷史", "攝影", "雕刻"]): 
            category = "藝文歷史"
        elif any(kw in clean_name for kw in ["AI", "科技", "數位", "資訊", "半導體", "機器人"]): 
            category = "科技趨勢"
        elif any(kw in clean_name for kw in ["動漫", "玩具", "市集", "IP", "卡通", "遊戲"]): 
            category = "娛樂動漫"

        ex_description = f"歡迎蒞臨「{location}」親身體驗【{clean_name}】的獨特魅力！本展演活動精心策劃，現場結合豐富的展品呈現與知性互動，非常適合週末假日安排行程前往探索！"

        # 🌟 終極修正核心：如果網站上真的沒有多餘文字，不要再給沒養分的罐頭簡介了！
        # 塞入有意義的「結構化導引線索」，明確指令 Gemini 動用內建大腦直接擴充知識
        if not full_text or len(full_text.strip()) <= 15:
            final_full_text = f"本展覽為在『{location}』舉辦的『{category}』類型活動，主題聚焦於『{clean_name}』。請主編直接調動你強大的藝文知識庫與最新資料，針對這個展覽主題及其相關背景，直接撰寫一篇高質感的展覽核心亮點與策展大綱摘要導覽。"
        else:
            final_full_text = full_text

        data.append({
            "title": clean_name, 
            "location": location,
            "address": location,
            "lat": lat,
            "lon": lon,
            "start_date": start_date, 
            "end_date": end_date,     
            "exhibition_time": "09:00 ~ 18:00",
            "description": ex_description, 
            "image_url": img_url,  
            "category": category,  
            "price": random.choice([0, 100, 150, 200, 250, 300]),        
            "eta_car": random.randint(12, 35),
            "eta_moto": random.randint(8, 20),
            "eta_transit": random.randint(15, 45),
            "rating_avg": 0,
            "reviews": [],
            "full_text": final_full_text  # 完美過渡給 main.py
        })

    return data

def start_crawling():
    print("🚀 Crawler process started...")
    all_data = []
    for url in URLS:
        all_data.extend(scrape(url))
        
    unique = []
    seen = set()
    for item in all_data:
        if item["title"] not in seen:
            seen.add(item["title"])
            unique.append(item)
            
    print(f"✅ Crawler finished. Total unique valid records: {len(unique)}")
    return unique

if __name__ == "__main__":
    start_crawling()