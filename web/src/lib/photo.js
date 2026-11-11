// Phone photos → two JPEGs shrunk on the phone before upload (from Vixen Vault's tested helper):
// 1600 px long edge for viewing and the AI scan, 400 px thumbnail for the tackle-box list.
export const FULL = 1600;
export const THUMB = 400;

async function decode(file) {
  if (typeof createImageBitmap === "function") {
    try { return await createImageBitmap(file, { imageOrientation: "from-image" }); } catch { /* fall back below */ }
  }
  const url = URL.createObjectURL(file);
  try {
    const img = new Image();
    img.decoding = "async";
    img.src = url;
    await img.decode();
    return img;
  } finally { setTimeout(() => URL.revokeObjectURL(url), 1000); }
}

function toJpeg(src, longEdge, quality) {
  const w0 = src.width, h0 = src.height;
  const s = Math.min(1, longEdge / Math.max(w0, h0));
  const w = Math.max(1, Math.round(w0 * s)), h = Math.max(1, Math.round(h0 * s));
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  const g = c.getContext("2d");
  g.fillStyle = "#fff"; g.fillRect(0, 0, w, h); // transparent PNGs get a white ground, like the Python app
  g.imageSmoothingQuality = "high";
  g.drawImage(src, 0, 0, w, h);
  return new Promise((res, rej) => c.toBlob((b) => (b ? res(b) : rej(new Error("Couldn't convert the photo"))), "image/jpeg", quality));
}

/** {full, thumb} JPEG blobs. Throws a plain-English error for formats the phone's browser can't open. */
export async function preparePhoto(file) {
  let img;
  try { img = await decode(file); }
  catch { throw new Error("This photo format can't be opened here — try a JPEG or take it with the camera button."); }
  return { full: await toJpeg(img, FULL, 0.9), thumb: await toJpeg(img, THUMB, 0.82) };
}

/** Storage path stem: lures/20261105-1a2b3c4d5e6f (+ .jpg / _thumb.jpg). */
export function photoStem(folder) {
  const d = new Date();
  const day = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}${String(d.getDate()).padStart(2, "0")}`;
  const rnd = Array.from(crypto.getRandomValues(new Uint8Array(6)), (b) => b.toString(16).padStart(2, "0")).join("");
  return `${folder}/${day}-${rnd}`;
}

/** A blob as base64 (no data: prefix), for the scan. */
export async function blobB64(blob) {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}
