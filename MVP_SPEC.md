# TUUZA Procurement Desk v2 specification

## User workflow
1. Select a normalized medicine using searchable type-ahead product dropdown.
2. Add quantity, unit, batch and expiry details to requisition.
3. Compare known supplier prices from the supplied requisition comparison workbook and Ubumwe catalogue.
4. Import additional supplier Excel/CSV lists and include them as comparison offers.
5. Select the preferred supplier price per line.
6. Export the purchase requisition as PDF or PNG for review/submission; CSV/Excel available for data transfer.

## Product normalization
- Normalize case, punctuation, spaces and common abbreviations.
- Generate fuzzy candidate suggestions.
- Preserve the source product description.
- Require human confirmation of strength, dosage form and pack size.
- Add user-maintained alias mappings (currently session-only).

## Seed files
- `data/ubumwe_catalogue.csv`: derived from the provided Ubumwe Depot August 2026 price list.
- `data/supplier_comparison_reference.csv`: derived from the supplied requisition comparison workbook, including Ubumwe, FEDILIS and Sun Ltd price columns.

## Not yet production-ready
No persistent database/authentication, no live stock availability, no durable alias store, no cross-tenant security, and OCR import is not integrated into this version. Price observations should retain source and date in a production system.
