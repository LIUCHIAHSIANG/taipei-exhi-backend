from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import math
import os
from google.cloud import firestore
from crawler import start_crawling

app = FastAPI()

# 允許跨網域請求 (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"],
)

# 初始化 Firebase 連線 (具備絕對路徑自動偵測防呆)
db = None
try:
    current_folder = os.path.dirname(os.path.abspath(__file__))
    key_absolute_path = os.path.join(current_folder, "firebase_key.json")
    
    if os.path.exists(key_absolute_path):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = key_absolute_path
        db = firestore.Client(project="taipei-expo-app", database="default")
        print("✅ Firebase 透過絕對路徑連線成功！")
    else:
        print(f"ℹ️ 找不到金鑰，路徑嘗試為: {key_absolute_path}，目前以離線模式執行。")
except Exception as e:
    print(f"⚠️ Firebase 連線錯誤: {e}")

class ReviewInput(BaseModel):
    title: str
    rating: int
    comment: str

# 數學公式：半正矢公式計算地球表面兩點距離
def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 1)

def get_mock_data():
    return [
        {"title": "2026 台北當代藝術博覽會", "status": "現在", "category": "藝術", "price": 350, "location": "台北南港展覽館", "address": "台北市南港區經貿二路1號", "lat": 25.056965, "lon": 121.616641, "description": "匯集全球頂尖畫廊，展出當代最具代表性的藝術作品，是亞洲年度最重要的藝術盛會之一。"},
        {"title": "咒術迴戰特展", "status": "未來", "category": "動漫", "price": 0, "location": "華山文創園區", "address": "台北市中正區八德路一段1號", "lat": 25.044147, "lon": 121.529402, "description": "日本現象級動漫《咒術迴戰》海外首度大型特展！原畫、等比例模型、沉浸式領域展開體驗一次滿足。"},
        {"title": "AI 未來科技展", "status": "現在", "category": "科技", "price": 200, "location": "松山文創園區", "address": "台北市信義區光復南路133號", "lat": 25.043741, "lon": 121.560649, "description": "探討 AI 如何改變人類未來。現場有最新的機器人互動、生成式 AI 體驗，適合全家大小一同探索。"}
    ]

# 提供給前端網頁讀取的接口
@app.get("/api/exhibitions")
def fetch_exhibitions(lat: float = 25.0478, lon: float = 121.5170):
    user_lat = lat
    user_lon = lon
    exhibitions = []
    
    # 1. 去 Firebase 撈出所有資料
    if db:
        try:
            docs = db.collection('exhibitions').stream()
            for doc in docs:
                exhibitions.append(doc.to_dict())
            
            # 如果資料庫是空的，拿 Mock 補上避免畫面太空
            if not exhibitions:
                exhibitions = get_mock_data()
        except Exception as e:
            print(f"⚠️ 讀取失敗: {e}")
            exhibitions = get_mock_data()
    else:
        exhibitions = get_mock_data()

    # 2. 逐筆檢查與計算交通時間（加入強大防呆）
    cleaned_exhibitions = []
    
    for ex in exhibitions:
        # 防呆：連名稱都沒有的髒資料直接剔除
        if "title" not in ex or not ex["title"]:
            continue 
            
        # 核心防呆：如果組員爬蟲缺失經緯度，自動補上台北車站座標，防止 KeyError 崩潰
        if "lat" not in ex or "lon" not in ex or ex["lat"] is None or ex["lon"] is None:
            ex["lat"] = 25.0478
            ex["lon"] = 121.5170
            
        if "price" not in ex or ex["price"] is None: ex["price"] = 0 
        if "location" not in ex or not ex["location"]: ex["location"] = "未知展館"
        if "address" not in ex or not ex["address"]: ex["address"] = "未知地址"
        if "status" not in ex: ex["status"] = "現在"
        if "category" not in ex: ex["category"] = "藝術"
        if "description" not in ex: ex["description"] = "暫無詳細介紹。"

        # 3. 安全地計算距離與智慧交通 ETA
        distance = haversine_distance(user_lat, user_lon, ex["lat"], ex["lon"])
        dist_factor = distance * 1.25 
        
        if "rating_avg" not in ex: ex["rating_avg"] = "目前無資料"
        if "reviews" not in ex: ex["reviews"] = ["尚無評論，來搶頭香吧！"]
        
        ex["eta_car"] = max(5, round((dist_factor / 35) * 60))     
        ex["eta_moto"] = max(5, round((dist_factor / 40) * 60))    
        ex["eta_transit"] = 10 + round((dist_factor / 18) * 60) # 加上 10 分鐘基礎等車步行時間
        
        # 4. 整合使用者留在資料庫的評分與評論
        try:
            doc_ref = db.collection('exhibitions').document(ex['title']).get()
            if doc_ref.exists:
                data = doc_ref.to_dict()
                if data.get('rating_count', 0) > 0:
                    ex["rating_avg"] = round(data['total_score'] / data['rating_count'], 1)
                if data.get('reviews'):
                    ex["reviews"] = data['reviews']
        except: 
            pass

        cleaned_exhibitions.append(ex)

    return {"status": "success", "data": cleaned_exhibitions}

# 留言評論接口
@app.post("/api/review")
def post_review(info: ReviewInput):
    if not db: 
        return {"status": "error", "message": "目前伺服器為離線模式，無法儲存評論。"}
    try:
        doc_ref = db.collection('exhibitions').document(info.title)
        doc = doc_ref.get()
        new_review_str = f"「{info.comment}」 ({info.rating}星)"
        if doc.exists:
            current_data = doc.to_dict()
            doc_ref.update({
                'total_score': current_data.get('total_score', 0) + info.rating,
                'rating_count': current_data.get('rating_count', 0) + 1,
                'reviews': current_data.get('reviews', []) + [new_review_str]
            })
        else:
            doc_ref.set({'total_score': info.rating, 'rating_count': 1, 'reviews': [new_review_str]})
        return {"status": "success", "message": "評論上傳雲端成功！"}
    except Exception as e:
        return {"status": "error", "message": f"上傳失敗: {str(e)}"}
@app.get("/api/trigger-crawler")
def trigger_crawler_and_update_db():
    try:
        # 啟動（假）爬蟲
        new_data = start_crawling() 
        
        # 寫入 Firebase
        for ex in new_data:
            doc_ref = db.collection('exhibitions').document(ex['title'])
            doc_ref.set(ex, merge=True)
            
        return {"status": "success", "message": f"太棒了！成功爬取並更新 {len(new_data)} 筆展覽資料到資料庫！"}
    except Exception as e:
        return {"status": "error", "message": str(e)}