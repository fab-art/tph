# TUUZA Procurement Desk v4 workflow specification

## Stage 1 — Requisition
- Pharmacy, reference and date metadata.
- Searchable product suggestion control based on included catalogue and workbook names.
- Add lines with quantity, unit and optional product code.
- Editable requisition table.
- Submit active lines to review.

## Stage 2 — Review and quantity confirmation
- Editable review table.
- Reviewer checks product names, quantities and units.
- Explicit confirmation required before quotation matching becomes available.

## Stage 3 — Quotation matching
- Supplier quotation import in a dialog.
- Supported files: PDF, image, XLSX/XLS and CSV.
- Selectable PDF text/table extraction first; OCR fallback for images/scanned PDFs.
- Editable extraction table; arithmetic warnings for line totals.
- Only user-confirmed rows are appended to the supplier offer list.
- Comparison table displays the requisition lines against available supplier prices.
- A per-line action explicitly accepts the chosen supplier and price.

## Stage 4 — Supplier purchase lists
- Group accepted requisition lines by supplier.
- Download each supplier-specific list as PDF and PNG.
- Download consolidated requisition as PDF and PNG.

## Normalization
- Normalize case, punctuation and common medicine abbreviations.
- Fuzzy-match potential catalogue names.
- Support manually approved aliases for recurrent supplier naming variants.
- Never treat name similarity as sufficient evidence when strength, form or pack size differs.

## Not yet included
- Persistent database, user authentication and role-based access.
- Saved aliases across sessions.
- Live stock checks, supplier confirmations and electronic order transmission.
- Automatic OCR benchmark/test suite.
