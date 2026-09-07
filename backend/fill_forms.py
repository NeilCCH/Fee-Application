# -*- coding: utf-8 -*-
"""
公勝保險 差旅報帳自動填表工具
- 出差旅費報告表 (.xls)  用 LibreOffice 轉 .xlsx -> openpyxl 填值(保留格式) -> 轉回 .xls
- 請款單 (.docx)        用 python-docx 填值
里程規則: 自駕距離(km) x 5 元 -> 填「自用車-油」欄
"""
import json, os, sys, subprocess, shutil, copy

MILEAGE_RATE = 5  # 每公里 5 元

def libre_convert(src, to_ext, outdir):
    subprocess.run(["libreoffice","--headless","--convert-to",to_ext,"--outdir",outdir,src],
                   check=True, capture_output=True)
    base = os.path.splitext(os.path.basename(src))[0]
    return os.path.join(outdir, base + "." + to_ext.split(":")[0])

def roc_date(s):
    """'2025/9/5' -> '114 年 9 月 5 日' (民國)"""
    try:
        y,m,d = [int(x) for x in s.replace("-","/").split("/")]
        return f"{y-1911} 年 {m} 月 {d} 日"
    except Exception:
        return s

def roc_slash(s):
    """'2025/9/5' -> '114/9/5' (民國，緊湊格式，給 Excel 小格用)。已是民國(<1911)則原樣。"""
    try:
        y,m,d = [int(x) for x in str(s).replace("-","/").split("/")]
        if y > 1911: y -= 1911
        return f"{y}/{m}/{d}"
    except Exception:
        return s

# ---------- Excel ----------
def fill_excel(template_xls, data, outdir):
    import openpyxl
    xlsx_tpl = libre_convert(template_xls, "xlsx", outdir)
    wb = openpyxl.load_workbook(xlsx_tpl)
    ws = wb.active

    def put(cell, val):
        ws[cell] = val

    put("A5", "出差人姓名：" + data.get("出差人姓名",""))
    put("H5", "部門：" + data.get("部門",""))
    put("L5", "職稱：" + data.get("職稱",""))
    put("P5", roc_slash(data.get("申請日期","")))
    put("C6", data.get("出差事由",""))
    put("J6", data.get("出差地點",""))
    put("C7", roc_slash(data.get("出差起日","")))
    put("E7", data.get("出差起時",""))
    put("H7", roc_slash(data.get("出差迄日","")))
    put("J7", data.get("出差迄時",""))
    put("M7", data.get("共日",""))
    put("O7", data.get("共時",""))

    cats = ["火車高鐵","計程車","自用車油","自用車通行","飛機","交通其他",
            "住宿費","膳雜費","交際費","其他"]
    col_letters = ["E","F","G","H","I","J","K","L","M","N"]  # 對應 cats
    grand = 0
    start_row = 10  # xlrd row9 -> excel row10
    for i, row in enumerate(data.get("rows", [])):
        r = start_row + i
        if r > 18:
            print("警告: 明細超過 9 列，多的沒填", file=sys.stderr); break
        ws[f"A{r}"] = row.get("日期起","")
        ws[f"B{r}"] = row.get("日期迄","")
        ws[f"C{r}"] = row.get("地點起","")
        ws[f"D{r}"] = row.get("地點迄","")
        rowsum = 0
        for cat, col in zip(cats, col_letters):
            v = row.get(cat, "")
            if v not in ("", None):
                ws[f"{col}{r}"] = v
                try: rowsum += float(v)
                except: pass
        ws[f"O{r}"] = rowsum if rowsum else ""
        ws[f"P{r}"] = row.get("摘要","")
        grand += rowsum

    used = len(data.get("rows", []))
    for r in range(start_row + used, 19):  # 清掉沒用到的明細列殘留的 0
        ws[f"O{r}"] = None
    ws["O19"] = grand                      # 差旅費總額
    adv = float(data.get("預支旅費", 0) or 0)
    if adv: ws["O20"] = adv                 # 預支旅費
    ws["O21"] = grand - adv                  # 應(收)付旅費
    if data.get("備註"):
        ws["A20"] = "備註說明：" + data["備註"]

    out_xlsx = os.path.join(outdir, "出差旅費報告表_已填.xlsx")
    wb.save(out_xlsx)
    out_xls = libre_convert(out_xlsx, "xls", outdir)
    final_xls = os.path.join(outdir, "出差旅費報告表_已填.xls")
    if os.path.abspath(out_xls) != os.path.abspath(final_xls):
        shutil.move(out_xls, final_xls)
    return final_xls, grand

# ---------- 中文金額 ----------
import re as _re
_CN_D = "零壹貳參肆伍陸柒捌玖"
_CN_SMALL = ["", "拾", "佰", "仟"]
_CN_BIG = ["", "萬", "億", "兆"]

def cn_amount_string(n):
    """標準國字大寫金額，例：4655→肆仟陸佰伍拾伍元整；5660→伍仟陸佰陸拾元整；120500→拾貳萬零伍佰元整"""
    n = int(round(n))
    if n == 0:
        return "新台幣：零元整"
    def conv4(x):  # 0..9999 -> 大寫(含內部零)
        out = []
        for pos in range(3, -1, -1):
            d = (x // (10 ** pos)) % 10
            if d == 0:
                if out and out[-1] != "零":
                    out.append("零")
            else:
                out.append(_CN_D[d] + _CN_SMALL[pos])
        return "".join(out).strip("零")
    groups = []
    while n > 0:
        groups.append(n % 10000); n //= 10000
    parts = []
    for i in range(len(groups) - 1, -1, -1):
        g = groups[i]
        if g == 0:
            if parts and parts[-1] != "零":
                parts.append("零")
        else:
            seg = conv4(g)
            # 若本節不足四位且前面還有更高節,前導補零 (例 100萬0500 需要 零)
            if i < len(groups) - 1 and g < 1000:
                seg = "零" + seg
            parts.append(seg + _CN_BIG[i])
    s = "".join(parts)
    s = _re.sub("零+", "零", s).strip("零")
    return "新台幣：" + s + "元整"

# ---------- Word ----------
def _append_to_paragraph(p, text):
    """在段落最後補上文字,沿用最後一個 run 的字型"""
    if p.runs:
        r = p.add_run(text)
        try:
            src = p.runs[0]
            r.font.name = src.font.name
            r.font.size = src.font.size
            r.bold = src.bold
            if src.font.name:
                from docx.oxml.ns import qn
                r._element.rPr.rFonts.set(qn('w:eastAsia'), src.font.name)
        except Exception:
            pass
    else:
        p.add_run(text)

def _set_cell_text(cell, text, keep_first_line_label=None):
    """設定儲存格文字。keep_first_line_label: 只在含該label的段落『結尾』接上文字(不動原字)。"""
    if keep_first_line_label:
        for p in cell.paragraphs:
            if keep_first_line_label in p.text:
                _append_to_paragraph(p, text)
                return
    # 一般: 用第一段第一個 run 保留字型
    p = cell.paragraphs[0]
    if p.runs:
        p.runs[0].text = text
        for extra in p.runs[1:]:
            extra.text = ""
    else:
        p.add_run(text)

def _total_row_idx(t):
    """回傳 (項次列 index list, 總計列 index)"""
    for idx, row in enumerate(t.rows):
        if row.cells[0].text.strip().startswith("總計"):
            return list(range(4, idx)), idx
    return list(range(4, 10)), 10

def _check_payment(t, method):
    """把付款方式的 □{method} 勾成 ■{method}"""
    if not method: return
    for row in t.rows:
        for cell in row.cells:
            for p in cell.paragraphs:
                if "電匯" in p.text and "支票" in p.text:
                    full = "".join(r.text for r in p.runs).replace("□"+method, "■"+method)
                    if p.runs:
                        p.runs[0].text = full
                        for x in p.runs[1:]: x.text = ""
                    return

def fill_word(template_docx, data, grand, outdir):
    from docx import Document
    from docx.table import Table
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    import copy
    doc = Document(template_docx)
    # P2 日期 (民國)
    for p in doc.paragraphs:
        if p.text.strip().startswith("日期"):
            if data.get("申請日期") and p.runs:
                p.runs[0].text = "日期:  " + roc_date(data["申請日期"])
                for extra in p.runs[1:]:
                    extra.text = ""
            break

    base = doc.tables[0]
    pristine = copy.deepcopy(base._tbl)  # 乾淨範本，供分頁複製
    method = data.get("付款方式", "電匯")

    def _md(s):  # '2025/9/1' -> '9月1日'
        try:
            y,m,d = [int(x) for x in str(s).replace("-","/").split("/")]
            return f"{m}月{d}日"
        except Exception:
            return str(s)
    # 出差模式未指定明細時：請款單只記一筆「MM月DD日到MM月DD日差旅費」＝總額
    if data.get("出差起日"):
        _default_desc = f"{_md(data.get('出差起日',''))}到{_md(data.get('出差迄日',''))}差旅費"
    else:
        _default_desc = "差旅費"
    items = data.get("請款明細") or [{"說明": _default_desc, "金額": grand}]
    total = sum(int(it.get("金額",0) or 0) for it in items) if items else grand
    n = len(items)
    # 每頁標準6、上限7；<=7 放一頁，>7 每頁6筆自動換頁
    pages = [items] if n <= 7 else [items[i:i+6] for i in range(0, n, 6)]

    def fill_header(t):
        _set_cell_text(t.cell(0,2), data.get("交易摘要") or ("出差旅費－" + data.get("出差事由","")))
        _set_cell_text(t.cell(0,7), data.get("部門",""))
        _set_cell_text(t.cell(1,2), data.get("出差人姓名",""), keep_first_line_label="收款人名稱")
        _check_payment(t, method)

    def ensure_rows(t, need):
        idxs, tot = _total_row_idx(t)
        while len(idxs) < need:  # 只有單頁7筆會用到:複製一列插在總計前
            src_tr = t.rows[idxs[-1]]._tr
            t.rows[tot]._tr.addprevious(copy.deepcopy(src_tr))
            idxs, tot = _total_row_idx(t)
        return idxs, tot

    start_no = 0
    for pi, page_items in enumerate(pages):
        if pi == 0:
            t = base
        else:
            new_el = copy.deepcopy(pristine)
            sectPr = doc.element.body.find(qn('w:sectPr'))
            sectPr.addprevious(new_el)
            t = Table(new_el, base._parent)
            fp = t.cell(0,0).paragraphs[0]._p       # 讓續頁表格從新頁開始
            pPr = fp.get_or_add_pPr()
            pPr.insert(0, OxmlElement('w:pageBreakBefore'))
        fill_header(t)
        need = len(page_items)
        idxs, tot = ensure_rows(t, need)
        for j, it in enumerate(page_items):
            r = idxs[j]
            _set_cell_text(t.cell(r,0), str(start_no + j + 1))  # 項次跨頁連號
            _set_cell_text(t.cell(r,1), it.get("說明",""))
            amt = it.get("金額","")
            _set_cell_text(t.cell(r,7), f"{int(amt):,}" if isinstance(amt,(int,float)) else str(amt))
        for r in idxs[need:]:  # 清掉未用列殘留的項次號
            _set_cell_text(t.cell(r,0), "")
        start_no += need
        is_last = (pi == len(pages) - 1)
        if is_last:
            _set_cell_text(t.cell(tot,1), cn_amount_string(total))  # 大寫
            _set_cell_text(t.cell(tot,7), f"{total:,}")             # 阿拉伯數字
        else:
            _set_cell_text(t.cell(tot,1), "（接次頁）")

    # 多頁時把「現金領款簽收」段落移到最後一頁之後
    if len(pages) > 1:
        body = doc.element.body
        sectPr = body.find(qn('w:sectPr'))
        for p in doc.paragraphs:
            if "現金領款簽收" in p.text:
                sectPr.addprevious(p._p)
                break

    out = os.path.join(outdir, "請款單_已填.docx")
    doc.save(out)
    return out

def main():
    # 用法: python3 fill_forms.py data.json <報告表.xls|-> <請款單.docx> ./out
    #   報告表傳 "-" = 一般費用模式(只填請款單)
    data = json.load(open(sys.argv[1], encoding="utf-8"))
    tpl_xls = sys.argv[2]; tpl_docx = sys.argv[3]; outdir = sys.argv[4]
    os.makedirs(outdir, exist_ok=True)
    if tpl_xls and tpl_xls not in ("-", "none", "NONE", "無"):
        xls_out, grand = fill_excel(tpl_xls, data, outdir)   # 出差模式:兩張都填
        print("差旅費總額:", grand); print("EXCEL:", xls_out)
    else:
        grand = sum(int(it.get("金額",0) or 0) for it in data.get("請款明細", []))
    docx_out = fill_word(tpl_docx, data, grand, outdir)
    print("WORD :", docx_out)

if __name__ == "__main__":
    main()
