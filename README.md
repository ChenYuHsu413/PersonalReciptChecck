# 郵件電子發票自動化解析與 Google Sheets 匯入工具 (Python 實作) 🧾✨

🚀 **Demo Link**: [https://chenyu-personalreciptchecck.streamlit.app/](https://chenyu-personalreciptchecck.streamlit.app/)

---

## 🛠️ 技術堆疊 (Technology Stack)

![Python](https://img.shields.io/badge/python-3.8+-blue.svg?style=for-the-badge&logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)
![Plotly](https://img.shields.io/badge/Plotly-3F4F75?style=for-the-badge&logo=plotly&logoColor=white)
![Google Sheets API](https://img.shields.io/badge/Google_Sheets_API-34A853?style=for-the-badge&logo=google-sheets&logoColor=white)
![Gmail API](https://img.shields.io/badge/Gmail_API-EA4335?style=for-the-badge&logo=gmail&logoColor=white)
![Gemini API](https://img.shields.io/badge/Gemini_API-8E75C2?style=for-the-badge&logo=google-gemini&logoColor=white)


---

## 🎯 功能特色

1. 💻 **雙模運作**：
   * **CLI 排程模式** (`main.py`)：適合配合 Cron 或工作排程器靜默執行。
   * **Web 儀表板模式** (`app.py`)：精美的毛玻璃（Glassmorphism）暗黑風格網頁，方便視覺化管理。
2. 🔍 **精準搜尋**：使用 Gmail 運算子自動篩選發票信件。支援對無附件的純 HTML 信件（如 Uber, 外送平台等信件內文）進行回退式內文解析。
3. 🏆 **自動對獎**：透過財政部電子發票 XML 獎號資訊，自動分析發票是否中獎（支援特別獎、特獎、頭獎至六獎、以及雲端發票專屬獎等位數對獎邏輯）。
4. 🛡️ **防重複機制**：本地 `processed_emails.json` 快取與雲端 Google Sheet 資料行重複檢驗（檢查發票號碼或 PDF 檔名）雙重防護，確保不重複寫入。
5. ⚡ **安全寫入技術**：程式會自動偵測試算表，僅更新有資料的下一列，防止資料被寫入到預設 1000 空白列下方。當手動清空試算表時，本地快取會自動重設重新匯入。
6. 🤖 **多解析模式支援**：
   * `local` 模式：使用 `pdfplumber` 進行本地免費正則提取，無須外部 API。
   * `gemini` 模式：使用 Gemini 多模態 API 解析 PDF，支援複雜、多樣的發票版面，辨識度極高。
   * `claude` 模式：將提取後的文字發送給 Claude API 輸出結構化資料。
7. 🔑 **異常處理**：若發票 PDF 設有密碼保護（加密），程式會自動偵測並在試算表中寫入「**無法對獎(加密)**」，避免腳本中斷。

---

## 📁 專案管理與日誌 (Project Management)

本專案所有的開發指令與工作報告已進行系統化整理：
* 📜 **指令互動日誌**：[docs/log.md](file:///d:/AI%20Class%20ChenYu/AIClass/ReciptCheck/docs/log.md) — 詳細記錄了在此專案的開發與部署過程中，使用者對 AI 助理下達的所有操作指令。
* 📊 **工作任務報告**：[docs/工作報告.md](file:///d:/AI%20Class%20ChenYu/AIClass/ReciptCheck/docs/工作報告.md) — 詳述了包含本地部署、金額數據驗證、Git 版本控制初始化、安全性憑證遮蔽設定在內的具體工作任務報告。

---

## 🛠️ 第一步：環境建置

請先在終端機安裝專案所需要的 Python 套件：

```bash
pip install -r requirements.txt
```

---

## 🔑 第二步：Google Cloud Platform (GCP) 憑證設定

本工具需要透過 **Gmail API** 讀取您的郵件，以及透過 **Google Sheets API** 寫入試算表。請按照以下步驟完成設定：

### 1. 啟用 API 與服務
1. 開啟 [Google Cloud Console](https://console.cloud.google.com/)。
2. 建立新專案或選擇現有專案。
3. 在上方搜尋欄搜尋並啟用以下三個 API：
   * **Gmail API**
   * **Google Sheets API**
   * **Google Drive API**

### 2. 設定 Gmail API 憑證 (OAuth 2.0 用戶端識別碼)
由於個人 Gmail 不支援 Service Account 直接讀取，我們必須使用 OAuth 2.0 代表您的帳號授權。

1. 在 GCP 左側選單點選 **「API 和服務」** > **「OAuth 同意畫面」** (OAuth consent screen)。
   * 使用者類型選擇 **「外部 (External)」**，並點選「建立」。
   * 填寫必要的資訊（應用程式名稱、測試用電子郵件等），點選儲存。
   * **重要**：在 **「測試使用者 (Test Users)」** 步驟中，**必須加入您要讀取發票的 Gmail 帳號**。
2. 點選左側選單的 **「憑證」** (Credentials)。
3. 點選 **「建立憑證」** > **「OAuth 用戶端識別碼」**。
4. 應用程式類型選擇 **「桌面應用程式 (Desktop App)」**，名稱自訂，然後點選「建立」。
5. 建立完成後，下載該憑證的 JSON 檔案，將其重新命名為 **`credentials.json`**，並放置於專案根目錄中。

### 3. 設定 Google Sheets API 憑證 (服務帳戶 Service Account)
為了方便後端直接寫入 Google 試算表，我們使用 Service Account：

1. 在 GCP 的 **「憑證」** 頁面，點選 **「建立憑證」** > **「服務帳戶」** (Service Account)。
2. 輸入服務帳戶名稱，點選「建立並繼續」。
3. 角色欄位可選擇「編輯者」或留空，然後點選「完成」。
4. 在憑證頁面下方找到剛建立的服務帳戶，點選右側的 **「鉛筆編輯圖示」** 或直接點擊帳戶進入管理頁面。
5. 切換到 **「金鑰 (Keys)」** 標籤頁，點選 **「新增金鑰」** > **「建立新金鑰」**，格式選擇 **JSON**。
6. 下載該 JSON 檔案，重新命名為 **`service_account.json`**，並放置於專案根目錄中。
7. **重要：複製該金鑰 JSON 檔案中的 `client_email` 地址（格式如：your-service-account@project-id.iam.gserviceaccount.com）。**
8. **開啟您的目標 Google 試算表**，點選右上角「共用」按鈕，將剛才複製的服務帳戶 Email 加入，並給予**「編輯者」**權限。

---

## 📝 第三步：設定環境變數 (.env)

1. 將專案目錄下的 `.env.example` 複製一份並重新命名為 `.env`：
   ```bash
   cp .env.example .env
   ```
2. 編輯 `.env` 並填入您的設定：
   * **`SPREADSHEET_ID`**：填入您 Google 試算表網址中的 ID。
     *例如網址為 `https://docs.google.com/spreadsheets/d/1A2B3C4D5E6F/edit`，則 ID 為 `1A2B3C4D5E6F`。*
   * **`SHEET_NAME`**：填入您要寫入的工作表標籤名稱，預設為 `工作表1` 或 `Sheet1`。
   * **`PARSER_MODE`**：設定為 `local`、`gemini` 或 `claude`。
   * **`GEMINI_API_KEY`** / **`ANTHROPIC_API_KEY`**：若使用 `gemini` 或 `claude` 解析模式，請填入對應的 API Key。

---

## 🚀 第四步：執行方式

### 模式 A：極致美觀的 Web App 儀表板 (推薦)
本專案採用 **Streamlit** 打造數據視覺化後台。在終端機中執行：

```bash
streamlit run app.py
```

1. 啟動後，請在瀏覽器打開預設網址：**`http://localhost:8501`**
2. **立即同步**：在左側側邊欄點擊「立即同步 Gmail」按鈕，系統會啟動背景線程拉取 Gmail，並在網頁的 **即時日誌視窗** 中滾動顯示詳細的分析進度。
3. **圖表分析**：
   * **月度消費趨勢**：採用 Plotly 繪製漸層面積圖，清晰掌握您的月度支出。
   * **發票狀態佔比**：Plotly 甜甜圈圓餅圖清晰區分「中獎」、「未中獎」、「未開獎」以及「加密/無法對獎」的發票比例。
4. **即時檢索明細**：
   * 下方的明細列表支持發票號碼、金額、郵件主旨、檔名等條件的 **即時模糊搜尋** 與 **對獎狀態篩選**。

> [!NOTE]
> 首次在本地啟動同步時，系統會自動在瀏覽器中彈出 Google OAuth 登入畫面。請登入您的 Gmail 帳號授權，成功後會在本地生成 `token.json`，以後執行將全自動跳過授權。

---

### ☁️ 部署至 Streamlit Cloud (streamlit.io) 的安全憑證設定

由於本專案為公開/私有開源倉庫，**請絕對不要將憑證檔案 (`credentials.json`, `service_account.json`, `token.json` 及 `.env`) 上傳到 GitHub**。

要在 Streamlit Cloud 上順利執行發票同步，請使用 Streamlit 的 **Secrets** 功能：

1. 登入 [Streamlit Share](https://share.streamlit.io/) 並進入您的 App 管理頁面。
2. 點擊 **Settings** -> **Secrets**，並貼入以下內容：
   ```toml
   SPREADSHEET_ID = "您的 Google 試算表 ID"
   SHEET_NAME = "工作表1"
   PARSER_MODE = "local"
   
   # [選填] 您的網頁解鎖密碼，若無設定則預設密碼為 "admin"
   DASHBOARD_PASSWORD = "您自訂的解鎖密碼"
   
   # 將您的金鑰檔案內容轉為一整行的 JSON 字串貼在單引號中：
   GCP_CREDENTIALS_JSON = '{"installed":...}'
   GCP_SERVICE_ACCOUNT_JSON = '{"type":"service_account",...}'
   GCP_TOKEN_JSON = '{"token":...}'
   ```
3. 儲存設定。系統會在啟動時自動讀取這些 Secrets，並安全地在雲端虛擬環境中生成對應的檔案完成認證！



---

### 模式 B：CLI 後台靜默模式
如果您需要透過排程器定時背景執行，可以使用 CLI 腳本：

```bash
python main.py
```

* 這將全自動執行：搜尋信件 -> 解析 PDF -> XML 比對對獎 -> 寫入 Google Sheets -> 退出。
* 適合用於 Windows 工作排程器 (Task Scheduler) 或 Linux Cron Job。

---

## ⚠️ 常見問題與注意事項

1. **為什麼資料一直寫入在第 1001 列？**
   本專案採用了自動行數過濾，會自動清除尾端全空的列，並精準插入到第一筆空白列（例如第二行）。如果您仍遇到問題，可以直接在 Google 試算表中手動選取 row 2 以下的所有空白列並點選右鍵「刪除資料列」。

2. **如何處理密碼保護的發票？**
   部分電信或水電發票 PDF 會使用身分證字號或統編加密。本程式會自動辨識並寫入 `無法對獎(加密)` 狀態，並在發票號碼欄寫入 `密碼保護(需手動處理)`，以供人工檢查。

3. **如何重新導入歷史發票？**
   如果您在試算表中手動清空了所有發票明細（保留首行標題），本程式會自動偵測並清空本地的 `processed_emails.json` 快取，讓您在下一次同步時重新掃描所有歷史郵件，無需手動刪除快取檔案。
