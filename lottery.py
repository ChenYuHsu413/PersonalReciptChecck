import requests
import xml.etree.ElementTree as ET
import re
from datetime import datetime
from typing import Dict, Tuple, Any

# 快取中獎號碼，避免單次執行重複發送 Request
_lottery_cache = {}


def get_period_dates(year: int, month: int) -> Tuple[str, datetime, datetime]:
    """
    根據發票的西元年月，計算出所屬的民國發票期別、開獎日期與領獎截止日期。
    
    台灣統一發票對獎規則：
    - 01~02月：3月25日開獎，領獎期限 04/06 - 07/05
    - 03~04月：5月25日開獎，領獎期限 06/06 - 09/05
    - 05~06月：7月25日開獎，領獎期限 08/06 - 11/05
    - 07~08月：9月25日開獎，領獎期限 10/06 - 次年01/05
    - 09~10月：11月25日開獎，領獎期限 12/06 - 次年03/05
    - 11~12月：次年1月25日開獎，領獎期限 次年02/06 - 次年05/05
    """
    if month in [1, 2]:
        period_str = "01~02"
        draw_date = datetime(year, 3, 25)
        claim_deadline = datetime(year, 7, 5)
    elif month in [3, 4]:
        period_str = "03~04"
        draw_date = datetime(year, 5, 25)
        claim_deadline = datetime(year, 9, 5)
    elif month in [5, 6]:
        period_str = "05~06"
        draw_date = datetime(year, 7, 25)
        claim_deadline = datetime(year, 11, 5)
    elif month in [7, 8]:
        period_str = "07~08"
        draw_date = datetime(year, 9, 25)
        claim_deadline = datetime(year + 1, 1, 5)
    elif month in [9, 10]:
        period_str = "09~10"
        draw_date = datetime(year, 11, 25)
        claim_deadline = datetime(year + 1, 3, 5)
    elif month in [11, 12]:
        period_str = "11~12"
        draw_date = datetime(year + 1, 1, 25)
        claim_deadline = datetime(year + 1, 5, 5)
    else:
        raise ValueError(f"不合法的月份: {month}")
        
    return period_str, draw_date, claim_deadline


def fetch_lottery_numbers() -> Dict[str, Dict[str, Any]]:
    """從財政部 XML 獲取最新的中獎號碼，並解析整理成字典。"""
    global _lottery_cache
    if _lottery_cache:
        return _lottery_cache
        
    try:
        url = 'https://invoice.etax.nat.gov.tw/invoice.xml'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        
        root = ET.fromstring(response.content)
        
        for item in root.findall('.//item'):
            title = item.find('title').text  # 例如： "115年 03~04月"
            description = item.find('description').text
            
            # 移除空白，方便後續比對
            clean_title = title.replace(" ", "")
            
            # 使用 Regex 提取特別獎、特獎、頭獎、增開六獎
            special_prize = re.search(r'特別獎：(\d{8})', description)
            grand_prize = re.search(r'特獎：(\d{8})', description)
            first_prizes = re.search(r'頭獎：([\d、]+)', description)
            add_six_prizes = re.search(r'增開六獎：([\d、]+)', description)
            
            _lottery_cache[clean_title] = {
                "special": special_prize.group(1) if special_prize else "",
                "grand": grand_prize.group(1) if grand_prize else "",
                "first": first_prizes.group(1).split('、') if first_prizes else [],
                "add_six": add_six_prizes.group(1).split('、') if add_six_prizes else []
            }
    except Exception as e:
        print(f"[警告] 無法獲取統一發票中獎號碼 XML: {e}")
        
    return _lottery_cache


def check_lottery(invoice_number: str, invoice_date_str: str) -> str:
    """
    根據發票號碼與開立日期自動對獎。
    
    Args:
        invoice_number: 發票號碼 (如 "BL-23435070")
        invoice_date_str: 西元日期字串 (如 "2026-05-11")
        
    Returns:
        str: 對獎結果說明 (如 "未中獎", "中特別獎 1000 萬元", "未開獎", "已逾期")
    """
    # 1. 清理號碼，只保留 8 碼數字
    clean_num = "".join([c for c in invoice_number if c.isdigit()])
    if len(clean_num) != 8:
        return "對獎失敗(號碼不符)"
        
    # 2. 解析日期
    try:
        dt = datetime.strptime(invoice_date_str, "%Y-%m-%d")
    except Exception:
        return "對獎失敗(日期不符)"
        
    # 3. 取得期別與時間範圍
    now = datetime.now()
    try:
        period_str, draw_date, claim_deadline = get_period_dates(dt.year, dt.month)
    except Exception as e:
        return "對獎失敗(無法判斷期別)"
        
    # 4. 判斷是否開獎 / 逾期
    if now < draw_date:
        return f"未開獎 (將於 {draw_date.strftime('%Y/%m/%d')} 開獎)"
    if now > claim_deadline:
        return f"已逾期 (領獎截止於 {claim_deadline.strftime('%Y/%m/%d')})"
        
    # 5. 取得中獎號碼資料
    roc_year = dt.year - 1911
    period_title = f"{roc_year}年{period_str}月"
    
    lottery_data = fetch_lottery_numbers()
    if period_title not in lottery_data:
        return f"查無此期獎號 ({period_title})"
        
    numbers = lottery_data[period_title]
    
    # 6. 開始進行比對
    # 6.1 特別獎 (8碼全中, 1000 萬元)
    if clean_num == numbers["special"]:
        return "中特別獎 1,000 萬元"
        
    # 6.2 特獎 (8碼全中, 200 萬元)
    if clean_num == numbers["grand"]:
        return "中特獎 200 萬元"
        
    # 6.3 頭獎 (8碼全中, 20 萬元) 與各等級獎項 (比對末 N 碼)
    for first_prize in numbers["first"]:
        if len(first_prize) == 8:
            if clean_num == first_prize:
                return "中頭獎 20 萬元"
            elif clean_num[-7:] == first_prize[-7:]:
                return "中二獎 4 萬元"
            elif clean_num[-6:] == first_prize[-6:]:
                return "中三獎 10,000 元"
            elif clean_num[-5:] == first_prize[-5:]:
                return "中四獎 4,000 元"
            elif clean_num[-4:] == first_prize[-4:]:
                return "中五獎 1,000 元"
            elif clean_num[-3:] == first_prize[-3:]:
                return "中六獎 200 元"
                
    # 6.4 增開六獎 (末3碼全中, 200 元)
    for add_six in numbers["add_six"]:
        if len(add_six) == 3 and clean_num[-3:] == add_six:
            return "中增開六獎 200 元"
            
    return "未中獎"


# 測試用區塊
if __name__ == "__main__":
    print("--- 統一發票自動對獎模組測試 ---")
    # 測試一個開獎中但未中獎的號碼
    print(f"測試對獎 (2026-04-10, 12345678): {check_lottery('12345678', '2026-04-10')}")
    # 測試未來尚未開獎的發票
    print(f"測試未來 (2026-06-08, 87654321): {check_lottery('87654321', '2026-06-08')}")
    # 測試歷史已過期發票
    print(f"測試過期 (2025-10-15, 12345678): {check_lottery('12345678', '2025-10-15')}")
