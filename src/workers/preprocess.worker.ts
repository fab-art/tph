/// <reference lib="webworker" />
type Request = { file: File; crop: {left:number;top:number;width:number;height:number}; scale?:number; thresholdWindow?:number; thresholdBias?:number };
const ctx: DedicatedWorkerGlobalScope = self as unknown as DedicatedWorkerGlobalScope;

ctx.onmessage = async (event: MessageEvent<Request>) => {
  try {
    const {file,crop,scale=2,thresholdWindow=31,thresholdBias=8} = event.data;
    const bitmap = await createImageBitmap(file);
    const sx = Math.max(0, Math.floor(bitmap.width * crop.left / 100));
    const sy = Math.max(0, Math.floor(bitmap.height * crop.top / 100));
    const sw = Math.max(1, Math.min(bitmap.width-sx, Math.floor(bitmap.width*crop.width/100)));
    const sh = Math.max(1, Math.min(bitmap.height-sy, Math.floor(bitmap.height*crop.height/100)));
    const canvas = new OffscreenCanvas(Math.max(1,sw*scale), Math.max(1,sh*scale));
    const context = canvas.getContext("2d", {willReadFrequently:true});
    if (!context) throw new Error("OffscreenCanvas 2D context is unavailable in this browser.");
    context.imageSmoothingEnabled = true;
    context.imageSmoothingQuality = "high";
    context.drawImage(bitmap,sx,sy,sw,sh,0,0,canvas.width,canvas.height);
    bitmap.close();

    const image = context.getImageData(0,0,canvas.width,canvas.height);
    const {data,width,height} = image;
    const gray = new Uint8ClampedArray(width*height);
    // Grayscale conversion in worker.
    for (let i=0,p=0;i<data.length;i+=4,p++) gray[p] = Math.round(0.299*data[i]+0.587*data[i+1]+0.114*data[i+2]);

    // Integral image enables fast local mean thresholding (adaptive binarization).
    const integral = new Float64Array((width+1)*(height+1));
    const stride = width+1;
    for (let y=1;y<=height;y++) {
      let rowSum=0;
      for (let x=1;x<=width;x++) {
        rowSum += gray[(y-1)*width+(x-1)];
        integral[y*stride+x] = integral[(y-1)*stride+x] + rowSum;
      }
    }
    const radius = Math.max(3,Math.floor(thresholdWindow/2));
    for (let y=0;y<height;y++) {
      const y1=Math.max(0,y-radius), y2=Math.min(height-1,y+radius);
      for (let x=0;x<width;x++) {
        const x1=Math.max(0,x-radius), x2=Math.min(width-1,x+radius);
        const count=(x2-x1+1)*(y2-y1+1);
        const sum=integral[(y2+1)*stride+(x2+1)]-integral[y1*stride+(x2+1)]-integral[(y2+1)*stride+x1]+integral[y1*stride+x1];
        const mean=sum/count;
        const value=gray[y*width+x] < mean-thresholdBias ? 0 : 255;
        const i=(y*width+x)*4;
        data[i]=value;data[i+1]=value;data[i+2]=value;data[i+3]=255;
      }
    }
    context.putImageData(image,0,0);
    const blob = await canvas.convertToBlob({type:"image/png"});
    ctx.postMessage({type:"done",blob,width,height});
  } catch (e) {
    ctx.postMessage({type:"error",message:e instanceof Error?e.message:String(e)});
  }
};
export {};
