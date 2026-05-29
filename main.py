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
# 1. 初始化 Firebase (雲端環境變數 + 本地相容雙棲版)
# ==========================================
db = None

# 優先嘗試從 Render 的環境變數讀取金鑰
if "FIREBASE_CONFIG" in os.environ:
    try:
        print("🌐 偵測到雲端環境變數，正在初始化 Firebase...")
        cred_dict = json.loads(os.environ["FIREBASE_CONFIG"])
        
        if "private_key" in cred_dict:
            cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
            
        # 🛡️ 終極綁定：直接走你一開始建好的預設資料庫
        credentials = service_account.Credentials.from_service_account_info(cred_dict)
        db = firestore.Client(project=cred_dict["project_id"], credentials=credentials)
        print("🚀 Firebase 雲端連線成功！")
    except Exception as e:
        print(f"❌ 雲端 Firebase 初始化失敗: {str(e)}")

# 如果雲端沒有變數，則嘗試尋找本地檔案（方便你在電腦本機測試）
if db is None:
    current_folder = os.path.dirname(os.path.abspath(__file__))
    key_absolute_path = os.path.join(current_folder, "firebase_key.json")
    if os.path.exists(key_absolute_path):
        try:
            print(f"🔍 偵測到本地金鑰，正在初始化: {key_absolute_path}")
            credentials = service_account.Credentials.from_service_account_info(json.load(open(key_absolute_path)))
            db = firestore.Client(project=credentials.project_id, credentials=credentials)
            print("🏠 本地 Firebase 連線成功！")
        except Exception as e:
            print(f"❌ 本地 Firebase 初始化失敗: {str(e)}")

# ==========================================
# 2. 初始化 FastAPI 與開放 CORS 跨域限制
# ==========================================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 開放所有網域（包含你的 GitHub Pages 前端網頁）
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 定義前端傳入評論的標準格式
class Review(BaseModel):
    title: str
    rating: int
    comment: str

# ==========================================
# 3. API 路由設計
# ==========================================

@app.get("/")
def read_root():
    return {"message": "雙北展覽 API 伺服器正常運作中！"}

@app.get("/api/exhibitions")
def get_exhibitions(lat: float = None, lon: float = None):
    if db is None:
        return {"status": "error", "message": "資料庫未連線"}
    
    try:
        docs = db.collection('exhibitions').stream()
        result = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            
            # 🛡️ 【核心重大修復】：必須確保使用者有傳座標，且展覽本身也有抓到經緯度，才能計算距離
            if lat is not None and lon is not None and data.get('lat') is not None and data.get('lon') is not None:
                try:
                    # 使用海正公式 (Haversine Formula) 計算精確的地球表面兩點距離 (公里)
                    R = 6371.0  
                    lat1 = math.radians(lat)
                    lon1 = math.radians(lon)
                    lat2 = math.radians(float(data['lat']))
                    lon2 = math.radians(float(data['lon']))
                    
                    dlat = lat2 - lat1
                    dlon = lon2 - lon1
                    
                    a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
                    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
                    distance = R * c
                    
                    data['distance'] = round(distance, 2)
                    # 預估開車時間：每公里約 2 分鐘 + 固定塞車 3 分鐘緩衝
                    data['eta_car'] = max(2, int(distance * 2 + 3))
                    # 預估大眾運輸時間：每公里約 4 分鐘 + 固定等車 8 分鐘
                    data['eta_transit'] = max(5, int(distance * 4 + 8))
                except Exception:
                    # 萬一運算過程還是有意外，給予安全極大值，防止當機
                    data['distance'] = 999
                    data['eta_car'] = 999
                    data['eta_transit'] = 999
            else:
                # 🛡️ 沒抓到經緯度（如模糊地址）或沒開啟定位，直接給預設值，徹底免除 NoneType 炸彈
                data['distance'] = 999
                data['eta_car'] = 999
                data['eta_transit'] = 999
            
            # 確保評論欄位格式正確
            reviews = data.get('reviews', [])
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
        # 執行 crawler.py 裡的自動爬蟲功能
        new_data = start_crawling() 
        
        # 安全防護：如果爬蟲有回傳清單，則在後端主動為其同步更新至 Firebase
        if new_data and isinstance(new_data, list):
            for ex in new_data:
                if "title" in ex:
                    safe_title = ex['title'].replace('/', '／')
                    db.collection('exhibitions').document(safe_title).set(ex, merge=True)
                    
        return {"status": "success", "message": "雙北展覽資料爬取與 Firebase 同步完成！"}
    except Exception as e:
        return {"status": "error", "message": str(e)}