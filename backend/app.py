# -*- coding: utf-8 -*-
"""
公勝保險 差旅／費用報帳 APP — 後端服務
流程：先個別記錄出差明細／費用項次草稿（存 Supabase）-> 挑選要用哪幾筆 ->
填共同資訊 -> 預覽 -> 合併產出一份 PDF（成功後刪除已使用的草稿）。
核心填表引擎 fill_forms.py 直接沿用，未修改任何邏輯。
"""
import os

os.environ.setdefault("HOME", "/tmp")  # 供 LibreOffice 建立設定檔用

import json
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import db
import combine
from db import DbNotConfigured

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
    from ocr import OcrError, recognize_receipt

    raw = await photo.read()
    try:
        result = recognize_receipt(raw, photo.content_type or "", mode)
    except OcrError as e:
        raise HTTPException(400, str(e)) from e
    finally:
        del raw
    return result


# ---------- 草稿 CRUD ----------

@app.post("/api/drafts/trip-leg")
def create_trip_leg_draft(body: dict[str, Any]):
    owner = (body.get("owner_name") or "").strip()
    if not owner:
        raise HTTPException(400, "缺少姓名，無法歸屬草稿")
    try:
        row = db.create_trip_leg(owner, body)
    except DbNotConfigured as e:
        raise HTTPException(500, str(e)) from e
    return row


@app.post("/api/drafts/expense-item")
def create_expense_item_draft(body: dict[str, Any]):
    owner = (body.get("owner_name") or "").strip()
    if not owner:
        raise HTTPException(400, "缺少姓名，無法歸屬草稿")
    try:
        row = db.create_expense_item(owner, body)
    except DbNotConfigured as e:
        raise HTTPException(500, str(e)) from e
    return row


@app.get("/api/drafts")
def list_drafts(owner_name: str):
    owner = (owner_name or "").strip()
    if not owner:
        raise HTTPException(400, "缺少姓名")
    try:
        return db.list_drafts(owner)
    except DbNotConfigured as e:
        raise HTTPException(500, str(e)) from e


@app.delete("/api/drafts/trip-leg/{leg_id}")
def delete_trip_leg_draft(leg_id: str):
    try:
        db.delete_trip_leg(leg_id)
    except DbNotConfigured as e:
        raise HTTPException(500, str(e)) from e
    return {"ok": True}


@app.delete("/api/drafts/expense-item/{item_id}")
def delete_expense_item_draft(item_id: str):
    try:
        db.delete_expense_item(item_id)
    except DbNotConfigured as e:
        raise HTTPException(500, str(e)) from e
    return {"ok": True}


# ---------- 預覽與產出 ----------

class SelectionError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(400, detail)


def _load_selection(payload: dict[str, Any]) -> tuple[dict, list, list]:
    common = dict(payload.get("common") or {})
    trip_leg_ids = payload.get("trip_leg_ids") or []
    expense_item_ids = payload.get("expense_item_ids") or []
    if not trip_leg_ids and not expense_item_ids:
        raise SelectionError("請至少挑選一筆出差明細或費用項次")
    try:
        trip_legs = db.get_trip_legs_by_ids(trip_leg_ids)
        expense_items = db.get_expense_items_by_ids(expense_item_ids)
    except DbNotConfigured as e:
        raise HTTPException(500, str(e)) from e
    _validate_common(common, has_trip=bool(trip_legs))
    return common, trip_legs, expense_items


def _validate_common(common: dict[str, Any], has_trip: bool) -> None:
    missing = []
    if not common.get("出差人姓名"):
        missing.append("姓名（收款人名稱）")
    if not common.get("部門"):
        missing.append("部門")
    if not common.get("申請日期"):
        missing.append("申請日期")
    if not has_trip and not (common.get("交易摘要") or "").strip():
        missing.append("交易摘要／費用類別")
    if missing:
        raise HTTPException(400, "缺少必填欄位：" + "、".join(missing))


@app.post("/api/preview")
def preview(payload: dict[str, Any]):
    common, trip_legs, expense_items = _load_selection(payload)
    return combine.build_preview(common, trip_legs, expense_items)


@app.post("/api/generate")
async def generate(
    payload: str = Form(..., description="JSON 字串：{common, trip_leg_ids, expense_item_ids}"),
    map_file: UploadFile | None = File(None, description="點對點地圖電子檔（圖片或PDF，選填）"),
    toll_file: UploadFile | None = File(None, description="國道收費電子檔（圖片或PDF，選填）"),
):
    try:
        req = json.loads(payload)
    except (TypeError, ValueError) as e:
        raise HTTPException(400, "payload 不是合法的 JSON") from e

    common, trip_legs, expense_items = _load_selection(req)

    if not TPL_XLS.exists() or not TPL_DOCX.exists():
        raise HTTPException(500, "找不到官方表單範本，請確認 templates 目錄")

    map_bytes = await map_file.read() if (map_file and map_file.filename) else None
    map_ctype = map_file.content_type or "" if map_file else ""
    toll_bytes = await toll_file.read() if (toll_file and toll_file.filename) else None
    toll_ctype = toll_file.content_type or "" if toll_file else ""

    workdir = Path(tempfile.mkdtemp(prefix="feeapp_"))
    outdir = workdir / "out"

    try:
        final_pdf, _summary = combine.generate_combined_pdf(
            common, trip_legs, expense_items,
            str(TPL_XLS), str(TPL_DOCX), str(outdir),
            map_bytes=map_bytes, map_content_type=map_ctype,
            toll_bytes=toll_bytes, toll_content_type=toll_ctype,
        )
    except HTTPException:
        shutil.rmtree(workdir, ignore_errors=True)
        raise
    except Exception as e:  # noqa: BLE001 - 交給前端顯示錯誤訊息
        shutil.rmtree(workdir, ignore_errors=True)
        raise HTTPException(500, f"產檔失敗：{e}") from e

    try:
        db.delete_drafts(
            [leg["id"] for leg in trip_legs],
            [item["id"] for item in expense_items],
        )
    except DbNotConfigured:
        pass  # 沒接資料庫的情況不會有這些 id，忽略即可

    filename = f"報帳資料_{uuid.uuid4().hex[:6]}.pdf"
    return FileResponse(
        final_pdf,
        media_type="application/pdf",
        filename=filename,
        background=_cleanup(workdir),
    )


def _cleanup(workdir: Path):
    from starlette.background import BackgroundTask

    return BackgroundTask(shutil.rmtree, workdir, ignore_errors=True)


# 前端靜態檔（表單頁）
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
