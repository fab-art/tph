# TUUZA Procurement Desk v2

## What's new
- Searchable product dropdown: type to filter; use Up/Down and Enter to select.
- Seed medicine catalogue extracted from the supplied Ubumwe Depot price list.
- Normalization and fuzzy product-name suggestions.
- Supplier comparison seeded from `req 14-10-2026.xlsx` and the Ubumwe price list.
- Select a supplier price per requisition line and use it in the final requisition.
- Export final requisition as PDF and PNG image, plus CSV/Excel data.
- Import additional supplier Excel/CSV price lists into the session for comparison.

## Run locally
1. Python 3.10+.
2. `python -m venv .venv`
3. Activate the environment.
4. `pip install -r requirements.txt`
5. `streamlit run app.py`

## Important
This is an MVP prototype. The provided comparison workbook and catalogue are seeded reference data, not live inventory. Product matching uses normalization plus fuzzy similarity and needs human confirmation. Supplier offers imported through the UI and aliases currently persist only for the current session. A production release should add Supabase/PostgreSQL, authentication, role-based permissions, durable alias management, price history, secure uploads and audit logs.

OCR upload is integrated for images and PDFs using Tesseract. OCR results are presented in an editable review table before being added to supplier offers. Extraction is heuristic and needs user verification.
