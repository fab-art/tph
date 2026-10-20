# MVP product specification

## Primary user
TUUZA Pharmacy staff.

## Core workflow A: Create requisition
1. Enter pharmacy, date and reference.
2. Add product code/name, strength/form, pack size, quantity and optional known price.
3. Review estimated totals.
4. Export CSV or Excel for sending to suppliers.

## Core workflow B: Read supplier quotation
1. Upload a screenshot/photo or PDF quotation.
2. Enter supplier name.
3. Run OCR and table-row detection.
4. Review and correct extracted product rows.
5. Export the reviewed quotation to Excel or add it to current working data.

## Fields to extract
Supplier, product code, product name, strength/form, pack size, quantity, unit, unit price, line total, batch, expiry and source file.

## Guardrails
- OCR output is never treated as verified without user review.
- Never infer live stock from a historical price list.
- Keep quoted prices distinct from actual purchase prices.
- Keep supplier/source and import date with each record.
- Product equivalence must account for ingredient, strength, dosage form and pack size.

## Next release
Persistent storage, product catalogue, supplier-specific price history, requisition-to-quotation matching, price-change alerts and PDF requisition export.
