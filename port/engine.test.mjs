// Pixel-level check of the JS port against ground truth computed by the real
// scripts/develop_engine.py (cv2-backed). Regenerate fixtures.json with
// `python port/gen_fixtures.py` (Python 3.10 -- needs cv2) after changing
// rgb_to_hsv/hsv_to_rgb/gaussian_blur on either side.
//
// Run with: node --test port/engine.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  rgbToHsv,
  hsvToRgb,
  gaussianBlur,
  parametricCurveLut,
  pointCurveLut,
  applyBasicTone,
  applyGrayscaleMixer,
  applyHslBands,
  applySaturationVibrance,
  applySplitToning,
  applyVignette,
  applySharpen,
  applyRecipe,
} from "./engine.js";

const here = dirname(fileURLToPath(import.meta.url));
const fixtures = JSON.parse(readFileSync(join(here, "fixtures.json"), "utf-8"));

function maxAbsDiff(a, b) {
  let max = 0;
  for (let i = 0; i < a.length; i++) max = Math.max(max, Math.abs(a[i] - b[i]));
  return max;
}

test("rgbToHsv matches cv2.cvtColor(COLOR_RGB2HSV)", () => {
  const rgb = new Float32Array(fixtures.rgbSamples.flat());
  const got = rgbToHsv(rgb);
  const expected = new Float32Array(fixtures.hsvExpected.flat());
  // hue is degrees (0-360), sat/value are 0-1 -- a shared tolerance in raw
  // units would be meaningless, so check each channel separately.
  for (let i = 0; i < fixtures.rgbSamples.length; i++) {
    const [h, s, v] = [got[i * 3], got[i * 3 + 1], got[i * 3 + 2]];
    const [eh, es, ev] = [expected[i * 3], expected[i * 3 + 1], expected[i * 3 + 2]];
    assert.ok(Math.abs(s - es) < 1e-3, `sample ${i} sat: got ${s}, expected ${es}`);
    assert.ok(Math.abs(v - ev) < 1e-3, `sample ${i} val: got ${v}, expected ${ev}`);
    // hue is meaningless at s==0 (gray) -- cv2 and our port can both emit
    // any value there without disagreeing about the actual color.
    if (es > 1e-6) {
      const hueDiff = Math.min(Math.abs(h - eh), 360 - Math.abs(h - eh));
      assert.ok(hueDiff < 1, `sample ${i} hue: got ${h}, expected ${eh}`);
    }
  }
  void maxAbsDiff; // kept for ad-hoc debugging
});

test("rgbToHsv -> hsvToRgb round trip matches cv2's own round trip", () => {
  const rgb = new Float32Array(fixtures.rgbSamples.flat());
  const got = hsvToRgb(rgbToHsv(rgb));
  const expected = new Float32Array(fixtures.roundtripExpected.flat());
  assert.ok(maxAbsDiff(got, expected) < 1e-3, `max diff ${maxAbsDiff(got, expected)}`);
});

test("gaussianBlur leaves a flat field flat, matching cv2", () => {
  const { input, width, height, sigma, expected } = fixtures.blur[0];
  const got = gaussianBlur(new Float32Array(input), width, height, sigma);
  const diff = maxAbsDiff(got, new Float32Array(expected));
  assert.ok(diff < 1e-4, `max diff ${diff}`);
});

test("gaussianBlur on noise is within tolerance of cv2.GaussianBlur", () => {
  const { input, width, height, sigma, expected } = fixtures.blur[1];
  const got = gaussianBlur(new Float32Array(input), width, height, sigma);
  const diff = maxAbsDiff(got, new Float32Array(expected));
  // Measured max diff against cv2 on this fixture is ~0.00024 (input range
  // 0..1) -- hand-rolled kernel sizing/reflect padding isn't bit-identical
  // to cv2's, but close enough that opencv.js buys nothing here. 0.01 is a
  // 40x margin over the measured gap, not an arbitrary guess -- if a future
  // change pushes past it, that's the signal to revisit (see the ponytail:
  // comment on gaussianBlur in engine.js).
  assert.ok(diff < 0.01, `max diff ${diff} (input range is 0..1)`);
});

test("parametricCurveLut matches develop_engine.py", () => {
  for (const { recipe, expected } of fixtures.parametricCurveLut) {
    const got = parametricCurveLut(recipe);
    const diff = maxAbsDiff(got, new Float32Array(expected));
    assert.ok(diff < 1e-4, `recipe ${JSON.stringify(recipe)}: max diff ${diff}`);
  }
});

test("pointCurveLut matches develop_engine.py", () => {
  for (const { points, expected } of fixtures.pointCurveLut) {
    const got = pointCurveLut(points);
    const diff = maxAbsDiff(got, new Float32Array(expected));
    assert.ok(diff < 1e-4, `points ${JSON.stringify(points)}: max diff ${diff}`);
  }
});

test("applyBasicTone matches apply_basic_tone", () => {
  for (const { input, width, height, recipe, expected } of fixtures.applyBasicTone) {
    const got = applyBasicTone(new Float32Array(input), width, height, recipe);
    const diff = maxAbsDiff(got, new Float32Array(expected));
    // Measured max diff across all cases is ~0.001 (Clarity's radius=25
    // blur is the biggest contributor) -- 2x margin over that.
    assert.ok(diff < 2e-3, `recipe ${JSON.stringify(recipe)}: max diff ${diff}`);
  }
});

test("applyGrayscaleMixer matches apply_grayscale_mixer", () => {
  for (const { input, recipe, expected } of fixtures.applyGrayscaleMixer) {
    const got = applyGrayscaleMixer(new Float32Array(input), recipe);
    const diff = maxAbsDiff(got, new Float32Array(expected));
    assert.ok(diff < 1e-3, `recipe ${JSON.stringify(recipe)}: max diff ${diff}`);
  }
});

test("applyHslBands matches apply_hsl_bands", () => {
  for (const { input, recipe, expected } of fixtures.applyHslBands) {
    const got = applyHslBands(new Float32Array(input), recipe);
    const diff = maxAbsDiff(got, new Float32Array(expected));
    assert.ok(diff < 1e-3, `recipe ${JSON.stringify(recipe)}: max diff ${diff}`);
  }
});

test("applySaturationVibrance matches apply_saturation_vibrance", () => {
  for (const { input, recipe, expected } of fixtures.applySaturationVibrance) {
    const got = applySaturationVibrance(new Float32Array(input), recipe);
    const diff = maxAbsDiff(got, new Float32Array(expected));
    assert.ok(diff < 1e-3, `recipe ${JSON.stringify(recipe)}: max diff ${diff}`);
  }
});

test("applySplitToning matches apply_split_toning", () => {
  for (const { input, recipe, expected } of fixtures.applySplitToning) {
    const got = applySplitToning(new Float32Array(input), recipe);
    const diff = maxAbsDiff(got, new Float32Array(expected));
    assert.ok(diff < 1e-3, `recipe ${JSON.stringify(recipe)}: max diff ${diff}`);
  }
});

test("applyVignette matches apply_vignette", () => {
  for (const { input, width, height, recipe, expected } of fixtures.applyVignette) {
    const got = applyVignette(new Float32Array(input), width, height, recipe);
    const diff = maxAbsDiff(got, new Float32Array(expected));
    assert.ok(diff < 1e-3, `recipe ${JSON.stringify(recipe)}: max diff ${diff}`);
  }
});

test("applySharpen is within tolerance of PIL's UnsharpMask", () => {
  for (const { input, width, height, recipe, expected } of fixtures.applySharpen) {
    const got = applySharpen(new Float32Array(input), width, height, recipe);
    const diff = maxAbsDiff(got, new Float32Array(expected));
    // PIL's UnsharpMask uses its own internal blur, not cv2 -- the other
    // flagged numeric-risk spot. Measured max diff ~0.0052 on a 0..1 range
    // (edge_image fixture, sharpness up to 80); 0.02 is a ~4x margin over
    // that, not a guess.
    assert.ok(diff < 0.02, `recipe ${JSON.stringify(recipe)}: max diff ${diff} (0..1 range)`);
  }
});

test("applyRecipe (full pipeline) matches apply_recipe end to end", () => {
  for (const { input, width, height, recipe, expected } of fixtures.applyRecipe) {
    const got = applyRecipe(new Float32Array(input), width, height, recipe, 1);
    const diff = maxAbsDiff(got, new Float32Array(expected));
    // Measured max diff ~0.0213 (dominated by the same sharpen/clarity
    // blur gaps compounding, one recipe includes Sharpness). ~2x margin --
    // this is the one check that would catch an orchestration/ordering
    // bug a passing per-stage test wouldn't.
    assert.ok(diff < 0.04, `recipe ${JSON.stringify(recipe)}: max diff ${diff} (0..1 range)`);
  }
});
