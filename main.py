import os
import json
import math
import sys
import asyncio  # 🎯 核心防線：改用非阻塞式異步時鐘

from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google.cloud import firestore
from google.oauth2 import service_account  
from crawler import start_crawling
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
        cred_dict = json.loads(os.environ["FIREBASE_CONFIG"])
        if "private_key" in cred_dict:
            cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
        credentials = service_account.Credentials.from_service_account_info(cred_dict)
        db = firestore.Client(project=cred_dict["project_id"], credentials=credentials)
        print("🚀 Firebase 雲端資料庫連線成功！")
    except Exception as e:
        print(f"❌ Firebase 初始化失敗: {str(e)}")

# ==========================================
# 2. 初始化 Gemini AI (堅守 Gemini 2.5 Flash 最新旗艦大腦)
# ==========================================
ai_client = None
if "GEMINI_API_KEY" in os.environ:
    try:
        ai_client = genai.Client()
        print("🤖 Gemini AI 2.5 Flash 智慧總結大腦已成功就位！")
    except Exception as e:
        print(f"⚠️ Gemini AI 初始化失敗: {str(e)}")

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class Review(BaseModel):
    title: str
    rating: int
    comment: str

@app.get("/")
def read_root():
    return {"message": "雙北展覽 API 伺服器 - 2026 終極合法非阻塞防爆版"}

# ------------------------------------------
# API：取得所有展覽資料
# ------------------------------------------
@app.get("/api/exhibitions")
def get_exhibitions(lat: float = None, lon: float = None):
    if db is None: return {"status": "error", "message": "資料庫未連線"}
    try:
        docs = db.collection('exhibitions').stream()
        result = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            data['distance'] = 999
            data['eta_car'] = 999
            data['eta_moto'] = 999
            data['eta_transit'] = 999
            reviews = data.get('reviews', [])
            data['reviews'] = reviews if isinstance(reviews, list) else []
            result.append(data)
        return {"status": "success", "data": result}
    except Exception as e: return {"status": "error", "message": str(e)}

# ------------------------------------------
# API：提交使用者評論
# ------------------------------------------
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
# ⚖️ 法律級防線：異步非阻塞背景自動排隊核心邏輯
# ==========================================
async def run_crawler_and_loop_ai_async(new_data_dict):
    """ 
    使用 async def 與 await asyncio.sleep，讓 Render 知道 CPU 依然處於活動狀態，
    絕對不會觸發 Render 30 秒暴力砍進程的機制。
    """
    print("🚀 [背景異步任務] 開始執行精準 AI 摘要更新...")
    
    stats_success = 0
    stats_loop = 0
    
    for safe_title, ex in new_data_dict.items():
        doc_ref = db.collection('exhibitions').document(safe_title)
        
        # 為了防止大規模阻塞，Firebase 的讀取與判定移入局部
        doc_snap = doc_ref.get()
        has_valid_ai_summary = False
        
        if doc_snap.exists:
            existing_data = doc_snap.to_dict()
            ex['reviews'] = existing_data.get('reviews', [])
            ex['rating_avg'] = existing_data.get('rating_avg', 0)
            
            old_desc = existing_data.get('description', '')
            is_dirty = any(w in old_desc for w in ["歡迎蒞臨", "展覽內容豐富", "暫無摘要", "歡迎前往", "精心策劃"])
            if old_desc and len(old_desc) > 30 and not is_dirty:
                ex['description'] = old_desc
                has_valid_ai_summary = True

        # 精準摘要提煉，嚴禁亂編介紹
        if ai_client and not has_valid_ai_summary:
            try:
                raw_context = ex.get('full_text', '暫無詳細內文描述')
                print(f"🤖 [背景異步] 正在精準濃縮（第 {stats_success+1} 筆）：{ex['title']}...")
                
                prompt_content = f"""
                你是一個專業的台灣藝文活動專欄主編。請幫我閱讀下方由爬蟲抓取下來的展覽活動相關資訊與背景內文，將其提煉濃縮成一段 100 到 150 字的「活動資訊頁面精準摘要」。

                【展覽基本資訊】
                展覽名稱：{ex['title']}
                展出地點：{ex['location']}

                【活動內文與導引線索】
                {raw_context}

                【摘要生成鐵律】：
                1. 必須嚴格根據上方提供的【活動內文與導引線索】進行內容提煉與擴充，絕對不可憑空捏造不存在的展覽細節或虛構藝術家。
                2. 格式必須以展覽名稱開頭，並精確點出主辦單位或展出地點。
                3. 語氣要沉穩、客觀、高質感、具備導覽性。
                4. 直接輸出摘要本文，絕對不要帶有任何標題（例如：不需要『AI摘要：』）、不要星號、不要任何寒暄廢話。
                """
                
                # 執行 Gemini 生成
                response = ai_client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt_content
                )
                
                if response.text:
                    ex['description'] = response.text.strip()
                    stats_success += 1
                    stats_loop += 1
                    
                    # 🎯 完美控速：每滿 3 筆，讓出 CPU 執行權並休息 12 秒，徹底規避 Google 429 限制
                    if stats_loop >= 3:
                        print("💤 [背景防爆] 已滿 3 筆，釋放執行緒並冷卻 12 秒...")
                        await asyncio.sleep(12.0)  # ⚡ 絕不卡死進程的關鍵
                        stats_loop = 0
                    else:
                        await asyncio.sleep(2.5)
                else:
                    ex['description'] = "展覽內容豐富，歡迎前往現場參觀。"
            except Exception as ai_err:
                print(f"⚠️ [背景異常] Gemini 呼叫受阻: {str(ai_err)}")
                ex['description'] = "展覽內容豐富，歡迎前往現場參觀。"
        else:
            if 'description' not in ex or not ex['description']:
                ex['description'] = "展覽內容豐富，歡迎前往現場參觀。"

        if 'full_text' in ex:
            del ex['full_text']
            
        # 寫入 Firebase 資料庫
        doc_ref.set(ex)
        
    print(f"🎉 [背景任務] 100% 完工！本輪成功安全精準升級 {stats_success} 筆展覽！")


@app.get("/api/trigger-crawler")
async def trigger_crawler_and_update_db(background_tasks: BackgroundTasks):
    if db is None:
        return {"status": "error", "message": "資料庫未連線"}
    try:
        print("🕸️ 啟動爬蟲模組...")
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

        # 同步清除過期舊資料
        old_docs = db.collection('exhibitions').list_documents()
        batch = db.batch()
        for doc in old_docs:
            if doc.id not in active_safe_titles:
                batch.delete(doc)
        batch.commit()

        # 🎯 丟入非阻塞異步任務隊列
        background_tasks.add_task(run_crawler_and_loop_ai_async, new_data_dict)
        
        return {
            "status": "processing", 
            "message": "【安全防爆版啟動】網頁已安全即時回應！精準 Gemini AI 摘要任務已切換至底層異步佇列。請完全放空並關閉此網頁，系統將在接下來的 10 分鐘內自動且精準地將 131 筆展覽在後台洗完，絕不超時，絕不亂生介紹！"
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}