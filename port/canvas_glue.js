// Canvas ImageData <-> flat RGB Float32Array conversion, plus alpha
// pass-through -- the glue-layer work engine.js's applyRecipe deliberately
// leaves to its caller (see the comment on applyRecipe in engine.js).
// Mirrors apply_recipe()'s own PIL handling in develop_engine.py: alpha is
// extracted before the pipeline runs and reattached unchanged after,
// never touched by any effect.

export function imageDataToRgb(imageData) {
  const { data, width, height } = imageData;
  const n = width * height;
  const rgb = new Float32Array(n * 3);
  const alpha = new Uint8ClampedArray(n);
  for (let p = 0; p < n; p++) {
    rgb[p * 3] = data[p * 4] / 255;
    rgb[p * 3 + 1] = data[p * 4 + 1] / 255;
    rgb[p * 3 + 2] = data[p * 4 + 2] / 255;
    alpha[p] = data[p * 4 + 3];
  }
  return { rgb, alpha, width, height };
}

export function rgbToImageData(rgb, width, height, alpha) {
  const n = width * height;
  const out = new ImageData(width, height);
  for (let p = 0; p < n; p++) {
    out.data[p * 4] = Math.round(Math.min(1, Math.max(0, rgb[p * 3])) * 255);
    out.data[p * 4 + 1] = Math.round(Math.min(1, Math.max(0, rgb[p * 3 + 1])) * 255);
    out.data[p * 4 + 2] = Math.round(Math.min(1, Math.max(0, rgb[p * 3 + 2])) * 255);
    out.data[p * 4 + 3] = alpha ? alpha[p] : 255;
  }
  return out;
}
