// Run with: node port/engine.selfcheck.mjs
// Node-only (uses Float32Array/Math same as engine.js, no browser APIs) --
// kept separate from engine.js so that file stays pure browser code.
import { rgbToHsv, hsvToRgb, luminance, gaussianBlur } from "./engine.js";

function approxEqual(a, b, eps = 1e-3) {
  return Math.abs(a - b) < eps;
}

// rgb<->hsv round trip on known colors, cross-checked against textbook HSV values
const cases = [
  { rgb: [1, 0, 0], hsv: [0, 1, 1] },
  { rgb: [0, 1, 0], hsv: [120, 1, 1] },
  { rgb: [0, 0, 1], hsv: [240, 1, 1] },
  { rgb: [0.5, 0.5, 0.5], hsv: [0, 0, 0.5] },
  { rgb: [0.2, 0.6, 0.8], hsv: null }, // just round-trip, no hand-checked hsv
];
for (const { rgb, hsv } of cases) {
  const rgbArr = new Float32Array(rgb);
  const gotHsv = rgbToHsv(rgbArr);
  if (hsv) {
    for (let i = 0; i < 3; i++) {
      if (!approxEqual(gotHsv[i], hsv[i], 0.5)) {
        throw new Error(`rgbToHsv(${rgb}) = ${Array.from(gotHsv)}, expected ~${hsv}`);
      }
    }
  }
  const roundTrip = hsvToRgb(gotHsv);
  for (let i = 0; i < 3; i++) {
    if (!approxEqual(roundTrip[i], rgb[i])) {
      throw new Error(`round trip failed for ${rgb}: got ${Array.from(roundTrip)}`);
    }
  }
}

// luminance of pure gray equals the gray value
const gray = luminance(new Float32Array([0.5, 0.5, 0.5]));
if (!approxEqual(gray[0], 0.5)) throw new Error(`luminance(gray) = ${gray[0]}`);

// blur: flat field stays flat, energy (mean) preserved on a random field
const flat = new Float32Array(25).fill(0.7);
const blurredFlat = gaussianBlur(flat, 5, 5, 1.5);
for (const v of blurredFlat) if (!approxEqual(v, 0.7)) throw new Error(`blur distorted flat field: ${v}`);

const noise = Float32Array.from({ length: 64 * 64 }, () => Math.random());
const blurredNoise = gaussianBlur(noise, 64, 64, 2.0);
const meanBefore = noise.reduce((a, b) => a + b, 0) / noise.length;
const meanAfter = blurredNoise.reduce((a, b) => a + b, 0) / blurredNoise.length;
if (!approxEqual(meanBefore, meanAfter, 0.05)) throw new Error(`blur shifted mean: ${meanBefore} -> ${meanAfter}`);

console.log("engine self-check passed");
