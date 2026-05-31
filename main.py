import os
import json
import math
import sys
import re

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google.cloud import firestore
from google.oauth2 import service_account  
from crawler import start_crawling

# 強制讓 Python 輸出（stdout）相容雲端環境，避免編碼衝突
if sys.stdout.encoding != 'utf-8':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

# ==========================================
# 1. 初始化 Firebase 
# ==========================================
db = None
if "FIREBASE_CONFIG" in os.environ:
    try:
        cred_dict = json.loads(os.environ["FIREBASE_CONFIG"])
        if "private_key" in cred_dict:
            cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
        credentials = service_account.Credentials.from_service_account_info(cred_dict)
        db = firestore.Client(project=cred_dict["project_id"], credentials=credentials)
    except Exception as e:
        print(f"❌ Firebase 初始化失敗: {str(e)}")

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class Review(BaseModel):
    title: str
    rating: int
    comment: str

@app.get("/")
def read_root():
    return {"message": "雙北展覽 API 伺服器 - 定位排序與本地無 AI 摘要完整版"}

# ==========================================
# 2. API：取得所有展覽資料 (📍 包含精準定位與自動排序)
# ==========================================
@app.get("/api/exhibitions")
def get_exhibitions(lat: float = None, lon: float = None):
    if db is None: return {"status": "error", "message": "資料庫未連線"}
    try:
        docs = db.collection('exhibitions').stream()
        result = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            
            # 如果前端有成功傳入使用者的經緯度
            if lat is not None and lon is not None and data.get('lat') is not None and data.get('lon') is not None:
                try:
                    R = 6371.0 # 地球半徑 (公里)
                    lat1 = math.radians(lat)
                    lon1 = math.radians(lon)
                    lat2 = math.radians(float(data['lat']))
                    lon2 = math.radians(float(data['lon']))
                    dlat = lat2 - lat1
                    dlon = lon2 - lon1
                    a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
                    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
                    
                    # 算出直線距離後，乘上 1.28 近似真實道路距離
                    straight_dist = R * c
                    real_road_dist = straight_dist * 1.28
                    data['distance'] = round(straight_dist, 2)
                    
                    # 依照距離動態計算 ETA (預估抵達時間)
                    if real_road_dist > 12:
                        data['eta_car'] = max(5, int(real_road_dist * 1.5 + 8))
                        data['eta_moto'] = max(4, int(real_road_dist * 2.6 + 4))
                    else:
                        data['eta_car'] = max(5, int(real_road_dist * 2.8 + 5))
                        data['eta_moto'] = max(4, int(real_road_dist * 2.0 + 4))
                    data['eta_transit'] = max(15, int(real_road_dist * 3.5 + 15))
                except Exception:
                    data['distance'] = 999
            else:
                # 如果使用者沒開 GPS，距離設為 999，但保留 crawler.py 生成的隨機 ETA 讓畫面不破圖
                data['distance'] = 999
                data['eta_car'] = data.get('eta_car', 30)
                data['eta_moto'] = data.get('eta_moto', 20)
                data['eta_transit'] = data.get('eta_transit', 45)
            
            reviews = data.get('reviews', [])
            data['reviews'] = reviews if isinstance(reviews, list) else []
            result.append(data)
            
        # 🎯 核心功能：如果使用者有開定位，自動把清單「由近到遠」排序！
        if lat is not None and lon is not None:
            result = sorted(result, key=lambda x: x.get('distance', 999))
            
        return {"status": "success", "data": result}
    except Exception as e: 
        return {"status": "error", "message": str(e)}

# ==========================================
# 3. API：提交使用者評論
# ==========================================
@app.post("/api/review")
def submit_review(review: Review):
    if db is None: return {"status": "error", "message": "資料庫未連線"}
    try:
        safe_title = review.title.replace('/', '／')
        doc_ref = db.collection('exhibitions').document(safe_title)
        doc = doc_ref.get()
        if not doc.exists: return {"status": "error", "message": "找不到該展覽"}
        data = doc.to_dict()
        reviews = data.get('reviews', [])
        reviews.append({"rating": review.rating, "comment": review.comment})
        doc_ref.update({"reviews": reviews, "rating_avg": round(sum(r.get('rating',0) for r in reviews)/len(reviews), 1)})
        return {"status": "success", "message": "評論發表成功！"}
    except Exception as e: return {"status": "error", "message": str(e)}

# ==========================================
# 4. 本地 Python 內文智能提取 (一秒搞定，完全無 AI)
# ==========================================
def extract_local_summary(title, location, text):
    """ 從爬蟲抓到的真實內文，精準切出前 130 字的精華介紹 """
    if not text or len(text.strip()) < 20:
        return f"歡迎蒞臨「{location}」親身體驗【{title}】的獨特魅力！本展演活動精心策劃，現場結合豐富的展品呈現與知性互動，非常適合週末假日前往探索！"
    
    # 移除多餘的換行與空白字元
    clean_text = re.sub(r'\s+', ' ', text.strip())
    
    # 加入前導句增加專欄質感
    intro = f"【{title}】於「{location}」展出。內容提要："
    
    # 計算剩餘字數額度 (總長控制在 140 字左右)
    budget = 135 - len(intro)
    
    # 如果內文超過額度，切斷並加上刪節號
    if len(clean_text) > budget:
        cut_text = clean_text[:budget]
        last_punct = max(cut_text.rfind('。'), cut_text.rfind('，'), cut_text.rfind('！'))
        if last_punct > (budget // 2): 
            summary = cut_text[:last_punct+1] + "..."
        else:
            summary = cut_text.strip() + "..."
    else:
        summary = clean_text

    return f"{intro} {summary}"

# ==========================================
# 5. API：觸發爬蟲 (無背景任務，瞬間執行完畢)
# ==========================================
@app.get("/api/trigger-crawler")
def trigger_crawler_and_update_db():
    if db is None: return {"status": "error", "message": "資料庫未連線"}
    try:
        new_data = start_crawling() 
        if not new_data or not isinstance(new_data, list): return {"status": "error", "message": "爬蟲回傳資料為空。"}
            
        active_safe_titles = set()
        new_data_dict = {}
        for ex in new_data:
            if "title" in ex:
                safe_title = ex['title'].replace('/', '／')
                active_safe_titles.add(safe_title)
                new_data_dict[safe_title] = ex

        # 清除過期舊資料
        old_docs = db.collection('exhibitions').list_documents()
        batch = db.batch()
        for doc in old_docs:
            if doc.id not in active_safe_titles:
                batch.delete(doc)
        batch.commit()

        stats_success = 0
        
        for safe_title, ex in new_data_dict.items():
            doc_ref = db.collection('exhibitions').document(safe_title)
            doc_snap = doc_ref.get()
            
            if doc_snap.exists:
                existing = doc_snap.to_dict()
                ex['reviews'] = existing.get('reviews', [])
                ex['rating_avg'] = existing.get('rating_avg', 0)
            else:
                ex['reviews'] = []
                ex['rating_avg'] = 0

            # 🔥 呼叫本地切割函數，瞬間完成，不用等 Google API 回應
            raw_context = ex.get('full_text', '')
            ex['description'] = extract_local_summary(ex['title'], ex['location'], raw_context)
            stats_success += 1

            if 'full_text' in ex: del ex['full_text']
            doc_ref.set(ex)
            
        return {
            "status": "success", 
            "message": f"🎉 爬蟲與摘要更新成功！利用本地程式高速提取了 {stats_success} 筆展覽真實內文，完全擺脫外部 API 限制！"
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}