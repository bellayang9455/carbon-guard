# API 參考

前端與後端同源。登入成功後以 HttpOnly Cookie 傳遞 Session；所有已登入的 POST 操作都需帶 `X-CSRF-Token`。登入回應與 GET /api/me 提供 csrf 值。沒有開放跨來源 CORS。

| 方法 | 路徑 | 權限 | 功能 |
|---|---|---|---|
| GET | /api/health | 公開 | 存活狀態 |
| POST | /api/login | 公開 | 登入，設定 Cookie |
| GET | /api/me | 登入 | 帳號、角色、供應商與 CSRF |
| POST | /api/logout | 登入 + CSRF | 撤銷目前 Session |
| GET | /api/records?limit=100&offset=0 | 登入 | 可見紀錄，limit 最大 500 |
| POST | /api/records | 登入 + CSRF | 整批新增，1–1000 筆 |
| GET | /api/export | 登入 | CSV 匯出全部可見資料 |
| GET | /api/model | 登入 | 模型狀態，供應商僅見版本摘要 |
| POST | /api/model/train | 管理員 + CSRF | 訓練，32–10000 筆 |
| POST | /api/predict | 登入 + CSRF | 單筆評分，不存檔 |
| GET | /api/integrity | 管理員 | 完整性檢查、筆數及鏈頭 |
| GET | /api/audit | 管理員 | 最近 200 筆稽核事件 |
| POST | /api/records/{id}/review | 管理員 + CSRF | 追加人工覆核事件 |

## 登入

```json
{"username":"admin","password":"你建立帳號時設定的密碼"}
```

## 新增紀錄

POST /api/records：

```json
{"records":[{"supplier":"示範供應商","month":"2026-11","scope":1,"emission":105.2,"production":1000}]}
```

supplier 最長 100 字元，首尾空白會移除；month 格式 YYYY-MM；scope 僅整數 1–3；emission 範圍 0–1e12；production 範圍 0.001–1e12；拒絕 NaN / Infinity。未訓練模型時 score / anomaly / model_id 為 null。

POST /api/predict 接受單一紀錄物件，不需 records 包裝；未訓練回傳 409。模型評分不表示認證或資料真偽。

## 訓練

```json
{"samples":["請替換為至少32個上述紀錄物件"],"contamination":0.05,"note":"已確認的歷史參考資料"}
```

samples 的每個元素須是實際物件，不是字串。訓練樣本不會新增排放紀錄。訓練為同步操作，請依硬體為反向代理配置合理逾時；同時僅接受一個訓練工作。

## 覆核

```json
{"decision":"confirmed","note":"已與盤查佐證核對"}
```

decision：confirmed（確認合理）、rejected（退回）、pending（待查）。覆核追加至 audit，不改寫原始排放紀錄或其評分；稽核頁可查看歷次覆核。

## 常見狀態碼

- 401：未登入、Session 過期或帳密錯誤。
- 403：CSRF 錯誤、角色不足或供應商不符。
- 404：紀錄不存在。
- 409：尚無模型、訓練中或完整性失敗。
- 413：請求超過 2 MB。
- 422：欄位格式或數值不符。
- 429：登入節流。

所有端點執行於單程序。機密檔案不在靜態資源目錄，/assets 僅提供 frontend 檔案。
