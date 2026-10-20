# Integrating into TUUZA Procurement Desk

The component currently returns `names: string[]` locally and offers JSON copy/download. To pass the list to a parent procurement screen, add a typed prop such as `onExtractedNames?: (names: string[]) => void`, and invoke it only after OCR results are reviewed. The parent can then show candidate matches from Supabase's `medicines` table.

Do not automatically assign a medicine UUID based only on OCR string similarity. Show a confirmation table with the OCR string, suggested catalogue medicine, strength, dosage form and pack size. The user must approve the mapping.

A production quotation row should retain:
- source quotation file/storage path
- original OCR text and extraction timestamp
- reviewed product name
- selected medicine ID or an unmatched state
- reviewer and confirmation timestamp
