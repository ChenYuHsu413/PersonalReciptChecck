import os
import sys
import io
import re
import threading
from typing import List, Dict, Any
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from datetime import datetime

# 將當前目錄加入 PATH 以利 import main & config
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import Config
from main import get_sheets_worksheet, process_invoices

app = FastAPI(title="Gmail 發票自動化對獎系統 API")

# 全域狀態與日誌快取
sync_lock = threading.Lock()
sync_in_progress = False
sync_logs: List[str] = []


class LogRedirector(io.StringIO):
    """自訂串流，用來捕獲 sys.stdout 的輸出並寫入日誌快取。"""
    def write(self, string):
        super().write(string)
        stripped = string.strip()
        if stripped:
            # 去除終端機一些轉義字元，只保留乾淨的文字
            clean_str = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', stripped) if 're' in globals() else stripped
            sync_logs.append(clean_str)


def run_sync_task():
    """在背景線程中執行 Gmail 搜尋與解析工作。"""
    global sync_in_progress, sync_logs
    
    # 確保安全重定向 stdout
    old_stdout = sys.stdout
    redirected = LogRedirector()
    sys.stdout = redirected
    
    try:
        print(f"[系統] 啟動背景同步排程 - 啟動時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        process_invoices()
        print("[系統] 背景同步作業完成！")
    except Exception as e:
        print(f"[錯誤] 背景執行失敗: {e}")
    finally:
        sys.stdout = old_stdout
        with sync_lock:
            sync_in_progress = False


@app.get("/api/invoices")
def get_invoices():
    """取得 Google Sheets 的所有發票列。"""
    if not Config.validate():
        raise HTTPException(status_code=500, detail="系統環境變數設定不完全，請先檢查 .env 檔案。")
        
    try:
        worksheet = get_sheets_worksheet()
        all_rows = worksheet.get_all_values()
        
        if not all_rows:
            return []
            
        headers = all_rows[0]
        data = []
        
        # 讀取資料行，並補齊不足的欄位避免 Index out of range
        for row in all_rows[1:]:
            d = {}
            for idx, header in enumerate(headers):
                d[header] = row[idx] if idx < len(row) else ""
            data.append(d)
            
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"無法從試算表讀取資料: {str(e)}")

def clean_amount(amt_str: str) -> int:
    """清理金額字串，移除逗號、貨幣符號、小數點等，並轉換為整數。"""
    if not amt_str:
        return 0
    # 移除千分位逗號、貨幣符號、空白與「元」
    cleaned = amt_str.replace(",", "").replace("$", "").replace("NT", "").replace("元", "").replace(" ", "")
    if "." in cleaned:
        cleaned = cleaned.split(".")[0]
    match = re.search(r'\d+', cleaned)
    if match:
        try:
            return int(match.group(0))
        except ValueError:
            pass
    return 0


@app.get("/api/stats")
def get_stats():
    """計算發票的統計數據（如總金額、各月份消費趨勢、對獎狀態分佈）。"""
    try:
        worksheet = get_sheets_worksheet()
        all_rows = worksheet.get_all_values()
        
        if len(all_rows) <= 1:
            return {
                "total_count": 0,
                "total_amount": 0,
                "status_dist": {},
                "monthly_spending": {}
            }
            
        headers = all_rows[0]
        rows = all_rows[1:]
        
        total_count = len(rows)
        total_amount = 0
        status_dist = {}
        monthly_spending = {}
        
        # 尋找關鍵欄位的索引
        col_idx = {h: idx for idx, h in enumerate(headers)}
        
        amt_idx = col_idx.get("總金額", 2)
        date_idx = col_idx.get("發票日期", 1)
        res_idx = col_idx.get("對獎結果", 6)
        
        for row in rows:
            # 1. 總金額累加
            amt_str = row[amt_idx] if amt_idx < len(row) else "0"
            total_amount += clean_amount(amt_str)
                
            # 2. 對獎狀態分佈
            res_str = row[res_idx] if res_idx < len(row) else "未知"
            # 簡化狀態分類，例如 "未開獎 (將於 2026/07/25 開獎)" -> 歸類為 "未開獎"
            status_key = "未知"
            if "未開獎" in res_str:
                status_key = "未開獎"
            elif "已逾期" in res_str:
                status_key = "已逾期"
            elif "未中獎" in res_str:
                status_key = "未中獎"
            elif "中" in res_str:
                status_key = "中獎發票"
            elif "無法對獎" in res_str or "密碼保護" in res_str:
                status_key = "無法對獎(加密)"
            else:
                status_key = res_str
                
            status_dist[status_key] = status_dist.get(status_key, 0) + 1
            
            # 3. 月份消費趨勢 (從發票日期擷取 YYYY-MM)
            date_str = row[date_idx] if date_idx < len(row) else ""
            if len(date_str) >= 7 and "-" in date_str:
                month_key = date_str[:7]  # YYYY-MM
                amt_str = row[amt_idx] if amt_idx < len(row) else "0"
                monthly_spending[month_key] = monthly_spending.get(month_key, 0) + clean_amount(amt_str)
                    
        # 將月份趨勢按時間排序
        sorted_spending = dict(sorted(monthly_spending.items()))
        
        return {
            "total_count": total_count,
            "total_amount": total_amount,
            "status_dist": status_dist,
            "monthly_spending": sorted_spending
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"無法計算統計資料: {str(e)}")


@app.post("/api/sync")
def trigger_sync(background_tasks: BackgroundTasks):
    """啟動 Gmail 與 Google Sheets 的非同步同步流程。"""
    global sync_in_progress, sync_logs
    
    with sync_lock:
        if sync_in_progress:
            return JSONResponse(status_code=400, content={"status": "already_running", "message": "同步作業目前正在執行中，請勿重複提交。"})
            
        sync_in_progress = True
        sync_logs.clear()  # 清空舊的日誌
        
    background_tasks.add_task(run_sync_task)
    return {"status": "started", "message": "已成功啟動同步作業。"}


@app.get("/api/sync/status")
def get_sync_status():
    """查詢同步作業的目前狀態以及日誌輸出。"""
    global sync_in_progress, sync_logs
    return {
        "in_progress": sync_in_progress,
        "logs": list(sync_logs)
    }


# 掛載靜態文件目錄，供前端頁面呈現
# 確保 static 目錄存在，並在最下方掛載，以便 API 路由優先
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    print("\n[系統] 正在啟動發票對獎 Web App 服務器...")
    print("[系統] 請在瀏覽器打開: http://localhost:8000")
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
