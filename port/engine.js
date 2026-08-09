// Step 1 prototype: elementwise helpers + hand-rolled color-space/blur,
// the JS replacements for numpy broadcasting + cv2.cvtColor + cv2.GaussianBlur
// identified in docs/cross-platform-port.md. Mirrors scripts/develop_engine.py's
// rgb_to_hsv/hsv_to_rgb/luminance/gaussian_blur -- ports the rest of the
// pipeline once these check out against the real fixtures (step 2).
//
// Images are flat Float32Array of length H*W*3, values in [0,1], row-major
// RGB triplets -- same layout apply_recipe() works with in numpy, minus the
// separate axis.
//
// .js not .mjs: some static file servers (Python's http.server on Windows,
// notably) don't map .mjs to a JS content-type, and browsers refuse to
// execute a module script served as text/plain -- silently, no console
// error a user would necessarily notice. .js is never ambiguous.
//
// Browser-only module: no Node builtins (e.g. "node:url"), no `process`
// reference anywhere, even inside an `if` guard -- referencing an
// undeclared global throws at module-evaluation time in a browser, which
// fails the whole module (and silently breaks every page that imports it,
// no console error surfaced). Self-check lives in engine.selfcheck.mjs.

export function clip(data, lo = 0, hi = 1) {
  for (let i = 0; i < data.length; i++) data[i] = Math.min(hi, Math.max(lo, data[i]));
  return data;
}

export function scale(data, factor) {
  for (let i = 0; i < data.length; i++) data[i] *= factor;
  return data;
}

export function blend(a, b, t) {
  const out = new Float32Array(a.length);
  for (let i = 0; i < a.length; i++) out[i] = a[i] + (b[i] - a[i]) * t;
  return out;
}

// lut: Float32Array of 256 values over [0,1] input range, from
// parametricCurveLut/pointCurveLut below.
export function applyLut(data, lut) {
  const out = new Float32Array(data.length);
  for (let i = 0; i < data.length; i++) {
    // Math.trunc, not round: matches Python's (channel*255).astype(np.int32)
    // -- rounding here would be a systematic off-by-one against the ported
    // LUT near .5 boundaries.
    const idx = Math.min(255, Math.max(0, Math.trunc(data[i] * 255)));
    out[i] = lut[idx];
  }
  return out;
}

// Mirrors numpy.interp(x, xp, fp): xp must be sorted ascending; x outside
// [xp[0], xp[-1]] clamps to fp[0]/fp[-1] rather than extrapolating.
export function interp(x, xp, fp) {
  if (x <= xp[0]) return fp[0];
  if (x >= xp[xp.length - 1]) return fp[fp.length - 1];
  let i = 1;
  while (xp[i] < x) i++;
  const t = (x - xp[i - 1]) / (xp[i] - xp[i - 1]);
  return fp[i - 1] + (fp[i] - fp[i - 1]) * t;
}

export function luminance(rgb) {
  const n = rgb.length / 3;
  const out = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    out[i] = rgb[i * 3] * 0.299 + rgb[i * 3 + 1] * 0.587 + rgb[i * 3 + 2] * 0.114;
  }
  return out;
}

// Matches cv2.cvtColor(..., COLOR_RGB2HSV) for float32: H in [0,360), S,V in [0,1].
export function rgbToHsv(rgb) {
  const n = rgb.length / 3;
  const out = new Float32Array(rgb.length);
  for (let i = 0; i < n; i++) {
    const r = rgb[i * 3], g = rgb[i * 3 + 1], b = rgb[i * 3 + 2];
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    const diff = max - min;
    let h = 0;
    if (diff !== 0) {
      if (max === r) h = 60 * (((g - b) / diff) % 6);
      else if (max === g) h = 60 * ((b - r) / diff + 2);
      else h = 60 * ((r - g) / diff + 4);
      if (h < 0) h += 360;
    }
    const s = max === 0 ? 0 : diff / max;
    out[i * 3] = h;
    out[i * 3 + 1] = s;
    out[i * 3 + 2] = max;
  }
  return out;
}

export function hsvToRgb(hsv) {
  const n = hsv.length / 3;
  const out = new Float32Array(hsv.length);
  for (let i = 0; i < n; i++) {
    const h = hsv[i * 3], s = hsv[i * 3 + 1], v = hsv[i * 3 + 2];
    const c = v * s;
    const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
    const m = v - c;
    let r = 0, g = 0, b = 0;
    if (h < 60) [r, g, b] = [c, x, 0];
    else if (h < 120) [r, g, b] = [x, c, 0];
    else if (h < 180) [r, g, b] = [0, c, x];
    else if (h < 240) [r, g, b] = [0, x, c];
    else if (h < 300) [r, g, b] = [x, 0, c];
    else [r, g, b] = [c, 0, x];
    out[i * 3] = r + m;
    out[i * 3 + 1] = g + m;
    out[i * 3 + 2] = b + m;
  }
  return out;
}

// Separable Gaussian with reflect-edge padding, radius sized like cv2's
// auto ksize (~6*sigma+1). Checked against cv2.GaussianBlur in
// engine.test.mjs -- max diff ~0.00024 on a 0..1 range, close enough that
// opencv.js isn't worth the ~8MB WASM dependency.
export function gaussianBlur(data, width, height, sigma) {
  const radius = Math.max(1, Math.round(sigma * 3));
  const kernel = new Float32Array(radius * 2 + 1);
  let sum = 0;
  for (let i = -radius; i <= radius; i++) {
    const v = Math.exp(-(i * i) / (2 * sigma * sigma));
    kernel[i + radius] = v;
    sum += v;
  }
  for (let i = 0; i < kernel.length; i++) kernel[i] /= sum;

  const reflect = (i, n) => {
    if (i < 0) return -i - 1 < n ? -i - 1 : 0;
    if (i >= n) return 2 * n - i - 1 >= 0 ? 2 * n - i - 1 : n - 1;
    return i;
  };

  const tmp = new Float32Array(data.length);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      let acc = 0;
      for (let k = -radius; k <= radius; k++) {
        acc += data[y * width + reflect(x + k, width)] * kernel[k + radius];
      }
      tmp[y * width + x] = acc;
    }
  }
  const out = new Float32Array(data.length);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      let acc = 0;
      for (let k = -radius; k <= radius; k++) {
        acc += tmp[reflect(y + k, height) * width + x] * kernel[k + radius];
      }
      out[y * width + x] = acc;
    }
  }
  return out;
}

function getChannel(img, c) {
  const n = img.length / 3;
  const out = new Float32Array(n);
  for (let p = 0; p < n; p++) out[p] = img[p * 3 + c];
  return out;
}

function setChannel(img, c, values) {
  const n = img.length / 3;
  for (let p = 0; p < n; p++) img[p * 3 + c] = values[p];
}

// ---------------------------------------------------------------------------
// tone curve construction
// ---------------------------------------------------------------------------

export function parametricCurveLut(recipe) {
  const shadows = (recipe.ParametricShadows ?? 0) / 100;
  const darks = (recipe.ParametricDarks ?? 0) / 100;
  const lights = (recipe.ParametricLights ?? 0) / 100;
  const highlights = (recipe.ParametricHighlights ?? 0) / 100;
  const ss = (recipe.ParametricShadowSplit ?? 25) / 100;
  const ms = (recipe.ParametricMidtoneSplit ?? 50) / 100;
  const hs = (recipe.ParametricHighlightSplit ?? 75) / 100;

  const lut = new Float32Array(256);
  if (shadows === 0 && darks === 0 && lights === 0 && highlights === 0) {
    for (let i = 0; i < 256; i++) lut[i] = i / 255;
    return lut;
  }

  const strength = 0.35;
  const points = [
    [0.0, 0.0 + shadows * strength],
    [ss, ss + darks * strength],
    [ms, ms],
    [hs, hs + lights * strength],
    [1.0, 1.0 + highlights * strength],
  ];
  // mirrors np.unique(xs, return_index=True): keep each unique x's FIRST
  // occurrence, then sort ascending -- not "last wins".
  const byX = new Map();
  for (const [x, y] of points) if (!byX.has(x)) byX.set(x, y);
  const xs = Array.from(byX.keys()).sort((a, b) => a - b);
  const ys = xs.map((x) => byX.get(x));

  for (let i = 0; i < 256; i++) {
    lut[i] = Math.min(1, Math.max(0, interp(i / 255, xs, ys)));
  }
  return lut;
}

export function pointCurveLut(points) {
  const lut = new Float32Array(256);
  if (!points || points.length < 2) {
    for (let i = 0; i < 256; i++) lut[i] = i / 255;
    return lut;
  }
  // Python's sorted() on tuples compares element-by-element (x, then y).
  const pts = [...points].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  for (let i = 0; i < 256; i++) {
    lut[i] = Math.min(1, Math.max(0, interp(i, xs, ys) / 255));
  }
  return lut;
}

// point_lut evaluated at each of master_lut's own output values -- point_lut
// acts as a lookup function over the [0,1] domain, sampled at 256 points.
export function combineLuts(masterLut, pointLut) {
  const domain = new Float32Array(256);
  for (let i = 0; i < 256; i++) domain[i] = i / 255;
  const combined = new Float32Array(256);
  for (let i = 0; i < 256; i++) combined[i] = interp(masterLut[i], domain, pointLut);
  return combined;
}

// ---------------------------------------------------------------------------
// basic tone controls
// ---------------------------------------------------------------------------

const TEXTURE_REFERENCE_WIDTH = 640;
const TEXTURE_BLUR_RADIUS = 1.6;
const TEXTURE_STRENGTH = 0.4;

const DEHAZE_POS_GAMMA = [0.273, 0.278];
const DEHAZE_NEG_GAMMA = [0.861, 0.218];
const DEHAZE_POS_SAT = [0.271, 0.014];
const DEHAZE_NEG_SAT = [0.057, 0.33];

export function applyDehaze(img, dehaze) {
  const d = dehaze / 100;
  let gamma, satBoost;
  if (d >= 0) {
    const [a, b] = DEHAZE_POS_GAMMA;
    gamma = 1 + a * d + b * d * d;
    const [a2, b2] = DEHAZE_POS_SAT;
    satBoost = a2 * d + b2 * d * d;
  } else {
    const e = -d;
    const [a, b] = DEHAZE_NEG_GAMMA;
    gamma = 1 - a * e + b * e * e;
    const [a2, b2] = DEHAZE_NEG_SAT;
    satBoost = -(a2 * e + b2 * e * e);
  }

  const out = new Float32Array(img.length);
  for (let i = 0; i < img.length; i++) {
    out[i] = Math.min(1, Math.max(0, img[i])) ** gamma;
  }
  if (satBoost) {
    const lum = luminance(out);
    const n = out.length / 3;
    for (let p = 0; p < n; p++) {
      for (let c = 0; c < 3; c++) {
        const idx = p * 3 + c;
        out[idx] = lum[p] + (out[idx] - lum[p]) * (1 + satBoost);
      }
    }
  }
  return out;
}

export function applyBasicTone(img, width, height, recipe) {
  let out = Float32Array.from(img);
  const n = out.length / 3;

  const exposure = recipe.Exposure2012 ?? 0;
  if (exposure) {
    const f = 2 ** exposure;
    for (let i = 0; i < out.length; i++) out[i] *= f;
  }

  const contrast = (recipe.Contrast2012 ?? 0) / 100;
  if (contrast) {
    for (let i = 0; i < out.length; i++) out[i] = 0.5 + (out[i] - 0.5) * (1 + contrast);
  }

  const blacks = (recipe.Blacks2012 ?? 0) / 100;
  const whites = (recipe.Whites2012 ?? 0) / 100;
  const lo = Math.min(0.9, Math.max(-0.5, blacks * 0.2));
  const hi = Math.min(1.5, Math.max(0.1, 1.0 + whites * 0.2));
  if (lo !== 0 || hi !== 1) {
    const denom = Math.max(hi - lo, 1e-6);
    for (let i = 0; i < out.length; i++) out[i] = (out[i] - lo) / denom;
  }

  // Both masks below use this SAME pre-shadows/highlights luminance --
  // develop_engine.py computes `lum` once and reuses it for both blocks,
  // it doesn't recompute after the shadows delta is applied.
  const shadows = (recipe.Shadows2012 ?? 0) / 100;
  const highlights = (recipe.Highlights2012 ?? 0) / 100;
  if (shadows || highlights) {
    const lum = luminance(out);
    for (let p = 0; p < n; p++) {
      let delta = 0;
      if (shadows) delta += shadows * 0.4 * Math.min(1, Math.max(0, 1 - lum[p] / 0.5)) ** 1.5;
      if (highlights) delta += highlights * 0.4 * Math.min(1, Math.max(0, (lum[p] - 0.5) / 0.5)) ** 1.5;
      for (let c = 0; c < 3; c++) out[p * 3 + c] += delta;
    }
  }

  const texture = (recipe.Texture ?? 0) / 100;
  if (texture) {
    const lum = luminance(out);
    const radius = Math.max(TEXTURE_BLUR_RADIUS * (width / TEXTURE_REFERENCE_WIDTH), 0.15);
    const fineBlur = gaussianBlur(lum, width, height, radius);
    for (let p = 0; p < n; p++) {
      const detail = (lum[p] - fineBlur[p]) * texture * TEXTURE_STRENGTH;
      for (let c = 0; c < 3; c++) out[p * 3 + c] += detail;
    }
  }

  const clarity = (recipe.Clarity2012 ?? 0) / 100;
  if (clarity) {
    const lum = luminance(out);
    const blurred = gaussianBlur(lum, width, height, 25);
    for (let p = 0; p < n; p++) {
      const detail = (lum[p] - blurred[p]) * clarity * 1.2;
      for (let c = 0; c < 3; c++) out[p * 3 + c] += detail;
    }
  }

  const dehaze = recipe.Dehaze ?? 0;
  if (dehaze) out = applyDehaze(out, dehaze);

  return clip(out, 0, 1);
}

// ---------------------------------------------------------------------------
// hue-band helpers, shared by the gray mixer and the 8-band HSL sliders
// ---------------------------------------------------------------------------

const BAND_HUES = { Red: 0, Orange: 30, Yellow: 60, Green: 120, Aqua: 180, Blue: 240, Purple: 275, Magenta: 315 };
const BAND_ORDER = ["Red", "Orange", "Yellow", "Green", "Aqua", "Blue", "Purple", "Magenta"];

export function hueBandWeights(hueArr, values) {
  const baseH = BAND_ORDER.map((b) => BAND_HUES[b]);
  const baseV = BAND_ORDER.map((b) => values[b] ?? 0);
  const anchorsH = [...baseH.map((h) => h - 360), ...baseH, ...baseH.map((h) => h + 360)];
  const anchorsV = [...baseV, ...baseV, ...baseV];
  const out = new Float32Array(hueArr.length);
  for (let i = 0; i < hueArr.length; i++) out[i] = interp(hueArr[i], anchorsH, anchorsV);
  return out;
}

// ---------------------------------------------------------------------------
// grayscale conversion (Adobe-style B&W mixer)
// ---------------------------------------------------------------------------

export function applyGrayscaleMixer(img, recipe) {
  const hsv = rgbToHsv(img);
  const n = img.length / 3;
  const hue = new Float32Array(n);
  const sat = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    hue[i] = hsv[i * 3];
    sat[i] = hsv[i * 3 + 1];
  }
  const mixer = {};
  for (const b of BAND_ORDER) mixer[b] = recipe[`GrayMixer${b}`] ?? 0;
  const weight = hueBandWeights(hue, mixer);
  const base = luminance(img);

  const out = new Float32Array(img.length);
  for (let i = 0; i < n; i++) {
    const gray = Math.min(1, Math.max(0, base[i] * (1 + (weight[i] / 100) * sat[i] * 1.1)));
    out[i * 3] = out[i * 3 + 1] = out[i * 3 + 2] = gray;
  }
  return out;
}

// ---------------------------------------------------------------------------
// HSL hue/saturation/luminance 8-band adjustments (color looks)
// ---------------------------------------------------------------------------

export function applyHslBands(img, recipe) {
  const anyNonZero = BAND_ORDER.some(
    (b) =>
      (recipe[`HueAdjustment${b}`] ?? 0) ||
      (recipe[`SaturationAdjustment${b}`] ?? 0) ||
      (recipe[`LuminanceAdjustment${b}`] ?? 0)
  );
  if (!anyNonZero) return img;

  const hsv = rgbToHsv(img);
  const n = img.length / 3;
  const hue = new Float32Array(n);
  for (let i = 0; i < n; i++) hue[i] = hsv[i * 3];

  const hueVals = {}, satVals = {}, lumVals = {};
  for (const b of BAND_ORDER) {
    hueVals[b] = recipe[`HueAdjustment${b}`] ?? 0;
    satVals[b] = recipe[`SaturationAdjustment${b}`] ?? 0;
    lumVals[b] = recipe[`LuminanceAdjustment${b}`] ?? 0;
  }
  const hueShift = hueBandWeights(hue, hueVals);
  const satShift = hueBandWeights(hue, satVals);
  const lumShift = hueBandWeights(hue, lumVals);

  const newHsv = new Float32Array(hsv.length);
  for (let i = 0; i < n; i++) {
    // JS `%` keeps the sign of the dividend (can go negative); Python's
    // never does for a positive divisor -- correct for that or hue wraps
    // to a negative degree instead of 0..360.
    let h = (hsv[i * 3] + hueShift[i] * 0.3) % 360;
    if (h < 0) h += 360;
    const s = Math.min(1, Math.max(0, hsv[i * 3 + 1] * (1 + satShift[i] / 100)));
    const v = Math.min(1, Math.max(0, hsv[i * 3 + 2] * (1 + (lumShift[i] / 100) * 0.5)));
    newHsv[i * 3] = h;
    newHsv[i * 3 + 1] = s;
    newHsv[i * 3 + 2] = v;
  }
  return clip(hsvToRgb(newHsv), 0, 1);
}

// ---------------------------------------------------------------------------
// saturation / vibrance
// ---------------------------------------------------------------------------

export function applySaturationVibrance(img, recipe) {
  const saturation = (recipe.Saturation ?? 0) / 100;
  const vibrance = (recipe.Vibrance ?? 0) / 100;
  if (!saturation && !vibrance) return img;

  const hsv = rgbToHsv(img);
  const n = img.length / 3;
  for (let i = 0; i < n; i++) {
    let s = hsv[i * 3 + 1];
    if (saturation) s = s * (1 + saturation);
    if (vibrance) {
      const protect = 1 - s;
      const sClipped = Math.min(1, Math.max(0, s));
      s = s + vibrance * protect * sClipped * 1.5;
    }
    hsv[i * 3 + 1] = Math.min(1, Math.max(0, s));
  }
  return clip(hsvToRgb(hsv), 0, 1);
}

// ---------------------------------------------------------------------------
// split toning
// ---------------------------------------------------------------------------

function hueToRgb1(h) {
  const rgb = hsvToRgb(new Float32Array([h, 1.0, 1.0]));
  return [rgb[0], rgb[1], rgb[2]];
}

export function applySplitToning(img, recipe) {
  const shHue = recipe.SplitToningShadowHue ?? 0;
  const shSat = recipe.SplitToningShadowSaturation ?? 0;
  const hiHue = recipe.SplitToningHighlightHue ?? 0;
  const hiSat = recipe.SplitToningHighlightSaturation ?? 0;
  const balance = (recipe.SplitToningBalance ?? 0) / 100;
  if (!shSat && !hiSat) return img;

  const n = img.length / 3;
  const lum = luminance(img);
  const mid = 0.5 + balance * 0.3;
  const out = Float32Array.from(img);

  if (shSat) {
    const color = hueToRgb1(shHue);
    const coef = (shSat / 100) * 0.6;
    for (let p = 0; p < n; p++) {
      const w = Math.min(1, Math.max(0, 1 - lum[p] / Math.max(mid, 1e-3)));
      for (let c = 0; c < 3; c++) out[p * 3 + c] += w * (color[c] - 0.5) * coef;
    }
  }
  if (hiSat) {
    const color = hueToRgb1(hiHue);
    const coef = (hiSat / 100) * 0.6;
    for (let p = 0; p < n; p++) {
      const w = Math.min(1, Math.max(0, (lum[p] - mid) / Math.max(1 - mid, 1e-3)));
      for (let c = 0; c < 3; c++) out[p * 3 + c] += w * (color[c] - 0.5) * coef;
    }
  }
  return clip(out, 0, 1);
}

// ---------------------------------------------------------------------------
// grain
// ---------------------------------------------------------------------------

const GRAIN_REFERENCE_WIDTH = 4096;
const GRAIN_SIZE_SCALE = 0.85;

function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function gaussianRng(rand) {
  let spare = null;
  return function () {
    if (spare !== null) {
      const v = spare;
      spare = null;
      return v;
    }
    let u, v, s;
    do {
      u = rand() * 2 - 1;
      v = rand() * 2 - 1;
      s = u * u + v * v;
    } while (s === 0 || s >= 1);
    const mul = Math.sqrt((-2 * Math.log(s)) / s);
    spare = v * mul;
    return u * mul;
  };
}

// ponytail: seeded RNG here is a small hand-rolled generator (mulberry32 +
// Box-Muller), not numpy's PCG64 -- grain is inherently a random-looking
// texture, and there's no need for this port's grain pattern to be
// bit-identical to the Python desktop build's, only for it to have the
// same statistical character (zero-mean, unit-std, blurred to the same
// radius). engine.test.mjs checks that statistically, not against a
// pixel fixture. Upgrade path: only worth it if cross-runtime pixel
// parity ever becomes an actual requirement.
export function applyGrain(img, width, height, recipe, seed) {
  const amount = (recipe.GrainAmount ?? 0) / 100;
  if (!amount) return img;
  const size = Math.max(recipe.GrainSize ?? 25, 1);
  const frequency = recipe.GrainFrequency ?? 50;

  const rand = mulberry32(seed ?? 0);
  const gauss = gaussianRng(rand);
  const n = width * height;
  let noise = new Float32Array(n);
  for (let i = 0; i < n; i++) noise[i] = gauss();

  const blurRadius = Math.max((0.3 + (size / 100) * 1.6) * GRAIN_SIZE_SCALE * (width / GRAIN_REFERENCE_WIDTH), 0.15);
  noise = gaussianBlur(noise, width, height, blurRadius);

  let mean = 0;
  for (let i = 0; i < n; i++) mean += noise[i];
  mean /= n;
  let variance = 0;
  for (let i = 0; i < n; i++) variance += (noise[i] - mean) ** 2;
  variance /= n;
  const std = Math.sqrt(variance);
  for (let i = 0; i < n; i++) noise[i] = (noise[i] - mean) / (std + 1e-9);

  const detailScale = 0.6 + (frequency / 100) * 0.8;
  const out = Float32Array.from(img);
  for (let p = 0; p < n; p++) {
    const delta = noise[p] * detailScale * amount * 0.12;
    out[p * 3] += delta;
    out[p * 3 + 1] += delta;
    out[p * 3 + 2] += delta;
  }
  return clip(out, 0, 1);
}

// ---------------------------------------------------------------------------
// vignette
// ---------------------------------------------------------------------------

const VIGNETTE_FLOOR_CURVE = 1.8;
const VIGNETTE_FALLOFF_SHAPE = 2.0;
const VIGNETTE_PAINT_STRENGTH = 0.94;

function vignetteDistance(x, y, cx, cy, roundness) {
  let p, rx, ry;
  if (roundness >= 0) {
    p = 2.0;
    const r = Math.min(cx, cy);
    rx = cx + (r - cx) * roundness;
    ry = cy + (r - cy) * roundness;
  } else {
    p = 2.0 + 4.0 * -roundness;
    rx = cx;
    ry = cy;
  }
  const dx = Math.abs(x - cx) / rx;
  const dy = Math.abs(y - cy) / ry;
  const dist = (dx ** p + dy ** p) ** (1 / p);
  const corner = ((cx / rx) ** p + (cy / ry) ** p) ** (1 / p);
  return dist / corner;
}

export function applyVignette(img, width, height, recipe) {
  const amount = recipe.PostCropVignetteAmount || recipe.VignetteAmount || 0;
  const amountFrac = amount / 100;
  if (!amountFrac) return img;
  const midpoint = (recipe.PostCropVignetteMidpoint ?? 50) / 100;
  const feather = Math.max(recipe.PostCropVignetteFeather ?? 50, 1) / 100;
  const roundness = Math.min(1, Math.max(-1, (recipe.PostCropVignetteRoundness ?? 0) / 100));
  const highlightContrast = (recipe.PostCropVignetteHighlightContrast ?? 0) / 100;
  const style = recipe.PostCropVignetteStyle || 1;

  const cy = height / 2, cx = width / 2;
  const n = width * height;
  const falloff = new Float32Array(n);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const dist = vignetteDistance(x, y, cx, cy, roundness);
      falloff[y * width + x] = Math.min(1, Math.max(0, (dist - midpoint) / Math.max(feather, 1e-3)));
    }
  }

  const isDarkening = amountFrac < 0;
  let floor = 0;
  if (isDarkening) {
    let strength = -amountFrac;
    if (style === 3) strength *= VIGNETTE_PAINT_STRENGTH;
    floor = (1 - strength) ** VIGNETTE_FLOOR_CURVE;
  }

  const origLum = luminance(img);
  const out = new Float32Array(img.length);
  for (let p = 0; p < n; p++) {
    const factor = isDarkening
      ? floor + (1 - floor) * (1 - falloff[p]) ** VIGNETTE_FALLOFF_SHAPE
      : 1 + amountFrac * falloff[p] * 0.7;
    for (let c = 0; c < 3; c++) out[p * 3 + c] = img[p * 3 + c] * factor;
  }

  if (style === 1 && isDarkening) {
    for (let p = 0; p < n; p++) {
      const bright = Math.min(1, Math.max(0, (origLum[p] - 0.7) / 0.3));
      const w = bright * falloff[p] * 0.3;
      for (let c = 0; c < 3; c++) out[p * 3 + c] += (img[p * 3 + c] - out[p * 3 + c]) * w;
    }
  } else if (style === 2) {
    const outLum = luminance(out);
    for (let p = 0; p < n; p++) {
      const f = 1 + falloff[p] * 0.25;
      for (let c = 0; c < 3; c++) out[p * 3 + c] = outLum[p] + (out[p * 3 + c] - outLum[p]) * f;
    }
  }

  if (highlightContrast) {
    for (let p = 0; p < n; p++) {
      const w = highlightContrast * falloff[p] * 0.5;
      for (let c = 0; c < 3; c++) out[p * 3 + c] += (out[p * 3 + c] - 0.5) * w;
    }
  }

  return clip(out, 0, 1);
}

// ---------------------------------------------------------------------------
// sharpening
// ---------------------------------------------------------------------------

// PIL's ImageFilter.UnsharpMask uses its own internal blur, not cv2 -- a
// second potential numeric-mismatch spot (see docs/cross-platform-port.md).
// Reuses gaussianBlur (already validated against cv2) rather than a third
// blur implementation; engine.test.mjs measures the actual gap against
// real apply_sharpen() output the same way gaussianBlur's was measured.
export function applySharpen(img, width, height, recipe) {
  const sharpness = recipe.Sharpness ?? 0;
  if (!sharpness) return img;
  const radius = recipe.SharpenRadius ?? 1.0;
  const percent = Math.trunc(Math.min(sharpness * 3, 250));
  const threshold = 2 / 255; // PIL's threshold=2 is in 0..255 units

  const n = width * height;
  const out = Float32Array.from(img);
  for (let c = 0; c < 3; c++) {
    const channel = getChannel(img, c);
    const blurred = gaussianBlur(channel, width, height, radius);
    for (let p = 0; p < n; p++) {
      const diff = channel[p] - blurred[p];
      if (Math.abs(diff) >= threshold) {
        out[p * 3 + c] = Math.min(1, Math.max(0, channel[p] + diff * (percent / 100)));
      }
    }
  }
  return out;
}

// ---------------------------------------------------------------------------
// top level
// ---------------------------------------------------------------------------

// Operates on a flat RGB Float32Array (no alpha, no PIL/Image wrapper) --
// alpha handling and Canvas ImageData <-> Float32Array conversion are
// glue-layer concerns for whatever calls this, same split the Python
// per-effect functions already have from apply_recipe()'s own PIL handling.
// recipe._lut3d, if present, is anything with an `.apply(rgbFloat32Array)`
// method (e.g. lut_engine.js's Lut3D) -- duck-typed rather than imported,
// so engine.js doesn't need a hard dependency on lut_engine.js.
export function applyRecipe(img, width, height, recipe, grainSeed) {
  let out = applyBasicTone(img, width, height, recipe);

  if (recipe._lut3d) out = recipe._lut3d.apply(out);

  const masterLut = parametricCurveLut(recipe);
  const pointLut = pointCurveLut(recipe.ToneCurvePV2012);
  const combinedLut = combineLuts(masterLut, pointLut);
  for (let c = 0; c < 3; c++) setChannel(out, c, applyLut(getChannel(out, c), combinedLut));

  const perChannelKeys = ["ToneCurvePV2012Red", "ToneCurvePV2012Green", "ToneCurvePV2012Blue"];
  for (let c = 0; c < 3; c++) {
    const pts = recipe[perChannelKeys[c]];
    if (pts && pts.length > 2) {
      const lut = pointCurveLut(pts);
      setChannel(out, c, applyLut(getChannel(out, c), lut));
    }
  }

  if (!recipe.ConvertToGrayscale) {
    out = applyHslBands(out, recipe);
    out = applySaturationVibrance(out, recipe);
  } else {
    out = applyGrayscaleMixer(out, recipe);
  }

  out = applySplitToning(out, recipe);
  out = applyGrain(out, width, height, recipe, grainSeed);
  out = applyVignette(out, width, height, recipe);

  out = clip(out, 0, 1);
  // Matches PIL's uint8 quantization before apply_sharpen() in the real
  // pipeline -- sharpening runs on 8-bit-quantized data there, not float.
  for (let i = 0; i < out.length; i++) out[i] = Math.round(out[i] * 255) / 255;
  out = applySharpen(out, width, height, recipe);

  return out;
}

