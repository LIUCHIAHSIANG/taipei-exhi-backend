import os
import json
import math
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google.cloud import firestore
from google.oauth2 import service_account  # 導入安全憑證工具
from crawler import start_crawling

# ==========================================
# 1. 初始化 Firebase (最強力直接連線版)
# ==========================================
db = None

# 優先嘗試從 Render 的環境變數讀取金鑰
if "FIREBASE_CONFIG" in os.environ:
    try:
        print("🌐 偵測到雲端環境變數，正在初始化 Firebase...")
        cred_dict = json.loads(os.environ["FIREBASE_CONFIG"])
        
        if "private_key" in cred_dict:
            cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
            
        # 🛡️ 終極綁定：不指定資料庫名稱，讓它直接走你一開始建好的預設資料庫！
        credentials = service_account.Credentials.from_service_account_info(cred_dict)
        db = firestore.Client(project=cred_dict["project_id"], credentials=credentials)
        print("🚀 Firebase 雲端連線成功！")
    except Exception as e:
        print(f"❌ 雲端 Firebase 初始化失敗: {str(e)}")

# 如果雲端沒有，才嘗試找本地檔案
if db is None:
    local_key_path = "firebase_key.json"
    if os.path.exists(local_key_path):
        try:
            print("💻 找不到雲端變數，嘗試讀取本地金鑰檔案...")
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = local_key_path
            db = firestore.Client(project="taipei-expo-app") 
            print("🚀 本地 Firebase 連線成功！")
        except Exception as e:
            print(f"❌ 本地 Firebase 初始化失敗: {str(e)}")
    else:
        print("ℹ️ 找不到任何金鑰設定，資料庫將處於離線狀態。")

# ==========================================
# 2. 初始化 FastAPI 與跨域設定
# ==========================================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Review(BaseModel):
    title: str
    rating: int
    comment: str

def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371  
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2) * math.sin(dlat/2) + math.cos(math.radians(lat1)) \
        * math.cos(math.radians(lat2)) * math.sin(dlon/2) * math.sin(dlon/2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

# ==========================================
# 3. API 路由設定
# ==========================================

@app.get("/")
def read_root():
    return {"message": "雙北展覽 API 伺服器正常運作中！"}

@app.get("/api/exhibitions")
def get_exhibitions(lat: float = 25.0478, lon: float = 121.5170):
    if db is None:
        return {"status": "error", "message": "資料庫未連線"}
    try:
        docs = db.collection('exhibitions').stream()
        result = []
        for doc in docs:
            data = doc.to_dict()
            exhi_lat = data.get('lat', 25.0478)
            exhi_lon = data.get('lon', 121.5170)
            dist = calculate_distance(lat, lon, exhi_lat, exhi_lon)
            data['eta_car'] = int(dist * 2) + 5
            data['eta_moto'] = int(dist * 2.5) + 3
            data['eta_transit'] = int(dist * 4) + 10
            reviews = data.get('reviews', [])
            if reviews and isinstance(reviews[0], dict) and 'rating' in reviews[0]:
                avg = sum(r['rating'] for r in reviews) / len(reviews)
                data['rating_avg'] = round(avg, 1)
                data['reviews'] = [r['comment'] for r in reviews if 'comment' in r]
            else:
                data['rating_avg'] = "暫無評分"
                data['reviews'] = reviews if isinstance(reviews, list) else []
            result.append(data)
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/review")
def submit_review(review: Review):
    if db is None:
        return {"status": "error", "message": "資料庫未連線"}
    try:
        safe_title = review.title.replace('/', '／')
        doc_ref = db.collection('exhibitions').document(safe_title)
        doc = doc_ref.get()
        new_review = {"rating": review.rating, "comment": review.comment}
        if doc.exists:
            doc_ref.update({"reviews": firestore.ArrayUnion([new_review])})
        else:
            return {"status": "error", "message": "找不到該展覽"}
        return {"status": "success", "message": "評論新增成功！"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/trigger-crawler")
def trigger_crawler_and_update_db():
    if db is None:
        return {"status": "error", "message": "資料庫未連線，無法更新資料"}
    try:
        new_data = start_crawling() 
        for ex in new_data:
            safe_title = ex['title'].replace('/', '／')
            doc_ref = db.collection('exhibitions').document(safe_title)
            doc_ref.set(ex, merge=True)
        return {"status": "success", "message": f"太棒了！成功爬取並更新 {len(new_data)} 筆展覽資料到資料庫！"}
    except Exception as e:
        return {"status": "error", "message": str(e)}