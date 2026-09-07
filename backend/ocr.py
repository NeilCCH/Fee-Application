# -*- coding: utf-8 -*-
"""
收據拍照辨識。照片只在記憶體處理、呼叫視覺模型辨識完即丟，不寫入磁碟、不留存。
需要環境變數 ANTHROPIC_API_KEY；模型可用 ANTHROPIC_OCR_MODEL 覆寫（預設 claude-sonnet-5）。
"""
import base64
import json
import os
import re

TRIP_CATEGORIES = ["火車高鐵", "計程車", "自用車油", "自用車通行", "飛機", "交通其他", "住宿費", "膳雜費", "交際費", "其他"]

_SUPPORTED_MEDIA = {"image/jpeg", "image/png", "image/webp", "image/gif"}

_PROMPT = """你是保險經紀公司的收據辨識助手。請仔細看這張收據／發票／憑證照片，盡量準確判讀，並且只回傳一個 JSON物件（不要任何其他文字、不要 markdown code fence），格式如下：
{{
  "日期": "YYYY/MM/DD 格式的西元日期，看不出來就填空字串",
  "金額": 整數金額數字，看不出來就填 0,
  "類別": "從這些選項中選最接近的一個：{categories}；看不出來就填「其他」",
  "說明": "簡短描述，例如店家名稱、品項或用途，10個字以內"
}}
只回 JSON，不要加任何說明文字。"""


class OcrError(Exception):
    pass


def recognize_receipt(image_bytes: bytes, content_type: str, mode: str = "trip") -> dict:
    if not image_bytes:
        raise OcrError("沒有收到照片內容")

    media_type = content_type if content_type in _SUPPORTED_MEDIA else _sniff_media_type(image_bytes)
    if media_type not in _SUPPORTED_MEDIA:
        raise OcrError("不支援的圖片格式，請用 JPG／PNG／WebP")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise OcrError("伺服器尚未設定 ANTHROPIC_API_KEY，無法使用拍照辨識")

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    model = os.environ.get("ANTHROPIC_OCR_MODEL", "claude-sonnet-5")
    categories = "、".join(TRIP_CATEGORIES) if mode == "trip" else "交際費、文康費、雜支、其他"

    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=300,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                        {"type": "text", "text": _PROMPT.format(categories=categories)},
                    ],
                }
            ],
        )
    except anthropic.APIError as e:
        raise OcrError(f"辨識服務呼叫失敗：{e}") from e

    text = "".join(block.text for block in resp.content if getattr(block, "type", None) == "text")
    return _parse_result(text, mode)


def _sniff_media_type(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return "application/octet-stream"


def _parse_result(text: str, mode: str) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise OcrError("辨識結果無法解析，請手動輸入")
    try:
        j = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise OcrError("辨識結果無法解析，請手動輸入") from e

    date = str(j.get("日期") or "").strip()
    try:
        amount = int(round(float(j.get("金額") or 0)))
    except (TypeError, ValueError):
        amount = 0
    desc = str(j.get("說明") or "").strip()

    category = str(j.get("類別") or "").strip()
    if mode == "trip" and category not in TRIP_CATEGORIES:
        category = "其他"

    return {"日期": date, "金額": amount, "類別": category, "說明": desc}
