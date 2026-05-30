import os
import json
import math
import random
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google.cloud import firestore
from google.oauth2 import service_account  
from crawler import start_crawling

# 🎯 匯入 Google 官方最新的 Gemini API 套件
from google import genai

# 強制讓 Python 輸出（stdout）相容雲端環境，避免 Big5/UTF-8 編碼衝突
import sys
if sys.stdout.encoding != 'utf-8':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

# ==========================================
# 1. 初始化 Firebase 
# ==========================================
db = None

if "FIREBASE_CONFIG" in os.environ:
    try:
        print("🌐 偵測到雲端環境，開始初始化 Firebase...")
        cred_dict = json.loads(os.environ["FIREBASE_CONFIG"])
        if "private_key" in cred_dict:
            cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
        credentials = service_account.Credentials.from_service_account_info(cred_dict)
        db = firestore.Client(project=cred_dict["project_id"], credentials=credentials)
        print("🚀 Firebase 雲端資料庫連線成功！")
    except Exception as e:
        print(f"❌ Firebase 雲端初始化失敗: {str(e)}")

if db is None:
    current_folder = os.path.dirname(os.path.abspath(__file__))
    key_absolute_path = os.path.join(current_folder, "firebase_key.json")
    if os.path.exists(key_absolute_path):
        try:
            print(f"🔍 偵測到本地金鑰: {key_absolute_path}")
            credentials = service_account.Credentials.from_service_account_info(json.load(open(key_absolute_path)))
            db = firestore.Client(project=credentials.project_id, credentials=credentials)
            print("🏠 本地 Firebase 資料庫連線成功！")
        except Exception as e:
            print(f"❌ 本地 Firebase 初始化失敗: {str(e)}")

# ==========================================
# 2. 初始化 Gemini AI 大腦
# ==========================================
ai_client = None
if "GEMINI_API_KEY" in os.environ:
    try:
        ai_client = genai.Client()
        print("🤖 Gemini AI 智慧總結大腦已成功就位！")
    except Exception as e:
        print(f"⚠️ Gemini AI 初始化失敗: {str(e)}")
else:
    print(f"⚠️ 未偵測到 GEMINI_API_KEY 環境變數，新展覽將使用預設罐頭簡介。")

# ==========================================
# 3. 初始化 FastAPI 與 允許跨網域 (CORS)
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

# ==========================================
# 4. API 路由設計
# ==========================================

@app.get("/")
def read_root():
    return {"message": "雙北展覽 API 伺服器正常運作中！2026 旗艦完全體（國道校正+Gemini AI 完整版）"}

# ------------------------------------------
# API：取得所有展覽資料（包含國道分流交通時間計算）
# ------------------------------------------
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
            
            # 如果前端有傳入使用者的真實 GPS 座標，即時計算距離與交通時間
            if lat is not None and lon is not None and data.get('lat') is not None and data.get('lon') is not None:
                try:
                    R = 6371.0  # 地球半徑公里
                    lat1 = math.radians(lat)
                    lon1 = math.radians(lon)
                    lat2 = math.radians(float(data['lat']))
                    lon2 = math.radians(float(data['lon']))
                    dlat = lat2 - lat1
                    dlon = lon2 - lon1
                    a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
                    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
                    
                    # 算出直線距離並校正為實際道路繞路距離 (約 1.28 倍)
                    straight_dist = R * c
                    real_road_dist = straight_dist * 1.28
                    data['distance'] = round(straight_dist, 2)
                    
                    # 🌟 雙北老司機擬真交通時間公式 🌟
                    if real_road_dist > 12:
                        # 🛣️【遠距離狀況】：汽車走高架國道效率高
                        data['eta_car'] = max(5, int(real_road_dist * 1.5 + 8))
                        # 🛵【機車走平面】：不能上國道，越遠紅綠燈越多，開始輸給汽車
                        data['eta_moto'] = max(4, int(real_road_dist * 2.6 + 4))
                    else:
                        # 🚦【近距離/市區狀況】：汽車容易塞車、等車位
                        data['eta_car'] = max(5, int(real_road_dist * 2.8 + 5))
                        # 🛵【機車靈活】：平面鑽車縫，近距離機車完勝！
                        data['eta_moto'] = max(4, int(real_road_dist * 2.0 + 4))
                    
                    # 大眾運輸：強制加上「走路、候車、轉乘」的 15 分鐘隱形成本
                    data['eta_transit'] = max(15, int(real_road_dist * 3.5 + 15))
                    
                except Exception:
                    data['distance'] = 999
                    data['eta_car'] = 999
                    data['eta_moto'] = 999
                    data['eta_transit'] = 999
            else:
                data['distance'] = 999
                data['eta_car'] = 999
                data['eta_moto'] = 999
                data['eta_transit'] = 999
            
            reviews = data.get('reviews', [])
            data['reviews'] = reviews if isinstance(reviews, list) else []
            result.append(data)
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ------------------------------------------
# API：提交使用者評論
# ------------------------------------------
@app.post("/api/review")
def submit_review(review: Review):
    if db is None:
        return {"status": "error", "message": "資料庫未連線"}
    try:
        safe_title = review.title.replace('/', '／')
        doc_ref = db.collection('exhibitions').document(safe_title)
        doc = doc_ref.get()
        
        if not doc.exists:
            return {"status": "error", "message": "找不到該展覽"}
            
        data = doc.to_dict()
        reviews = data.get('reviews', [])
        if not isinstance(reviews, list):
            reviews = []
            
        new_review = {"rating": review.rating, "comment": review.comment}
        reviews.append(new_review)
        
        total_rating = sum(r.get('rating', 0) for r in reviews)
        rating_avg = round(total_rating / len(reviews), 1) if reviews else 0
        
        doc_ref.update({
            "reviews": reviews,
            "rating_avg": rating_avg
        })
        return {"status": "success", "message": "評論發表成功！"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ------------------------------------------
# API：觸發爬蟲（精準下架過期、鎖定歷史評論、全新展覽調度 Gemini 生成 AI 簡介）
# ------------------------------------------
@app.get("/api/trigger-crawler")
def trigger_crawler_and_update_db():
    if db is None:
        return {"status": "error", "message": "資料庫未連線"}
    try:
        new_data = start_crawling() 
        
        if not new_data or not isinstance(new_data, list):
            return {"status": "error", "message": "爬蟲回傳資料為空。"}
            
        active_safe_titles = set()
        new_data_dict = {}
        for ex in new_data:
            if "title" in ex:
                safe_title = ex['title'].replace('/', '／')
                active_safe_titles.add(safe_title)
                new_data_dict[safe_title] = ex

        old_docs = db.collection('exhibitions').list_documents()
        
        batch = db.batch()
        delete_count = 0
        for doc in old_docs:
            if doc.id not in active_safe_titles:
                batch.delete(doc)
                delete_count += 1
        batch.commit()
        print(f"🧹 歷史倉庫整理完畢，已自動下架過期展覽 {delete_count} 筆。")

        success_count = 0
        for safe_title, ex in new_data_dict.items():
            doc_ref = db.collection('exhibitions').document(safe_title)
            doc_snap = doc_ref.get()
            
            if doc_snap.exists:
                # 完美繼承歷史評論與之前生過的 AI 簡介
                existing_data = doc_snap.to_dict()
                ex['reviews'] = existing_data.get('reviews', [])
                ex['rating_avg'] = existing_data.get('rating_avg', 0)
                ex['description'] = existing_data.get('description', ex['description'])
            else:
                ex['reviews'] = []
                ex['rating_avg'] = 0