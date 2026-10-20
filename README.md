# TUUZA Client-Side Quotation OCR

A Next.js PWA starter for extracting medicine names from dense supplier quotation images. Image preprocessing is performed in a dedicated Web Worker using OffscreenCanvas. OCR is performed by Tesseract.js, which manages its own Web Worker. There is no OCR server/API call.

## Why this path
- No per-page OCR API bill.
- No Vercel serverless OCR function or server-side ML dependencies.
- Human-adjustable NAME-column crop.
- Local grayscale + adaptive threshold preprocessing.
- Local Tesseract OCR, deduplicated JSON output.
- Service worker caches the app shell and local OCR assets after first successful online load.

## Run locally
Requires a supported Node.js LTS.
```bash
npm install
npm run dev
```
Open http://localhost:3000/quotation-ocr.

`postinstall` attempts to copy Tesseract worker/core runtime assets into `public/tesseract`. Inspect `public/tesseract` after install. Tesseract language data is often distributed separately from the package bundle: ensure `eng.traineddata.gz` is at `public/tesseract/lang-data/eng.traineddata.gz`. If your installed Tesseract.js version uses a different core filename, update `corePath` in `src/components/QuotationOcr.tsx` to the exact file copied into `public/tesseract`.

## Vercel
1. Push to GitHub.
2. Import the repository in Vercel as a Next.js project.
3. Deploy with default build settings.
4. Test the deployed app over HTTPS and use DevTools > Application > Service Workers / Cache Storage to verify offline assets.
5. Visit the OCR page online once and run OCR successfully; the worker, WASM runtime, language data and app shell are then cached as requests succeed.
6. After a hard reload, switch to offline mode and test again. Browser storage may be evicted; offline use is best-effort, not a guaranteed archival mechanism.

## OCR limitations
- This initial version accepts PNG, JPG and WEBP. PDF support requires PDF.js to render each selected page into an image before cropping.
- User manually sets crop percentages; it avoids fragile automatic table detection and works across varying supplier templates.
- It uses local adaptive mean thresholding. This is not a full Sauvola implementation and may need tuning for colored/low-contrast scans.
- Tesseract may merge or split rows. Names are editable and should be reviewed before they enter a procurement catalogue.
- OCR output is not a verified product identity. Match strength, dosage form, pack size, and catalogue records separately.
- Offline caching can require significant storage (English traineddata + WASM). Do not pre-cache large assets in the install event; this starter caches them after first successful request.

## Main files
- `src/components/QuotationOcr.tsx`: upload, crop controls, OCR, review and JSON export.
- `src/workers/preprocess.worker.ts`: OffscreenCanvas crop, grayscale and adaptive thresholding.
- `public/sw.js`: cache-first offline behavior for the app shell and local OCR runtime.
- `scripts/copy-tesseract-assets.mjs`: copies available Tesseract runtime files into `public/tesseract`.

## Production integration
Before saving extracted names into TUUZA Procurement Desk:
1. Keep the original quotation image.
2. Store raw OCR text and corrected names separately.
3. Match candidates against medicine name + strength + form + pack size.
4. Ask the user to confirm ambiguous matches.
5. Add audit metadata (user, timestamp, source quotation).
6. Do not auto-accept a supplier offer based only on OCR output.
