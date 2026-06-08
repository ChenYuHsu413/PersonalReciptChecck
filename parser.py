import re
import os
import pypdf
import pdfplumber
from typing import Dict, Any, Optional
from config import Config

# Pydantic 用於 Gemini Structured Output
try:
    from pydantic import BaseModel, Field
    class InvoiceSchema(BaseModel):
        invoice_number: str = Field(description="發票號碼，台灣格式通常為兩碼大寫英文加上8碼數字，例如 AB-12345678 或 AB12345678")
        date: str = Field(description="發票開立日期，格式為 YYYY-MM-DD，如果是民國年（如 115年），請轉換為西元（如 2026-06-08）")
        amount: int = Field(description="發票總金額（含稅），必須是整數數字，去除所有逗號或符號")
except ImportError:
    # 預防沒有安裝 pydantic 時的備用
    InvoiceSchema = None


def check_pdf_encrypted(pdf_path: str) -> bool:
    """
    檢查 PDF 檔案是否被密碼保護（加密）。
    
    Args:
        pdf_path: PDF 檔案的絕對路徑。
        
    Returns:
        bool: True 代表已加密，False 代表未加密。
    """
    try:
        with open(pdf_path, 'rb') as f:
            reader = pypdf.PdfReader(f)
            return reader.is_encrypted
    except Exception as e:
        print(f"[錯誤] 無法檢查 PDF 加密狀態: {e}")
        return False


def extract_invoice_number(text: str) -> str:
    """從純文字中提取發票號碼，支援台灣與國際格式。"""
    # 1. 優先匹配台灣電子發票格式 (2位大寫英文 + 8位數字，例如 AB-12345678 或 AB12345678)
    tw_match = re.search(r'(?<![A-Z])([A-Z]{2})[- ]?(\d{8})(?!\d)', text)
    if tw_match:
        return f"{tw_match.group(1)}-{tw_match.group(2)}"
        
    # 2. 搜尋常見發票號碼關鍵字後面的值 (如 Invoice No, Invoice #, INV-XXXXX)
    patterns = [
        r'(?:Invoice\s*No\.?|Invoice\s*#|Invoice\s*Number|Receipt\s*No\.?|Receipt\s*#)[^\S\r\n]*:?[^\S\r\n]*([A-Z0-9-_#]{4,15})',
        r'(?<![A-Z0-9])(INV-\d{4,8})(?!\d)',
        r'(?<![A-Z0-9])(INV\d{4,8})(?!\d)'
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
            
    return "無法辨識"


def extract_date(text: str) -> str:
    """從純文字中提取開立日期，支援多種西元與民國格式，防止跨國格式混淆。"""
    # 1. 搜尋西元格式 YYYY-MM-DD 或 YYYY/MM/DD (如 2026-06-08)
    ymd_match = re.search(r'(?<!\d)(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)', text)
    if ymd_match:
        year, month, day = int(ymd_match.group(1)), int(ymd_match.group(2)), int(ymd_match.group(3))
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{year:04d}-{month:02d}-{day:02d}"

    # 2. 搜尋西元格式 DD-MM-YYYY 或 DD/MM/YYYY (例如澳洲/英國發票常用: 08/06/2026)
    dmy_match = re.search(r'(?<!\d)(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})(?!\d)', text)
    if dmy_match:
        day, month, year = int(dmy_match.group(1)), int(dmy_match.group(2)), int(dmy_match.group(3))
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{year:04d}-{month:02d}-{day:02d}"

    # 3. 搜尋民國年中文格式 (例如 115年06月08日 或 115年6月8日)
    roc_zh_match = re.search(r'(\d{2,3})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日', text)
    if roc_zh_match:
        roc_year, month, day = int(roc_zh_match.group(1)), int(roc_zh_match.group(2)), int(roc_zh_match.group(3))
        if 1 <= month <= 12 and 1 <= day <= 31:
            ce_year = roc_year + 1911 if roc_year < 1911 else roc_year
            return f"{ce_year:04d}-{month:02d}-{day:02d}"

    # 4. 搜尋民國年斜線格式 (例如 115/06/08，限制年份必須是 3 位數，避免與西元日/月混淆)
    roc_slash_match = re.search(r'(?<!\d)(\d{3})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)', text)
    if roc_slash_match:
        roc_year, month, day = int(roc_slash_match.group(1)), int(roc_slash_match.group(2)), int(roc_slash_match.group(3))
        if 1 <= month <= 12 and 1 <= day <= 31:
            ce_year = roc_year + 1911
            return f"{ce_year:04d}-{month:02d}-{day:02d}"

    return "無法辨識"


def extract_amount(text: str) -> int:
    """從純文字中提取發票總金額（含稅），支援千分位逗號與小數點。"""
    # 尋找金額關鍵字後面的數字 (可帶有千分位逗號，以及美分小數點，例如 $1,250.00)
    patterns = [
        r'(?:總計|總金額|合計|應付總額|實付金額|應付金額|Total\s*Amount|Grand\s*Total|Amount\s*Due|Total)[^\d\n]*?([\d,]+(?:\.\d{2})?)'
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            # 取得最後一個匹配項（通常總金額會出現在文件尾端）
            last_match = matches[-1]
            # 如果包含小數點，則將小數點後的美分/角除掉（只取整數部分）
            if '.' in last_match:
                last_match = last_match.split('.')[0]
            clean_val = last_match.replace(",", "")
            if clean_val.isdigit():
                return int(clean_val)
                
    return 0


def parse_invoice_local(pdf_path: str) -> Dict[str, Any]:
    """
    【本地解析模式】使用 pdfplumber 讀取 PDF 文字，並以更強健的提取邏輯獲取資訊。
    
    Args:
        pdf_path: PDF 檔案路徑。
        
    Returns:
        Dict[str, Any]: 包含 'invoice_number'、'date'、'amount' 的字典。
    """
    result = {
        "invoice_number": "無法辨識",
        "date": "無法辨識",
        "amount": 0
    }
    
    try:
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
                    
        if not text.strip():
            print(f"[警告] {os.path.basename(pdf_path)} 本地讀取無文字，可能是掃描檔/圖片型 PDF。")
            return result
            
        result["invoice_number"] = extract_invoice_number(text)
        result["date"] = extract_date(text)
        result["amount"] = extract_amount(text)
                    
        return result
        
    except Exception as e:
        print(f"[錯誤] 本地解析 PDF 失敗: {e}")
        return result


def parse_invoice_gemini(pdf_path: str) -> Dict[str, Any]:
    """
    【Gemini API 解析模式】使用 Google GenAI SDK 直接上傳 PDF 進行結構化提取。
    
    Args:
        pdf_path: PDF 檔案路徑。
        
    Returns:
        Dict[str, Any]: 包含發票資訊的字典。
    """
    result = {"invoice_number": "無法辨識", "date": "無法辨識", "amount": 0}
    
    if not Config.GEMINI_API_KEY:
        print("[錯誤] 未設定 GEMINI_API_KEY，無法使用 Gemini 解析模式。")
        return result

    try:
        from google import genai
        from google.genai import types
        
        # 初始化 Gemini Client
        client = genai.Client(api_key=Config.GEMINI_API_KEY)
        
        # 讀取 PDF 二進位資料
        with open(pdf_path, 'rb') as f:
            pdf_bytes = f.read()
            
        prompt = """
        請分析這份 PDF 電子發票，並精確提取出以下資訊：
        1. 發票號碼 (invoice_number)：格式為 XX-12345678。
        2. 開立日期 (date)：格式為 YYYY-MM-DD，若發票上為民國年請自行加上 1911 轉換為西元年。
        3. 總金額 (amount)：整數，代表發票的實付總金額（含稅）。
        
        請嚴格按照規定的 JSON Schema 格式回傳。
        """
        
        # 呼叫 Gemini 2.5/1.5 模型（這兩個模型皆支援 PDF 多模態輸入與 Structured Outputs）
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                types.Part.from_bytes(
                    data=pdf_bytes,
                    mime_type='application/pdf',
                ),
                prompt
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=InvoiceSchema,
                temperature=0.1
            ),
        )
        
        # 解析回傳的 JSON 字串
        import json
        data = json.loads(response.text)
        result["invoice_number"] = data.get("invoice_number", "無法辨識")
        result["date"] = data.get("date", "無法辨識")
        result["amount"] = int(data.get("amount", 0))
        return result
        
    except Exception as e:
        print(f"[錯誤] Gemini API 解析失敗: {e}。嘗試降級使用本地解析。")
        return parse_invoice_local(pdf_path)


def parse_invoice_claude(pdf_path: str) -> Dict[str, Any]:
    """
    【Claude API 解析模式】先用 pdfplumber 提取文字，再將文字發送至 Claude API 取得結構化 JSON。
    
    Args:
        pdf_path: PDF 檔案路徑。
        
    Returns:
        Dict[str, Any]: 包含發票資訊的字典。
    """
    result = {"invoice_number": "無法辨識", "date": "無法辨識", "amount": 0}
    
    if not Config.ANTHROPIC_API_KEY:
        print("[錯誤] 未設定 ANTHROPIC_API_KEY，無法使用 Claude 解析模式。")
        return result

    try:
        # 先利用 pdfplumber 提取純文字
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
                    
        if not text.strip():
            print(f"[警告] Claude 模式：{os.path.basename(pdf_path)} 為空或掃描檔，無法以純文字方式傳給 Claude。")
            return parse_invoice_local(pdf_path)
            
        import anthropic
        client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
        
        prompt = f"""
        請從以下發票文字中提取關鍵資訊，並以 JSON 格式回傳。
        發票文字內容：
        {text}
        
        要求 JSON 格式必須如下，不要包含 markdown 標籤或任何多餘文字：
        {{
            "invoice_number": "XX-XXXXXXXX", // 發票號碼
            "date": "YYYY-MM-DD",           // 西元開立日期（例如 2026-06-08，若是民國年請自行轉換）
            "amount": 1250                 // 總計金額（整數，無逗號）
        }}
        """
        
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1000,
            temperature=0,
            system="你是一個專業的發票數據解析助手，只回傳純 JSON 字串，不得包含 markdown 包裝 (如 ```json)。",
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        # 解析回傳的 JSON
        import json
        response_text = message.content[0].text.strip()
        data = json.loads(response_text)
        
        result["invoice_number"] = data.get("invoice_number", "無法辨識")
        result["date"] = data.get("date", "無法辨識")
        result["amount"] = int(data.get("amount", 0))
        return result
        
    except Exception as e:
        print(f"[錯誤] Claude API 解析失敗: {e}。嘗試降級使用本地解析。")
        return parse_invoice_local(pdf_path)


def parse_invoice(pdf_path: str) -> Dict[str, Any]:
    """
    整合解析進入點，根據 config 中的設定選擇解析模式。
    """
    # 優先檢查是否加密
    if check_pdf_encrypted(pdf_path):
        print(f"[警告] 檔案 {os.path.basename(pdf_path)} 已被密碼保護，將略過解析。")
        return {
            "invoice_number": "密碼保護",
            "date": "密碼保護",
            "amount": 0,
            "status": "encrypted"
        }
        
    mode = Config.PARSER_MODE
    if mode == "gemini":
        return parse_invoice_gemini(pdf_path)
    elif mode == "claude":
        return parse_invoice_claude(pdf_path)
    else:
        return parse_invoice_local(pdf_path)


# 測試用區塊
if __name__ == "__main__":
    # 這裡可以用一個測試發票路徑來測試
    print("--- 測試解析功能 ---")
    # test_pdf = "test.pdf"
    # if os.path.exists(test_pdf):
    #     print(parse_invoice(test_pdf))
