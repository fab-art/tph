# TUUZA Procurement Desk — MVP

A Streamlit prototype for:
- Building a pharmacy purchase requisition
- Uploading quotation screenshots/photos/PDFs
- OCR extraction of table rows into editable product/price fields
- Exporting requisitions and extracted quotations to Excel/CSV

## Run locally

1. Install Python 3.10+.
2. Install Tesseract OCR:
   - Ubuntu/Zorin: `sudo apt update && sudo apt install tesseract-ocr tesseract-ocr-eng`
   - Windows: install Tesseract OCR and add its installation folder to PATH.
3. In this folder, run:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   streamlit run app.py
   ```

## Deploy on Streamlit Community Cloud

1. Push `app.py`, `requirements.txt`, and `packages.txt` to a GitHub repository.
2. Create a Streamlit Community Cloud app pointing to `app.py`.
3. The `packages.txt` file requests the system Tesseract packages.

## Important prototype limitations

- OCR is best-effort. Small, low-resolution, rotated, or heavily compressed tables may need manual correction.
- Product/column matching is heuristic and should not be used without review.
- Data is held in Streamlit session state and is not permanent. Do not use this prototype as a production record system.
- No user authentication, supplier permissions, database, price-history service, or direct ordering is implemented yet.
- Before production, add Supabase/Postgres persistence, authentication, tenant-level access controls, audit logs, secure file storage, backup and validation.
- Do not expose supplier quotations to other organizations without authorization.
