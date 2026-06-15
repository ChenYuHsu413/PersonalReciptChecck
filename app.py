import os
import sys
import re
import html
import time
import queue
import threading
import pandas as pd
import streamlit as st
import plotly.express as px
from datetime import datetime

# 將當前目錄加入 PATH 以利 import main & config
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import Config
from main import get_sheets_worksheet, process_invoices

# 頁面配置
st.set_page_config(
    page_title="發票自動化對獎系統",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 載入自訂 CSS 樣式使界面更具現代感 (微暗黑/玻璃擬態風格)
st.markdown("""
    <style>
        .main {
            background-color: #0f111a;
            color: #ffffff;
        }
        .stMetric {
            background: rgba(255, 255, 255, 0.05);
            padding: 15px;
            border-radius: 10px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        div[data-testid="stMetricValue"] {
            font-size: 28px;
            font-weight: bold;
            color: #00d2ff;
        }
        h1, h2, h3 {
            color: #ffffff !important;
        }
        .stButton>button {
            background: linear-gradient(135deg, #00c6ff, #0072ff);
            color: white;
            border: none;
            padding: 8px 20px;
            border-radius: 5px;
            font-weight: bold;
            transition: all 0.3s ease;
        }
        .stButton>button:hover {
            box-shadow: 0 0 15px rgba(0, 198, 255, 0.5);
            transform: scale(1.02);
        }
        /* 發票卡片牆樣式 */
        .invoice-card {
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-left: 4px solid #00d2ff;
            border-radius: 12px;
            padding: 16px 18px;
            margin-bottom: 16px;
            min-height: 188px;
            transition: all 0.25s ease;
        }
        .invoice-card:hover {
            background: rgba(255, 255, 255, 0.07);
            box-shadow: 0 6px 18px rgba(0, 0, 0, 0.35);
            transform: translateY(-3px);
        }
        .invoice-card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 8px;
            margin-bottom: 10px;
        }
        .invoice-no {
            font-size: 15px;
            font-weight: 700;
            color: #ffffff;
            letter-spacing: 0.5px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .status-badge {
            font-size: 12px;
            font-weight: 700;
            color: #0f111a;
            padding: 3px 11px;
            border-radius: 999px;
            white-space: nowrap;
        }
        .invoice-amount {
            font-size: 26px;
            font-weight: 800;
            color: #00d2ff;
            margin-bottom: 12px;
        }
        .invoice-meta {
            font-size: 13px;
            color: #c3c9d5;
            line-height: 1.85;
        }
        .invoice-meta .label { color: #8b93a7; }
        .invoice-meta .row {
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
    </style>
""", unsafe_allow_html=True)

# ----------------- Helper Functions -----------------

def clean_amount(amt_str: str) -> int:
    """清理金額字串，移除逗號、貨幣符號、小數點等，並轉換為整數。"""
    if not amt_str:
        return 0
    cleaned = str(amt_str).replace(",", "").replace("$", "").replace("NT", "").replace("元", "").replace(" ", "")
    if "." in cleaned:
        cleaned = cleaned.split(".")[0]
    match = re.search(r'\d+', cleaned)
    if match:
        try:
            return int(match.group(0))
        except ValueError:
            pass
    return 0

def group_status(res_str: str) -> str:
    """歸類發票對獎狀態，簡化統計分類。"""
    if not res_str:
        return "未知"
    if "未開獎" in res_str:
        return "未開獎"
    elif "已逾期" in res_str:
        return "已逾期"
    elif "未中獎" in res_str:
        return "未中獎"
    elif "中" in res_str:
        return "中獎發票"
    elif "無法對獎" in res_str or "密碼保護" in res_str:
        return "無法對獎(加密)"
    return res_str

def status_style(status: str):
    """依對獎狀態回傳 (emoji, 主色) 供卡片色標使用。"""
    mapping = {
        "中獎發票": ("🏆", "#f5a623"),
        "未中獎": ("😔", "#6b7280"),
        "已逾期": ("⏰", "#ef4444"),
        "未開獎": ("⏳", "#00d2ff"),
        "無法對獎(加密)": ("🔒", "#f97316"),
        "未知": ("❔", "#9ca3af"),
    }
    return mapping.get(status, ("📄", "#9ca3af"))

def render_invoice_card(row) -> str:
    """將單筆發票 (DataFrame row) 轉為 HTML 卡片字串。"""
    emoji, color = status_style(str(row["狀態"]))
    no = html.escape(str(row.get("發票號碼", "") or "—"))
    amount = int(row.get("總金額_int", 0) or 0)
    date = html.escape(str(row.get("發票日期", "") or "—"))
    result = html.escape(str(row.get("對獎結果", "") or "—"))
    subject = html.escape(str(row.get("來源郵件主旨", "") or "—"))
    pdf = html.escape(str(row.get("PDF 檔名", "") or "—"))
    status = html.escape(str(row["狀態"]))
    return f"""
    <div class="invoice-card" style="border-left-color:{color}">
        <div class="invoice-card-header">
            <span class="invoice-no">📄 {no}</span>
            <span class="status-badge" style="background:{color}">{emoji} {status}</span>
        </div>
        <div class="invoice-amount">NT$ {amount:,}</div>
        <div class="invoice-meta">
            <div class="row"><span class="label">🗓️ 日期：</span>{date}</div>
            <div class="row" title="{result}"><span class="label">🎯 對獎：</span>{result}</div>
            <div class="row" title="{subject}"><span class="label">✉️ 主旨：</span>{subject}</div>
            <div class="row" title="{pdf}"><span class="label">📎 檔名：</span>{pdf}</div>
        </div>
    </div>
    """

class QueueStream:
    """自訂輸出串流，將 sys.stdout 重新導向至 Queue 中以利 Streamlit 讀取日誌。"""
    def __init__(self, q):
        self.q = q
    def write(self, buf):
        for line in buf.rstrip().split('\n'):
            if line.strip():
                # 去除終端機轉義字元
                clean_str = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', line.strip())
                self.q.put(clean_str)
    def flush(self):
        pass

# ----------------- Password Lock Check -----------------

def get_dashboard_password():
    # 1. 優先從環境變數讀取
    val = os.getenv("DASHBOARD_PASSWORD")
    if val is not None:
        return val
    # 2. 嘗試從 Streamlit Secrets 讀取
    try:
        import streamlit as st
        if "DASHBOARD_PASSWORD" in st.secrets:
            return str(st.secrets["DASHBOARD_PASSWORD"])
    except Exception:
        pass
    return "admin"  # 本地預設密碼

correct_password = get_dashboard_password()

# 密碼輸入框
st.sidebar.markdown("### 🔑 系統身分驗證")
password_input = st.sidebar.text_input("輸入系統檢視密碼", type="password")

if password_input != correct_password:
    st.title("🔒 統一發票自動化對獎系統")
    st.warning("⚠️ 請在左側側邊欄輸入正確的系統密碼以解鎖儀表板。")
    if correct_password == "admin":
        st.info("💡 目前系統使用預設密碼 `admin`。如果要自訂密碼，請在您的環境變數 (.env) 或 Streamlit Secrets 中設定 `DASHBOARD_PASSWORD`。")
    st.stop()

# ----------------- Sidebar & Configurations -----------------


st.sidebar.title("🧾 系統設定 & 同步")

# 先驗證環境變數
config_ok = Config.validate()

if not config_ok:
    st.sidebar.error("❌ 系統環境設定不完全")
else:
    st.sidebar.success("⚡ 系統配置狀態：就緒")
    st.sidebar.info(f"📋 工作表：{Config.SHEET_NAME}")

# 同步按鈕
if st.sidebar.button("立即同步 Gmail", disabled=not config_ok):
    st.sidebar.warning("🔄 Gmail 同步中，請勿關閉視窗...")
    
    # 建立日誌容器與 Queue
    log_container = st.empty()
    log_queue = queue.Queue()
    stream = QueueStream(log_queue)
    
    # 備份與重新導向 stdout
    old_stdout = sys.stdout
    sys.stdout = stream
    
    # 啟動同步線程
    sync_thread = threading.Thread(target=process_invoices)
    sync_thread.start()
    
    logs = []
    # 輪詢線程狀態並實時渲染日誌
    while sync_thread.is_alive():
        while not log_queue.empty():
            logs.append(log_queue.get())
        if logs:
            log_container.code("\n".join(logs[-25:]), language="text")
        time.sleep(0.5)
        
    # 線程結束後撈出剩下日誌
    while not log_queue.empty():
        logs.append(log_queue.get())
    log_container.code("\n".join(logs), language="text")
    
    # 還原 stdout
    sys.stdout = old_stdout
    st.sidebar.success("🎉 同步作業完成！")
    time.sleep(1.5)
    st.rerun()

# ----------------- Main Dashboard -----------------

st.title("📊 統一發票自動化對獎系統")
st.markdown("基於 Gmail API 與 Google Sheets API 實現的發票自動解析、對獎與雲端備份後台。")
st.markdown("---")

if not config_ok:
    st.error("### ⚠️ 系統尚未完成設定")
    st.markdown("""
        請按照以下步驟完成設定：
        
        #### 本地運行 (.env)：
        1. 在專案根目錄建立 `.env` 檔案。
        2. 填入以下必要的變數：
           * `SPREADSHEET_ID`: 您的 Google 試算表 ID。
           * `SHEET_NAME`: 匯入的工作表分頁名稱 (如 `工作表1`)。
           * `PARSER_MODE`: `local` / `gemini` / `claude` 之一。
        3. 確保專案根目錄有 `credentials.json` 與 `service_account.json`。
        
        #### Streamlit.io (Cloud) 雲端運行：
        1. 登入 Streamlit 管理後台，點進您的 App 設定。
        2. 尋找 **Secrets** 配置區塊，填入以下設定：
           ```toml
           SPREADSHEET_ID = "您的 Google 試算表 ID"
           SHEET_NAME = "工作表1"
           PARSER_MODE = "local"
           # 將金鑰檔案內容轉為一整行的 JSON 字串
           GCP_CREDENTIALS_JSON = '{"installed":...}'
           GCP_SERVICE_ACCOUNT_JSON = '{"type":"service_account",...}'
           GCP_TOKEN_JSON = '{"token":...}'
           ```
    """)
else:
    # 取得 Google Sheets 資料
    with st.spinner("正在從 Google 試算表讀取發票資料..."):
        try:
            worksheet = get_sheets_worksheet()
            all_rows = worksheet.get_all_values()
        except Exception as e:
            st.error(f"❌ 無法連接至試算表: {e}")
            all_rows = []

    if not all_rows or len(all_rows) <= 1:
        st.info("ℹ️ 試算表中目前無任何發票明細。請在左側選單點選「立即同步 Gmail」開始匯入。")
    else:
        headers = all_rows[0]
        rows = all_rows[1:]
        
        # 建立 DataFrame
        data = []
        for row in rows:
            d = {}
            for idx, header in enumerate(headers):
                d[header] = row[idx] if idx < len(row) else ""
            data.append(d)
        
        df = pd.DataFrame(data)
        
        # 清理並轉化欄位
        df["總金額_int"] = df["總金額"].apply(clean_amount)
        df["狀態"] = df["對獎結果"].apply(group_status)
        
        # 計算指標
        total_count = len(df)
        total_amount = df["總金額_int"].sum()
        
        # 中獎數計數
        winning_count = df["對獎結果"].str.contains("中").sum()
        
        # 雲端加密或無法對獎計數
        encrypted_count = df["狀態"].str.contains("無法對獎").sum()
        
        # 1. 指標卡列
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("累積讀取發票", f"{total_count} 張", help="經由 Gmail 解析並記錄之發票總數")
        col2.metric("累積消費金額", f"NT$ {total_amount:,}", f"平均每張 NT$ {int(total_amount/total_count) if total_count > 0 else 0:,}")
        col3.metric("中獎發票數", f"{winning_count} 張", delta=f"+{winning_count}" if winning_count > 0 else None, delta_color="inverse")
        col4.metric("加密/無法對獎", f"{encrypted_count} 張", help="因密碼保護或格式異常而需手動處置的發票")
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # 2. 圖表統計列
        chart_col1, chart_col2 = st.columns([3, 2])
        
        with chart_col1:
            st.subheader("📈 月度消費趨勢")
            # 依據發票日期 (YYYY-MM) 進行分組
            df["發票月份"] = df["發票日期"].apply(lambda x: x[:7] if len(str(x)) >= 7 and "-" in str(x) else "未知")
            monthly_spending = df[df["發票月份"] != "未知"].groupby("發票月份")["總金額_int"].sum().reset_index()
            monthly_spending = monthly_spending.sort_values("發票月份")
            
            if not monthly_spending.empty:
                fig_trend = px.area(
                    monthly_spending, 
                    x="發票月份", 
                    y="總金額_int", 
                    title="每月累計消費金額 (NT$)",
                    labels={"發票月份": "月份", "總金額_int": "總金額 (元)"},
                    template="plotly_dark",
                    line_shape="spline"
                )
                fig_trend.update_traces(line_color="#00d2ff", fillcolor="rgba(0, 210, 255, 0.2)")
                st.plotly_chart(fig_trend, use_container_width=True)
            else:
                st.info("無足夠的月份日期資料繪製趨勢圖。")
                
        with chart_col2:
            st.subheader("🍩 發票對獎狀態佔比")
            status_counts = df["狀態"].value_counts().reset_index()
            status_counts.columns = ["狀態", "張數"]
            
            if not status_counts.empty:
                fig_pie = px.pie(
                    status_counts, 
                    values="張數", 
                    names="狀態", 
                    hole=0.4,
                    template="plotly_dark",
                    color_discrete_sequence=px.colors.qualitative.Pastel
                )
                fig_pie.update_layout(showlegend=True)
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("無資料繪製狀態佔比圖。")
                
        st.markdown("---")
        
        # 3. 搜尋與明細列表
        st.subheader("🔍 發票明細即時搜尋")
        
        # 搜尋篩選區
        filter_col1, filter_col2 = st.columns([3, 1])
        with filter_col1:
            search_query = st.text_input("輸入關鍵字進行模糊搜尋 (如發票號碼、金額、郵件主旨、檔名)", "")
        with filter_col2:
            status_list = ["全部"] + list(df["狀態"].unique())
            selected_status = st.selectbox("狀態篩選", status_list)
            
        # 套用篩選邏輯
        filtered_df = df.copy()
        if selected_status != "全部":
            filtered_df = filtered_df[filtered_df["狀態"] == selected_status]
            
        if search_query:
            q = search_query.lower()
            filtered_df = filtered_df[
                filtered_df["發票號碼"].str.lower().str.contains(q) |
                filtered_df["總金額"].str.lower().str.contains(q) |
                filtered_df["來源郵件主旨"].str.lower().str.contains(q) |
                filtered_df["PDF 檔名"].str.lower().str.contains(q)
            ]
            
        # 顯示明細
        st.write(f"🔍 找到 {len(filtered_df)} 筆符合條件的發票：")

        if filtered_df.empty:
            st.info("😶 沒有符合條件的發票，試試其他關鍵字或調整狀態篩選。")
        else:
            # 依發票日期由新到舊排序，較新發票優先呈現
            display_df = filtered_df.sort_values("發票日期", ascending=False)

            # 檢視模式切換
            view_mode = st.radio(
                "檢視模式",
                ["🪪 卡片檢視", "📋 表格檢視"],
                horizontal=True,
                label_visibility="collapsed"
            )

            if view_mode == "📋 表格檢視":
                # 隱藏不需要對外的計算列
                display_columns = [c for c in display_df.columns if c not in ["總金額_int", "狀態", "發票月份"]]
                st.dataframe(
                    display_df[display_columns],
                    use_container_width=True,
                    hide_index=True
                )
            else:
                # 卡片牆（含分頁，避免一次渲染過多卡片）
                PAGE_SIZE = 12
                COLS_PER_ROW = 3
                total = len(display_df)
                total_pages = (total - 1) // PAGE_SIZE + 1

                page = 1
                if total_pages > 1:
                    page = st.number_input(
                        f"頁數（共 {total_pages} 頁）",
                        min_value=1, max_value=total_pages, value=1, step=1
                    )

                start = (page - 1) * PAGE_SIZE
                page_df = display_df.iloc[start:start + PAGE_SIZE]

                cards = [render_invoice_card(r) for _, r in page_df.iterrows()]
                for i in range(0, len(cards), COLS_PER_ROW):
                    cols = st.columns(COLS_PER_ROW)
                    for j, card_html in enumerate(cards[i:i + COLS_PER_ROW]):
                        cols[j].markdown(card_html, unsafe_allow_html=True)

                st.caption(f"顯示第 {start + 1}–{min(start + PAGE_SIZE, total)} 筆，共 {total} 筆發票。")
