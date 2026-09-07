# -*- coding: utf-8 -*-
"""
公勝保險 差旅／費用報帳 APP — 後端服務 (開發順序第 1 步)
表單頁 -> data.json 組裝 -> fill_forms.py 產檔 -> 回傳可下載的 zip。
核心填表引擎 fill_forms.py 直接沿用，未修改任何邏輯。
"""
import os

os.environ.setdefault("HOME", "/tmp")  # 供 LibreOffice 建立設定檔用

import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import fill_forms

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
FRONTEND_DIR = BASE_DIR / "frontend"
TPL_XLS = TEMPLATES_DIR / "出差旅費報告表_範本.xls"
TPL_DOCX = TEMPLATES_DIR / "請款單_範本.docx"

app = FastAPI(title="公勝保險報帳工具")


class GenerateRequest(BaseModel):
    mode: str = Field(..., description="trip=出差模式 / general=一般費用模式")
    data: dict[str, Any] = Field(..., description="組裝好的 data.json 內容")


@app.post("/api/generate")
def generate(req: GenerateRequest):
    if req.mode not in ("trip", "general"):
        raise HTTPException(400, "mode 必須是 trip 或 general")
    if not TPL_XLS.exists() or not TPL_DOCX.exists():
        raise HTTPException(500, "找不到官方表單範本，請確認 templates 目錄")

    data = dict(req.data or {})
    _validate(req.mode, data)

    workdir = Path(tempfile.mkdtemp(prefix="feeapp_"))
    outdir = workdir / "out"
    outdir.mkdir(parents=True, exist_ok=True)

    try:
        if req.mode == "trip":
            xls_out, grand = fill_forms.fill_excel(str(TPL_XLS), data, str(outdir))
        else:
            grand = sum(int(it.get("金額", 0) or 0) for it in data.get("請款明細", []))
        fill_forms.fill_word(str(TPL_DOCX), data, grand, str(outdir))
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
