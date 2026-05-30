import os
import json
import math
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google.cloud import firestore
from google.oauth2 import service_account  
from crawler import start_crawling

# 強制讓 Python 輸出（stdout）相容雲端環境
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
        print("🌐 Cloud env detected, initializing Firebase...")
        cred_dict = json.loads(os.environ["FIREBASE_CONFIG"])
        if "private_key" in cred_dict:
            cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
        credentials = service_account.Credentials.from_service_account_info(cred_dict)
        db = firestore.Client(project=cred_dict["project_id"], credentials=credentials)
        print("🚀 Firebase Cloud connection successful!")
    except Exception as e:
        print(f"❌ Firebase init failed: {str(e)}")

if db is None:
    current_folder = os.path.dirname(os.path.abspath(__file__))
    key_absolute_path = os.path.join(current_folder, "firebase_key.json")
    if os.path.exists(key_absolute_path):
        try:
            print(f"🔍 Local key detected: {key_absolute_path}")
            credentials = service_account.Credentials.from_service_account_info(json.load(open(key_absolute_path)))
            db = firestore.Client(project=credentials.project_id, credentials=credentials)
            print("🏠 Local Firebase connection successful!")
        except Exception as e:
            print(f"❌ Local Firebase init failed: {str(e)}")

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
# 2. API 路由設計
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
            
            # 計算距離與時間
            if lat is not None and lon is not None and data.get('lat') is not None and data.get('lon') is not None:
                try:
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
                    data['eta_car'] = max(2, int(distance * 2 + 3))
                    data['eta_transit'] = max(5, int(distance * 4 + 8))
                except Exception:
                    data['distance'] = 999
                    data['eta_car'] = 999
                    data['eta_transit'] = 999
            else:
                data['distance'] = 999
                data['eta_car'] = 999
                data['eta_transit'] = 999
            
            reviews = data.get('reviews', [])
            data['reviews'] = reviews if isinstance(reviews, list) else []
            result.append(data)
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# 🎯 優化點：使用者留評論時，即時計算平均分並存入資料庫
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
            
        # 塞入新評論
        new_review = {"rating": review.rating, "comment": review.comment}
        reviews.append(new_review)
        
        # 算分數：即時重新計算這台展覽的真實平均分數
        total_rating = sum(r.get('rating', 0) for r in reviews)
        rating_avg = round(total_rating / len(reviews), 1) if reviews else 0
        
        # 同步更新
        doc_ref.update({
            "reviews": reviews,
            "rating_avg": rating_avg
        })
        return {"status": "success", "message": "評論發表成功，評分已即時重新計算！"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# 🎯 優化點：每天爬蟲更新時，精準下架過期展覽，同時「完美保留」沒過期展覽的歷史評論
@app.get("/api/trigger-crawler")
def trigger_crawler_and_update_db():
    if db is None:
        return {"status": "error", "message": "資料庫未連線"}
    try:
        # 1. 抓到今天最新、未過期的展覽
        new_data = start_crawling() 
        
        if not new_data or not isinstance(new_data, list):
            return {"status": "error", "message": "爬蟲回傳資料為空。"}
            
        # 將今天爬到的資料轉成字典，方便比對，同時蒐集今日合法的 ID 集合
        active_safe_titles = set()
        new_data_dict = {}
        for ex in new_data:
            if "title" in ex:
                safe_title = ex['title'].replace('/', '／')
                active_safe_titles.add(safe_title)
                new_data_dict[safe_title] = ex

        # 2. 找出目前 Firebase 裡「所有人」正在看的所有展覽文檔
        old_docs = db.collection('exhibitions').list_documents()
        
        # 3. 精準下架：如果 Firebase 裡的展覽，不在今天最新爬取的名單內，代表它過期了，這時才刪除
        batch = db.batch()
        delete_count = 0
        for doc in old_docs:
            if doc.id not in active_safe_titles:
                batch.delete(doc)
                delete_count += 1
        batch.commit()
        print(f"🧹 已自動清理並下架 {delete_count} 筆過期歷史展覽。")

        # 4. 精準合體：更新或寫入今日展覽，並絕對保護使用者的歷史評論
        success_count = 0
        for safe_title, ex in new_data_dict.items():
            doc_ref = db.collection('exhibitions').document(safe_title)
            doc_snap = doc_ref.get()
            
            if doc_snap.exists:
                # 🔥【核心保護線】：展覽原本就存在，把資料庫裡的評論與分數取出來
                existing_data = doc_snap.to_dict()
                existing_reviews = existing_data.get('reviews', [])
                
                # 重新根據歷史評論計分，不被爬蟲的初始值蓋掉
                if existing_reviews:
                    total_rating = sum(r.get('rating', 0) for r in existing_reviews)
                    rating_avg = round(total_rating / len(existing_reviews), 1)
                else:
                    rating_avg = 0
                
                # 強制把歷史評論和真實評分，接回到爬蟲準備寫入的新封包裡！
                ex['reviews'] = existing_reviews
                ex['rating_avg'] = rating_avg
            else:
                # 全新品項，初始化欄位
                ex['reviews'] = []
                ex['rating_avg'] = 0
            
            # 覆蓋寫入最新的展覽資訊（圖片、日期等），但 reviews 和評分毫髮無傷
            doc_ref.set(ex)
            success_count += 1
            
        return {
            "status": "success", 
            "message": f"同步完成！自動下架過期展覽 {delete_count} 筆，同步最新展覽 {success_count} 筆（已成功鎖定歷史評論與評分紀錄）。"
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}