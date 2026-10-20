# TUUZA Procurement Desk v4 — staged procurement workflow

This release reorganizes the app into the workflow requested for TUUZA Pharmacy:

1. **Requisition** — build a table of medicine lines using searchable catalogue suggestions; add custom products when needed.
2. **Review & confirm** — edit and confirm product names, quantities and units before supplier matching.
3. **Quotation matching** — open a dialog to upload a supplier quotation (PDF, image, Excel or CSV); run OCR/table extraction where applicable; review and correct rows; confirm rows into the comparison data.
4. **Supplier purchase lists** — compare supplier prices in a table, accept a supplier for each line, and generate separate supplier-specific purchase lists plus a consolidated requisition.
5. **Medicine library** — test name normalization and create aliases for recurring supplier descriptions.

## Included reference data

- `data/ubumwe_catalogue.csv`: catalogue extracted from the Ubumwe Depot price list provided for the project.
- `data/supplier_comparison_reference.csv`: supplier comparison data extracted from the requisition workbook provided for the project.

## Run locally

Requires Python 3.10+ and Tesseract OCR installed on the operating system.

Linux/Zorin:
```bash
sudo apt update
sudo apt install tesseract-ocr tesseract-ocr-eng
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Windows:
1. Install Tesseract OCR and ensure `tesseract.exe` is available on PATH.
2. Create/activate a virtual environment.
3. Run `pip install -r requirements.txt` and `streamlit run app.py`.

## Deploy on Streamlit Community Cloud

1. Push the entire folder contents to a GitHub repository.
2. In Streamlit Community Cloud, select the repository and `app.py` as the main file.
3. The `packages.txt` file installs Tesseract system packages; `requirements.txt` installs Python dependencies.

## Important limits

- OCR output is a draft. Always review medicine identity, strength, dosage form, pack size, quantity, price, batch and expiry before confirming.
- Fuzzy matching helps find candidate offers but cannot guarantee pharmaceutical equivalence. The comparison view uses a conservative similarity threshold, but users must confirm product details.
- Catalogue prices and workbook prices are reference data from supplied files, not live stock feeds.
- The app is session-based: requisitions, aliases and imported quotation rows are not yet persisted to a database. A refresh/new session may lose them.
- No supplier login, electronic order transmission, or live wholesaler stock integration is implemented.
- Supplier-specific PDFs/PNGs are generated from selected lines. Check the generated document before submitting it for purchasing.
