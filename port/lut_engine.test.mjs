// Pixel-level check of lut_engine.js against ground truth computed by the
// real scripts/lut_engine.py. Regenerate fixtures.json with
// `python port/gen_fixtures.py` (Python 3.10 -- needs cv2) after changing
// Lut3D.apply/load_cube on either side.
//
// Run with: node --test port/lut_engine.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { Lut3D, parseCube } from "./lut_engine.js";

const here = dirname(fileURLToPath(import.meta.url));
const fixtures = JSON.parse(readFileSync(join(here, "fixtures.json"), "utf-8"));

function maxAbsDiff(a, b) {
  let max = 0;
  for (let i = 0; i < a.length; i++) max = Math.max(max, Math.abs(a[i] - b[i]));
  return max;
}

test("Lut3D.apply matches lut_engine.py's trilinear interpolation", () => {
  for (const { size, table, domainMin, domainMax, colors, expected } of fixtures.lut3dApply) {
    const lut = new Lut3D(new Float32Array(table), size, domainMin, domainMax, "test");
    const got = lut.apply(new Float32Array(colors.flat()));
    const diff = maxAbsDiff(got, new Float32Array(expected.flat()));
    // Pure math, no cross-library risk (unlike blur/sharpen) -- should be
    // near float32 precision.
    assert.ok(diff < 1e-4, `domain [${domainMin}, ${domainMax}]: max diff ${diff}`);
  }
});

test("parseCube recovers the same table load_cube does, correct axis order", () => {
  const { text, expectedSize, expectedTitle, expectedTable } = fixtures.loadCube;
  const lut = parseCube(text);
  assert.equal(lut.size, expectedSize);
  assert.equal(lut.title, expectedTitle);
  const diff = maxAbsDiff(lut.table, new Float32Array(expectedTable));
  assert.ok(diff < 1e-6, `table max diff ${diff}`);
});

test("parseCube rejects 1D LUTs, same as load_cube", () => {
  assert.throws(() => parseCube("LUT_1D_SIZE 4\n0 0 0\n1 1 1\n"), /1D .cube LUTs aren't supported/);
});

test("parseCube rejects a file with no LUT_3D_SIZE", () => {
  assert.throws(() => parseCube('TITLE "no size"\n0 0 0\n'), /no LUT_3D_SIZE/);
});

test("parseCube rejects a data-line count mismatch", () => {
  assert.throws(() => parseCube("LUT_3D_SIZE 2\n0 0 0\n1 1 1\n"), /expected 8 data lines/);
});
