import re, difflib, json, unicodedata
from io import BytesIO
from pathlib import Path
from datetime import date, datetime

import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageEnhance, ImageFilter
import pytesseract
from pytesseract import Output
try:
    import fitz
except Exception:
    fitz = None

try:
    from rapidfuzz import process, fuzz
except Exception:
    process = None
    fuzz = None

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.units import mm
except Exception:
    SimpleDocTemplate = None

st.set_page_config(page_title="TUUZA Procurement Desk", page_icon="💊", layout="wide")
st.markdown("""
<style>
.block-container{padding-top:1.2rem;max-width:1500px}
.hero{padding:1.2rem 1.4rem;border-radius:16px;background:linear-gradient(110deg,#e7f8f4,#f8fbfc);border:1px solid #cce6df}
.hero h1{margin:0;font-size:1.8rem;color:#123d39}.hero p{margin:.35rem 0 0;color:#52616b}
div[data-testid="stMetric"]{border:1px solid #e2e8f0;padding:12px;border-radius:12px}
</style>
<div class="hero"><h1>💊 TUUZA Procurement Desk</h1><p>Medicine catalogue · normalized product search · supplier price comparison · OCR-assisted procurement</p></div>
""", unsafe_allow_html=True)
st.caption("Prototype for TUUZA Pharmacy. Review supplier offers and all extracted/imported values before purchasing.")

DATA_DIR = Path(__file__).parent / "data"
CAT_PATH = DATA_DIR / "ubumwe_catalogue.csv"
COMP_PATH = DATA_DIR / "supplier_comparison_reference.csv"

def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii","ignore").decode().lower()
    s = s.replace("&", " and ")
    # normalize common dosage/form and packaging variants
    substitutions = [
        (r"\btab(s|let|lets)?\b", " tablet "),
        (r"\bcap(s|sule|sules)?\b", " capsule "),
        (r"\bsyr\b", " syrup "),
        (r"\bsp\b", " syrup "),
        (r"\b susp\b", " suspension "),
        (r"\bcrm\b", " cream "),
        (r"\boint\b", " ointment "),
        (r"\bdrops?\b", " drop "),
        (r"\binj\b", " injection "),
        (r"\bpcs?\b", " piece "),
        (r"\bmls\b", " ml "),
        (r"\bgrs?\b", " g "),
        (r"\bb\s*/\s*(\d+)", r" pack \1 "),
        (r"\b(\d+)\s*x\s*(\d+)\b", r" pack \1 \2 "),
    ]
    for pat, rep in substitutions:
        s = re.sub(pat, rep, s)
    s = re.sub(r"[^a-z0-9.]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def fuzzy_best(query, choices, limit=5):
    if not choices: return []
    if process and fuzz:
        return [(name, score) for name, score, _ in process.extract(query, choices, scorer=fuzz.WRatio, limit=limit)]
    q=norm(query)
    return [(name, int(difflib.SequenceMatcher(None,q,norm(name)).ratio()*100)) for name in sorted(choices,key=lambda n:difflib.SequenceMatcher(None,q,norm(n)).ratio(),reverse=True)[:limit]]

def read_catalogue():
    if CAT_PATH.exists():
        df=pd.read_csv(CAT_PATH).fillna("")
        for c in ["Product name","Batch","Unit price","Supplier"]:
            if c not in df: df[c]=""
        df["Unit price"]=pd.to_numeric(df["Unit price"],errors="coerce")
        return df
    return pd.DataFrame(columns=["Product name","Batch","Unit price","Supplier"])

def read_reference():
    if COMP_PATH.exists():
        df=pd.read_csv(COMP_PATH).fillna("")
        return df
    return pd.DataFrame(columns=["Product name","Quantity","Unit","Ubumwe","FEDILIS","Sun ltd"])

def as_num(v, default=0):
    try:
        if pd.isna(v) or str(v).strip()=="": return default
        return float(str(v).replace(",","").strip())
    except Exception: return default

def money(v):
    return f"{as_num(v):,.0f}" if as_num(v) else "—"

def build_pdf(df, pharmacy, ref, req_date, mode="Requisition"):
    if SimpleDocTemplate is None:
        return None
    buf=BytesIO()
    doc=SimpleDocTemplate(buf,pagesize=landscape(A4),rightMargin=12*mm,leftMargin=12*mm,topMargin=12*mm,bottomMargin=12*mm)
    styles=getSampleStyleSheet()
    story=[Paragraph(f"<b>{pharmacy}</b>",styles["Title"]),Paragraph(f"{mode} | Reference: {ref} | Date: {req_date}",styles["Normal"]),Spacer(1,8)]
    cols=["No.","Product name","Quantity","Unit","Selected supplier","Unit price (RWF)","Total (RWF)"]
    data=[cols]
    for i,(_,r) in enumerate(df.iterrows(),1):
        data.append([str(i),str(r.get("Product name","")),str(r.get("Quantity","")),str(r.get("Unit","")),str(r.get("Selected supplier","")),money(r.get("Selected price",0)),money(as_num(r.get("Quantity",0))*as_num(r.get("Selected price",0)))])
    if len(data)==1: data.append(["","","","","","",""])
    t=Table(data,repeatRows=1,colWidths=[12*mm,90*mm,22*mm,18*mm,43*mm,30*mm,30*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#164e63")),("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),8),
        ("GRID",(0,0),(-1,-1),0.4,colors.HexColor("#cbd5e1")),("VALIGN",(0,0),(-1,-1),"TOP"),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f1f5f9")]),
        ("ALIGN",(2,1),(-1,-1),"RIGHT"),("LEFTPADDING",(0,0),(-1,-1),5),("RIGHTPADDING",(0,0),(-1,-1),5),
        ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)
    ]))
    story += [t,Spacer(1,8),Paragraph(f"<b>Estimated total: {sum(as_num(r.get('Quantity',0))*as_num(r.get('Selected price',0)) for _,r in df.iterrows()):,.0f} RWF</b>",styles["Heading2"]),Spacer(1,10),Paragraph("Prepared for review. Confirm prices, pack sizes and availability with the supplier before purchase.",styles["Italic"])]
    doc.build(story)
    return buf.getvalue()

def build_png(df, pharmacy, ref, req_date):
    width=1500
    pad=42
    cols=[("No.",55),("Product name",560),("Qty",90),("Unit",100),("Supplier",230),("Unit price",180),("Total",180)]
    row_h=42
    title_h=140
    height=title_h + row_h*(len(df)+2)+pad*2
    im=Image.new("RGB",(width,height),"white")
    d=ImageDraw.Draw(im)
    try:
        font=ImageFont.truetype("DejaVuSans.ttf",18)
        bold=ImageFont.truetype("DejaVuSans-Bold.ttf",23)
        small=ImageFont.truetype("DejaVuSans.ttf",16)
    except Exception:
        font=bold=small=ImageFont.load_default()
    d.text((pad,25),pharmacy,font=bold,fill="#123d39")
    d.text((pad,66),f"PURCHASE REQUISITION  |  {ref}  |  {req_date}",font=font,fill="#334155")
    y=title_h
    d.rectangle((pad,y,width-pad,y+row_h),fill="#164e63")
    x=pad
    for name,w in cols:
        d.text((x+7,y+10),name,font=font,fill="white"); x+=w
    y+=row_h
    total=0
    for i,(_,r) in enumerate(df.iterrows(),1):
        if i%2==0: d.rectangle((pad,y,width-pad,y+row_h),fill="#f1f5f9")
        q=as_num(r.get("Quantity",0)); price=as_num(r.get("Selected price",0)); line=q*price; total+=line
        vals=[str(i),str(r.get("Product name",""))[:54],str(r.get("Quantity","")),str(r.get("Unit","")),str(r.get("Selected supplier",""))[:20],money(price),money(line)]
        x=pad
        for (name,w),val in zip(cols,vals):
            d.text((x+7,y+10),val,font=small,fill="#0f172a"); x+=w
        d.line((pad,y+row_h,width-pad,y+row_h),fill="#cbd5e1",width=1)
        y+=row_h
    y+=18
    d.text((pad,y),f"Estimated total: {total:,.0f} RWF",font=bold,fill="#123d39")
    d.text((pad,y+40),"Confirm supplier quotation, pack size and availability before final purchase.",font=small,fill="#475569")
    out=BytesIO(); im.save(out,format="PNG"); return out.getvalue()



def ocr_to_images(uploaded, dpi=300):
    """Render uploaded images/PDF pages to PIL images for OCR fallback."""
    raw = uploaded.getvalue()
    if uploaded.name.lower().endswith(".pdf"):
        if fitz is None:
            st.error("PDF support needs PyMuPDF. Install the requirements.")
            return []
        doc = fitz.open(stream=raw, filetype="pdf")
        result = []
        scale = max(1.5, min(4.0, dpi / 72))
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            result.append(Image.frombytes("RGB", [pix.width, pix.height], pix.samples))
        return result
    try:
        return [Image.open(BytesIO(raw)).convert("RGB")]
    except Exception:
        return []


def _preprocess_variants(image):
    """Generate multiple lightweight preprocessing candidates for difficult scans."""
    image = ImageOps.exif_transpose(image).convert("RGB")
    candidates = []
    # Scale small screenshots; avoid excessive memory use on cloud deployments.
    if image.width < 1600:
        scale = min(3.0, max(1.5, 1600 / max(image.width, 1)))
        image = image.resize((int(image.width * scale), int(image.height * scale)))
    gray = ImageOps.grayscale(image)
    gray = ImageOps.autocontrast(gray)
    candidates.append(("autocontrast", ImageEnhance.Contrast(gray).enhance(1.4).filter(ImageFilter.SHARPEN)))
    candidates.append(("high_contrast", ImageEnhance.Contrast(gray).enhance(2.0).filter(ImageFilter.SHARPEN)))
    # Adaptive threshold is optional; OpenCV may not be available on a constrained host.
    try:
        import cv2
        import numpy as np
        arr = np.array(gray)
        arr = cv2.fastNlMeansDenoising(arr, None, 8, 7, 21)
        th = cv2.adaptiveThreshold(arr, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY, 31, 11)
        candidates.append(("adaptive_threshold", Image.fromarray(th)))
    except Exception:
        pass
    return candidates


def _ocr_words(image, psm=6):
    config = f"--oem 3 --psm {psm}"
    data = pytesseract.image_to_data(image, output_type=Output.DATAFRAME, config=config, timeout=15)
    if data is None or data.empty:
        return pd.DataFrame()
    data = data.dropna(subset=["text"]).copy()
    data["text"] = data["text"].astype(str).str.strip()
    data = data[data["text"] != ""]
    if "conf" in data:
        data["conf"] = pd.to_numeric(data["conf"], errors="coerce")
        data = data[(data["conf"].isna()) | (data["conf"] >= 0)]
    return data


def _group_ocr_lines(data):
    lines = []
    if data.empty:
        return lines
    keys = [c for c in ["page_num", "block_num", "par_num", "line_num"] if c in data.columns]
    for _, g in data.groupby(keys, sort=True):
        g = g.sort_values("left")
        text = " ".join(g["text"].astype(str).tolist()).strip()
        if not text:
            continue
        confs = pd.to_numeric(g.get("conf", pd.Series(dtype=float)), errors="coerce").dropna()
        lines.append({
            "top": int(pd.to_numeric(g["top"], errors="coerce").median()),
            "words": g.to_dict("records"),
            "text": text,
            "confidence": float(confs.mean()) if not confs.empty else 0.0,
        })
    return sorted(lines, key=lambda x: x["top"])


def _header_key(token):
    t = re.sub(r"[^a-z0-9#]", "", str(token).lower())
    aliases = {
        "product":"Product name", "products":"Product name", "description":"Product name",
        "name":"Product name", "drug":"Product name", "item":"Product name", "medicine":"Product name",
        "code":"Product code", "productcode":"Product code", "sku":"Product code",
        "batch":"Batch", "batch#":"Batch", "batchno":"Batch", "batchnumber":"Batch",
        "expiry":"Expiry", "exp":"Expiry", "expiration":"Expiry", "expirydate":"Expiry",
        "qty":"Quantity", "qty.":"Quantity", "quantity":"Quantity", "quant":"Quantity", "quanti":"Quantity", "quantit":"Quantity",
        "unit":"Unit", "uom":"Unit",
        "price":"Price", "unitprice":"Price", "rate":"Price", "cost":"Price",
        "total":"Line total", "amount":"Line total", "linetotal":"Line total",
        "pack":"Pack size", "packsize":"Pack size",
    }
    return aliases.get(t)


def _number_from_text(value, default=0):
    """Parse common RWF amounts with commas, decimal points, or currency labels."""
    if value is None:
        return default
    s = str(value).strip().replace("RWF", "").replace("FRW", "").replace("rwf", "")
    s = s.replace(",", "").replace(" ", "")
    # Correct frequent OCR confusion only in numeric-looking values.
    if not re.search(r"\d", s):
        return default
    s = re.sub(r"[^0-9.\-]", "", s)
    try:
        return float(s) if s not in ("", ".", "-", "-.") else default
    except ValueError:
        return default


def _expiry_is_plausible(value):
    value = str(value or "").strip()
    if not value:
        return True
    # Accept common MM/YYYY, MM/YY, YYYY-MM and DD/MM/YYYY representations.
    return bool(re.search(r"^(0?[1-9]|1[0-2])[/.-](20)?\d{2}$", value)
                or re.search(r"^20\d{2}[-/](0?[1-9]|1[0-2])$", value)
                or re.search(r"^(0?[1-9]|[12]\d|3[01])[/.-](0?[1-9]|1[0-2])[/.-]20\d{2}$", value)
                or re.search(r"^\d{6}$", value) or re.search(r"^\d{8}$", value))



def _detect_vertical_boundaries(image):
    """Detect long vertical table rules to avoid assigning cells by header text centers alone."""
    try:
        import cv2
        import numpy as np
        gray = np.array(ImageOps.grayscale(image))
        h, w = gray.shape[:2]
        bw = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                   cv2.THRESH_BINARY_INV, 15, 8)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(18, h // 25)))
        vertical = cv2.morphologyEx(bw, cv2.MORPH_OPEN, kernel)
        projection = (vertical > 0).sum(axis=0)
        xs = np.where(projection >= h * 0.30)[0]
        groups = []
        if len(xs):
            start = previous = int(xs[0])
            for x in xs[1:]:
                x = int(x)
                if x > previous + 2:
                    groups.append((start, previous))
                    start = x
                previous = x
            groups.append((start, previous))
        lines = [int((a + b) / 2) for a, b in groups]
        # Keep only distinct boundaries; force image edges as table edges.
        lines = sorted(set([0, w - 1] + [x for x in lines if 2 < x < w - 3]))
        # A usable table usually has at least 4 vertical rules.
        return lines if len(lines) >= 4 else []
    except Exception:
        return []


def _parse_table_from_lines(lines, supplier, source_name, image=None):
    header_idx, headers = None, []
    # Prefer a row with product plus at least two other recognizable column labels.
    for i, line in enumerate(lines):
        found = []
        for w in line["words"]:
            key = _header_key(w.get("text", ""))
            if key:
                found.append((int(w.get("left", 0) + w.get("width", 0) / 2), key))
        unique, seen = [], set()
        for item in sorted(found):
            if item[1] not in seen:
                unique.append(item)
                seen.add(item[1])
        if "Product name" in seen and len(unique) >= 3:
            header_idx, headers = i, unique
            break

    rows = []
    if header_idx is None:
        return pd.DataFrame(), None

    centers = [x[0] for x in headers]
    names = [x[1] for x in headers]
    grid_bounds = _detect_vertical_boundaries(image) if image is not None else []
    if grid_bounds:
        # Restrict detected rules to the table's header span. This removes page edges,
        # scrollbars and unrelated vertical marks that otherwise shift every column.
        min_header_x, max_header_x = min(centers), max(centers)
        left_candidates = [x for x in grid_bounds if x <= min_header_x]
        right_candidates = [x for x in grid_bounds if x >= max_header_x]
        left_edge = max(left_candidates, key=lambda x: x) if left_candidates else grid_bounds[0]
        right_edge = min(right_candidates, key=lambda x: x) if right_candidates else grid_bounds[-1]
        trimmed = [x for x in grid_bounds if left_edge <= x <= right_edge]
        grid_bounds = trimmed if len(trimmed) >= 4 else []
    grid_names = []
    if grid_bounds:
        grid_names = [""] * (len(grid_bounds) - 1)
        for x_center, key in headers:
            col = 0
            while col < len(grid_bounds) - 2 and x_center > grid_bounds[col + 1]:
                col += 1
            if not grid_names[col]:
                grid_names[col] = key
        # Preserve empty physical columns as generic fields so positions remain stable.
        grid_names = [name if name else f"Unused column {i+1}" for i, name in enumerate(grid_names)]
    for line in lines[header_idx + 1:]:
        cell_names = grid_names if grid_names else names
        cells = {n: [] for n in cell_names}
        for w in line["words"]:
            x = int(w.get("left", 0) + w.get("width", 0) / 2)
            if grid_bounds:
                col = 0
                while col < len(grid_bounds) - 2 and x > grid_bounds[col + 1]:
                    col += 1
            else:
                col = 0
                while col < len(centers) - 1 and x > (centers[col] + centers[col + 1]) / 2:
                    col += 1
            col = min(col, len(cell_names) - 1)
            cells[cell_names[col]].append((int(w.get("left", 0)), str(w.get("text", "")), _number_from_text(w.get("conf", 0), 0)))
        cell_conf = {
            k: round(sum(max(0, c) for _, _, c in vs) / max(1, sum(1 for _, _, c in vs if c >= 0)), 1)
            if vs else 0.0
            for k, vs in cells.items()
        }
        cells = {k: " ".join(v for _, v, _ in sorted(vs)).strip() for k, vs in cells.items()}
        joined = " ".join(cells.values()).lower()
        if not joined.strip() or re.search(r"total pages|customer name|number of items|total a-ex|grand total|quotation$", joined):
            continue
        product = cells.get("Product name", "").strip(" -|_[]")
        if len(re.sub(r"\W", "", product)) < 3:
            continue
        def clean_edge(value):
            return re.sub(r"^[^A-Za-z0-9]+|[^A-Za-z0-9/.-]+$", "", str(value or "").strip())
        qty = _number_from_text(cells.get("Quantity", ""), 0)
        price = _number_from_text(cells.get("Price", ""), 0)
        total = _number_from_text(cells.get("Line total", ""), 0)
        batch_value = clean_edge(cells.get("Batch", ""))
        expiry_value = clean_edge(cells.get("Expiry", ""))
        # OCR text confidence is aggregated from the row's word confidence.
        row_conf = line.get("confidence", 0.0)
        flags = []
        if not price:
            flags.append("Price missing/unclear")
        if qty <= 0:
            flags.append("Quantity missing/unclear")
        if not _expiry_is_plausible(expiry_value):
            flags.append("Expiry format needs review")
        if total and qty and price and abs(total - qty * price) > max(2.0, 0.02 * total):
            flags.append("Line total differs from quantity × price")
        product_conf = cell_conf.get("Product name", 0.0)
        price_conf = cell_conf.get("Price", 0.0)
        qty_conf = cell_conf.get("Quantity", 0.0)
        batch_conf = cell_conf.get("Batch", 0.0)
        expiry_conf = cell_conf.get("Expiry", 0.0)
        if row_conf < 65 or product_conf < 65:
            flags.append("Low OCR confidence")
        if price and price_conf < 65:
            flags.append("Price OCR confidence is low")
        rows.append({
            "Product name": product,
            "Supplier": supplier,
            "Price": price,
            "Unit": cells.get("Unit", ""),
            "Batch": batch_value,
            "Expiry": expiry_value,
            "Source": source_name,
            "Quantity": qty,
            "Line total": total if total else qty * price,
            "OCR confidence": round(row_conf, 1),
            "Product confidence": product_conf,
            "Quantity confidence": qty_conf,
            "Price confidence": price_conf,
            "Batch confidence": batch_conf,
            "Expiry confidence": expiry_conf,
            "Validation flags": "; ".join(flags) if flags else "Review product identity and pack size",
            "OCR review": "Required",
        })
    return pd.DataFrame(rows), header_idx



def _candidate_quality(rows, data, raw, psm):
    if rows.empty:
        return -1000.0
    avg_conf = float(pd.to_numeric(data.get("conf", pd.Series(dtype=float)), errors="coerce").dropna().mean() or 0) if not data.empty else 0
    missing_price = int((pd.to_numeric(rows["Price"], errors="coerce").fillna(0) <= 0).sum())
    missing_qty = int((pd.to_numeric(rows["Quantity confidence"], errors="coerce").fillna(0) <= 0).sum())
    mismatch = int(rows["Validation flags"].astype(str).str.contains("differs", case=False).sum())
    low_conf = int(rows["Validation flags"].astype(str).str.contains("Low OCR", case=False).sum())
    return (len(rows) * 2 + avg_conf * 0.4 + min(len(raw), 2000) / 300
            - missing_price * 8 - missing_qty * 5 - mismatch * 5 - low_conf
            + (4 if psm == 4 else 0))


def ocr_image_rows(image, supplier, source_name="Uploaded quotation"):
    """Run a bounded multi-pass OCR pipeline and use table structure/validation to rank candidates."""
    variants = _preprocess_variants(image)
    # First pass: two lightweight contrast variants and two layout modes.
    candidates = []
    best_raw = ""
    for variant_name, candidate in variants[:2]:
        for psm in (4, 6):
            try:
                data = _ocr_words(candidate, psm=psm)
                lines = _group_ocr_lines(data)
                raw = "\n".join(x["text"] for x in lines)
                rows, _ = _parse_table_from_lines(lines, supplier, source_name, candidate)
                score = _candidate_quality(rows, data, raw, psm)
                candidates.append({"rows": rows, "raw": raw, "score": score, "variant": variant_name, "psm": psm})
                if len(raw) > len(best_raw):
                    best_raw = raw
            except Exception:
                continue

    # Adaptive threshold is a targeted fallback for dense tables where quantity/price
    # columns appear incomplete, instead of running every OCR mode on every upload.
    valid = [c for c in candidates if not c["rows"].empty]
    need_adaptive = not valid
    if valid:
        current = max(valid, key=lambda c: c["score"])["rows"]
        qty = pd.to_numeric(current.get("Quantity", pd.Series(dtype=float)), errors="coerce").fillna(0)
        price = pd.to_numeric(current.get("Price", pd.Series(dtype=float)), errors="coerce").fillna(0)
        qty_conf = pd.to_numeric(current.get("Quantity confidence", pd.Series(dtype=float)), errors="coerce").fillna(0)
        missing_price_ratio = float((price <= 0).mean()) if len(price) else 1
        missing_qty_conf_ratio = float((qty_conf <= 0).mean()) if len(qty_conf) else 1
        single_qty_ratio = float((qty == 1).mean()) if len(qty) else 0
        need_adaptive = missing_price_ratio >= 0.10 or missing_qty_conf_ratio >= 0.10 or (len(current) >= 10 and single_qty_ratio >= 0.45)

    if need_adaptive and len(variants) > 2:
        try:
            variant_name, candidate = variants[2]
            data = _ocr_words(candidate, psm=6)
            lines = _group_ocr_lines(data)
            raw = "\n".join(x["text"] for x in lines)
            rows, _ = _parse_table_from_lines(lines, supplier, source_name, candidate)
            score = _candidate_quality(rows, data, raw, 6)
            candidates.append({"rows": rows, "raw": raw, "score": score, "variant": variant_name, "psm": 6})
            if len(raw) > len(best_raw):
                best_raw = raw
        except Exception:
            pass

    valid = [c for c in candidates if not c["rows"].empty]
    if valid:
        chosen = max(valid, key=lambda c: c["score"])
        # If the chosen table has many default-looking single quantities, prefer a
        # thresholded result that captured more quantity cells and still has prices.
        chosen_rows = chosen["rows"]
        chosen_qty = pd.to_numeric(chosen_rows["Quantity"], errors="coerce").fillna(0)
        if len(chosen_rows) >= 10 and float((chosen_qty == 1).mean()) >= 0.45:
            adaptive = [c for c in valid if c["variant"] == "adaptive_threshold"]
            if adaptive:
                alt = max(adaptive, key=lambda c: c["score"])
                alt_rows = alt["rows"]
                alt_qty = pd.to_numeric(alt_rows["Quantity"], errors="coerce").fillna(0)
                alt_price = pd.to_numeric(alt_rows["Price"], errors="coerce").fillna(0)
                if len(alt_rows) >= len(chosen_rows) - 2 and float((alt_qty == 1).mean()) < float((chosen_qty == 1).mean()) and float((alt_price > 0).mean()) >= 0.85:
                    chosen = alt
        result = chosen["rows"].copy()
        # Explicitly flag suspicious default-like quantity patterns for human review.
        qty = pd.to_numeric(result["Quantity"], errors="coerce").fillna(0)
        if len(result) >= 10 and float((qty == 1).mean()) >= 0.45:
            result["Validation flags"] = result["Validation flags"].astype(str).apply(
                lambda x: (x + "; " if x else "") + "Many quantities read as 1; verify quantities against source"
            )
        return result, chosen["raw"]

    # Fallback lines are unstructured suggestions only; all numeric fields remain blank/zero.
    try:
        candidate = variants[0][1]
        data = _ocr_words(candidate, psm=6)
        lines = _group_ocr_lines(data)
        best_raw = "\n".join(x["text"] for x in lines) or best_raw
        fallback = []
        for line in lines:
            txt = line["text"]
            if len(txt) > 12 and re.search(r"\d", txt) and not re.search(r"quotation|customer name|total pages|total a-ex", txt, re.I):
                fallback.append({
                    "Product name": txt, "Supplier": supplier, "Price": 0.0, "Unit": "",
                    "Batch": "", "Expiry": "", "Source": source_name, "Quantity": 0,
                    "Line total": 0.0, "OCR confidence": round(line["confidence"], 1),
                    "Product confidence": round(line["confidence"], 1), "Quantity confidence": 0.0,
                    "Price confidence": 0.0, "Batch confidence": 0.0, "Expiry confidence": 0.0,
                    "Validation flags": "Could not detect table columns - verify every field",
                    "OCR review": "Manual row reconstruction required",
                })
        return pd.DataFrame(fallback), best_raw
    except Exception:
        return pd.DataFrame(), best_raw


def _pdf_text_rows(uploaded, supplier):
    """Try direct extraction for selectable-text PDFs before raster OCR."""
    if fitz is None or not uploaded.name.lower().endswith(".pdf"):
        return pd.DataFrame(), ""
    try:
        doc = fitz.open(stream=uploaded.getvalue(), filetype="pdf")
    except Exception:
        return pd.DataFrame(), ""
    frames, text_pages = [], []
    for page_no, page in enumerate(doc, 1):
        text = page.get_text("text") or ""
        text_pages.append(f"Page {page_no}:\n{text}")
        if len(text.strip()) < 80:
            continue
        # pdfplumber's table extraction is preferable where available.
        try:
            import pdfplumber
            with pdfplumber.open(BytesIO(uploaded.getvalue())) as pdf:
                tables = pdf.pages[page_no - 1].extract_tables() or []
            for table in tables:
                if not table or len(table) < 2:
                    continue
                header = [str(x or "").strip() for x in table[0]]
                keys = [_header_key(x) for x in header]
                if "Product name" not in keys:
                    continue
                records = []
                for cells in table[1:]:
                    row = {keys[i]: str(cells[i] or "").strip() for i in range(min(len(keys), len(cells))) if keys[i]}
                    product = row.get("Product name", "")
                    if not product or len(product) < 3:
                        continue
                    qty = _number_from_text(row.get("Quantity", ""), 0)
                    price = _number_from_text(row.get("Price", ""), 0)
                    total = _number_from_text(row.get("Line total", ""), 0)
                    flags = []
                    if not price: flags.append("Price missing/unclear")
                    if total and qty and price and abs(total - qty * price) > max(2, total * .02):
                        flags.append("Line total differs from quantity × price")
                    if not _expiry_is_plausible(row.get("Expiry", "")):
                        flags.append("Expiry format needs review")
                    records.append({
                        "Product name": product, "Supplier": supplier, "Price": price,
                        "Unit": row.get("Unit", ""), "Batch": row.get("Batch", ""),
                        "Expiry": row.get("Expiry", ""), "Source": uploaded.name,
                        "Quantity": qty, "Line total": total if total else qty * price,
                        "OCR confidence": 100.0, "Product confidence": 100.0,
                        "Quantity confidence": 100.0, "Price confidence": 100.0,
                        "Batch confidence": 100.0, "Expiry confidence": 100.0,
                        "Validation flags": "; ".join(flags) if flags else "Review product identity and pack size",
                        "OCR review": "Extracted from PDF text/table; verify",
                    })
                if records:
                    frames.append(pd.DataFrame(records))
        except Exception:
            continue
    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return combined, "\n\n".join(text_pages)

if "requisition" not in st.session_state:
    st.session_state.requisition = pd.DataFrame(columns=["Product name", "Normalized name", "Quantity", "Unit", "Selected supplier", "Selected price", "Product code", "Batch", "Expiry"])
if "supplier_quotes" not in st.session_state:
    st.session_state.supplier_quotes = pd.DataFrame(columns=["Product name", "Supplier", "Price", "Unit", "Batch", "Expiry", "Source", "Quantity", "Line total"])
if "requisition_reviewed" not in st.session_state:
    st.session_state.requisition_reviewed = False
if "show_quote_dialog" not in st.session_state:
    st.session_state.show_quote_dialog = False
if "aliases" not in st.session_state:
    st.session_state.aliases = {}
if "selected_offers" not in st.session_state:
    st.session_state.selected_offers = {}

catalogue = read_catalogue()
refdata = read_reference()
catalogue_names = sorted(catalogue["Product name"].dropna().astype(str).unique().tolist(), key=str.lower)
ref_names = refdata["Product name"].dropna().astype(str).unique().tolist() if not refdata.empty else []
all_names = sorted(set(catalogue_names + ref_names), key=str.lower)

# Header and workflow progress
steps = ["1 · Requisition", "2 · Review & confirm", "3 · Quotation matching", "4 · Supplier purchase lists"]
if "workflow_step" not in st.session_state:
    st.session_state.workflow_step = 1
st.markdown("#### Procurement workflow")
st.caption("Complete each stage in order. Quotation offers are not treated as confirmed stock until the supplier confirms them.")
step_cols = st.columns(4)
for i, label in enumerate(steps, 1):
    with step_cols[i-1]:
        st.markdown(("**▶ " if st.session_state.workflow_step == i else "✓ " if st.session_state.workflow_step > i else "") + label)

tabs = st.tabs(["1 · Requisition", "2 · Review & confirm", "3 · Quotation matching", "4 · Supplier lists", "Medicine library"])

with tabs[0]:
    st.subheader("1. Make a requisition")
    c1, c2, c3 = st.columns([1.5, 1, 1])
    with c1: pharmacy = st.text_input("Pharmacy name", "PHARMACY TUUZA LTD", key="pharmacy_name")
    with c2: req_ref = st.text_input("Requisition reference", f"TU-REQ-{date.today():%Y%m%d}", key="req_ref")
    with c3: req_date = st.date_input("Requisition date", date.today(), key="req_date")
    st.markdown("##### Add products to the table")
    st.caption("Search the catalogue by typing. Use ↑ / ↓ to move through suggestions and Enter to select. You can also enter a product not found in the library.")
    add1, add2, add3, add4 = st.columns([3, 1, 1, 1])
    with add1:
        chosen_product = st.selectbox("Medicine / product", [""] + all_names + ["＋ Add custom product…"], key="req_product_search", placeholder="Type a medicine name…")
        custom_product = ""
        if chosen_product == "＋ Add custom product…":
            custom_product = st.text_input("Custom product name", key="req_custom_product")
    with add2: add_qty = st.number_input("Quantity", min_value=1, value=1, step=1, key="req_add_qty")
    with add3: add_unit = st.selectbox("Unit", ["BX", "BOX", "PACK", "BOT", "BOTTLE", "TUBE", "PCS", "UNIT", "VIAL", "AMPOULE", "OTHER"], key="req_add_unit")
    with add4: add_code = st.text_input("Code (optional)", key="req_add_code")
    selected_name = custom_product.strip() if chosen_product == "＋ Add custom product…" else chosen_product.strip()
    if selected_name and norm(selected_name) in st.session_state.aliases:
        selected_name = st.session_state.aliases[norm(selected_name)]
    if st.button("＋ Add line to requisition", type="primary", disabled=not bool(selected_name), key="add_req_line"):
        new_row = {"Product name": selected_name, "Normalized name": norm(selected_name), "Quantity": int(add_qty), "Unit": add_unit, "Selected supplier": "", "Selected price": 0.0, "Product code": add_code, "Batch": "", "Expiry": ""}
        st.session_state.requisition = pd.concat([st.session_state.requisition, pd.DataFrame([new_row])], ignore_index=True)
        st.session_state.requisition_reviewed = False
        st.session_state.workflow_step = 1
        st.rerun()

    st.markdown("##### Requisition table")
    if st.session_state.requisition.empty:
        st.info("Start by adding medicine lines above. The requisition table will appear here.")
    else:
        editable = st.data_editor(
            st.session_state.requisition,
            num_rows="dynamic", use_container_width=True, key="draft_requisition_table",
            column_config={
                "Product name": st.column_config.SelectboxColumn("Product name", options=sorted(set(all_names + st.session_state.requisition["Product name"].fillna("").astype(str).tolist())), required=True, help="Choose a catalogue product. For custom names, use the add-line form above."),
                "Quantity": st.column_config.NumberColumn("Quantity", min_value=1, step=1, required=True),
                "Unit": st.column_config.SelectboxColumn("Unit", options=["BX", "BOX", "PACK", "BOT", "BOTTLE", "TUBE", "PCS", "UNIT", "VIAL", "AMPOULE", "OTHER"]),
                "Selected price": st.column_config.NumberColumn("Selected price (RWF)", min_value=0, format="%.0f", disabled=True),
                "Selected supplier": st.column_config.TextColumn("Selected supplier", disabled=True),
                "Normalized name": st.column_config.TextColumn("Normalized name", disabled=True),
            },
        )
        editable["Normalized name"] = editable["Product name"].fillna("").map(norm)
        st.session_state.requisition = editable
        active = editable[editable["Product name"].fillna("").astype(str).str.strip() != ""]
        m1, m2 = st.columns(2)
        m1.metric("Requisition lines", len(active))
        m2.metric("Total requested units", int(active["Quantity"].apply(as_num).sum()) if not active.empty else 0)
        if st.button("Submit requisition for review →", type="primary", key="submit_for_review", disabled=active.empty):
            st.session_state.requisition = active.reset_index(drop=True)
            st.session_state.requisition_reviewed = False
            st.session_state.workflow_step = 2
            st.success("Requisition submitted to the review stage.")
            st.rerun()

with tabs[1]:
    st.subheader("2. Review and confirm quantities")
    st.write("Review product identity, quantities, units and any notes before the requisition can proceed to supplier quotation matching.")
    if st.session_state.requisition.empty:
        st.info("Create a requisition in Stage 1 first.")
    else:
        review_df = st.data_editor(
            st.session_state.requisition,
            num_rows="dynamic", use_container_width=True, key="review_requisition_table",
            column_config={
                "Product name": st.column_config.TextColumn("Product name", required=True),
                "Quantity": st.column_config.NumberColumn("Confirm quantity", min_value=1, step=1, required=True),
                "Unit": st.column_config.SelectboxColumn("Unit", options=["BX", "BOX", "PACK", "BOT", "BOTTLE", "TUBE", "PCS", "UNIT", "VIAL", "AMPOULE", "OTHER"]),
                "Selected price": st.column_config.NumberColumn("Selected price (RWF)", min_value=0, format="%.0f", disabled=True),
                "Selected supplier": st.column_config.TextColumn("Selected supplier", disabled=True),
                "Normalized name": st.column_config.TextColumn("Normalized name", disabled=True),
            },
        )
        review_df["Normalized name"] = review_df["Product name"].fillna("").map(norm)
        if st.button("Save review changes", key="save_review_changes"):
            st.session_state.requisition = review_df.reset_index(drop=True)
            st.session_state.requisition_reviewed = False
            st.success("Review edits saved. Confirm them below when ready.")
        st.divider()
        confirmed = st.checkbox("I confirm the product names, quantities and units above are correct and ready for quotation matching.", value=bool(st.session_state.requisition_reviewed), key="review_confirm_checkbox")
        if st.button("Confirm requisition and continue to quotation matching →", type="primary", disabled=not confirmed, key="confirm_review"):
            st.session_state.requisition = review_df.reset_index(drop=True)
            st.session_state.requisition_reviewed = True
            st.session_state.workflow_step = 3
            st.success("Requisition confirmed. You can now import supplier quotations and compare offers.")
            st.rerun()

with tabs[2]:
    st.subheader("3. Quotation matching")
    if st.session_state.requisition.empty:
        st.info("Create a requisition first.")
    elif not st.session_state.requisition_reviewed:
        st.warning("Complete Stage 2 and confirm the quantities before matching supplier quotations.")
    else:
        st.write("Upload each wholesaler quotation, review the OCR output, then confirm it to add its prices to the comparison table.")
        qtop1, qtop2 = st.columns([2, 1])
        with qtop1:
            st.markdown("**Supplier quotations**")
            st.caption(f"Confirmed quotation lines loaded: {len(st.session_state.supplier_quotes)}")
        with qtop2:
            if st.button("＋ Upload supplier quotation", type="primary", key="open_quote_dialog"):
                st.session_state.show_quote_dialog = True

        @st.dialog("Upload and review supplier quotation", width="large")
        def quotation_dialog():
            st.write("Upload a supplier quotation as a PDF, photo, screenshot, Excel or CSV. OCR/spreadsheet extraction results are editable. Only confirmed rows enter the comparison table.")
            supplier = st.text_input("Supplier name", value=st.session_state.get("dialog_supplier", ""), key="dialog_supplier_name")
            uploaded = st.file_uploader("Quotation file", type=["pdf", "png", "jpg", "jpeg", "webp", "tif", "tiff", "xlsx", "xls", "csv"], key="dialog_quote_upload")
            if uploaded and not uploaded.name.lower().endswith((".pdf", ".xlsx", ".xls", ".csv")):
                st.image(uploaded.getvalue(), caption=uploaded.name, use_container_width=True)
            if uploaded and st.button("Extract quotation rows", type="primary", key="dialog_run_extract"):
                if uploaded.name.lower().endswith((".xlsx", ".xls", ".csv")):
                    try:
                        raw_df = pd.read_csv(uploaded) if uploaded.name.lower().endswith(".csv") else pd.read_excel(uploaded)
                        cols = list(raw_df.columns)
                        def pick_col(words):
                            for c in cols:
                                if any(w in norm(c) for w in words): return c
                            return None
                        product_col = pick_col(["product name", "product", "description", "medicine", "item name", "name"])
                        price_col = pick_col(["unit price", "price", "rate"])
                        qty_col = pick_col(["quantity", "qty"])
                        unit_col = pick_col(["unit", "uom", "pack"])
                        batch_col = pick_col(["batch"])
                        expiry_col = pick_col(["expiry", "exp"])
                        total_col = pick_col(["total", "amount"])
                        if not product_col:
                            st.error("Could not identify a product-name column. Please use a spreadsheet with clear column headings.")
                        else:
                            out = []
                            for _, rr in raw_df.iterrows():
                                pname = str(rr.get(product_col, "")).strip()
                                if not pname or pname.lower() == "nan": continue
                                qtyv = as_num(rr.get(qty_col, 1), 1) if qty_col else 1
                                pricev = as_num(rr.get(price_col, 0), 0) if price_col else 0
                                out.append({"Product name": pname, "Supplier": supplier or "Supplier not named", "Quantity": qtyv, "Unit": str(rr.get(unit_col, "")) if unit_col else "", "Price": pricev, "Line total": as_num(rr.get(total_col, 0), 0) if total_col else qtyv*pricev, "Batch": str(rr.get(batch_col, "")) if batch_col else "", "Expiry": str(rr.get(expiry_col, "")) if expiry_col else "", "Source": uploaded.name, "OCR confidence": 100.0, "Validation flags": "Spreadsheet import — verify product identity and pack size"})
                            st.session_state.dialog_preview = pd.DataFrame(out)
                            st.session_state.dialog_preview_source = uploaded.name
                    except Exception as e:
                        st.error(f"Could not read spreadsheet: {e}")
                else:
                    frames, raw_parts = [], []
                    with st.spinner("Extracting text and detecting table rows…"):
                        direct_rows, direct_text = _pdf_text_rows(uploaded, supplier or "Supplier not named") if uploaded.name.lower().endswith(".pdf") else (pd.DataFrame(), "")
                        if not direct_rows.empty:
                            frames.append(direct_rows)
                            raw_parts.append("PDF text extraction:\n" + direct_text)
                        else:
                            images = ocr_to_images(uploaded)
                            for page_no, img in enumerate(images, 1):
                                rows, raw = ocr_image_rows(img, supplier or "Supplier not named", uploaded.name)
                                if not rows.empty: frames.append(rows)
                                raw_parts.append(f"Page {page_no}:\n{raw}")
                    st.session_state.dialog_preview = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["Product name", "Supplier", "Quantity", "Unit", "Price", "Line total", "Batch", "Expiry", "Source", "OCR confidence", "Validation flags"])
                    st.session_state.dialog_preview_source = uploaded.name
                    st.session_state.dialog_raw_text = "\n\n".join(raw_parts)
            if st.button("Close without importing", key="dialog_cancel_upload"):
                st.session_state.show_quote_dialog = False
                st.rerun()
            if "dialog_preview" in st.session_state:
                st.markdown("#### Review extracted lines")
                preview = st.session_state.dialog_preview.copy()
                if preview.empty:
                    st.warning("No table rows were detected. Add the quotation lines manually below.")
                    preview = pd.DataFrame([{"Product name":"", "Supplier":supplier or "Supplier not named", "Quantity":1, "Unit":"", "Price":0.0, "Line total":0.0, "Batch":"", "Expiry":"", "Source":st.session_state.get("dialog_preview_source", ""), "OCR confidence":0.0, "Validation flags":"Manual entry"}])
                for col, default in [("Product name", ""), ("Supplier", supplier or "Supplier not named"), ("Quantity", 1), ("Unit", ""), ("Price", 0.0), ("Line total", 0.0), ("Batch", ""), ("Expiry", ""), ("Source", st.session_state.get("dialog_preview_source", "")), ("OCR confidence", 0.0), ("Validation flags", "")]:
                    if col not in preview: preview[col] = default
                reviewed = st.data_editor(preview, num_rows="dynamic", use_container_width=True, key="dialog_preview_editor", column_config={"Quantity":st.column_config.NumberColumn(min_value=0, step=1), "Price":st.column_config.NumberColumn("Unit price (RWF)", min_value=0, format="%.2f"), "Line total":st.column_config.NumberColumn(min_value=0, format="%.2f"), "OCR confidence":st.column_config.NumberColumn(min_value=0, max_value=100, format="%.1f%%")})
                flags = []
                for _, rr in reviewed.iterrows():
                    qtyv, pricev, totalv = as_num(rr.get("Quantity",0)), as_num(rr.get("Price",0)), as_num(rr.get("Line total",0))
                    if not str(rr.get("Product name", "")).strip(): flags.append("A row has no product name")
                    if pricev <= 0: flags.append(f"Price missing/unclear: {rr.get('Product name','')}")
                    if qtyv <= 0: flags.append(f"Quantity missing/unclear: {rr.get('Product name','')}")
                    if totalv > 0 and qtyv > 0 and pricev > 0 and abs(totalv-qtyv*pricev) > max(2,totalv*.02): flags.append(f"Line total mismatch: {rr.get('Product name','')}")
                if flags: st.warning("Review flags: " + "; ".join(flags[:8]))
                else: st.success("Basic quantity and price checks passed. Confirm medicine identity, strength and pack size manually.")
                b1,b2 = st.columns(2)
                with b1:
                    if st.button("Confirm quotation and add to comparison", type="primary", key="dialog_confirm_quote"):
                        clean = reviewed.copy()
                        clean["Product name"] = clean["Product name"].fillna("").astype(str).str.strip()
                        clean = clean[clean["Product name"] != ""]
                        clean["Supplier"] = clean["Supplier"].fillna(supplier or "Supplier not named").astype(str)
                        clean["Price"] = clean["Price"].apply(as_num)
                        clean["Quantity"] = clean["Quantity"].apply(as_num)
                        clean["Line total"] = clean.apply(lambda r: as_num(r.get("Line total",0)) or as_num(r.get("Quantity",0))*as_num(r.get("Price",0)), axis=1)
                        keep = ["Product name", "Supplier", "Price", "Unit", "Batch", "Expiry", "Source", "Quantity", "Line total"]
                        for c in keep:
                            if c not in clean: clean[c] = ""
                        st.session_state.supplier_quotes = pd.concat([st.session_state.supplier_quotes, clean[keep]], ignore_index=True)
                        st.session_state.show_quote_dialog = False
                        for k in ["dialog_preview", "dialog_raw_text"]: st.session_state.pop(k, None)
                        st.success(f"Confirmed {len(clean)} quotation rows.")
                        st.rerun()
                with b2:
                    if st.button("Cancel", key="dialog_cancel_quote"):
                        st.session_state.show_quote_dialog = False
                        st.rerun()
                with st.expander("Raw OCR text"):
                    st.text(st.session_state.get("dialog_raw_text", "No raw OCR text available for spreadsheet imports."))
        if st.session_state.show_quote_dialog:
            quotation_dialog()

        st.divider()
        st.markdown("### Supplier comparison table")
        offers = []
        # Existing workbook reference prices
        if not refdata.empty:
            for _, rr in refdata.iterrows():
                for supplier_col in ["Ubumwe", "FEDILIS", "Sun ltd"]:
                    price = as_num(rr.get(supplier_col, 0))
                    if price > 0:
                        offers.append({"Product name":str(rr.get("Product name", "")), "Supplier":supplier_col, "Price":price, "Unit":str(rr.get("Unit", "")), "Batch":"", "Expiry":"", "Source":"Reference workbook", "Quantity":as_num(rr.get("Quantity",1),1), "Line total":price*as_num(rr.get("Quantity",1),1)})
        if not catalogue.empty:
            for _, rr in catalogue.iterrows():
                price = as_num(rr.get("Unit price",0))
                if price > 0:
                    offers.append({"Product name":str(rr.get("Product name", "")), "Supplier":str(rr.get("Supplier", "UBUMWE DEPOT")) or "UBUMWE DEPOT", "Price":price, "Unit":"", "Batch":str(rr.get("Batch", "")), "Expiry":"", "Source":"Ubumwe catalogue", "Quantity":1, "Line total":price})
        if not st.session_state.supplier_quotes.empty:
            offers.extend(st.session_state.supplier_quotes.to_dict("records"))
        offers_df = pd.DataFrame(offers)
        current = st.session_state.requisition.copy()
        supplier_names = sorted(offers_df["Supplier"].fillna("").astype(str).loc[lambda x:x.str.strip()!=""].unique().tolist()) if not offers_df.empty else []
        comparison_rows, options_by_idx = [], {}
        for idx, row in current.iterrows():
            product = str(row.get("Product name", ""))
            product_offers = []
            if not offers_df.empty:
                for _, offer in offers_df.iterrows():
                    raw_offer_name = str(offer.get("Product name", ""))
                    normalized_offer_name = st.session_state.aliases.get(norm(raw_offer_name), raw_offer_name)
                    score_list = fuzzy_best(product, [normalized_offer_name], 1)
                    score = score_list[0][1] if score_list else 0
                    # A high threshold reduces accidental cross-strength matches; human review remains required.
                    if score >= 78 and as_num(offer.get("Price",0)) > 0:
                        product_offers.append({**offer.to_dict(), "Match score":score})
            # One visible price per supplier: lowest matching listed offer, while preserving offers in details.
            by_supplier = {}
            for offer in product_offers:
                supplier_name = str(offer.get("Supplier", "Supplier"))
                if supplier_name not in by_supplier or as_num(offer.get("Price",0)) < as_num(by_supplier[supplier_name].get("Price",0)):
                    by_supplier[supplier_name] = offer
            options_by_idx[str(idx)] = by_supplier
            cr = {"Product name":product, "Qty":row.get("Quantity",1), "Unit":row.get("Unit","")}
            for sn in supplier_names:
                cr[sn] = by_supplier.get(sn, {}).get("Price", None)
            comparison_rows.append(cr)
        if comparison_rows:
            comparison = pd.DataFrame(comparison_rows)
            st.dataframe(comparison, use_container_width=True, hide_index=True, column_config={sn:st.column_config.NumberColumn(sn, format="RWF %.0f") for sn in supplier_names})
            st.caption("A supplier price is a match suggestion, not a guarantee of stock. Verify strength, dosage form, pack size, validity and availability before purchase.")
            st.markdown("#### Select the supplier for each requisition item")
            for idx, row in current.iterrows():
                product = str(row.get("Product name", "")); offers_for_item = options_by_idx.get(str(idx), {})
                with st.container(border=True):
                    c1,c2,c3 = st.columns([2.2, 1.6, 1])
                    c1.markdown(f"**{product}**")
                    c1.caption(f"Requested: {row.get('Quantity',1)} {row.get('Unit','')}")
                    if offers_for_item:
                        names = sorted(offers_for_item, key=lambda sn: as_num(offers_for_item[sn].get("Price",0)))
                        prior = str(row.get("Selected supplier", ""))
                        default_index = names.index(prior) if prior in names else 0
                        selected = c2.selectbox("Supplier / price offer", names, index=default_index, format_func=lambda sn: f"{sn} — {money(offers_for_item[sn].get('Price',0))} RWF", key=f"choose_supplier_{idx}")
                        chosen_offer = offers_for_item[selected]
                        c3.metric("Unit price", f"{as_num(chosen_offer.get('Price',0)):,.0f} RWF")
                        c2.caption(f"Matched description: {chosen_offer.get('Product name','')} · match {chosen_offer.get('Match score','—')}% · source: {chosen_offer.get('Source','')}")
                        if c2.button("Select and accept supplier", key=f"accept_supplier_{idx}"):
                            st.session_state.requisition.at[idx, "Selected supplier"] = selected
                            st.session_state.requisition.at[idx, "Selected price"] = as_num(chosen_offer.get("Price",0))
                            st.session_state.selected_offers[str(idx)] = chosen_offer
                            st.session_state.workflow_step = 4
                            st.rerun()
                    else:
                        c2.warning("No confident price match")
                        c3.caption("Import a quotation or review the product name/pack size.")
        else:
            st.info("No supplier prices are available yet. Upload a quotation to populate this table.")

with tabs[3]:
    st.subheader("4. Purchase lists grouped by selected supplier")
    current = st.session_state.requisition.copy()
    selected = current[current["Selected supplier"].fillna("").astype(str).str.strip() != ""] if not current.empty else pd.DataFrame()
    if selected.empty:
        st.info("No suppliers have been selected yet. Go to Quotation matching and accept an offer for each item.")
    else:
        selected = selected.copy()
        selected["Line total (RWF)"] = selected.apply(lambda r: as_num(r.get("Quantity",0))*as_num(r.get("Selected price",0)), axis=1)
        supplier_groups = sorted(selected["Selected supplier"].astype(str).unique())
        st.metric("Items assigned to suppliers", len(selected))
        st.dataframe(selected[["Product name", "Quantity", "Unit", "Selected supplier", "Selected price", "Line total (RWF)"]], use_container_width=True, hide_index=True)
        st.markdown("#### Supplier-specific purchase lists")
        for supplier in supplier_groups:
            group = selected[selected["Selected supplier"].astype(str) == supplier].copy()
            group["Selected supplier"] = supplier
            total = sum(as_num(r.get("Quantity",0))*as_num(r.get("Selected price",0)) for _,r in group.iterrows())
            with st.expander(f"{supplier} · {len(group)} item(s) · {total:,.0f} RWF", expanded=True):
                st.dataframe(group[["Product name", "Quantity", "Unit", "Selected price", "Line total (RWF)"]], use_container_width=True, hide_index=True)
                pdf = build_pdf(group, pharmacy if "pharmacy" in locals() else "PHARMACY TUUZA LTD", req_ref if "req_ref" in locals() else "TU-REQ", req_date if "req_date" in locals() else date.today(), mode=f"Purchase request to {supplier}")
                if pdf: st.download_button(f"Download {supplier} purchase list (PDF)", pdf, f"{re.sub(r'[^A-Za-z0-9_-]+','_',supplier)}_purchase_request.pdf", "application/pdf", key=f"pdf_supplier_{supplier}")
                png = build_png(group, pharmacy if "pharmacy" in locals() else "PHARMACY TUUZA LTD", req_ref if "req_ref" in locals() else "TU-REQ", req_date if "req_date" in locals() else date.today())
                st.download_button(f"Download {supplier} purchase list (PNG)", png, f"{re.sub(r'[^A-Za-z0-9_-]+','_',supplier)}_purchase_request.png", "image/png", key=f"png_supplier_{supplier}")
        st.divider()
        pdf_all = build_pdf(selected, pharmacy if "pharmacy" in locals() else "PHARMACY TUUZA LTD", req_ref if "req_ref" in locals() else "TU-REQ", req_date if "req_date" in locals() else date.today(), mode="Consolidated purchase requisition")
        if pdf_all: st.download_button("Download consolidated requisition (PDF)", pdf_all, "tuuza_consolidated_purchase_requisition.pdf", "application/pdf")
        png_all = build_png(selected, pharmacy if "pharmacy" in locals() else "PHARMACY TUUZA LTD", req_ref if "req_ref" in locals() else "TU-REQ", req_date if "req_date" in locals() else date.today())
        st.download_button("Download consolidated requisition (PNG)", png_all, "tuuza_consolidated_purchase_requisition.png", "image/png")

with tabs[4]:
    st.subheader("Medicine library and normalization")
    c1,c2,c3 = st.columns(3)
    c1.metric("Catalogue products", len(catalogue_names))
    c2.metric("Reference products", len(ref_names))
    c3.metric("Confirmed quotation lines", len(st.session_state.supplier_quotes))
    search = st.text_input("Test a medicine name or supplier alias", placeholder="e.g. amoxi 500 caps")
    if search:
        hits = fuzzy_best(search, all_names, 10)
        if hits:
            st.dataframe(pd.DataFrame([{"Catalogue product":n,"Similarity":f"{s}%","Normalized query":norm(search),"Normalized product":norm(n)} for n,s in hits]), use_container_width=True, hide_index=True)
        else: st.info("No likely matches found.")
    st.markdown("#### Add a supplier-specific alias")
    st.caption("Use aliases for recurring spelling differences, but keep strength, dosage form and pack size equivalent.")
    alias_variant = st.text_input("Observed alternate product name", placeholder="e.g. amoxi caps 500")
    alias_canonical = st.selectbox("Canonical catalogue product", [""] + all_names, key="alias_canonical_v4")
    if st.button("Save alias for this session", disabled=not(alias_variant.strip() and alias_canonical), key="save_alias_v4"):
        st.session_state.aliases[norm(alias_variant)] = alias_canonical
        st.success(f"Alias added: {alias_variant} → {alias_canonical}")
    if st.session_state.aliases:
        st.dataframe(pd.DataFrame([{"Normalized alias":k,"Canonical product":v} for k,v in st.session_state.aliases.items()]), use_container_width=True, hide_index=True)
    st.caption("This prototype keeps requisitions, aliases and imported offers in the current session. Persistent database storage is a separate production upgrade.")
