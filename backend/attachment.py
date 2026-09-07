# -*- coding: utf-8 -*-
"""
里程地圖／國道收費電子檔 -> 合併成單頁 A4 PDF 附件。
不嵌入出差旅費報告表或請款單，作為獨立檔案一起下載、供列印。
"""
import io

from PIL import Image

A4_DPI = 150
A4_W = round(210 / 25.4 * A4_DPI)  # ~1240px
A4_H = round(297 / 25.4 * A4_DPI)  # ~1754px
MARGIN = 40
GAP = 24


def to_pil_image(data: bytes, content_type: str = "") -> Image.Image:
    """把上傳的電子檔（圖片或 PDF 第一頁）轉成 PIL Image。"""
    is_pdf = (content_type == "application/pdf") or data[:4] == b"%PDF"
    if is_pdf:
        import pymupdf

        doc = pymupdf.open(stream=data, filetype="pdf")
        page = doc[0]
        pix = page.get_pixmap(dpi=A4_DPI)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    return Image.open(io.BytesIO(data)).convert("RGB")


def _fit_paste(canvas: Image.Image, img: Image.Image, box: tuple[int, int, int, int]) -> None:
    bx, by, bw, bh = box
    scale = min(bw / img.width, bh / img.height)
    w, h = max(1, round(img.width * scale)), max(1, round(img.height * scale))
    resized = img.resize((w, h), Image.LANCZOS)
    x = bx + (bw - w) // 2
    y = by + (bh - h) // 2
    canvas.paste(resized, (x, y))


def build_mileage_attachment(
    map_img: Image.Image | None,
    toll_img: Image.Image | None,
    outpath: str,
) -> str | None:
    """
    map_img：點對點地圖；toll_img：國道收費證明。
    兩者皆有 -> 上下合併於一張 A4；只有其中一個 -> 該圖滿版 A4。
    """
    if not map_img and not toll_img:
        return None

    canvas = Image.new("RGB", (A4_W, A4_H), "white")
    full_box = (MARGIN, MARGIN, A4_W - 2 * MARGIN, A4_H - 2 * MARGIN)

    if map_img and toll_img:
        half_h = (A4_H - 2 * MARGIN - GAP) // 2
        _fit_paste(canvas, map_img, (MARGIN, MARGIN, A4_W - 2 * MARGIN, half_h))
        _fit_paste(canvas, toll_img, (MARGIN, MARGIN + half_h + GAP, A4_W - 2 * MARGIN, half_h))
    else:
        _fit_paste(canvas, map_img or toll_img, full_box)

    canvas.save(outpath, "PDF", resolution=A4_DPI)
    return outpath
