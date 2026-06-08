import os
import base64
import json
import re
from datetime import datetime
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import gspread

from config import Config
from parser import parse_invoice
from lottery import check_lottery

# Gmail API 讀取權限
GMAIL_SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# 快取檔案路徑，用來記錄已處理過的郵件 ID，避免重複處理
PROCESSED_CACHE_FILE = "processed_emails.json"


def load_processed_emails() -> set:
    """載入已處理過的郵件 ID 列表。"""
    if os.path.exists(PROCESSED_CACHE_FILE):
        try:
            with open(PROCESSED_CACHE_FILE, 'r', encoding='utf-8') as f:
                return set(json.load(f))
        except Exception as e:
            print(f"[警告] 無法讀取已處理郵件快取: {e}")
    return set()


def save_processed_emails(processed_ids: set):
    """儲存已處理過的郵件 ID 列表。"""
    try:
        with open(PROCESSED_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(list(processed_ids), f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"[錯誤] 無法儲存郵件快取: {e}")


def get_gmail_service():
    """取得 Gmail API 服務（OAuth 2.0 授權模式）。"""
    creds = None
    # 檢查是否有先前儲存的 token.json
    if os.path.exists(Config.OAUTH_TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(Config.OAUTH_TOKEN_FILE, GMAIL_SCOPES)
        
    # 如果沒有憑證或憑證失效，重新進行登入驗證
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                # 若 refresh token 失敗則刪除它以重新進行驗證
                os.remove(Config.OAUTH_TOKEN_FILE)
                creds = None
                
        if not creds:
            if not os.path.exists(Config.OAUTH_CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"找不到 Gmail API 憑證檔案 '{Config.OAUTH_CREDENTIALS_FILE}'。\n"
                    "請至 Google Cloud Console 下載 OAuth 2.0 用戶端識別碼的 JSON 檔案，"
                    "並將其重新命名為 'credentials.json' 放置於專案根目錄中。"
                )
            
            flow = InstalledAppFlow.from_client_secrets_file(Config.OAUTH_CREDENTIALS_FILE, GMAIL_SCOPES)
            creds = flow.run_local_server(port=0)
            
        # 儲存憑證供下次使用
        with open(Config.OAUTH_TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
            
    return build('gmail', 'v1', credentials=creds)


def get_sheets_worksheet():
    """取得 Google Sheets 工作表（Service Account 授權模式）。"""
    if not os.path.exists(Config.SERVICE_ACCOUNT_FILE):
        raise FileNotFoundError(
            f"找不到 Google Sheets 金鑰檔案 '{Config.SERVICE_ACCOUNT_FILE}'。\n"
            "請至 Google Cloud Console 申請服務帳戶 (Service Account) 金鑰 JSON 檔案，"
            "並將其重新命名為 'service_account.json' 放置於專案根目錄中。"
        )
        
    gc = gspread.service_account(filename=Config.SERVICE_ACCOUNT_FILE)
    sh = gc.open_by_key(Config.SPREADSHEET_ID)
    try:
        worksheet = sh.worksheet(Config.SHEET_NAME)
    except gspread.exceptions.WorksheetNotFound:
        # 如果找不到指定的工作表（例如預設為 Sheet1 但用戶使用的是繁體中文的 '工作表1'）
        # 自動選擇試算表的第一個分頁，以防程式崩潰
        worksheet = sh.get_worksheet(0)
        print(f"[提示] 找不到名稱為 '{Config.SHEET_NAME}' 的工作表，已自動選擇第一個工作表：'{worksheet.title}'")
    return worksheet


def write_to_sheet_safely(worksheet, row_data):
    """
    安全地寫入資料到 Google Sheet。
    會自動找出第一個「非格式化且真正空白」的列，避免因為 Sheet 預設的 1000 筆空白列
    而導致資料從第 1001 行開始寫入。
    """
    # 讀取工作表所有的儲存格資料
    all_values = worksheet.get_all_values()
    
    # 移除尾部完全是空值的列
    while all_values and not any(cell.strip() for cell in all_values[-1]):
        all_values.pop()
        
    # 重複寫入檢查 (如果試算表已有資料)
    if all_values:
        invoice_num = row_data[0]
        filename = row_data[5]
        
        # 1. 檢查發票號碼是否已存在於第一欄 (只針對合法的台灣發票號碼)
        is_taiwan_invoice = bool(re.match(r'^[A-Z]{2}-\d{8}$', invoice_num))
        if is_taiwan_invoice:
            existing_numbers = [row[0] for row in all_values if len(row) > 0]
            if invoice_num in existing_numbers:
                print(f" -> [略過] 發票號碼 '{invoice_num}' 已經存在於 Google 試算表中，避免重複寫入。")
                return False
                
        # 2. 針對非標準號碼（如密碼保護或內文解析），使用「PDF 檔名」在第六欄 (Index 5) 進行重複檢查
        if filename != "郵件內文解析":
            existing_filenames = [row[5] for row in all_values if len(row) > 5]
            if filename in existing_filenames:
                print(f" -> [略過] 檔案 '{filename}' 已經存在於 Google 試算表中，避免重複寫入。")
                return False

    # 計算出真正的下一列行號
    next_row = len(all_values) + 1
    
    # 如果是空表（連標題都沒有），先寫入標題
    if next_row == 1:
        headers = ["發票號碼", "發票日期", "總金額", "來源郵件主旨", "收信時間", "PDF 檔名", "對獎結果", "處理時間"]
        worksheet.update("A1", [headers])
        next_row = 2
    elif len(all_values[0]) >= 7 and all_values[0][6] == "處理時間":
        # 如果是舊版的 7 欄格式，自動將第 7 欄改成 '對獎結果'，並新增第 8 欄為 '處理時間'
        worksheet.update("G1:H1", [["對獎結果", "處理時間"]])
        print("[系統] 偵測到舊版欄位，已自動升級欄位標題：新增「對獎結果」欄位。")
        
    # 寫入發票資料到計算出的下一列
    range_name = f"A{next_row}"
    worksheet.update(range_name, [row_data], value_input_option='USER_ENTERED')
    print(f"[成功] 資料已寫入到第 {next_row} 行: {row_data[0]} | {row_data[1]} | {row_data[2]}元")
    return True


def get_email_body_text(message) -> str:
    """從 Gmail 郵件結構中提取純文字內容。"""
    payload = message.get('payload', {})
    import re
    
    def parse_parts(parts):
        text_content = ""
        for part in parts:
            mime_type = part.get('mimeType')
            body = part.get('body', {})
            data = body.get('data')
            
            if mime_type == 'text/plain' and data:
                text_content += base64.urlsafe_b64decode(data.encode('UTF-8') if isinstance(data, str) else data).decode('utf-8', errors='ignore') + "\n"
            elif mime_type == 'text/html' and data:
                html_text = base64.urlsafe_b64decode(data.encode('UTF-8') if isinstance(data, str) else data).decode('utf-8', errors='ignore')
                html_text = re.sub(r'<(script|style).*?>.*?</\1>', '', html_text, flags=re.DOTALL | re.IGNORECASE)
                plain_text = re.sub(r'<[^>]*>', ' ', html_text)
                plain_text = plain_text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                text_content += plain_text + "\n"
            elif part.get('parts'):
                text_content += parse_parts(part['parts'])
        return text_content

    if 'parts' in payload:
        body_text = parse_parts(payload['parts'])
    else:
        body = payload.get('body', {})
        data = body.get('data')
        if data:
            body_text = base64.urlsafe_b64decode(data.encode('UTF-8') if isinstance(data, str) else data).decode('utf-8', errors='ignore')
            if payload.get('mimeType') == 'text/html':
                body_text = re.sub(r'<(script|style).*?>.*?</\1>', '', body_text, flags=re.DOTALL | re.IGNORECASE)
                body_text = re.sub(r'<[^>]*>', ' ', body_text)
                body_text = body_text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        else:
            body_text = ""
            
    return body_text


def download_attachment(service, message_id, attachment_id, filename, download_dir):
    """下載郵件附件並儲存至本地。"""
    try:
        attachment = service.users().messages().attachments().get(
            userId='me', messageId=message_id, id=attachment_id
        ).execute()
        
        file_data = base64.urlsafe_b64decode(attachment['data'].encode('UTF-8'))
        
        # 確保檔名安全
        safe_filename = "".join([c for c in filename if c.isalpha() or c.isdigit() or c in (' ', '.', '_', '-')]).rstrip()
        if not safe_filename.lower().endswith('.pdf'):
            safe_filename += '.pdf'
            
        file_path = os.path.join(download_dir, safe_filename)
        
        with open(file_path, 'wb') as f:
            f.write(file_data)
            
        return file_path
    except Exception as e:
        print(f"[錯誤] 下載附件 {filename} 失敗: {e}")
        return None


def process_invoices():
    """執行完整的主排程與自動化流程。"""
    # 1. 驗證變數設定
    if not Config.validate():
        print("[結束] 請先修復上述設定問題後再執行。")
        return
        
    # 確保 downloads 目錄存在
    download_dir = "downloads"
    os.makedirs(download_dir, exist_ok=True)
    
    # 2. 連接 Gmail API 與 Google Sheets
    print("\n[系統] 正在連接 Gmail 與 Google Sheets API...")
    try:
        gmail_service = get_gmail_service()
        worksheet = get_sheets_worksheet()
    except Exception as e:
        import traceback
        print(f"[致命錯誤] 初始化 API 連線失敗: {e}")
        traceback.print_exc()
        return
        
    # 3. 讀取快取已處理郵件
    processed_ids = load_processed_emails()
    print(f"[系統] 已載入 {len(processed_ids)} 筆已處理郵件紀錄。")
    
    # 3.5 偵測試算表是否為空。若已被手動清空，自動重設本地快取以重新匯入歷史郵件
    try:
        all_values = worksheet.get_all_values()
        while all_values and not any(cell.strip() for cell in all_values[-1]):
            all_values.pop()
        if len(all_values) <= 1 and len(processed_ids) > 0:
            print("[系統] 偵測到 Google 試算表目前無資料（已被清空），自動重設本地已處理郵件快取以重新匯入。")
            processed_ids = set()
            save_processed_emails(processed_ids)
    except Exception as e:
        print(f"[警告] 無法檢查試算表是否為空: {e}")
    
    # 4. 搜尋郵件
    query = Config.GMAIL_SEARCH_QUERY
    print(f"[搜尋] 使用 Gmail 運算子: {query}")
    
    try:
        results = gmail_service.users().messages().list(userId='me', q=query).execute()
        messages = results.get('messages', [])
    except Exception as e:
        print(f"[錯誤] 搜尋 Gmail 失敗: {e}")
        return
        
    if not messages:
        print("[資訊] 未找到符合搜尋條件的郵件。")
        return
        
    print(f"[資訊] 找到 {len(messages)} 封符合條件的郵件，開始檢查...")
    
    new_processed_count = 0
    
    # 5. 逐一處理郵件
    for msg_summary in messages:
        msg_id = msg_summary['id']
        
        # 略過已處理的郵件
        if msg_id in processed_ids:
            continue
            
        try:
            # 取得郵件詳細內容
            message = gmail_service.users().messages().get(userId='me', id=msg_id).execute()
            
            # 解析郵件標題資訊
            headers = message.get('payload', {}).get('headers', [])
            subject = "無主旨"
            date_str = ""
            for header in headers:
                if header['name'].lower() == 'subject':
                    subject = header['value']
                elif header['name'].lower() == 'date':
                    date_str = header['value']
                    
            print(f"\n[處理中] 郵件主旨: {subject} (時間: {date_str})")
            
            # 遍歷 payload parts 尋找 PDF 附件
            parts = message.get('payload', {}).get('parts', [])
            
            # 有時郵件是巢狀的，需要遞迴或扁平化檢查
            def get_attachments(parts_list):
                att_list = []
                for part in parts_list:
                    if part.get('parts'):
                        att_list.extend(get_attachments(part['parts']))
                    filename = part.get('filename')
                    mime_type = part.get('mimeType')
                    body = part.get('body', {})
                    attachment_id = body.get('attachmentId')
                    
                    # 鎖定 PDF 附件
                    if attachment_id and filename and (filename.lower().endswith('.pdf') or mime_type == 'application/pdf'):
                        att_list.append((attachment_id, filename))
                return att_list
                
            attachments = get_attachments(parts)
            
            if not attachments:
                print(f" -> 未發現 PDF 附件，嘗試從郵件內文解析...")
                body_text = get_email_body_text(message)
                
                # 從郵件主旨與本文提取發票號碼、日期、金額
                from parser import extract_invoice_number, extract_date, extract_amount
                combined_text = f"主旨: {subject}\n內文: {body_text}"
                
                invoice_num = extract_invoice_number(combined_text)
                invoice_date = extract_date(combined_text)
                invoice_amt = extract_amount(combined_text)
                
                # 如果找不到發票號碼，做一次備用強悍匹配
                if invoice_num == "無法辨識":
                    tw_match = re.search(r'(?<![A-Z])([A-Z]{2})[- ]?(\d{8})(?!\d)', combined_text)
                    if tw_match:
                        invoice_num = f"{tw_match.group(1)}-{tw_match.group(2)}"
                        
                is_taiwan_invoice = bool(re.match(r'^[A-Z]{2}-\d{8}$', invoice_num))
                
                if is_taiwan_invoice:
                    lottery_res = check_lottery(invoice_num, invoice_date)
                    row_data = [
                        invoice_num,
                        invoice_date,
                        invoice_amt,
                        subject,
                        date_str,
                        "郵件內文解析",
                        lottery_res,
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    ]
                    write_to_sheet_safely(worksheet, row_data)
                    new_processed_count += 1
                else:
                    print(f" -> [過濾] 郵件內文未偵測到合法的台灣發票號碼，已略過。")
                    
                processed_ids.add(msg_id)
                continue
                
            # 處理每個 PDF 附件
            for att_id, filename in attachments:
                print(f" -> 發現發票附件: {filename}")
                
                # 下載 PDF 到本地
                pdf_path = download_attachment(gmail_service, msg_id, att_id, filename, download_dir)
                if not pdf_path:
                    continue
                    
                # 解析 PDF
                print(f" -> 開始解析發票 PDF (模式: {Config.PARSER_MODE})...")
                invoice_data = parse_invoice(pdf_path)
                
                # 準備寫入資料
                status = invoice_data.get("status")
                invoice_num = invoice_data.get("invoice_number", "")
                
                # 判斷是否符合台灣統一發票格式 (例如 AB-12345678)
                is_taiwan_invoice = bool(re.match(r'^[A-Z]{2}-\d{8}$', invoice_num))
                
                # 若發票未加密且號碼不符合台灣發票格式，則過濾（略過寫入）
                if status != "encrypted" and not is_taiwan_invoice:
                    print(f" -> [過濾] 偵測到非台灣發票格式號碼 '{invoice_num}'，已略過寫入。")
                    try:
                        os.remove(pdf_path)
                    except OSError:
                        pass
                    continue
                
                # 處理例外狀況：加密 PDF
                if status == "encrypted":
                    print(f" -> [警告] 發票 {filename} 被密碼保護，已記錄異常狀態。")
                    row_data = [
                        "密碼保護(需手動處理)",
                        "密碼保護",
                        0,
                        subject,
                        date_str,
                        filename,
                        "無法對獎(加密)",
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    ]
                else:
                    lottery_res = check_lottery(invoice_num, invoice_data.get("date", ""))
                    row_data = [
                        invoice_num,
                        invoice_data.get("date", "無法辨識"),
                        invoice_data.get("amount", 0),
                        subject,
                        date_str,
                        filename,
                        lottery_res,
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    ]
                
                # 寫入 Google Sheet
                write_to_sheet_safely(worksheet, row_data)
                
                # 刪除本地暫存 PDF
                try:
                    os.remove(pdf_path)
                except OSError:
                    pass
                    
            # 成功處理完成，加入快取
            processed_ids.add(msg_id)
            new_processed_count += 1
            
        except Exception as e:
            print(f"[錯誤] 處理郵件 ID {msg_id} 時發生異常: {e}")
            
    # 儲存最新的快取狀態
    save_processed_emails(processed_ids)
    print(f"\n[結束] 流程執行完畢。本次共處理了 {new_processed_count} 封新發票郵件。")


if __name__ == "__main__":
    process_invoices()
