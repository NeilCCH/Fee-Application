# -*- coding: utf-8 -*-
"""
把挑選好的出差明細草稿 ＋ 費用項次草稿 ＋ 這次送件的共同資訊，組成 fill_forms.py
需要的 data，呼叫既有引擎（原樣沿用、未修改）產出 .xls／.docx，再轉成 PDF
合併成一份（不再保留分開的 .xls/.docx 檔）。

出差旅費報告表表頭的「出差地點」「出差起訖日期時間」「共日／共時」依使用者決定
一律忽略不填，只以每一列（每筆出差明細草稿）自己的起迄點/日期為準。
"""
import os
import re
from typing import Any

import fill_forms
from attachment import build_mileage_attachment, to_pil_image

_MD_RE = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*$")


def _md_key(s: str) -> tuple[int, int]:
    m = _MD_RE.match(str(s or ""))
    if not m:
        return (99, 99)
    return (int(m.group(1)), int(m.group(2)))


def _fmt_md(s: str) -> str:
    m = _MD_RE.match(str(s or ""))
    if not m:
        return str(s or "")
    return f"{int(m.group(1))}月{int(m.group(2))}日"


def _leg_to_row(leg: dict[str, Any]) -> dict[str, Any]:
    row = {
        "日期起": leg.get("date_from", ""),
        "日期迄": leg.get("date_to", ""),
        "地點起": leg.get("loc_from", ""),
        "地點迄": leg.get("loc_to", ""),
        "摘要": leg.get("note", ""),
    }
    for k, v in (leg.get("amounts") or {}).items():
        if v not in ("", None):
            row[k] = v
    return row


def _trip_date_range(trip_legs: list[dict]) -> tuple[str, str]:
    with_start = [leg for leg in trip_legs if leg.get("date_from")]
    with_end = [leg for leg in trip_legs if leg.get("date_to")]
    start = min(with_start, key=lambda r: _md_key(r.get("date_from")))["date_from"] if with_start else ""
    end = max(with_end, key=lambda r: _md_key(r.get("date_to")))["date_to"] if with_end else ""
    return start, end


def _expense_line(item: dict[str, Any]) -> dict[str, Any]:
    date = str(item.get("item_date") or "").strip()
    desc = str(item.get("description") or "").strip()
    label = f"{date} {desc}".strip() if date else desc
    amount = item.get("amount", 0) or 0
    return {"說明": label, "金額": int(round(float(amount))), "類別": item.get("category") or "其他"}


def build_preview(common: dict[str, Any], trip_legs: list[dict], expense_items: list[dict]) -> dict[str, Any]:
    """不寫檔，純計算，給前端『預覽』畫面用。"""
    trip_total = 0.0
    for leg in trip_legs:
        trip_total += sum(float(v) for v in (leg.get("amounts") or {}).values() if v not in ("", None))
    trip_total = round(trip_total)

    lines = []
    if trip_legs:
        start, end = _trip_date_range(trip_legs)
        desc = f"{_fmt_md(start)}到{_fmt_md(end)}差旅費" if start and end else "差旅費"
        lines.append({"說明": desc, "金額": trip_total, "類別": "出差"})
    for item in expense_items:
        lines.append(_expense_line(item))

    grand = sum(line["金額"] for line in lines)
    return {
        "出差筆數": len(trip_legs),
        "費用筆數": len(expense_items),
        "出差旅費小計": trip_total,
        "項次": lines,
        "總計": grand,
        "總計大寫": fill_forms.cn_amount_string(grand),
    }


def generate_combined_pdf(
    common: dict[str, Any],
    trip_legs: list[dict],
    expense_items: list[dict],
    tpl_xls: str,
    tpl_docx: str,
    outdir: str,
    map_bytes: bytes | None = None,
    map_content_type: str = "",
    toll_bytes: bytes | None = None,
    toll_content_type: str = "",
) -> tuple[str, dict[str, Any]]:
    os.makedirs(outdir, exist_ok=True)
    has_trip = len(trip_legs) > 0

    data: dict[str, Any] = {
        "出差人姓名": common.get("出差人姓名", ""),
        "部門": common.get("部門", ""),
        "職稱": common.get("職稱", ""),
        "申請日期": common.get("申請日期", ""),
        "備註": common.get("備註", ""),
        "預支旅費": common.get("預支旅費", 0) or 0,
        "rows": [_leg_to_row(leg) for leg in trip_legs],
    }
    if has_trip:
        data["出差事由"] = common.get("出差事由", "")
    summary = (common.get("交易摘要") or "").strip()
    if summary:
        data["交易摘要"] = summary

    pdf_parts: list[str] = []
    grand = 0

    if has_trip:
        xls_out, grand = fill_forms.fill_excel(tpl_xls, data, outdir)
        start, end = _trip_date_range(trip_legs)
        desc = f"{_fmt_md(start)}到{_fmt_md(end)}差旅費" if start and end else "差旅費"
        trip_line = {"說明": desc, "金額": round(grand), "類別": "出差"}
        xls_pdf = fill_forms.libre_convert(xls_out, "pdf", outdir)
        pdf_parts.append(xls_pdf)
    else:
        trip_line = None

    請款明細 = ([trip_line] if trip_line else []) + [_expense_line(it) for it in expense_items]
    data["請款明細"] = 請款明細

    docx_out = fill_forms.fill_word(tpl_docx, data, grand, outdir)
    docx_pdf = fill_forms.libre_convert(docx_out, "pdf", outdir)
    pdf_parts.append(docx_pdf)

    if map_bytes or toll_bytes:
        map_img = to_pil_image(map_bytes, map_content_type) if map_bytes else None
        toll_img = to_pil_image(toll_bytes, toll_content_type) if toll_bytes else None
        attach_path = os.path.join(outdir, "_mileage_attachment.pdf")
        if build_mileage_attachment(map_img, toll_img, attach_path):
            pdf_parts.append(attach_path)

    final_path = os.path.join(outdir, "報帳資料.pdf")
    _merge_pdfs(pdf_parts, final_path)

    total = sum(line["金額"] for line in 請款明細)
    summary_info = {
        "出差旅費小計": grand if has_trip else 0,
        "總計": total,
        "總計大寫": fill_forms.cn_amount_string(total),
    }
    return final_path, summary_info


def _merge_pdfs(paths: list[str], out_path: str) -> str:
    import pymupdf

    merged = pymupdf.open()
    for p in paths:
        with pymupdf.open(p) as doc:
            merged.insert_pdf(doc)
    merged.save(out_path)
    merged.close()
    return out_path
