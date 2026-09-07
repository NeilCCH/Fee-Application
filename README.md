# 公勝保險 差旅／費用報帳 APP

依 [`SPEC.md`](./SPEC.md) 建置。核心填表引擎 `backend/fill_forms.py` 直接沿用 SPEC 中已驗證版本，未修改任何邏輯。

「建議開發順序」進度：
1. ✅ 表單頁 + data.json 組裝 + fill_forms.py 產檔
2. ✅ 常用路線選取（自動帶出里程試算，可手動修正）
3. ✅ 拍照 OCR 回填
4. ⬜ 首頁列表／草稿／分享（尚未開始）

另外加做了 SPEC 沒有的功能：出差地點起迄分開輸入、里程地圖／國道收費電子檔合併成 A4 附件（獨立檔案，不嵌入正式表單）。

## 專案結構

```
backend/        FastAPI 服務
  app.py          路由：/api/generate（產檔）、/api/routes（常用路線）、/api/ocr（拍照辨識）
  fill_forms.py   填表引擎（原樣沿用，未修改）
  attachment.py   地圖／國道收費電子檔 -> 合併 A4 PDF
  ocr.py          收據拍照辨識（呼叫 Anthropic 視覺模型）
frontend/       表單頁（純 HTML/CSS/JS，無建置流程）
templates/      官方空白範本（出差旅費報告表.xls、請款單.docx）
samples/        data.json 範例
routes.json     常用路線資料庫（里程為估計值，正式使用前建議用 Google Maps 校正）
SPEC.md         完整規格文件
```

## 本機執行

```bash
pip install -r backend/requirements.txt --break-system-packages
export HOME=/tmp                        # 供 LibreOffice 建立設定檔用
export ANTHROPIC_API_KEY=sk-ant-xxxxx   # 拍照 OCR 需要，沒設定該功能會回錯誤訊息但不影響其他功能
cd backend
uvicorn app:app --host 0.0.0.0 --port 8000
```

需系統已安裝 **LibreOffice**（含 Writer、Calc 模組，只裝 core 會導致轉檔全部失敗）。開啟瀏覽器進入 `http://localhost:8000/` 即為表單頁。

## 使用流程

1. 選擇「出差報帳」或「一般費用」。
2. 填寫基本資料與明細：
   - 出差模式：一趟＝一列，可選常用路線自動帶出里程金額，或按「拍照辨識收據」讓照片自動判讀金額/日期/類別回填（可再手動修正）。
   - 一般費用模式：逐筆項次，同樣可拍照辨識回填說明與金額。
3. （選填）上傳里程地圖／國道收費電子檔，合併成一張 A4 附件一起下載。
4. 按「產生表單並下載」→ 回傳 zip：
   - 出差模式：`出差旅費報告表_已填.xls` ＋ `請款單_已填.docx` ＋（如有上傳）`里程證明.pdf`
   - 一般費用模式：`請款單_已填.docx`
5. 下載後請自行附上單據正本送件。

## 收據照片處理原則

拍照辨識時，照片會傳送至 Anthropic 視覺模型做單次判讀，**辨識完立即捨棄、不寫入伺服器磁碟或資料庫**，也不會出現在下載的檔案裡。地圖／國道收費附件則是使用者主動選擇要保留、合併進下載檔案的，性質不同。

## 已驗證

- `POST /api/generate`：出差模式、一般費用模式皆已用範例資料實測，產出的 .xls／.docx 欄位、民國日期、國字大寫金額、■電匯勾選、總計金額皆正確；地圖＋國道收費合併附件的 A4 版面、單張滿版情境皆已用測試圖檔驗證。
- `POST /api/ocr`：JSON 解析與欄位對應邏輯已用假回應驗證（含格式錯亂、非 JSON 的錯誤情況）；缺少 `ANTHROPIC_API_KEY` 時回傳清楚錯誤訊息、不影響其餘功能；瀏覽器端已用 mock 後端驗證成功／失敗兩種情境的回填、疊加金額、狀態顯示皆正常。
- 表單頁以 Chromium 模擬手機寬度實測：模式切換、必填驗證、明細新增/刪除、送出下載、成功訊息皆正常。

## 部署方式（最省錢／最簡單）

已附上根目錄 `Dockerfile`（Python 3.11-slim + LibreOffice Writer/Calc + CJK 字型）。因為此表單不含機密資料、不需要登入機制，最簡單便宜的路徑：

1. **Zeabur**（推薦，台灣團隊做的平台）或 **Railway**：GitHub repo 接上去、自動偵測 Dockerfile 建置部署，免費／每月幾美元額度即可跑這種小型內部工具，自動配 HTTPS 網域，不用自己管伺服器。
2. **Render** 免費方案：完全免費，但閒置一段時間會休眠，下次有人用時要等三、五十秒喚醒——內部工具偶爾用的話可接受。
3. 若公司已有自己的 VM／虛擬主機：`docker build` 後 `docker run -p 8000:8000 -e ANTHROPIC_API_KEY=xxx feeapp` 即可，前面接 nginx/Caddy 做 HTTPS。

部署時只需設定一個環境變數 `ANTHROPIC_API_KEY`（拍照 OCR 用；沒設定其他功能仍正常，只有拍照辨識會顯示錯誤訊息）。

> Dockerfile 內容已對照這次在本機驗證過的安裝步驟（`libreoffice-writer` + `libreoffice-calc` 缺一會讓轉檔全部失敗，已踩過這個坑），但這個沙盒環境的網路政策擋掉了 Docker Hub 的映像檔下載，沒辦法在這裡實際跑一次 `docker build` 驗證——建議你部署時第一次跑完整流程，確認出檔正常再正式上線。

## 其他注意事項

- 目前**沒有登入驗證機制**，任何拿到網址的人都能使用（你已確認這是可接受的，因為不是機密資料）。
- 沒有資料庫，「首頁列表／草稿」（開發順序第 4 步）若要做，需另外加簡易儲存（如 SQLite）。
