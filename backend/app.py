# -*- coding: utf-8 -*-
"""
公勝保險 差旅／費用報帳 APP — 後端服務 (開發順序第 1 步)
表單頁 -> data.json 組裝 -> fill_forms.py 產檔 -> 回傳可下載的 zip。
核心填表引擎 fill_forms.py 直接沿用，未修改任何邏輯。
"""
import os

os.environ.setdefault("HOME", "/tmp")  # 供 LibreOffice 建立設定檔用

import json
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import fill_forms
from attachment import build_mileage_attachment, to_pil_image
from ocr import OcrError, recognize_receipt

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
FRONTEND_DIR = BASE_DIR / "frontend"
TPL_XLS = TEMPLATES_DIR / "出差旅費報告表_範本.xls"
TPL_DOCX = TEMPLATES_DIR / "請款單_範本.docx"
ROUTES_JSON = BASE_DIR / "routes.json"

app = FastAPI(title="公勝保險報帳工具")


@app.get("/api/routes")
def get_routes():
    if not ROUTES_JSON.exists():
        return {"base": {}, "routes": []}
    return json.loads(ROUTES_JSON.read_text(encoding="utf-8"))


@app.post("/api/ocr")
async def ocr(photo: UploadFile = File(...), mode: str = Form("trip")):
    """收據拍照辨識：照片只在記憶體處理，這裡讀完 bytes 就不再持有檔案，辨識完即丟、不落地存檔。"""
    raw = await photo.read()
    try:
        result = recognize_receipt(raw, photo.content_type or "", mode)
    except OcrError as e:
        raise HTTPException(400, str(e)) from e
    finally:
        del raw
    return result


@app.post("/api/generate")
async def generate(
    payload: str = Form(..., description="JSON 字串：{mode, data}"),
    map_file: UploadFile | None = File(None, description="點對點地圖電子檔（圖片或PDF，選填）"),
    toll_file: UploadFile | None = File(None, description="國道收費電子檔（圖片或PDF，選填）"),
):
    try:
        req = json.loads(payload)
    except (TypeError, ValueError) as e:
        raise HTTPException(400, "payload 不是合法的 JSON") from e

    mode = req.get("mode")
    if mode not in ("trip", "general"):
        raise HTTPException(400, "mode 必須是 trip 或 general")
    if not TPL_XLS.exists() or not TPL_DOCX.exists():
        raise HTTPException(500, "找不到官方表單範本，請確認 templates 目錄")

    data = dict(req.get("data") or {})
    _validate(mode, data)

    workdir = Path(tempfile.mkdtemp(prefix="feeapp_"))
    outdir = workdir / "out"
    outdir.mkdir(parents=True, exist_ok=True)

    try:
        if mode == "trip":
            xls_out, grand = fill_forms.fill_excel(str(TPL_XLS), data, str(outdir))
        else:
            grand = sum(int(it.get("金額", 0) or 0) for it in data.get("請款明細", []))
        fill_forms.fill_word(str(TPL_DOCX), data, grand, str(outdir))
        await _attach_mileage_pdf(map_file, toll_file, outdir)
    except HTTPException:
        shutil.rmtree(workdir, ignore_errors=True)
        raise
    except Exception as e:  # noqa: BLE001 - 交給前端顯示錯誤訊息
        shutil.rmtree(workdir, ignore_errors=True)
        raise HTTPException(500, f"產檔失敗：{e}") from e

    zip_path = workdir / "報帳資料.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(outdir.iterdir()):
            zf.write(f, arcname=f.name)

    filename = f"報帳資料_{uuid.uuid4().hex[:6]}.zip"
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=filename,
        background=_cleanup(workdir),
    )


async def _attach_mileage_pdf(
    map_file: UploadFile | None, toll_file: UploadFile | None, outdir: Path
) -> None:
    """把上傳的地圖／國道收費電子檔合併成一張 A4 PDF，附加進 outdir（不嵌入 xls/docx）。"""

    async def _load(f: UploadFile | None, label: str):
        if f is None or not f.filename:
            return None
        raw = await f.read()
        if not raw:
            return None
        try:
            return to_pil_image(raw, f.content_type or "")
        except Exception as e:  # noqa: BLE001
            raise HTTPException(400, f"{label}無法讀取，請確認是圖片或 PDF 檔：{e}") from e

    map_img = await _load(map_file, "里程地圖電子檔")
    toll_img = await _load(toll_file, "國道收費電子檔")
    if map_img or toll_img:
        build_mileage_attachment(map_img, toll_img, str(outdir / "里程證明.pdf"))


def _validate(mode: str, data: dict[str, Any]) -> None:
    missing = []
    if not data.get("交易摘要") and mode == "general":
        missing.append("交易摘要／費用類別")
    if not data.get("部門"):
        missing.append("部門")
    if not data.get("出差人姓名"):
        missing.append("姓名（收款人名稱）")
    if mode == "trip" and not data.get("rows"):
        missing.append("至少一筆出差明細")
    if mode == "general" and not data.get("請款明細"):
        missing.append("至少一筆請款項次")
    if missing:
        raise HTTPException(400, "缺少必填欄位：" + "、".join(missing))


def _cleanup(workdir: Path):
    from starlette.background import BackgroundTask

    return BackgroundTask(shutil.rmtree, workdir, ignore_errors=True)


# 前端靜態檔（表單頁）
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
