import re
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
import pytesseract
from pytesseract import Output

try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None

st.set_page_config(page_title="TUUZA Procurement", page_icon="💊", layout="wide")

def to_excel(df, sheet):
    b = BytesIO()
    with pd.ExcelWriter(b, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet[:31])
    return b.getvalue()


st.markdown("""
<style>
.block-container {padding-top: 1.5rem; padding-bottom: 2rem; max-width: 1450px;}
.hero {padding: 1.15rem 1.35rem; border: 1px solid #dce4e8; border-radius: 16px; background: linear-gradient(110deg,#f0fdfa,#ffffff 65%);}
.hero h1 {margin:0; font-size:1.75rem;}
.hero p {margin:.45rem 0 0; color:#52616b;}
.metric {border:1px solid #e2e8f0; border-radius:12px; padding:12px 14px;}
.small-muted {color:#64748b; font-size:.85rem;}
div[data-testid="stDataEditor"] {border-radius: 10px;}
</style>
<div class="hero">
<h1>💊 TUUZA Procurement Desk</h1>
<p>Build purchase requisitions, read wholesaler quotations, and review extracted prices before saving.</p>
</div>
""", unsafe_allow_html=True)

st.caption("MVP prototype • OCR results are suggestions and must be checked against the original document.")

FIELDS = ["Product code", "Product name", "Strength / form", "Pack size", "Quantity", "Unit", "Unit price (RWF)", "Line total (RWF)", "Batch", "Expiry", "Supplier", "OCR confidence"]

def blank_df():
    return pd.DataFrame([{
        "Product code": "", "Product name": "", "Strength / form": "", "Pack size": "",
        "Quantity": 1, "Unit": "BX", "Unit price (RWF)": 0.0, "Line total (RWF)": 0.0,
        "Batch": "", "Expiry": "", "Supplier": "", "OCR confidence": ""
    }])

def preprocess(img):
    img = ImageOps.exif_transpose(img).convert("RGB")
    # Enlarge small screenshots/scans to improve Tesseract's table recognition.
    if img.width < 1300:
        scale = min(3, max(2, int(1300 / max(img.width, 1))))
        img = img.resize((img.width * scale, img.height * scale))
    gray = ImageOps.grayscale(img)
    gray = ImageEnhance.Contrast(gray).enhance(1.7)
    gray = gray.filter(ImageFilter.SHARPEN)
    return gray

def normalize_header(s):
    x = re.sub(r"[^a-z0-9]+", "", s.lower())
    aliases = {
        "code":"Product code", "itemcode":"Product code", "productcode":"Product code", "sku":"Product code",
        "name":"Product name", "product":"Product name", "description":"Product name", "medicine":"Product name",
        "batch":"Batch", "batchno":"Batch", "batchnumber":"Batch",
        "exp":"Expiry", "expiry":"Expiry", "expiration":"Expiry", "expirydate":"Expiry",
        "qty":"Quantity", "quantity":"Quantity", "quant":"Quantity", "quanti":"Quantity", "quantit":"Quantity",
        "unit":"Unit", "uom":"Unit",
        "price":"Unit price (RWF)", "unitprice":"Unit price (RWF)", "rate":"Unit price (RWF)",
        "total":"Line total (RWF)", "amount":"Line total (RWF)", "linetotal":"Line total (RWF)",
        "pack":"Pack size", "packsize":"Pack size", "strength":"Strength / form", "form":"Strength / form",
        "supplier":"Supplier", "vendor":"Supplier"
    }
    return aliases.get(x)

def get_words(img):
    return pytesseract.image_to_data(preprocess(img), output_type=Output.DATAFRAME, config="--psm 6")

def extract_rows(img, supplier_name=""):
    data = get_words(img)
    data = data.dropna(subset=["text"])
    data["text"] = data["text"].astype(str).str.strip()
    data = data[data["text"] != ""]
    if data.empty:
        return pd.DataFrame(columns=FIELDS), ""

    # Group OCR words into visual text lines by block/paragraph/line.
    grouped = []
    for key, g in data.groupby(["page_num", "block_num", "par_num", "line_num"], sort=True):
        g = g.sort_values("left")
        text = " ".join(g["text"].tolist())
        top = int(g["top"].median())
        grouped.append({"top": top, "text": text, "words": g.to_dict("records")})
    grouped.sort(key=lambda x: x["top"])
    raw_text = "\n".join(x["text"] for x in grouped)

    # Detect the most likely table header row and use word x-coordinates as column anchors.
    header_idx, header_cols = None, []
    for i, line in enumerate(grouped):
        found = []
        for w in line["words"]:
            mapped = normalize_header(str(w["text"]))
            if mapped:
                found.append((int(w["left"] + w["width"]/2), mapped, str(w["text"])))
        unique = []
        seen = set()
        for item in found:
            if item[1] not in seen:
                unique.append(item)
                seen.add(item[1])
        if len(unique) >= 3:
            header_idx, header_cols = i, sorted(unique, key=lambda z:z[0])
            break

    rows = []
    if header_idx is not None:
        # Column boundaries halfway between header centers.
        centers = [x[0] for x in header_cols]
        bounds = [-10**9] + [(centers[i]+centers[i+1])/2 for i in range(len(centers)-1)] + [10**9]
        cols = [x[1] for x in header_cols]
        for line in grouped[header_idx+1:]:
            vals = {c: [] for c in cols}
            for w in line["words"]:
                x = int(w["left"] + w["width"]/2)
                j = 0
                while j < len(centers)-1 and x >= bounds[j+1]:
                    j += 1
                vals[cols[j]].append((int(w["left"]), str(w["text"])))
            row = {c: " ".join(t for _,t in sorted(v)) for c,v in vals.items()}
            # Skip totals, page footers and blank/non-item lines.
            combined = " ".join(row.values()).lower()
            if not combined.strip() or any(term in combined for term in ["total pages", "number of items", "total a-ex", "grand total"]):
                continue
            product_fields = [row.get(c, "") for c in ["Product name", "Strength / form", "Pack size"] if row.get(c, "").strip()]
            if not product_fields:
                continue
            product_name = " ".join(product_fields).strip()
            # Ignore rows with no product-like text or only headings.
            if len(re.sub(r"\W", "", product_name)) < 3:
                continue
            record = {f: "" for f in FIELDS}
            record["Product code"] = row.get("Product code", "")
            record["Product name"] = product_name
            record["Strength / form"] = row.get("Strength / form", "")
            record["Pack size"] = row.get("Pack size", "")
            record["Quantity"] = parse_number(row.get("Quantity", ""), default=1)
            record["Unit"] = row.get("Unit", "")
            record["Unit price (RWF)"] = parse_number(row.get("Unit price (RWF)", ""), default=0)
            record["Line total (RWF)"] = parse_number(row.get("Line total (RWF)", ""), default=0)
            record["Batch"] = row.get("Batch", "")
            record["Expiry"] = row.get("Expiry", "")
            record["Supplier"] = supplier_name
            record["OCR confidence"] = ""
            if record["Product name"].strip():
                rows.append(record)

    # Fallback for cases where the header detector cannot recognize the table.
    if not rows:
        for line in grouped:
            s = line["text"].strip()
            if len(s) > 12 and re.search(r"\d", s) and not re.search(r"quotation|customer name|total pages|total a-ex", s, re.I):
                rows.append({
                    "Product code":"", "Product name":s, "Strength / form":"", "Pack size":"",
                    "Quantity":1, "Unit":"", "Unit price (RWF)":0.0, "Line total (RWF)":0.0,
                    "Batch":"", "Expiry":"", "Supplier":supplier_name, "OCR confidence":"Review - raw line"
                })
    return pd.DataFrame(rows, columns=FIELDS), raw_text

def parse_number(value, default=0):
    if value is None:
        return default
    s = str(value).replace(",", "").replace(" ", "")
    s = re.sub(r"[^0-9.\-]", "", s)
    try:
        return float(s) if s not in ("", ".", "-", "-.") else default
    except ValueError:
        return default

def to_images(uploaded_file):
    name = uploaded_file.name.lower()
    raw = uploaded_file.getvalue()
    if name.endswith(".pdf"):
        if fitz is None:
            st.error("PDF support needs PyMuPDF. Install the dependencies listed in requirements.txt.")
            return []
        doc = fitz.open(stream=raw, filetype="pdf")
        images = []
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            images.append(Image.frombytes("RGB", [pix.width, pix.height], pix.samples))
        return images
    try:
        return [Image.open(BytesIO(raw)).convert("RGB")]
    except Exception:
        return []

def normalize_columns(df):
    for c in FIELDS:
        if c not in df.columns:
            df[c] = ""
    return df[FIELDS]

if "requisition" not in st.session_state:
    st.session_state.requisition = blank_df()
if "quotes" not in st.session_state:
    st.session_state.quotes = pd.DataFrame(columns=FIELDS)
if "raw_ocr" not in st.session_state:
    st.session_state.raw_ocr = ""

tab_req, tab_quote, tab_library = st.tabs(["🧾 Build requisition", "📷 Read wholesaler quotation", "📚 Saved working data"])

with tab_req:
    st.subheader("Create a purchase requisition")
    c1, c2, c3 = st.columns([1.3, 1, 1])
    with c1:
        pharmacy = st.text_input("Pharmacy", value="PHARMACY TUUZA LTD")
    with c2:
        req_date = st.date_input("Requisition date")
    with c3:
        req_ref = st.text_input("Requisition reference", value="TU-REQ-001")
    st.write("Add the medicines you need. You can edit every cell before exporting.")
    req_df = st.data_editor(
        st.session_state.requisition,
        num_rows="dynamic",
        use_container_width=True,
        key="req_editor",
        column_config={
            "Quantity": st.column_config.NumberColumn(min_value=0, step=1),
            "Unit price (RWF)": st.column_config.NumberColumn(min_value=0, format="%.2f"),
            "Line total (RWF)": st.column_config.NumberColumn(min_value=0, format="%.2f"),
        }
    )
    # Compute totals from quantity x unit price unless user has entered a non-zero line total.
    req_df = req_df.copy()
    if not req_df.empty:
        for i, r in req_df.iterrows():
            q = parse_number(r.get("Quantity", 0), 0)
            p = parse_number(r.get("Unit price (RWF)", 0), 0)
            if p and q:
                req_df.at[i, "Line total (RWF)"] = q * p
    st.session_state.requisition = req_df
    valid_items = req_df[req_df["Product name"].fillna("").astype(str).str.strip() != ""]
    total = sum(parse_number(x,0) for x in valid_items["Line total (RWF)"])
    a,b,c = st.columns(3)
    a.metric("Items requested", len(valid_items))
    b.metric("Total estimated value", f"{total:,.0f} RWF")
    c.metric("Requisition", req_ref or "Not set")
    export = valid_items.copy()
    if not export.empty:
        export.insert(0, "Requisition reference", req_ref)
        export.insert(1, "Pharmacy", pharmacy)
        export.insert(2, "Date", str(req_date))
    csv = export.to_csv(index=False).encode("utf-8-sig")
    st.download_button("Download requisition as CSV", data=csv, file_name=f"{req_ref or 'requisition'}.csv", mime="text/csv")
    xlsx_buffer = BytesIO()
    with pd.ExcelWriter(xlsx_buffer, engine="openpyxl") as writer:
        export.to_excel(writer, index=False, sheet_name="Requisition")
    st.download_button("Download requisition as Excel", data=xlsx_buffer.getvalue(), file_name=f"{req_ref or 'requisition'}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

with tab_quote:
    st.subheader("Upload and read a wholesaler quotation")
    st.write("Upload a quotation screenshot, photo, scanned PDF, or text-based PDF. The OCR result is editable before you add it to your working data.")
    u1, u2 = st.columns([1.4, 1])
    with u1:
        uploaded = st.file_uploader("Quotation file", type=["png","jpg","jpeg","webp","tif","tiff","pdf"], key="quote_upload")
    with u2:
        supplier = st.text_input("Wholesaler / supplier name", placeholder="Enter supplier name")
        st.caption("If the supplier name is not printed clearly, enter it here.")
    if uploaded:
        images = to_images(uploaded)
        if images:
            st.image(images[0], caption=f"Preview: {uploaded.name}", use_container_width=True)
            if st.button("Run OCR and identify table", type="primary"):
                all_frames, all_text = [], []
                with st.spinner("Reading document and detecting table rows..."):
                    for idx, img in enumerate(images, start=1):
                        frame, raw = extract_rows(img, supplier)
                        if len(images) > 1:
                            all_text.append(f"--- Page {idx} ---\n{raw}")
                        else:
                            all_text.append(raw)
                        if not frame.empty:
                            all_frames.append(frame)
                extracted = pd.concat(all_frames, ignore_index=True) if all_frames else pd.DataFrame(columns=FIELDS)
                st.session_state.ocr_result = extracted
                st.session_state.raw_ocr = "\n".join(all_text)
                st.session_state.ocr_filename = uploaded.name
            if "ocr_result" in st.session_state:
                st.markdown("#### Review extracted items")
                st.info("Check product names, quantities, prices, batch numbers and expiry dates against the preview. OCR may confuse characters such as O/0, I/1 and commas/decimal points.")
                edited = st.data_editor(
                    normalize_columns(st.session_state.ocr_result.copy()),
                    num_rows="dynamic",
                    use_container_width=True,
                    key="ocr_editor",
                    column_config={
                        "Quantity": st.column_config.NumberColumn(min_value=0, step=1),
                        "Unit price (RWF)": st.column_config.NumberColumn(min_value=0, format="%.2f"),
                        "Line total (RWF)": st.column_config.NumberColumn(min_value=0, format="%.2f"),
                    }
                )
                if not edited.empty:
                    # Only fill totals where a price and quantity exist and the total is empty/zero.
                    for i, r in edited.iterrows():
                        q = parse_number(r.get("Quantity", 0), 0)
                        p = parse_number(r.get("Unit price (RWF)", 0), 0)
                        t = parse_number(r.get("Line total (RWF)", 0), 0)
                        if t == 0 and q and p:
                            edited.at[i, "Line total (RWF)"] = q*p
                x,y = st.columns(2)
                with x:
                    if st.button("Add reviewed rows to working data", type="primary"):
                        st.session_state.quotes = pd.concat([st.session_state.quotes, edited], ignore_index=True)
                        st.success(f"Added {len(edited)} rows to working data.")
                with y:
                    out = BytesIO()
                    with pd.ExcelWriter(out, engine="openpyxl") as writer:
                        edited.to_excel(writer, index=False, sheet_name="Quotation")
                    st.download_button("Download extracted quotation (Excel)", data=out.getvalue(), file_name="extracted_quotation.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                with st.expander("View raw OCR text for troubleshooting"):
                    st.text(st.session_state.raw_ocr)
        else:
            st.error("This file could not be opened as an image or PDF.")

with tab_library:
    st.subheader("Working data")
    st.write("This prototype keeps data in the current app session only. It does not yet save records to a permanent database.")
    st.markdown("#### Imported quotation rows")
    if st.session_state.quotes.empty:
        st.info("No quotation rows have been added yet.")
    else:
        qdf = st.data_editor(st.session_state.quotes, num_rows="dynamic", use_container_width=True, key="saved_quotes_editor")
        st.session_state.quotes = qdf
        st.metric("Quotation lines", len(qdf))
        st.download_button("Export all quotation rows as Excel", data=to_excel(qdf, "QuotationData"), file_name="tuuza_quotation_data.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.markdown("#### Next build stage")
    st.markdown("- Persistent database and user login\n- Supplier profiles and catalogue history\n- Product matching across quotations\n- Price-change alerts and supplier comparison\n- Printable requisition / PDF export")

def to_excel(df, sheet):
    b = BytesIO()
    with pd.ExcelWriter(b, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet[:31])
    return b.getvalue()
