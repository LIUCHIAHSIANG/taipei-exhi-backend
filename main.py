import os
import json
import math
import random
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google.cloud import firestore
from google.oauth2 import service_account  
from crawler import start_crawling

# 🎯 匯入 Google 官方最新的 Gemini API 套件
from google import genai

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
    print(f"⚠️ 未偵測到 GEMINI_API_KEY 環境變數，將使用預設罐頭簡介。")

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
    return {"message": "雙北展覽 API 伺服器正常運作中！2026 旗艦完全體（真實內容 AI 摘要版）"}

# ------------------------------------------
# API：取得所有展覽資料
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
                    
                    straight_dist = R * c
                    real_road_dist = straight_dist * 1.28
                    data['distance'] = round(straight_dist, 2)
                    
                    if real_road_dist > 12:
                        data['eta_car'] = max(5, int(real_road_dist * 1.5 + 8))
                        data['eta_moto'] = max(4, int(real_road_dist * 2.6 + 4))
                    else:
                        data['eta_car'] = max(5, int(real_road_dist * 2.8 + 5))
                        data['eta_moto'] = max(4, int(real_road_dist * 2.0 + 4))
                    
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
# API：觸發爬蟲（強制經由最新引導線索進行 AI 深度摘要）
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

        success_count = 0
        for safe_title, ex in new_data_dict.items():
            doc_ref = db.collection('exhibitions').document(safe_title)
            doc_snap = doc_ref.get()
            
            # 🔥 關鍵修正：保留既有的使用者星等評論，但「不沿用」舊的罐頭描述，強制用 AI 刷新
            if doc_snap.exists:
                existing_data = doc_snap.to_dict()
                ex['reviews'] = existing_data.get('reviews', [])
                ex['rating_avg'] = existing_data.get('rating_avg', 0)
            else:
                ex['reviews'] = []
                ex['rating_avg'] = 0
                
            # 🌟 啟動 Gemini 進行文章內容深度真摘要 🌟
            if ai_client:
                try:
                    raw_context = ex.get('full_text', '暫無詳細內文描述')
                    print(f"🤖 AI 正在閱讀文獻並精準摘要：{ex['title']}...")
                    
                    prompt_content = f"""
                    你是一個專業的台灣藝文活動專欄主編。請幫我閱讀下方由爬蟲抓取下來的展覽活動相關資訊與背景內文，將其提煉濃縮成一段 100 到 150 字的「活動資訊頁面精準摘要」。

                    【展覽基本資訊】
                    展覽名稱：{ex['title']}
                    展出地點：{ex['location']}

                    【活動內文與導引線索】
                    {raw_context}

                    【摘要生成鐵律】：
                    1. 必須嚴格根據上方提供的【活動內文與導引線索】進行內容提煉與擴充。請精準指出或依據主題推論這個展覽「到底在展出什麼核心東西」（例如：它的策展大綱、可能包含的藝術風格、核心亮點或歷史文物價值）。如果內文為引導線索，請直接調動你身為主編的藝文知識儲備將其擴寫完整。
                    2. 格式必須以展覽名稱開頭，並精確點出主辦單位或展出地點。
                    3. 語氣要沉穩、客觀、高質感、具備導覽性。
                    4. 直接輸出摘要本文，絕對不要帶有任何標題（例如：不需要『AI摘要：』）、不要星號、不要任何寒暄廢話。
                    """
                    
                    response = ai_client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=prompt_content
                    )
                    if response.text:
                        ex['description'] = response.text.strip()
                except Exception as ai_err:
                    print(f"⚠️ Gemini AI 生成失敗: {str(ai_err)}")
                    ex['description'] = "展覽內容豐富，歡迎前往現場參觀。"
            
            # 寫入 Firebase 前刪除超長原始文字，保持資料庫苗條乾淨
            if 'full_text' in ex:
                del ex['full_text']
                
            doc_ref.set(ex)
            success_count += 1
            
        return {
            "status": "success", 
            "message": f"同步完成！已透過真實網頁內文經由 Gemini 完成精準內容總結。同步最新展覽 {success_count} 筆。"
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}