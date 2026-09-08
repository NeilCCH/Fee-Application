# 公勝保險 差旅／費用報帳 APP

依 [`SPEC.md`](./SPEC.md) 建置。核心填表引擎 `backend/fill_forms.py` 直接沿用 SPEC 中已驗證版本，未修改任何邏輯。

「建議開發順序」進度：
1. ✅ 表單頁 + data.json 組裝 + fill_forms.py 產檔
2. ✅ 常用路線選取（自動帶出里程試算，可手動修正）
3. ❌ 拍照 OCR 回填 — 已實作又拿掉，實測辨識準確度不夠，決定金額一律手動輸入（key-in）
4. ✅ 草稿系統（取代原本的「首頁列表」構想，改成更符合實際送件方式的設計，見下）

另外加做了 SPEC 沒有的功能：出差地點起迄分開輸入、里程地圖／國道收費電子檔合併成 A4 附件。

## 為什麼流程跟 SPEC 原本設計不一樣

實際送件時，一張請款單常常同時包含出差費＋交際費＋文康費，不是單選一種。而且交際費、文康費常常是分好幾次、不同活動才發生的，沒辦法一次填完。所以改成：

1. **先個別記錄**：出差明細（一趟＝一列）、費用項次（交際費/文康費/雜支…每筆活動＝一筆），填完就存成草稿，不會馬上產檔
2. **要送件時再挑選**：從草稿清單裡勾選這次要用哪幾筆（可以同時勾出差明細＋好幾筆費用項次）
3. **補共同資訊**：姓名/部門/申請日期/出差事由/交易摘要等，這些是「這次送件」層級的，不隨草稿存
4. **預覽**：算好總額、大寫金額、各項次明細，確認無誤
5. **產出**：合併成**一份 PDF**（出差旅費報告表頁 + 請款單頁 + 里程地圖附件頁，都在同一份檔案裡），不再是分開的 .xls/.docx
6. 產出成功後，這次用到的草稿**自動從資料庫刪除**（草稿本來就設計成短命，不需要久放）

出差旅費報告表表頭的「出差地點」「出差起訖日期時間」「共日/共時」不使用，一律以每一列（每筆出差明細）自己的起迄點/日期為準。

## 專案結構

```
backend/        FastAPI 服務
  app.py          路由：草稿 CRUD、/api/preview（預覽）、/api/generate（合併產出PDF）、
                  /api/routes（常用路線）
  fill_forms.py   填表引擎（原樣沿用，未修改）
  db.py           Supabase 草稿存取層
  combine.py      把挑選的草稿＋共同資訊組成 data，呼叫 fill_forms 產檔後轉 PDF 合併
  attachment.py   地圖／國道收費電子檔 -> 合併 A4 PDF 頁面
db/schema.sql   Supabase 建表 SQL（feeapp_ 前綴，可跟其他專案共用同一個 Supabase 專案不互相干擾）
frontend/       表單頁（純 HTML/CSS/JS，無建置流程）
templates/      官方空白範本（出差旅費報告表.xls、請款單.docx）
routes.json     常用路線資料庫（里程為估計值，正式使用前建議用 Google Maps 校正）
SPEC.md         完整規格文件
```

## 環境變數

```bash
export HOME=/tmp                              # 供 LibreOffice 建立設定檔用
export SUPABASE_URL=https://xxxxx.supabase.co # 草稿功能用；沒設定草稿相關端點會回錯誤訊息
export SUPABASE_SERVICE_KEY=xxxxx             # 注意是 service_role/secret 金鑰，不是 anon/publishable
```

## 建立資料表

把 `db/schema.sql` 的內容貼到 Supabase 專案的 **SQL Editor** 執行一次即可（`CREATE TABLE IF NOT EXISTS`，重複執行不會出錯）。

## 本機執行

```bash
pip install -r backend/requirements.txt --break-system-packages
cd backend
uvicorn app:app --host 0.0.0.0 --port 8000
```

需系統已安裝 **LibreOffice**（含 Writer、Calc 模組，只裝 core 會導致轉檔全部失敗）。開啟瀏覽器進入 `http://localhost:8000/` 即為表單頁。

## 使用流程

1. 填姓名/部門/職稱（姓名用來辨認「我的草稿」）。
2. 新增出差明細（可選常用路線自動帶出里程金額）／新增費用項次，金額皆手動輸入，各自存成草稿。
3. 下方草稿清單勾選這次要用的幾筆。
4. 填這次送件的共同資訊（出差事由只在有勾出差明細時顯示）。
5. 按「預覽」確認總額/大寫金額，再按「產生 PDF」。
6. 下載一份合併好的 PDF，送件請自行附上單據正本。

## 已驗證

- 草稿 CRUD、依姓名過濾、預覽計算、合併產出 PDF、產出成功後自動清除已用草稿、不影響其他人的草稿：已用 mock 版 Supabase client 完整跑過（`/api/drafts/*`、`/api/preview`、`/api/generate`）。
- 合併後的 PDF 內容已驗證：出差旅費報告表頁（多筆出差明細＝多列，金額/合計正確）、請款單頁（出差彙總行＋費用項次逐筆列出、國字大寫、總計皆正確）。
- 表單頁以 Chromium 模擬手機寬度、mock 後端跑過完整流程：新增草稿、勾選、預覽、下載、草稿清空皆正常。
- **已部署到 Render 並用真實 Supabase 專案實測**：新增草稿、勾選、產出 PDF 皆正常運作。

## 部署方式（最省錢／最簡單）

已附上根目錄 `Dockerfile`（Python 3.11-slim + LibreOffice Writer/Calc + CJK 字型）。因為此表單不含機密資料、不需要登入機制，最簡單便宜的路徑：

1. **Render** 免費方案：完全免費，但閒置一段時間會休眠，下次有人用時要等三、五十秒喚醒。
2. **Railway**：每月 $5 起（無真正免費方案），SOC 2 Type II 認證、有正式 Trust Center，資安治理較成熟。
3. 若公司已有自己的 VM／虛擬主機：`docker build` 後 `docker run` 帶上面幾個環境變數即可，前面接 nginx/Caddy 做 HTTPS。

已實際部署到 Render 並用真實 Supabase 專案跑過完整流程，出檔與草稿存取皆正常。

## 其他注意事項

- 目前**沒有登入驗證機制**，任何拿到網址的人都能使用（你已確認這是可接受的，因為不是機密資料）；草稿用姓名簡單過濾，不是帳號登入。
- Supabase 免費專案閒置 7 天會自動暫停，需手動到後台恢復；正式上線後建議加個排程定期 ping 資料庫避免被暫停。
- `SUPABASE_SERVICE_KEY` 是專案最高權限金鑰，只能放在後端環境變數，絕不能出現在前端程式碼或 git 版控裡。
