"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { createWorker, PSM } from "tesseract.js";

type Crop = { left: number; top: number; width: number; height: number };
type WorkerResult = { type: "done"; blob: Blob; previewUrl: string; width: number; height: number } | { type: "error"; message: string };

function cleanLines(text: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of text.split(/\r?\n/)) {
    // Remove row numbering and common table separators, but avoid aggressive drug-name rewriting.
    let value = raw.replace(/\|/g, " ").replace(/^\s*[\d.]+\s+/, "").replace(/\s{2,}/g, " ").trim();
    value = value.replace(/^[^A-Za-z0-9]+|[^A-Za-z0-9%)\]]+$/g, "").trim();
    if (!value || !/[A-Za-z]/.test(value)) continue;
    if (/^(name|description|product|item|medicine|code|quant|quantity|price|total|unit price)$/i.test(value)) continue;
    // A line with mostly numeric content is unlikely to be a medicine name.
    const letters = (value.match(/[A-Za-z]/g) ?? []).length;
    if (letters < 3 || letters / value.length < 0.25) continue;
    const key = value.toLocaleUpperCase().replace(/[^A-Z0-9]+/g, " ").trim();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push(value);
  }
  return out;
}

export default function QuotationOcr() {
  const [file, setFile] = useState<File | null>(null);
  const [sourceUrl, setSourceUrl] = useState("");
  const [crop, setCrop] = useState<Crop>({left: 18, top: 12, width: 42, height: 78});
  const [processedUrl, setProcessedUrl] = useState("");
  const [names, setNames] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState("Choose a quotation image to begin.");
  const [error, setError] = useState("");
  const [workerReady, setWorkerReady] = useState(false);
  const preprocessWorker = useRef<Worker | null>(null);
  const imageRef = useRef<HTMLImageElement>(null);

  useEffect(() => {
    const worker = new Worker(new URL("../workers/preprocess.worker.ts", import.meta.url));
    preprocessWorker.current = worker;
    worker.onmessage = (event: MessageEvent<WorkerResult>) => {
      if (event.data.type === "done") {
        setProcessedUrl(URL.createObjectURL(event.data.blob));
        setProgress(`Preprocessed NAME-column crop: ${event.data.width} × ${event.data.height}px.`);
      } else {
        setError(event.data.message);
        setBusy(false);
      }
    };
    worker.onerror = event => { setError(event.message || "Image preprocessing worker failed."); setBusy(false); };
    if ("serviceWorker" in navigator) {
      window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}), {once:true});
    }
    return () => {
      worker.terminate();
      if (sourceUrl) URL.revokeObjectURL(sourceUrl);
      if (processedUrl) URL.revokeObjectURL(processedUrl);
    };
    // Worker lifecycle is intentionally one-per-component.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const cropStyle = useMemo(() => ({
    left: `${crop.left}%`, top: `${crop.top}%`, width: `${crop.width}%`, height: `${crop.height}%`
  }), [crop]);

  function chooseFile(next: File | null) {
    setFile(next); setNames([]); setError(""); setProcessedUrl("");
    if (sourceUrl) URL.revokeObjectURL(sourceUrl);
    if (next) setSourceUrl(URL.createObjectURL(next));
  }

  function preprocess() {
    if (!file || !preprocessWorker.current) return;
    setBusy(true); setError(""); setProgress("Cropping and enhancing image in a Web Worker…");
    preprocessWorker.current.postMessage({file, crop, scale: 2, thresholdWindow: 31, thresholdBias: 8});
  }

  async function recognize() {
    if (!processedUrl) { setError("Preprocess the image crop first."); return; }
    setBusy(true); setError(""); setNames([]);
    let worker: Awaited<ReturnType<typeof createWorker>> | undefined;
    try {
      setProgress("Loading local Tesseract runtime and English language data…");
      worker = await createWorker("eng", 1, {
        workerPath: "/tesseract/worker.min.js",
        corePath: "/tesseract/tesseract-core.wasm.js",
        langPath: "/tesseract/lang-data",
        gzip: true,
        logger: m => {
          if (m.status === "recognizing text") setProgress(`Recognizing NAME column… ${Math.round((m.progress || 0) * 100)}%`);
          else if (m.status) setProgress(`${m.status}…`);
        }
      });
      await worker.setParameters({
        tessedit_pageseg_mode: PSM.SINGLE_COLUMN,
        preserve_interword_spaces: "1"
      });
      const result = await worker.recognize(processedUrl, {}, {text: true, blocks: true});
      const extracted = cleanLines(result.data.text);
      setNames(extracted);
      setProgress(`Finished. Extracted ${extracted.length} unique candidate name(s). Verify before saving.`);
      setWorkerReady(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setProgress("OCR failed.");
    } finally {
      if (worker) await worker.terminate();
      setBusy(false);
    }
  }

  function updateName(index:number, value:string) {
    setNames(prev => prev.map((name,i)=>i===index?value:name));
  }
  function removeName(index:number) { setNames(prev=>prev.filter((_,i)=>i!==index)); }
  function downloadJson() {
    const blob = new Blob([JSON.stringify(names.filter(n=>n.trim()), null, 2)], {type:"application/json"});
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href=url; a.download="tuuza-medicine-names.json"; a.click();
    URL.revokeObjectURL(url);
  }
  async function copyNames() {
    try { await navigator.clipboard.writeText(JSON.stringify(names.filter(n=>n.trim()))); setProgress("Copied JSON array to clipboard."); }
    catch { setError("Clipboard access was blocked by the browser."); }
  }

  return <main className="page">
    <header className="header"><div className="mark">T</div><div><div className="brand">TUUZA <span>Quote OCR</span></div><p>Local, client-side extraction of medicine names from supplier quotations.</p></div><span className="localBadge">Runs on this device</span></header>
    <section className="intro"><div className="eyebrow">PROCUREMENT TOOL · CLIENT-SIDE OCR</div><h1>Extract the NAME column, not the whole table.</h1><p>Upload a quotation image, set the column boundaries, preprocess the crop, and run OCR locally. No OCR API or backend function is needed.</p></section>
    <section className="card">
      <div className="cardHead"><div><span className="step">01</span><h2>Upload quotation</h2></div><span className="muted">PNG · JPG · WEBP</span></div>
      <label className="drop"><input type="file" accept="image/png,image/jpeg,image/webp" onChange={e=>chooseFile(e.target.files?.[0]??null)}/><strong>{file?.name ?? "Choose quotation image"}</strong><span>Use a clear, straight-on image. PDF page rendering can be added separately.</span></label>
      {sourceUrl&&<><div className="previewTitle"><strong>02 · Mark the NAME column</strong><span>Adjust the crop percentages below; the green rectangle is the crop.</span></div>
        <div className="imageStage"><img ref={imageRef} src={sourceUrl} alt="Uploaded supplier quotation" onLoad={()=>setProgress("Adjust the green crop rectangle to cover the NAME column and data rows.")}/><div className="cropOverlay" style={cropStyle}><span>NAME COLUMN</span></div></div>
        <div className="sliders">
          <Range label="Left edge" value={crop.left} min={0} max={90} onChange={v=>setCrop(c=>({...c,left:Math.min(v,100-c.width)}))}/>
          <Range label="Top edge" value={crop.top} min={0} max={90} onChange={v=>setCrop(c=>({...c,top:Math.min(v,100-c.height)}))}/>
          <Range label="Column width" value={crop.width} min={5} max={100-crop.left} onChange={v=>setCrop(c=>({...c,width:v}))}/>
          <Range label="Table height" value={crop.height} min={10} max={100-crop.top} onChange={v=>setCrop(c=>({...c,height:v}))}/>
        </div>
        <div className="actions"><button className="secondary" disabled={busy} onClick={()=>setCrop({left:18,top:12,width:42,height:78})}>Reset crop</button><button className="primary" disabled={busy} onClick={preprocess}>{busy?"Processing…":"Crop & enhance image"}</button></div>
      </>}
    </section>
    {processedUrl&&<section className="card">
      <div className="cardHead"><div><span className="step">03</span><h2>Review enhanced crop</h2></div><span className="muted">Grayscale + local threshold</span></div>
      <div className="processedPreview"><img src={processedUrl} alt="Enhanced crop of NAME column"/></div>
      <p className="muted note">If letters are clipped, reset or adjust the crop. If text looks too dark or too faint, improve the source photo or tune threshold settings.</p>
      <div className="actions"><button className="primary" disabled={busy} onClick={recognize}>{busy?"Recognizing…":"Run OCR locally"}</button></div>
    </section>}
    {(progress||error)&&<section className={`status ${error?"error":""}`} role="status"><strong>{error?"Needs attention":"Processing status"}</strong><span>{error||progress}</span></section>}
    {names.length>0&&<section className="card">
      <div className="cardHead"><div><span className="step">04</span><h2>Review medicine names</h2></div><span className="muted">{names.length} candidates</span></div>
      <p className="muted note">OCR can still split, merge or miss rows. Edit or remove errors before exporting this list to your procurement workflow.</p>
      <ol className="nameList">{names.map((name,i)=><li key={`${i}-${name}`}><input aria-label={`Medicine name ${i+1}`} value={name} onChange={e=>updateName(i,e.target.value)}/><button className="remove" onClick={()=>removeName(i)} aria-label={`Remove ${name}`}>×</button></li>)}</ol>
      <div className="actions"><button className="secondary" onClick={copyNames}>Copy JSON array</button><button className="primary" onClick={downloadJson}>Download JSON</button></div>
      <pre className="jsonPreview">{JSON.stringify(names.filter(n=>n.trim()),null,2)}</pre>
    </section>}
    <footer>Private by design: OCR is performed in the browser. Files are not uploaded by this OCR component.</footer>
  </main>;
}

function Range({label,value,min,max,onChange}:{label:string;value:number;min:number;max:number;onChange:(v:number)=>void}) {
  return <label className="range"><span>{label}<b>{value}%</b></span><input type="range" min={min} max={Math.max(min,max)} value={value} onChange={e=>onChange(Number(e.target.value))}/></label>;
}
