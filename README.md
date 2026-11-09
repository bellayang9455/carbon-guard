# 碳鏈 CarbonGuard — 完整可執行專案

繁體中文前端 + FastAPI 後端 + SQLite + Isolation Forest。適合開發、專題與內部概念驗證；部署與訓練由你自行操作。本專案不會自動上線，也沒有預設密碼或正式資料。

## 1. 執行需求

- Python 3.12（已驗證版本）
- 瀏覽器 Chrome / Edge / Firefox
- 不需要 Node.js，也不需要外部 AI API Key
- 安裝依賴時需要網路；執行介面與模型不依賴外部服務

## 2. 啟動（Windows）

在解壓縮後的 carbon-guard 目錄開啟 PowerShell：

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe scripts\configure.py
.venv\Scripts\python.exe run.py add-user admin --role admin
.venv\Scripts\python.exe run.py
```

建立帳號時輸入至少 12 字元的密碼，輸入內容不回顯。開啟 **http://127.0.0.1:8000**，使用剛建立的帳號登入。123456789123

## 3. 啟動（macOS / Linux）

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/configure.py
.venv/bin/python run.py add-user admin --role admin
.venv/bin/python run.py
```

`configure.py` 只會建立新 .env，不會覆寫舊密鑰。run.py 自動載入 .env；環境變數的優先序較高。不要直接雙擊 frontend/index.html：前端必須透過後端伺服器提供，才能使用登入與 API。

## 4. 建立供應商帳號

```bash
# Windows 請改用 .venv\Scripts\python.exe
.venv/bin/python run.py add-user supplier01 --role supplier --supplier "示範供應商"
```

管理員可查看所有資料、訓練模型、驗證完整性及追加人工覆核；供應商只能新增、查看及匯出自己所屬供應商的資料。供應商名稱是本版本的租戶識別值，建立帳號時務必正確指定；不得讓不同公司共用名稱。帳號管理目前提供本機建立指令；停用、重設密碼及 SSO 可依需求擴充。

## 5. 完整操作流程

1. 管理員登入後進入「AI 異常偵測」。
2. 選擇 samples/training-demo.csv，輸入訓練備註，點選「上傳並訓練」。這是 120 筆合成資料，只用於測試流程。
3. 使用「新增排放資料」單筆上傳，或選擇 samples/upload-demo.csv 批次匯入。範例中包含正常值與明顯離群值。
4. 至資料頁查看評分，管理員可點選「詳情 / 覆核」，追加 confirmed / rejected / pending 及原因。覆核事件存於稽核頁，不會覆寫原始資料。
5. 進入「資料完整性」執行驗證；至「資安與稽核」讀取操作事件。
6. 可匯出目前帳號可見的全部紀錄。列表每頁 100 筆，搜尋、篩選及圖表統計均清楚標示為本頁範圍。

CSV 欄位與順序：

```csv
supplier,month,scope,emission,production
示範供應商,2026-11,1,105.2,1000
```

emission 單位固定為 tCO₂e；production 必須先統一成可比較的單位。scope 為 1、2、3。CSV 支援 UTF-8 / UTF-8 BOM 及引號欄位。檔案最多 2 MB，紀錄匯入最多 1,000 筆；訓練最多 10,000 筆、至少 32 筆。JSON 請求也受 2 MB 上限限制。

## 6. AI 模型說明

- 使用 scikit-learn IsolationForest，200 棵樹，max_samples=min(256,樣本數)，random_state=42。
- 特徵：log1p(排放量)、log1p(產量)、log1p(排放強度)、排放範疇。
- contamination 控制預期離群比例，預設 0.05；以模型 predict 判斷是否需要覆核。
- 顯示分數為負 score_samples，越高越離群，**不是錯誤機率，也不是碳排合規判定**。
- 首次執行沒有模型，可先存資料，評分為空值。
- 模型版本、參考樣本與訓練參數存於資料庫，以 HMAC 保護；重啟時使用相同版本的 scikit-learn 重建模型，沒有載入任意 pickle 的風險。
- 上傳時固定保存當時的模型版本與評分；重訓不會改寫既有紀錄。/api/predict 可用新模型評估單筆資料。
- 訓練前請由人員確認資料品質，依產業 / 產品 / 單位分組。本版共用一個模型，適合單一可比較群組；多產業使用前應擴充模型路由。數字型範疇特徵僅是基礎實作，多類別建模可改採獨立模型或 One-Hot。
- 請自行以時間切分資料驗證誤報率、召回率及漂移；合成資料測試結果不能代表正式準確率。

## 7. 完整性與安全邊界

已實作：

- 密碼 PBKDF2-HMAC-SHA256，600,000 次迭代與每帳號隨機鹽。
- 8 小時 Session，伺服器僅存 Token 的 SHA-256；Cookie 使用 HttpOnly / SameSite=Strict。
- 寫入 API 需要 CSRF Token；管理員操作與供應商租戶權限均由後端驗證。
- 登入每來源 IP 五分鐘最多 10 次嘗試，成功後清除計數；請求上限 2 MB。
- 參數化 SQL、Pydantic 輸入檢核、前端 HTML 跳脫、CSV 公式注入處理及 CSP 等安全標頭。
- 排放紀錄、上傳事件、登入成功、模型訓練與人工覆核寫入 SHA-256 雜湊鏈；指紋由 HMAC 驗證，偵測失敗時拒絕追加紀錄。
- 寫入使用 SQLite 交易；沒有刪除或原地編輯排放紀錄的 API。

雜湊不等於加密，也不能阻擋擁有資料庫管理權的人直接刪除資料。HMAC 也不是公開可驗證的數位簽章。若密鑰和資料庫同時被掌握，仍可偽造。整庫回滾、尾端刪除及歷史模型回滾需要獨立可信的外部錨點與版本策略。

請定期執行：

```bash
.venv/bin/python run.py checkpoint
```

輸出包含 records / audit 的筆數、鏈頭與驗證結果。將輸出保存到獨立 WORM 儲存或簽章時間戳服務，並監控驗證結果；不要只存回同一台機器。工具目前輸出 checkpoint，不會自動連接 WORM 或比較歷史快照。

CARBON_SECRET 不可提交到 Git，不能放在前端。正式環境請使用密鑰管理服務；變更密鑰需要完整的 HMAC 遷移流程，直接更換會使舊資料驗證失敗。資料庫本身未加密，請使用加密磁碟、最小檔案權限、備份及還原測試。用戶與 Session 資料表不屬於防竄改鏈，需保護管理存取。

本版不含 WAF、MFA、病毒掃描、SIEM、SSO 或合規認證。登入節流存於單程序記憶體，重啟會重設；正式網路入口應另加持久且分散式的限流機制。

## 8. Docker（選用）

```bash
python scripts/configure.py
docker compose build
docker compose run --rm carbon-guard python run.py add-user admin --role admin
docker compose up -d
```

開啟 http://127.0.0.1:8000。具名 volume carbon-data 會保留資料。請備份此 volume 及 .env，勿執行會刪除 volume 的指令，除非確定要清空資料。

正式使用需在前方配置 HTTPS 反向代理，並設定 CARBON_SECURE_COOKIE=true。沒有 HTTPS 時設為 true 將導致瀏覽器無法正常送出登入 Cookie。Docker 對外綁定主機 127.0.0.1，預設不開放公網。

**只使用一個應用程序 / Uvicorn Worker**：模型與登入節流位於記憶體，不支援多程序同步。擴展前請改為 PostgreSQL、集中式 Session / 限流與模型服務。反向代理後以 app 看到的來源 IP 節流，可能讓多位使用者共享限制；需在受信任代理上配置入口限流，勿直接信任客戶端任意提供的 X-Forwarded-For。

## 9. 測試

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
```

Windows 改用 .venv\Scripts\python.exe。測試使用暫存資料庫與測試密鑰，不讀取正式 .env。整合測試涵蓋登入、CSRF、租戶隔離、完整性、HMAC 偽造拒絕、模型恢復、離群分數排序、整批輸入原子性、覆核稽核、匯出防護及登入節流。

執行時若看見 Starlette 關於 httpx 的棄用提示，不影響目前版本測試；requirements 已鎖定實際驗證的主要套件版本。更新套件後請重跑測試並確認模型重建的一致性。

## 10. 專案結構

```text
carbon-guard/
├── backend/             # API、資料庫、身分權限、模型、完整性
├── frontend/            # 已串接 API 的繁體中文介面
├── tests/               # 整合測試
├── samples/             # 合成訓練與上傳 CSV
├── scripts/configure.py # 產生本機隨機密鑰
├── data/.gitkeep        # 執行時產生資料庫，交付內容不含正式資料
├── run.py               # 跨平台入口及 .env 載入
├── requirements*.txt
├── .env.example
├── Dockerfile
├── compose.yaml
├── API.md
└── README.md
```

API 詳細格式參閱 API.md。沒有啟用公開 Swagger 頁面；前端已提供主要功能操作。
