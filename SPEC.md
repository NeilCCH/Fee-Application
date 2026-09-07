---
name: gongshen-expense-forms
description: 填公勝保險經紀人的「出差旅費報告表」(.xls) 與「請款單」(.docx)。拍收據→視覺辨識金額→自動分類填欄、算里程與總額，產出可送件的檔案。出差報帳或一般費用（差旅費/交際費/文康費…）申請時使用。
---

# 公勝保險 差旅／費用報帳填表工具 — 規格與實作

> 這份 MD 是給 Claude Code 的完整建置文件：包含兩張官方表單的結構、公司規則、資料結構，以及**已驗證可用**的填表程式 `fill_forms.py`。可直接作為 Claude Code 專案的規格 + 參考實作，或作為 Claude App 技能的 SKILL.md。

## 目標
把收據與出差資訊，自動填進公司兩份官方表單並算好金額，產出可送件的檔案。收據照片只在當下辨識、不儲存、不上傳；使用者送件時自行附上單據正本。

兩份官方表單：
- **出差旅費報告表**（表單編號 CD-2-007-01-01，.xls）— 只用於**出差**。**一趟出差＝一列**（可多趟多列，最多 9 列），該趟各類費用填在同一列的對應欄位。
- **請款單**（表單編號 CE-1-003-01-01，.docx）— **通用請款表**，差旅費、交際費、文康費…各種費用都用它。

## 兩種模式
- **出差模式**：填「出差旅費報告表」+「請款單」。轉到請款單時**只加總、只記一筆「MM月DD日到MM月DD日差旅費」＝差旅費總額，不列明細**（程式自動帶入日期區間）。交易摘要預設「出差旅費－{事由}」。
- **一般費用模式**：交際費、文康費、雜支等非出差 →**只填請款單**。交易摘要＝費用類別（如「交際費－客戶餐敘」），項次逐筆列。執行時報告表範本參數傳 `-`。

## 已確認的公司規則（照此做）
1. **日期一律民國**：報告表用「114/9/5」；請款單頁首用「114 年 9 月 5 日」（程式自動把西元轉民國，輸入實際年份即可）。
2. **請款單必填欄位**：交易摘要、部門、收款人名稱（其餘如付款日、預算代號、銀行分行/帳號非必填，留空）。
3. **付款方式預設勾「電匯」**（■電匯）。
4. **請款單金額**：大寫欄用標準國字大寫（例 4655→肆仟陸佰伍拾伍元整）；總計列的金額格填**阿拉伯數字**（例 4,655）。
5. **項次每頁標準 6、上限 7，超過 7 自動換頁**（每頁 6 筆、項次跨頁連號，現金領款簽收移到最後一頁）。
6. **里程**：自駕 km × 5 元，填「自用車-油」。
7. **國道通行費（未裝 eTag）**：使用者**沒有 eTag**，通行費依里程計算，不抓 eTag 扣款。算法：每日每車前 20 公里免費；20–200 公里每公里 1.2 元；200 公里以上每公里 0.9 元；四捨五入至元（無 eTag 用戶按此原價、無 eTag 額外折扣）。以**當日國道里程**計，填「自用車-通行」。程式函式 `freeway_toll_no_etag(km)` 已內建。
8. 一律填**實際發生數字**（金額類），不拆免稅／未稅。全程繁體中文。

## 建置流程（給 Claude Code 或技能執行）

### 1. 判斷模式 + 取得基本資料
先問「出差」或「一般費用」。再問（姓名／部門／職稱可記憶帶入）：姓名、部門、職稱、申請日期、交易摘要（或費用類別）；出差另問：事由、地點、起訖日期時間、共幾日幾時。

### 2. 辨識收據 → 分類
使用者拍照丟進來（或口述），視覺辨識抓 日期/類別/金額。
- 出差模式：一趟出差整理成報告表的一列（rows 一筆），該趟各類費用填進同一列對應欄位 key：火車/高鐵→`火車高鐵`；計程車→`計程車`；自駕油錢→`自用車油`；國道通行→`自用車通行`；機票→`飛機`；捷運/停車→`交通其他`；住宿→`住宿費`；餐費→`膳雜費`；交際→`交際費`；其餘→`其他`。多趟多列。
- 一般費用模式：每張收據＝請款單一筆項次（說明＋金額）。

### 3. 自駕里程與國道通行費（出差模式）
- **里程油資**：來回 km × 5 元 → `自用車油`。
- **國道通行費（未裝 eTag）**：以當日國道里程用 `freeway_toll_no_etag(km)` 計 → `自用車通行`。
- 取得里程方式（優先序）：①使用者從**常用路線資料庫**選一條（見下，直接帶出來回里程與國道里程）；②使用者貼 Google Maps 公里數；③只給地名則估算並請使用者對照 Google Maps 確認。**務必列出算式**，例：「高雄→台南 單程 45、來回 90 × 5＝450 元；國道來回約 65 km → 通行費 54 元」。

### 3-1. 常用路線資料庫（routes）
使用者提供的固定出差起迄點清單，供快速選取、自動帶出里程。建議存成 `routes.json`：
```json
[
  {"名稱":"高雄業務中心↔台南業務中心", "起":"", "迄":"", "來回里程": 0, "國道來回里程": 0}
]
```
選取一條後：`自用車油 = 來回里程 × 5`、`自用車通行 = freeway_toll_no_etag(國道來回里程)`。
（清單由使用者提供；尚待補入實際路線與公里數。）

### 4. 取得空白範本
優先從 Google Drive 搜檔名含「出差旅費報告表」「請款單」（或 CD20070101 / CE10030101）下載；找不到或未連 Drive 就請使用者附檔。一般費用模式只需請款單範本。

### 5. 產出
```bash
pip install openpyxl python-docx --break-system-packages -q
export HOME=/tmp
# 出差模式（兩張）：
python3 fill_forms.py data.json <報告表.xls> <請款單.docx> ./out
# 一般費用模式（只請款單）：報告表參數傳 -
python3 fill_forms.py data.json - <請款單.docx> ./out
```
需 LibreOffice 轉 .xls（雲端環境已內建；獨立 APP 需一併安裝 LibreOffice 或改用能保留 .xls 格式的方案）。

`data.json`（出差模式範例；日期可給西元，自動轉民國；一趟出差＝rows 一筆；不給「請款明細」→請款單自動帶入一筆日期區間差旅費）：
```json
{
  "出差人姓名": "", "部門": "", "職稱": "", "申請日期": "2025/9/5",
  "出差事由": "", "出差地點": "高雄→台南",
  "出差起日": "2025/9/1", "出差起時": "08", "出差迄日": "2025/9/2", "出差迄時": "18",
  "共日": 2, "共時": 0,
  "rows": [
    {"日期起":"9/1","日期迄":"9/2","地點起":"高雄","地點迄":"台南","自用車油":450,"自用車通行":60,"住宿費":2000,"膳雜費":600,"摘要":"自駕來回90km×5、住宿一晚"}
  ],
  "預支旅費": 0, "備註": ""
}
```
一般費用模式只給：`出差人姓名`、`部門`、`申請日期`、`交易摘要`、`請款明細`（`[{"說明":"","金額":0}, ...]` 多筆自動換頁）；`rows` 留空。程式自動算合計、差旅費總額、應(收)付旅費、國字大寫與阿拉伯總計。

### 6. 交付
產出 `./out/出差旅費報告表_已填.xls`（出差模式）與 `./out/請款單_已填.docx`；手機/iPad 可順便附 PDF。提醒：照片未留存；送件記得附單據正本。

---

## fill_forms.py（已驗證可用）

```python
# -*- coding: utf-8 -*-
import json, os, sys, subprocess, shutil, copy
import re as _re

def libre_convert(src, to_ext, outdir):
    subprocess.run(["libreoffice","--headless","--convert-to",to_ext,"--outdir",outdir,src],
                   check=True, capture_output=True)
    base = os.path.splitext(os.path.basename(src))[0]
    return os.path.join(outdir, base + "." + to_ext.split(":")[0])

def roc_date(s):
    try:
        y,m,d = [int(x) for x in str(s).replace("-","/").split("/")]
        if y > 1911: y -= 1911
        return f"{y} 年 {m} 月 {d} 日"
    except Exception: return s

def roc_slash(s):
    try:
        y,m,d = [int(x) for x in str(s).replace("-","/").split("/")]
        if y > 1911: y -= 1911
        return f"{y}/{m}/{d}"
    except Exception: return s

def freeway_toll_no_etag(km, daily_free=20):
    """未裝 eTag 國道計程通行費(小型車)。每日前20km免費；20-200km@1.2；>200km@0.9；四捨五入至元。"""
    km = float(km); b = max(0.0, km - daily_free)
    toll = b*1.2 if b <= 180 else 180*1.2 + (b-180)*0.9
    return round(toll)

def fill_excel(template_xls, data, outdir):
    import openpyxl
    xlsx_tpl = libre_convert(template_xls, "xlsx", outdir)
    wb = openpyxl.load_workbook(xlsx_tpl); ws = wb.active
    def put(c,v): ws[c]=v
    put("A5","出差人姓名："+data.get("出差人姓名",""))
    put("H5","部門："+data.get("部門",""))
    put("L5","職稱："+data.get("職稱",""))
    put("P5",roc_slash(data.get("申請日期","")))
    put("C6",data.get("出差事由","")); put("J6",data.get("出差地點",""))
    put("C7",roc_slash(data.get("出差起日",""))); put("E7",data.get("出差起時",""))
    put("H7",roc_slash(data.get("出差迄日",""))); put("J7",data.get("出差迄時",""))
    put("M7",data.get("共日","")); put("O7",data.get("共時",""))
    cats=["火車高鐵","計程車","自用車油","自用車通行","飛機","交通其他","住宿費","膳雜費","交際費","其他"]
    cols=["E","F","G","H","I","J","K","L","M","N"]
    grand=0; start=10; rows=data.get("rows",[])
    for i,row in enumerate(rows):
        r=start+i
        if r>18: print("警告:明細超過9列",file=sys.stderr); break
        ws[f"A{r}"]=row.get("日期起",""); ws[f"B{r}"]=row.get("日期迄","")
        ws[f"C{r}"]=row.get("地點起",""); ws[f"D{r}"]=row.get("地點迄","")
        rs=0
        for cat,col in zip(cats,cols):
            v=row.get(cat,"")
            if v not in ("",None):
                ws[f"{col}{r}"]=v
                try: rs+=float(v)
                except: pass
        ws[f"O{r}"]=rs if rs else ""; ws[f"P{r}"]=row.get("摘要",""); grand+=rs
    for r in range(start+len(rows),19): ws[f"O{r}"]=None
    ws["O19"]=grand
    adv=float(data.get("預支旅費",0) or 0)
    if adv: ws["O20"]=adv
    ws["O21"]=grand-adv
    if data.get("備註"): ws["A20"]="備註說明："+data["備註"]
    out_xlsx=os.path.join(outdir,"出差旅費報告表_已填.xlsx"); wb.save(out_xlsx)
    out_xls=libre_convert(out_xlsx,"xls",outdir)
    final=os.path.join(outdir,"出差旅費報告表_已填.xls")
    if os.path.abspath(out_xls)!=os.path.abspath(final): shutil.move(out_xls,final)
    return final,grand

_CN_D="零壹貳參肆伍陸柒捌玖"; _CN_SMALL=["","拾","佰","仟"]; _CN_BIG=["","萬","億","兆"]
def cn_amount_string(n):
    n=int(round(n))
    if n==0: return "新台幣：零元整"
    def conv4(x):
        out=[]
        for pos in range(3,-1,-1):
            d=(x//(10**pos))%10
            if d==0:
                if out and out[-1]!="零": out.append("零")
            else: out.append(_CN_D[d]+_CN_SMALL[pos])
        return "".join(out).strip("零")
    groups=[]
    while n>0: groups.append(n%10000); n//=10000
    parts=[]
    for i in range(len(groups)-1,-1,-1):
        g=groups[i]
        if g==0:
            if parts and parts[-1]!="零": parts.append("零")
        else:
            seg=conv4(g)
            if i<len(groups)-1 and g<1000: seg="零"+seg
            parts.append(seg+_CN_BIG[i])
    s=_re.sub("零+","零","".join(parts)).strip("零")
    return "新台幣："+s+"元整"

def _append(p,text):
    if p.runs:
        r=p.add_run(text)
        try:
            src=p.runs[0]; r.font.name=src.font.name; r.font.size=src.font.size; r.bold=src.bold
            if src.font.name:
                from docx.oxml.ns import qn; r._element.rPr.rFonts.set(qn('w:eastAsia'),src.font.name)
        except Exception: pass
    else: p.add_run(text)

def _set(cell,text,label=None):
    if label:
        for p in cell.paragraphs:
            if label in p.text: _append(p,text); return
    p=cell.paragraphs[0]
    if p.runs:
        p.runs[0].text=text
        for x in p.runs[1:]: x.text=""
    else: p.add_run(text)

def _total_row_idx(t):
    for idx,row in enumerate(t.rows):
        if row.cells[0].text.strip().startswith("總計"): return list(range(4,idx)),idx
    return list(range(4,10)),10

def _check_payment(t,method):
    if not method: return
    for row in t.rows:
        for cell in row.cells:
            for p in cell.paragraphs:
                if "電匯" in p.text and "支票" in p.text:
                    full="".join(r.text for r in p.runs).replace("□"+method,"■"+method)
                    if p.runs:
                        p.runs[0].text=full
                        for x in p.runs[1:]: x.text=""
                    return

def fill_word(template_docx,data,grand,outdir):
    from docx import Document
    from docx.table import Table
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    doc=Document(template_docx)
    for p in doc.paragraphs:
        if p.text.strip().startswith("日期") and data.get("申請日期") and p.runs:
            p.runs[0].text="日期:  "+roc_date(data["申請日期"])
            for x in p.runs[1:]: x.text=""
            break
    base=doc.tables[0]; pristine=copy.deepcopy(base._tbl)
    method=data.get("付款方式","電匯")
    def _md(s):
        try:
            y,m,d=[int(x) for x in str(s).replace("-","/").split("/")]; return f"{m}月{d}日"
        except Exception: return str(s)
    if data.get("出差起日"):
        _dd=f"{_md(data.get('出差起日',''))}到{_md(data.get('出差迄日',''))}差旅費"
    else:
        _dd="差旅費"
    items=data.get("請款明細") or [{"說明":_dd,"金額":grand}]
    total=sum(int(it.get("金額",0) or 0) for it in items) if items else grand
    n=len(items)
    pages=[items] if n<=7 else [items[i:i+6] for i in range(0,n,6)]
    def fill_header(t):
        _set(t.cell(0,2),data.get("交易摘要") or ("出差旅費－"+data.get("出差事由","")))
        _set(t.cell(0,7),data.get("部門",""))
        _set(t.cell(1,2),data.get("出差人姓名",""),label="收款人名稱")
        _check_payment(t,method)
    def ensure_rows(t,need):
        idxs,tot=_total_row_idx(t)
        while len(idxs)<need:
            t.rows[tot]._tr.addprevious(copy.deepcopy(t.rows[idxs[-1]]._tr))
            idxs,tot=_total_row_idx(t)
        return idxs,tot
    start_no=0
    for pi,page_items in enumerate(pages):
        if pi==0: t=base
        else:
            new_el=copy.deepcopy(pristine)
            doc.element.body.find(qn('w:sectPr')).addprevious(new_el)
            t=Table(new_el,base._parent)
            pPr=t.cell(0,0).paragraphs[0]._p.get_or_add_pPr()
            pPr.insert(0,OxmlElement('w:pageBreakBefore'))
        fill_header(t)
        need=len(page_items); idxs,tot=ensure_rows(t,need)
        for j,it in enumerate(page_items):
            r=idxs[j]
            _set(t.cell(r,0),str(start_no+j+1))
            _set(t.cell(r,1),it.get("說明",""))
            amt=it.get("金額","")
            _set(t.cell(r,7),f"{int(amt):,}" if isinstance(amt,(int,float)) else str(amt))
        for r in idxs[need:]: _set(t.cell(r,0),"")
        start_no+=need
        if pi==len(pages)-1:
            _set(t.cell(tot,1),cn_amount_string(total)); _set(t.cell(tot,7),f"{total:,}")
        else:
            _set(t.cell(tot,1),"（接次頁）")
    if len(pages)>1:
        sectPr=doc.element.body.find(qn('w:sectPr'))
        for p in doc.paragraphs:
            if "現金領款簽收" in p.text: sectPr.addprevious(p._p); break
    out=os.path.join(outdir,"請款單_已填.docx"); doc.save(out); return out

def main():
    data=json.load(open(sys.argv[1],encoding="utf-8"))
    tpl_xls,tpl_docx,outdir=sys.argv[2],sys.argv[3],sys.argv[4]
    os.makedirs(outdir,exist_ok=True)
    if tpl_xls and tpl_xls not in ("-","none","NONE","無"):
        xls,grand=fill_excel(tpl_xls,data,outdir); print("差旅費總額:",grand); print("EXCEL:",xls)
    else:
        grand=sum(int(it.get("金額",0) or 0) for it in data.get("請款明細",[]))
    docx=fill_word(tpl_docx,data,grand,outdir); print("WORD :",docx)

if __name__=="__main__": main()
```

## 表單欄位對照（供 Claude Code 校對用）

**出差旅費報告表（Excel，1-indexed 儲存格）**
- A5 出差人姓名｜H5 部門｜L5 職稱｜P5 申請日期
- C6 出差事由｜J6 出差地點
- C7 出差起日｜E7 起時｜H7 迄日｜J7 迄時｜M7 共日｜O7 共時
- 明細列 第 10~18 列（最多 9 列），欄 E~N 對應：E火車/高鐵 F計程車 G自用車油 H自用車通行 I飛機 J交通其他 K住宿 L膳雜 M交際 N其他；O 合計（=E:N 加總）；P 工作摘要
- O19 差旅費總額｜O20 預支旅費｜O21 應(收)付旅費（=O19-O20）｜A20 備註

**請款單（Word，表格 0，row/col 0-indexed）**
- 頁首段落「日期」→ 民國
- (0,2) 交易摘要｜(0,7) 部門｜(1,2) 收款人名稱（接在「收款人名稱：」後）｜(2,2) 付款方式（■電匯）
- 項次列 row 4 起，(r,0) 項次 (r,1) 說明 (r,6合併於1) (r,7) 金額
- 總計列 (tot,1) 國字大寫、(tot,7) 阿拉伯總計
- 6/頁、上限 7、超過換頁；現金領款簽收段落多頁時移到最後

## 若要做成獨立 APP 的提醒
- 視覺辨識收據：APP 端可接雲端視覺模型或 OCR；若要「照片不落地」，在記憶體處理、辨識完即丟。
- .xls 保留格式：目前用 LibreOffice 轉檔最穩；獨立 APP 需內含 LibreOffice 或改用其他保格式方案。
- 里程：可串 Google Maps Distance Matrix API 自動算距離（需金鑰），或維持使用者貼公里數。

---

## APP 介面規格（給 Claude Code 做 UI）

使用者端只操作介面與拍照，**不接觸 JSON**。介面收集資料 → 組成 `data.json`（見上）→ 呼叫 `fill_forms.py` 產檔。JSON 是 UI 與引擎之間的內部合約。

### 資訊架構（畫面清單）
1. **首頁 / 申請列表**：列出已建立的申請（日期、摘要、金額、狀態：草稿／已產出）。右上「＋ 新增申請」。
2. **新增申請 — 選模式**：兩顆大按鈕：「出差報帳」／「一般費用」。
3. **表單頁（單筆申請）**：
   - 共同欄位：申請人姓名、部門、職稱、申請日期、交易摘要（一般費用＝費用類別下拉：差旅費/交際費/文康費/…可自訂）。姓名/部門/職稱記住上次值自動帶入。
   - 出差模式加：事由、地點、起訖日期時間；**明細以「一趟＝一列」新增**，每列可填各類費用欄或拍照帶入；另有「從常用路線選取」按鈕（讀 `routes.json`，選了自動帶來回里程→油資、國道里程→通行費，顯示算式可微調）。
   - 一般費用模式：逐筆「新增項次」（說明＋金額），可拍照帶入；超過 7 筆提示會自動分頁。
4. **拍照 OCR**：每個金額/日期欄位旁有相機鈕。拍照→視覺辨識→回填該欄（金額、日期、品項）。**照片只在記憶體辨識、不儲存、不上傳**；辨識後即丟。使用者可手動修正辨識值。
5. **預覽頁**：顯示將產出的表單摘要（總額、大寫、應收付、頁數），可返回修改。
6. **產出 / 交付**：產生 Excel（出差模式）＋Word 請款單；提供下載／分享（送印）。提醒附單據正本。

### 資料流
`介面輸入 / 拍照OCR` → 回填欄位 → APP 組 `data.json` → `fill_forms.py`（出差：兩檔；一般：`- ` 只出請款單）→ 檔案回傳介面下載。

### 狀態與儲存
- 一筆申請可存「草稿」續填。表單值可存本機（申請人/部門/職稱、常用類別、routes.json）。
- **收據照片一律不落地保存**（符合原始需求）。

### 建議技術棧（Claude Code 可自行定案）
- 跨平台：行動端 React Native／Flutter，或 PWA（手機/iPad/桌面通用，最低相依）。
- OCR：接雲端視覺模型（拍照→欄位值）；離線需求可評估 on-device OCR，但中文收據準度較低。
- 產檔：伺服器端跑 `fill_forms.py`＋LibreOffice；或找能保留 .xls 格式的等效函式庫。
- 里程：串 Google Maps Distance Matrix API 自動算，或用 `routes.json` 預存值＋手動貼公里數。

### 建議開發順序
1. 表單頁 + `data.json` 組裝 + `fill_forms.py` 產檔（核心，先能手動填就出檔）。
2. 常用路線選取（讀 routes.json 自動帶里程/通行費）。
3. 拍照 OCR 回填。
4. 首頁列表 / 草稿 / 分享。
