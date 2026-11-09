# 交付驗證紀錄

已執行並通過：

- `python -m unittest discover -s tests -v`：5 組整合測試，涵蓋登入、Cookie、CSRF、供應商隔離、管理員權限、模型訓練與重啟恢復、離群排序、雜湊鏈、HMAC 偽造拒絕、完整性失敗停止寫入、人工覆核、整批驗證、登出、CSV 公式跳脫、2 MB 請求上限及登入節流。
- `node --check frontend/app.js`：JavaScript 語法檢查。
- `python -m compileall -q backend run.py scripts`：Python 語法檢查。
- Chromium / Playwright 端到端操作：登入、合成 CSV 訓練、上傳離群值、自動評分、資料顯示、完整性驗證、登出。
- 1360×900 與 390×844 視窗檢視；瀏覽器流程沒有 JavaScript 或 CSP 錯誤。

驗證環境：Python 3.12、FastAPI 0.141.1、scikit-learn 1.8.0、NumPy 2.3.5、Pydantic 2.13.4。

未執行 Docker 建置、正式網路部署、壓力測試、滲透測試或真實碳排放資料準確率評估。Docker 設定及部署說明已提供，請於目標環境驗證。
