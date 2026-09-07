# 公勝保險 差旅／費用報帳 APP

依 [`SPEC.md`](./SPEC.md) 建置。核心填表引擎 `backend/fill_forms.py` 直接沿用 SPEC 中已驗證版本，未修改任何邏輯。

目前完成「建議開發順序」第 1 步：**表單頁 + data.json 組裝 + fill_forms.py 產檔**（手動填表即可產出可送件檔案）。後續步驟（常用路線選取、拍照 OCR、首頁列表）尚未開始。

## 專案結構

```
backend/        FastAPI 服務 + fill_forms.py（填表引擎，原樣沿用）
frontend/       表單頁（純 HTML/CSS/JS，無建置流程）
templates/      官方空白範本（出差旅費報告表.xls、請款單.docx）
samples/        data.json 範例
routes.json     常用路線資料庫（供後續步驟使用，目前 UI 尚未串接）
SPEC.md         完整規格文件
```

## 本機執行

```bash
pip install -r backend/requirements.txt --break-system-packages
export HOME=/tmp   # 供 LibreOffice 建立設定檔用
cd backend
uvicorn app:app --host 0.0.0.0 --port 8000
```

需系統已安裝 **LibreOffice**（含 Writer、Calc 模組，用來保留 .xls 格式）。開啟瀏覽器進入 `http://localhost:8000/` 即為表單頁。

## 使用流程

1. 選擇「出差報帳」或「一般費用」。
2. 填寫基本資料與明細（出差：一趟＝一列；一般費用：逐筆項次）。
3. 按「產生表單並下載」→ 後端組成 `data.json`、呼叫 `fill_forms.py` 產檔，回傳 zip：
   - 出差模式：`出差旅費報告表_已填.xls` ＋ `請款單_已填.docx`
   - 一般費用模式：`請款單_已填.docx`
4. 下載後請自行附上單據正本送件。收據照片本步驟尚未支援拍照辨識（見開發順序第 3 步）。

## 已驗證

- `POST /api/generate`：出差模式、一般費用模式皆已用範例資料實測，產出的 .xls／.docx 欄位、民國日期、國字大寫金額、■電匯勾選、總計金額皆正確。
- 表單頁以 Chromium 模擬手機寬度實測：模式切換、必填驗證、明細新增/刪除、送出下載、成功訊息皆正常。
