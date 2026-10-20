import { cp, mkdir, access } from "node:fs/promises";
import path from "node:path";

const root = process.cwd();
const dest = path.join(root, "public", "tesseract");
await mkdir(dest, { recursive: true });

const candidates = [
  ["node_modules/tesseract.js/dist/worker.min.js", "worker.min.js"],
  ["node_modules/tesseract.js-core/tesseract-core.wasm.js", "tesseract-core.wasm.js"],
  ["node_modules/tesseract.js-core/tesseract-core.wasm", "tesseract-core.wasm"],
  ["node_modules/tesseract.js-core/tesseract-core-simd.wasm.js", "tesseract-core-simd.wasm.js"],
  ["node_modules/tesseract.js-core/tesseract-core-simd.wasm", "tesseract-core-simd.wasm"],
  ["node_modules/tesseract.js-core/tesseract-core-lstm.wasm.js", "tesseract-core-lstm.wasm.js"],
  ["node_modules/tesseract.js-core/tesseract-core-lstm.wasm", "tesseract-core-lstm.wasm"],
  ["node_modules/tesseract.js-core/tesseract-core-simd-lstm.wasm.js", "tesseract-core-simd-lstm.wasm.js"],
  ["node_modules/tesseract.js-core/tesseract-core-simd-lstm.wasm", "tesseract-core-simd-lstm.wasm"]
];

let copied = 0;
for (const [srcRel, destName] of candidates) {
  const src = path.join(root, srcRel);
  try {
    await access(src);
    await cp(src, path.join(dest, destName));
    copied++;
  } catch {}
}
const langDest = path.join(dest, "lang-data");
await mkdir(langDest, { recursive: true });
const langSrc = path.join(root, "node_modules", "tesseract.js", "lang-data");
try {
  await access(langSrc);
  await cp(langSrc, langDest, { recursive: true });
} catch {}
console.log(`Copied ${copied} Tesseract runtime asset(s) into public/tesseract.`);
console.log("Ensure eng.traineddata.gz exists at public/tesseract/lang-data/eng.traineddata.gz for offline English OCR.");
