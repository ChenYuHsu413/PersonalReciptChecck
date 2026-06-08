import os
from dotenv import load_dotenv

# 載入當前目錄下的 .env 檔案
load_dotenv()

class Config:
    """設定管理類別，負責讀取並驗證環境變數。"""
    
    # Google Sheet 設定
    SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
    SHEET_NAME = os.getenv("SHEET_NAME", "Sheet1")
    
    # Gmail 搜尋條件
    GMAIL_SEARCH_QUERY = os.getenv(
        "GMAIL_SEARCH_QUERY", 
        '"發票" OR (subject:(收據 OR receipt OR invoice) has:attachment filename:pdf)'
    )
    
    # 解析模式
    PARSER_MODE = os.getenv("PARSER_MODE", "local").lower()
    
    # API 金鑰
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    
    # 憑證檔案路徑（預設在專案目錄下）
    OAUTH_CREDENTIALS_FILE = "credentials.json"
    OAUTH_TOKEN_FILE = "token.json"
    SERVICE_ACCOUNT_FILE = "service_account.json"

    @classmethod
    def setup_secrets(cls):
        """如果環境變數中存在憑證 JSON 內容且本地檔案不存在，則動態寫入檔案。"""
        import json
        
        # 1. 檢查並寫入 credentials.json
        if not os.path.exists(cls.OAUTH_CREDENTIALS_FILE):
            creds_data = os.getenv("GCP_CREDENTIALS_JSON")
            if creds_data:
                try:
                    json.loads(creds_data)
                    with open(cls.OAUTH_CREDENTIALS_FILE, "w", encoding="utf-8") as f:
                        f.write(creds_data)
                    print("[系統] 已從環境變數載入 credentials.json")
                except Exception as e:
                    print(f"[系統] 寫入 credentials.json 失敗: {e}")
                    
        # 2. 檢查並寫入 service_account.json
        if not os.path.exists(cls.SERVICE_ACCOUNT_FILE):
            sa_data = os.getenv("GCP_SERVICE_ACCOUNT_JSON")
            if sa_data:
                try:
                    json.loads(sa_data)
                    with open(cls.SERVICE_ACCOUNT_FILE, "w", encoding="utf-8") as f:
                        f.write(sa_data)
                    print("[系統] 已從環境變數載入 service_account.json")
                except Exception as e:
                    print(f"[系統] 寫入 service_account.json 失敗: {e}")

        # 3. 檢查並寫入 token.json
        if not os.path.exists(cls.OAUTH_TOKEN_FILE):
            token_data = os.getenv("GCP_TOKEN_JSON")
            if token_data:
                try:
                    json.loads(token_data)
                    with open(cls.OAUTH_TOKEN_FILE, "w", encoding="utf-8") as f:
                        f.write(token_data)
                    print("[系統] 已從環境變數載入 token.json")
                except Exception as e:
                    print(f"[系統] 寫入 token.json 失敗: {e}")

    @classmethod
    def validate(cls):
        """驗證必要的設定是否存在。"""
        cls.setup_secrets()
        errors = []
        
        if not cls.SPREADSHEET_ID or cls.SPREADSHEET_ID == "your_google_sheet_id_here":
            errors.append("未設定 SPREADSHEET_ID。請在 .env 中填入 Google Sheet ID。")
            
        if cls.PARSER_MODE not in ["local", "gemini", "claude"]:
            errors.append("PARSER_MODE 必須為 'local'、'gemini' 或 'claude'。")
            
        if cls.PARSER_MODE == "gemini" and not cls.GEMINI_API_KEY:
            errors.append("當 PARSER_MODE 為 'gemini' 時，必須提供 GEMINI_API_KEY。")
            
        if cls.PARSER_MODE == "claude" and not cls.ANTHROPIC_API_KEY:
            errors.append("當 PARSER_MODE 為 'claude' 時，必須提供 ANTHROPIC_API_KEY。")
            
        if errors:
            print("\n[設定錯誤] 請修正以下環境變數問題：")
            for err in errors:
                print(f" - {err}")
            return False
        return True

# 測試用區塊
if __name__ == "__main__":
    print("--- 載入設定測試 ---")
    print(f"Spreadsheet ID: {Config.SPREADSHEET_ID}")
    print(f"Sheet Name: {Config.SHEET_NAME}")
    print(f"Search Query: {Config.GMAIL_SEARCH_QUERY}")
    print(f"Parser Mode: {Config.PARSER_MODE}")
    Config.validate()
