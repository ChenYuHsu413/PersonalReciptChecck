# 使用者互動指令日誌 (Interaction Log)

本文件記錄了使用者在專案開發與部署過程中，對 AI 助理下達的所有指令與處理動作。

## 📋 指令紀錄時間軸

### 1. 服務部署指令
* **時間**: 2026-06-08 10:36:09
* **使用者指令**: `幫我跑在localhost`
* **處理動作**:
  * 檢查專案依賴套件是否已安裝完成（確認 `requirements.txt` 中的套件均已滿足）。
  * 透過背景工作執行 `python app.py` 啟動 FastAPI 網頁伺服器（預設監聽 `http://127.0.0.1:8000`）。
  * 提供使用者在瀏覽器中訪問 Web 儀表板的說明。

---

### 2. 數據查詢與疑問
* **時間**: 2026-06-08 10:38:07
* **使用者指令**: `還是一樣 為什麼預設是十萬`
* **處理動作**:
  * 執行測試程式直接讀取使用者設定的 Google 試算表內容。
  * 撈取並解析出目前已匯入的 10 筆發票明細（包含 Apple 收據 NT$ 44,900、Klook 電子發票 NT$ 43,900 等高額發票，總計 NT$ 100,445）。
  * 向使用者澄清該金額非系統寫死的「預設值」，而是試算表發票金額加總的真實計算結果。
  * 提供使用者如何在試算表中手動修正發票金額的教學。

---

### 3. 指令確認與回饋
* **時間**: 2026-06-08 10:39:56
* **使用者指令**: `哦是我自己自己看錯了`
* **處理動作**:
  * 確認系統統計邏輯正常，並表示隨時能為後續的功能調整提供協助。

---

### 4. 版本控制與 GitHub 設定
* **時間**: 2026-06-08 10:44:20
* **使用者指令**: `https://github.com/ChenYuHsu413/PersonalReciptChecck.git 幫我做github設定`
* **處理動作**:
  * **安全性保護**：首要建立了關鍵的 `.gitignore` 檔案，徹底排除 `.env`、`credentials.json`、`service_account.json`、`token.json`、`processed_emails.json` 及下載暫存資料夾，避免敏感金鑰外洩。
  * **Git 初始化**：執行 `git init` 初始化專案目錄。
  * **設定 Remote**：添加 GitHub 遠端倉庫位址 `https://github.com/ChenYuHsu413/PersonalReciptChecck.git`。
  * **安全暫存**：執行 `git add .` 將過濾後的安全專案檔案加入暫存區。

---

### 5. 個人化設定與文件重構（本階段執行中）
* **時間**: 2026-06-08 10:47:52
* **使用者指令**: 
  * `可以幫我設定嗎 user name 是ChenYuHsu413`
  * `幫我在Readme的開頭加入Demo link 連結，格式為github預設deploy的格式`
  * `幫我整理我在這份專案中對你下過的所有指令，存放在docs/log.md裡面`
  * `針對這一份log生成一份工作報告.md詳述內容`
  * `這些也幫我寫到readme裡面`
  * `readme幫我美化得漂亮一點，可以加入圖示寫我用到什麼技術之類的，多一點圖示`
* **處理動作**:
  * 設定 Git 本地庫 `user.name` 為 `ChenYuHsu413`，以及 `user.email` 為 `ChenYuHsu413@users.noreply.github.com`。
  * 建立 `docs/log.md` 指令日誌。
  * 建立 `docs/工作報告.md` 詳細描述專案的歷程、現況與安全性考量。
  * 修改並大幅美化 `README.md`，加入各種精美 Badges、系統架構圖、Demo 連結與相關文檔連結。

---

### 6. Streamlit Cloud 錯誤排除
* **時間**: 2026-06-08 10:57:06
* **使用者指令**: `streamlit上面有錯誤`
* **處理動作**:
  * 排查發現 `app.py` 中載入自訂 CSS 樣式的 `st.markdown()` 被錯誤地使用了不存在的參數 `unsafe_view_check=True`。
  * 將該參數更正為正確的 `unsafe_allow_html=True`。
  * 將修復後的 [app.py](file:///d:/AI%20Class%20ChenYu/AIClass/ReciptCheck/app.py) 進行本地 commit 並推送至 GitHub，完成修復。

---

### 7. Streamlit Secrets 讀取與設定不全排查
* **時間**: 2026-06-08 11:04:21
* **使用者指令**: `我已經照做了但他還是說系統設定不完全，我漏掉什麼設定了嗎`
* **處理動作**:
  * 排查發現 Streamlit Cloud 平台執行時，寫入在側邊設定的 Secrets (如 `SPREADSHEET_ID` 等) 有時不會自動同步映射到作業系統的環境變數 (`os.environ`) 中，導致原先以 `os.getenv()` 取得變數的程式邏輯回傳為 `None`。
  * 修改了 [config.py](file:///d:/AI%20Class%20ChenYu/AIClass/ReciptCheck/config.py)，在 `setup_secrets()` 中增加 fallback 機制：若在 `os.getenv()` 讀取為 `None` 時，自動調用 Streamlit 內建的 `st.secrets` 機制取得對應值。
  * 將修改後的程式碼推送至 GitHub 倉庫（Commit 號：`5e67613`），完成雲端環境的完美相容。


