// Client-side "write results to disk" glue -- replaces app/api.py's
// apply_to_photo/apply_to_folder filesystem writes, which have no direct
// browser equivalent. Decision (see docs/cross-platform-port.md): a
// single universal path via <a download> (+ a client-side zip for the
// batch case), not the File System Access API -- that API only works in
// Chromium (no Firefox, no Safari/iOS), so anything built on it still
// needs this same fallback anyway, and one path covering every browser is
// less code than two.
//
// zipEntries is pure (Node-testable, see export_glue.test.mjs); everything
// below it touches Canvas/Blob/URL/DOM and only really runs in a browser.

import { zipSync } from "fflate";

// entries: [{filename, bytes: Uint8Array}] -> zip file bytes.
export function zipEntries(entries) {
  const files = {};
  for (const { filename, bytes } of entries) files[filename] = bytes;
  return zipSync(files);
}

export function canvasToBlob(canvas, { type = "image/jpeg", quality = 0.92 } = {}) {
  return new Promise((resolve) => canvas.toBlob(resolve, type, quality));
}

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// Single photo -- the apply_to_photo equivalent. Downloads instead of
// writing next to the original (browsers can't do that without the
// Chromium-only File System Access API -- see the module comment).
export async function downloadResult(canvas, filename, opts) {
  const blob = await canvasToBlob(canvas, opts);
  downloadBlob(blob, filename);
}

// Batch -- the apply_to_folder equivalent. entries: [{filename, canvas}].
// One zip, one download, instead of N automatic downloads (which browsers
// throttle/prompt after a handful).
export async function downloadResultsAsZip(entries, zipFilename, opts) {
  const zipped = [];
  for (const { filename, canvas } of entries) {
    const blob = await canvasToBlob(canvas, opts);
    zipped.push({ filename, bytes: new Uint8Array(await blob.arrayBuffer()) });
  }
  downloadBlob(new Blob([zipEntries(zipped)]), zipFilename);
}
