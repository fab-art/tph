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
<div class="hero"><h1>💊 TUUZA Procurement Desk</h1><p>Medicine catalogue · normalized product search · supplier price comparison · purchase requisitions</p></div>
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
        (r"\\btab(s|let|lets)?\\b", " tablet "),
        (r"\\bcap(s|sule|sules)?\\b", " capsule "),
        (r"\\bsyr\\b", " syrup "),
        (r"\\bsp\\b", " syrup "),
        (r"\\b susp\\b", " suspension "),
        (r"\\bcrm\\b", " cream "),
        (r"\\boint\\b", " ointment "),
        (r"\\bdrops?\\b", " drop "),
        (r"\\binj\\b", " injection "),
        (r"\\bpcs?\\b", " piece "),
        (r"\\bmls\\b", " ml "),
        (r"\\bgrs?\\b", " g "),
        (r"\\bb\\s*/\\s*(\\d+)", r" pack \\1 "),
        (r"\\b(\\d+)\\s*x\\s*(\\d+)\\b", r" pack \\1 \\2 "),
    ]
    for pat, rep in substitutions:
        s = re.sub(pat, rep, s)
    s = re.sub(r"[^a-z0-9.]+", " ", s)
    return re.sub(r"\\s+", " ", s).strip()

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


def ocr_to_images(uploaded):
    raw=uploaded.getvalue()
    if uploaded.name.lower().endswith(".pdf"):
        if fitz is None:
            st.error("PDF OCR needs PyMuPDF. Install the requirements.")
            return []
        doc=fitz.open(stream=raw,filetype="pdf")
        result=[]
        for page in doc:
            pix=page.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
            result.append(Image.frombytes("RGB",[pix.width,pix.height],pix.samples))
        return result
    try:
        return [Image.open(BytesIO(raw)).convert("RGB")]
    except Exception:
        return []

def ocr_image_rows(image, supplier):
    image=ImageOps.exif_transpose(image).convert("RGB")
    if image.width < 1400:
        scale=min(3,max(2,int(1400/image.width)))
        image=image.resize((image.width*scale,image.height*scale))
    gray=ImageOps.grayscale(image)
    gray=ImageEnhance.Contrast(gray).enhance(1.6).filter(ImageFilter.SHARPEN)
    data=pytesseract.image_to_data(gray,output_type=Output.DATAFRAME,config="--psm 6")
    data=data.dropna(subset=["text"])
    data["text"]=data["text"].astype(str).str.strip()
    data=data[data["text"]!=""]
    if data.empty: return pd.DataFrame(), ""
    lines=[]
    for _,g in data.groupby(["page_num","block_num","par_num","line_num"],sort=True):
        g=g.sort_values("left")
        lines.append({"top":int(g["top"].median()),"words":g.to_dict("records"),"text":" ".join(g["text"].tolist())})
    lines.sort(key=lambda x:x["top"])
    raw="\\n".join(x["text"] for x in lines)
    aliases={
      "product":"Product name","description":"Product name","name":"Product name","drug":"Product name","item":"Product name",
      "batch":"Batch","batch#":"Batch","batchno":"Batch","expiry":"Expiry","exp":"Expiry","qty":"Quantity","quantity":"Quantity",
      "unit":"Unit","unity":"Unit","price":"Price","rate":"Price","total":"Line total","amount":"Line total",
      "code":"Product code","productcode":"Product code"
    }
    header_idx=None; headers=[]
    for i,line in enumerate(lines):
        found=[]
        for w in line["words"]:
            token=re.sub(r"[^a-z#]","",str(w["text"]).lower())
            mapped=aliases.get(token)
            if mapped: found.append((int(w["left"]+w["width"]/2),mapped))
        unique=[];seen=set()
        for x in found:
            if x[1] not in seen: unique.append(x);seen.add(x[1])
        if len(unique)>=3 and "Product name" in [x[1] for x in unique]:
            header_idx=i;headers=sorted(unique);break
    rows=[]
    if header_idx is not None:
        centers=[x[0] for x in headers]
        names=[x[1] for x in headers]
        for line in lines[header_idx+1:]:
            cells={n:[] for n in names}
            for w in line["words"]:
                x=int(w["left"]+w["width"]/2)
                j=0
                while j<len(centers)-1 and x>(centers[j]+centers[j+1])/2: j+=1
                cells[names[j]].append((int(w["left"]),str(w["text"])))
            cells={k:" ".join(v for _,v in sorted(vs)) for k,vs in cells.items()}
            combined=" ".join(cells.values()).lower()
            if not combined.strip() or any(t in combined for t in ["total pages","customer name","number of items","total a-ex","grand total"]): continue
            product=cells.get("Product name","").strip()
            if len(re.sub(r"\\W","",product))<3: continue
            price=as_num(cells.get("Price",""),0)
            qty=as_num(cells.get("Quantity",""),1)
            total=as_num(cells.get("Line total",""),qty*price)
            rows.append({"Product name":product,"Supplier":supplier,"Price":price,"Unit":cells.get("Unit",""),
                         "Batch":cells.get("Batch",""),"Expiry":cells.get("Expiry",""),"Source":st.session_state.get("ocr_source_name","Uploaded quotation"),
                         "Quantity":qty,"Line total":total,"OCR review":"Check against original"})
    if not rows:
        for line in lines:
            text=line["text"].strip()
            if len(text)>15 and re.search(r"\\d",text) and not re.search(r"quotation|customer name|total pages|total a-ex",text,re.I):
                rows.append({"Product name":text,"Supplier":supplier,"Price":0,"Unit":"","Batch":"","Expiry":"",
                             "Source":st.session_state.get("ocr_source_name","Uploaded quotation"),"Quantity":1,"Line total":0,"OCR review":"Raw line - manual correction"})
    return pd.DataFrame(rows),raw

if "requisition" not in st.session_state:
    st.session_state.requisition=pd.DataFrame(columns=["Product name","Normalized name","Quantity","Unit","Selected supplier","Selected price","Product code","Batch","Expiry"])
if "supplier_quotes" not in st.session_state:
    st.session_state.supplier_quotes=pd.DataFrame(columns=["Product name","Supplier","Price","Unit","Batch","Expiry","Source"])
if "last_match" not in st.session_state:
    st.session_state.last_match=[]

catalogue=read_catalogue()
refdata=read_reference()
catalogue_names=sorted(catalogue["Product name"].dropna().astype(str).unique().tolist(),key=str.lower)
if refdata.empty:
    ref_names=[]
else:
    ref_names=refdata["Product name"].dropna().astype(str).unique().tolist()
all_names=sorted(set(catalogue_names+ref_names),key=str.lower)

tabs=st.tabs(["🧾 Requisition builder","📊 Price comparison","📷 Import supplier quotation","🧠 Product library & normalization"])

with tabs[0]:
    st.subheader("Build your pharmacy requisition")
    c1,c2,c3=st.columns([1.4,1,1])
    with c1: pharmacy=st.text_input("Pharmacy name", "PHARMACY TUUZA LTD")
    with c2: req_ref=st.text_input("Requisition reference", f"TU-REQ-{date.today():%Y%m%d}")
    with c3: req_date=st.date_input("Date",date.today())
    st.markdown("#### Add a medicine")
    st.caption("Start typing in the product field. The dropdown filters as you type; use ↑ / ↓ and Enter to choose a matching catalogue item.")
    if all_names:
        chosen=st.selectbox("Product name / type to search", options=[""]+all_names, index=0, placeholder="Type e.g. amoxi, paraceta, diclo…", key="product_autocomplete")
    else:
        chosen=""
        st.warning("No catalogue loaded yet. Import the supplied catalogue in the Product library tab or add a custom product below.")
    custom=st.text_input("Or enter a product not found in the library",placeholder="Custom product description")
    a,b,c,d=st.columns([1,1,1,1.2])
    with a: qty=st.number_input("Quantity",min_value=1,step=1,value=1)
    with b: unit=st.selectbox("Unit",["BX","BOX","PACK","BOT","BOTTLE","TUBE","PCS","UNIT","VIAL","AMPOULE","OTHER"])
    with c: batch=st.text_input("Batch (optional)")
    with d: expiry=st.text_input("Expiry (optional)",placeholder="MM/YYYY")
    selected_name=custom.strip() or chosen
    alias_map=st.session_state.get("aliases", {})
    if selected_name and norm(selected_name) in alias_map:
        selected_name=alias_map[norm(selected_name)]
    if selected_name and catalogue_names:
        matches=fuzzy_best(selected_name,catalogue_names,3)
        if matches:
            best,score=matches[0]
            if norm(best)!=norm(selected_name) and score>=65:
                st.caption(f"Normalization suggestion: **{best}** ({score}% similarity). Confirm the exact strength, form and pack size before selecting.")
    if st.button("＋ Add medicine to requisition",type="primary",disabled=not bool(selected_name)):
        new={"Product name":selected_name,"Normalized name":norm(selected_name),"Quantity":int(qty),"Unit":unit,"Selected supplier":"","Selected price":0.0,"Product code":"","Batch":batch,"Expiry":expiry}
        st.session_state.requisition=pd.concat([st.session_state.requisition,pd.DataFrame([new])],ignore_index=True)
        st.rerun()
    st.markdown("#### Requisition items")
    if st.session_state.requisition.empty:
        st.info("Add products above to begin.")
    else:
        edited=st.data_editor(st.session_state.requisition, num_rows="dynamic",use_container_width=True,key="req_editor_v2",
          column_config={"Quantity":st.column_config.NumberColumn(min_value=1,step=1),"Selected price":st.column_config.NumberColumn(min_value=0,format="%.0f")})
        edited["Normalized name"]=edited["Product name"].fillna("").map(norm)
        st.session_state.requisition=edited
        total=sum(as_num(r.get("Quantity",0))*as_num(r.get("Selected price",0)) for _,r in edited.iterrows())
        m1,m2,m3=st.columns(3);m1.metric("Items",len(edited));m2.metric("Estimated selected value",f"{total:,.0f} RWF");m3.metric("Suppliers selected",edited["Selected supplier"].replace("",pd.NA).nunique())
        if st.button("Find supplier prices for these items"):
            st.session_state.last_match=[str(x) for x in edited["Product name"].fillna("").tolist()]
            st.info("Open the Price comparison tab to review supplier prices and choose the supplier for each item.")
        req_export=edited.copy()
        req_export.insert(0,"Reference",req_ref);req_export.insert(1,"Pharmacy",pharmacy);req_export.insert(2,"Date",str(req_date))
        csv=req_export.to_csv(index=False).encode("utf-8-sig")
        st.download_button("Export requisition data (CSV)",csv,f"{req_ref}.csv","text/csv")
        xlsx=BytesIO()
        with pd.ExcelWriter(xlsx,engine="openpyxl") as writer:req_export.to_excel(writer,index=False,sheet_name="Requisition")
        st.download_button("Export requisition data (Excel)",xlsx.getvalue(),f"{req_ref}.xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        pdf=build_pdf(edited,pharmacy,req_ref,req_date)
        if pdf: st.download_button("Export final requisition (PDF)",pdf,f"{req_ref}.pdf","application/pdf")
        png=build_png(edited,pharmacy,req_ref,req_date)
        st.download_button("Export final requisition (PNG image)",png,f"{req_ref}.png","image/png")

with tabs[1]:
    st.subheader("Compare prices and select where each item will be purchased")
    st.caption("Seeded with the supplier comparison workbook you provided and the Ubumwe Depot price list. Prices are reference data from those files, not live stock confirmation.")
    if st.session_state.requisition.empty:
        st.info("Add items in the Requisition builder first.")
    else:
        current=st.session_state.requisition.copy()
        supplier_cols=["Ubumwe","FEDILIS","Sun ltd"]
        comparison_rows=[]
        choices_by_product={}
        for idx,row in current.iterrows():
            product=str(row.get("Product name",""))
            options={}
            # Exact/fuzzy supplier comparison workbook
            if not refdata.empty:
                hits=fuzzy_best(product,refdata["Product name"].astype(str).tolist(),3)
                if hits and hits[0][1]>=68:
                    matchname,score=hits[0]
                    matched=refdata[refdata["Product name"].astype(str)==matchname].iloc[0]
                    for s in supplier_cols:
                        if s in matched and pd.notna(matched[s]) and str(matched[s]).strip()!="":
                            options[s]=as_num(matched[s])
            # Ubumwe catalogue price, matched separately
            if not catalogue.empty:
                hits=fuzzy_best(product,catalogue_names,3)
                if hits and hits[0][1]>=68:
                    matchname,score=hits[0]
                    cr=catalogue[catalogue["Product name"].astype(str)==matchname].iloc[0]
                    if pd.notna(cr["Unit price"]) and as_num(cr["Unit price"])>0:
                        options["UBUMWE DEPOT (catalogue)"]=as_num(cr["Unit price"])
            # Imported quotation offers take precedence as additional offers.
            quotes=st.session_state.supplier_quotes
            if not quotes.empty:
                for _,qr in quotes.iterrows():
                    score=fuzzy_best(product,[str(qr["Product name"])],1)
                    if score and score[0][1]>=70 and as_num(qr.get("Price",0))>0:
                        options[str(qr.get("Supplier") or "Imported supplier")]=as_num(qr["Price"])
            cheapest=min(options,key=options.get) if options else ""
            comparison_rows.append({"Product name":product,"Qty":row.get("Quantity",1),"Unit":row.get("Unit",""),**{s:options.get(s,None) for s in supplier_cols},"Ubumwe catalogue":options.get("UBUMWE DEPOT (catalogue)",None),"Lowest listed supplier":cheapest,"Lowest listed price":options.get(cheapest,None) if cheapest else None,"Offers found":len(options)})
            choices_by_product[str(idx)]=options
        comp=pd.DataFrame(comparison_rows)
        st.dataframe(comp,use_container_width=True,hide_index=True,column_config={c:st.column_config.NumberColumn(c,format="RWF %.0f") for c in supplier_cols+["Ubumwe catalogue","Lowest listed price"]})
        st.markdown("#### Choose the supplier for each requisition line")
        for idx,row in current.iterrows():
            product=str(row.get("Product name",""))
            options=choices_by_product.get(str(idx),{})
            with st.container(border=True):
                c1,c2,c3=st.columns([2,1.2,1])
                c1.markdown(f"**{product}**")
                c1.caption(f"Requested: {row.get('Quantity',1)} {row.get('Unit','')}")
                if options:
                    supplier_names=sorted(options,key=lambda s:options[s])
                    default=row.get("Selected supplier","")
                    default_index=(supplier_names.index(default) if default in supplier_names else 0)
                    selected_supplier=c2.selectbox("Supplier",supplier_names,index=default_index,key=f"sup_{idx}")
                    selected_price=options[selected_supplier]
                    c3.metric("Unit price",f"{selected_price:,.0f} RWF")
                    if st.button("Use this price",key=f"use_{idx}"):
                        st.session_state.requisition.at[idx,"Selected supplier"]=selected_supplier
                        st.session_state.requisition.at[idx,"Selected price"]=selected_price
                        st.rerun()
                else:
                    c2.warning("No confident match")
                    c3.caption("Add quotation or check product naming.")
                    suggestions=fuzzy_best(product,all_names,3)
                    if suggestions:
                        c2.caption("Possible catalogue match: "+", ".join([f"{n} ({s}%)" for n,s in suggestions[:2]]))
        st.info("Choose a supplier and click **Use this price** for each line. The selected supplier and price are then carried into the final requisition export.")
    with st.expander("How product normalization works"):
        st.write("The app normalizes case, punctuation, spacing and common abbreviations such as tabs/tablets, caps/capsules, syr/syrup, crm/cream and pack-size patterns. It then uses fuzzy similarity to suggest possible matches. It does not automatically merge products with different strengths, dosage forms or pack sizes without review.")

with tabs[2]:
    st.subheader("Import a supplier quotation or price list")
    st.write("Upload a supplier quotation image, scanned/text PDF, Excel or CSV. OCR results are editable and must be reviewed before use.")
    ocr_upload=st.file_uploader("Upload quotation image or PDF for OCR",type=["png","jpg","jpeg","webp","tif","tiff","pdf"],key="ocr_upload_v2")
    ocr_supplier=st.text_input("Supplier name for OCR quotation", "Wholesaler", key="ocr_supplier_v2")
    if ocr_upload:
        ocr_images=ocr_to_images(ocr_upload)
        if ocr_images:
            st.image(ocr_images[0],caption=f"Preview: {ocr_upload.name}",use_container_width=True)
            if st.button("Run OCR on quotation",type="primary"):
                st.session_state["ocr_source_name"]=ocr_upload.name
                frames=[]; raw_pages=[]
                with st.spinner("Recognizing quotation table..."):
                    for pgno,img in enumerate(ocr_images,1):
                        frame,raw=ocr_image_rows(img,ocr_supplier)
                        if not frame.empty: frames.append(frame)
                        raw_pages.append(f"Page {pgno}:\\n{raw}")
                st.session_state["ocr_preview_rows"]=pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()
                st.session_state["ocr_raw_text"]="\\n\\n".join(raw_pages)
            if "ocr_preview_rows" in st.session_state:
                st.markdown("##### Review OCR extraction")
                if st.session_state["ocr_preview_rows"].empty:
                    st.warning("No table rows were confidently detected. View raw OCR text and enter/correct rows manually.")
                else:
                    ocr_edit=st.data_editor(st.session_state["ocr_preview_rows"],num_rows="dynamic",use_container_width=True,key="ocr_review_editor")
                    if st.button("Add reviewed OCR rows to supplier offers"):
                        mapped=pd.DataFrame({
                          "Product name":ocr_edit.get("Product name",""),
                          "Supplier":ocr_edit.get("Supplier",ocr_supplier),
                          "Price":ocr_edit.get("Price",0),
                          "Unit":ocr_edit.get("Unit",""),
                          "Batch":ocr_edit.get("Batch",""),
                          "Expiry":ocr_edit.get("Expiry",""),
                          "Source":ocr_edit.get("Source",ocr_upload.name)
                        })
                        st.session_state.supplier_quotes=pd.concat([st.session_state.supplier_quotes,mapped],ignore_index=True)
                        st.success(f"Added {len(mapped)} reviewed quotation rows.")
                with st.expander("Raw OCR text"):
                    st.text(st.session_state.get("ocr_raw_text",""))
    file=st.file_uploader("Or upload supplier price list (Excel or CSV)",type=["xlsx","xls","csv"],key="supplier_import")
    supplier_name=st.text_input("Supplier name for this upload", "Wholesaler")
    if file:
        try:
            if file.name.lower().endswith(".csv"):
                imported=pd.read_csv(file)
            else:
                imported=pd.read_excel(file)
            st.write("Preview",imported.head(20))
            cols=imported.columns.tolist()
            pcol=st.selectbox("Product-name column",cols,key="import_product_col")
            price_options=["(none)"]+cols
            pricecol=st.selectbox("Price column",price_options,key="import_price_col")
            unitcol=st.selectbox("Unit / pack column (optional)",["(none)"]+cols,key="import_unit_col")
            batchcol=st.selectbox("Batch column (optional)",["(none)"]+cols,key="import_batch_col")
            expcol=st.selectbox("Expiry column (optional)",["(none)"]+cols,key="import_exp_col")
            if st.button("Import rows into quotation offers"):
                new=[]
                for _,r in imported.iterrows():
                    name=str(r.get(pcol,"")).strip()
                    if not name or name.lower()=="nan": continue
                    new.append({"Product name":name,"Supplier":supplier_name,"Price":as_num(r.get(pricecol,0)) if pricecol!="(none)" else 0,
                                "Unit":str(r.get(unitcol,"")) if unitcol!="(none)" else "",
                                "Batch":str(r.get(batchcol,"")) if batchcol!="(none)" else "",
                                "Expiry":str(r.get(expcol,"")) if expcol!="(none)" else "","Source":file.name})
                st.session_state.supplier_quotes=pd.concat([st.session_state.supplier_quotes,pd.DataFrame(new)],ignore_index=True)
                st.success(f"Imported {len(new)} quotation rows.")
        except Exception as e:
            st.error(f"Could not read this file: {e}")
    if not st.session_state.supplier_quotes.empty:
        st.markdown("#### Imported offers")
        st.dataframe(st.session_state.supplier_quotes,use_container_width=True,hide_index=True)

with tabs[3]:
    st.subheader("Medicine catalogue and normalization engine")
    st.write("The included seed catalogue comes from the Ubumwe Depot price list uploaded for this project. The requisition workbook is used as a reference for supplier price comparisons.")
    c1,c2,c3=st.columns(3)
    c1.metric("Catalogue products",len(catalogue_names))
    c2.metric("Reference requisition products",len(ref_names))
    c3.metric("Imported quotation offers",len(st.session_state.supplier_quotes))
    search=st.text_input("Test normalization / search",placeholder="Type a product variant, e.g. amoxi 500 caps")
    if search:
        hits=fuzzy_best(search,all_names,10)
        if hits:
            st.dataframe(pd.DataFrame([{"Catalogue product":n,"Similarity":f"{s}%","Normalized query":norm(search),"Normalized product":norm(n)} for n,s in hits]),use_container_width=True,hide_index=True)
        else: st.info("No matches found.")
    st.markdown("#### Add or update an alias")
    st.caption("Aliases allow recurring wholesaler descriptions to point to the canonical catalogue name. Keep strength, dosage form and pack size aligned.")
    alias_variant=st.text_input("Observed alternate name",placeholder="e.g. amoxi caps 500")
    alias_canonical=st.selectbox("Canonical product",[""]+all_names,key="alias_canonical")
    if st.button("Save alias to session",disabled=not(alias_variant.strip() and alias_canonical)):
        if "aliases" not in st.session_state: st.session_state.aliases={}
        st.session_state.aliases[norm(alias_variant)]=alias_canonical
        st.success(f"Alias mapped: {alias_variant} → {alias_canonical}")
    if st.session_state.get("aliases"):
        st.dataframe(pd.DataFrame([{"Normalized alias":k,"Canonical product":v} for k,v in st.session_state.aliases.items()]),use_container_width=True,hide_index=True)
    st.caption("Aliases are session-only in this prototype. The production version should store them in a database with an approval history.")
