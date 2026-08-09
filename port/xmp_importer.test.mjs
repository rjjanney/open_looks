// Pixel-... well, byte-level check of xmp_importer.js against ground truth
// computed by the real scripts/xmp_importer.py, both on the real .xmp
// fixtures already in Source/LR_EXPORT_AND_LOOKS/ and on synthetic cases
// covering the tone-curve/warning paths those real files don't exercise.
// Regenerate xmp_fixtures.json with `python port/gen_xmp_fixtures.py`
// (any Python -- no cv2/numpy needed here) after changing xmp_importer.js
// or .py.
//
// xmp_importer.js expects a global DOMParser (as it would get for free in
// a real browser) -- @xmldom/xmldom supplies a real namespace-aware XML
// DOMParser for Node. (linkedom, tried first, doesn't implement
// getElementsByTagNameNS/namespaceURI correctly for XML -- see git
// history if picking this back up.)
//
// Run with: node --test port/xmp_importer.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { DOMParser } from "@xmldom/xmldom";

globalThis.DOMParser = DOMParser;

const { parseXmpBytes, loadXmpFiles, loadXmpZipBytes } = await import("./xmp_importer.js");

const here = dirname(fileURLToPath(import.meta.url));
const fixtures = JSON.parse(readFileSync(join(here, "xmp_fixtures.json"), "utf-8"));

// A minimal browser File-like stand-in (loadXmpFile only needs .name and
// async .text()) so loadXmpFiles/loadXmpFile can run outside a browser.
class FakeFile {
  constructor(name, text) {
    this.name = name;
    this._text = text;
  }
  async text() {
    return this._text;
  }
  async arrayBuffer() {
    return new TextEncoder().encode(this._text).buffer;
  }
}

test("parseXmpBytes matches xmp_importer.py on every real .xmp fixture", () => {
  for (const { filename, text, expected } of fixtures.realFiles) {
    const stem = filename.replace(/\.[^.]+$/, "");
    const got = parseXmpBytes(text, stem);
    assert.deepEqual(got, expected, `mismatch on ${filename}`);
  }
});

test("parseXmpBytes matches xmp_importer.py on synthetic tone-curve/warning cases", () => {
  for (const { name, text, expected } of fixtures.synthetic) {
    const got = parseXmpBytes(text, name);
    assert.deepEqual(got, expected, `mismatch on synthetic case "${name}"`);
  }
});

test("loadXmpFiles skips non-.xmp files and files that fail to parse", async () => {
  // preset_name comes from the filename's stem, not anything inside the
  // XML -- name the fake files after the fixture cases so the expected
  // recipe (which already has preset_name: "tone_curve") lines up exactly.
  const files = [
    new FakeFile(`${fixtures.synthetic[0].name}.xmp`, fixtures.synthetic[0].text),
    new FakeFile("readme.txt", "not xml at all"),
    new FakeFile("Broken.xmp", "<not><valid"),
  ];
  const presets = await loadXmpFiles(files);
  assert.deepEqual(Object.keys(presets), [fixtures.synthetic[0].name]);
  assert.deepEqual(presets[fixtures.synthetic[0].name], fixtures.synthetic[0].expected);
});

test("loadXmpZipBytes parses .xmp entries inside a zip, ignores everything else", async () => {
  const { zipSync, strToU8 } = await import("fflate");
  const [caseA, caseB] = fixtures.synthetic;
  const zipped = zipSync({
    [`Pack/${caseA.name}.xmp`]: strToU8(caseA.text),
    [`Pack/${caseB.name}.xmp`]: strToU8(caseB.text),
    "Pack/readme.txt": strToU8("not a preset"),
  });
  const presets = loadXmpZipBytes(zipped);
  assert.deepEqual(new Set(Object.keys(presets)), new Set([caseA.name, caseB.name]));
  assert.deepEqual(presets[caseA.name], caseA.expected);
  assert.deepEqual(presets[caseB.name], caseB.expected);
});

test("parseXmpBytes throws on malformed XML", () => {
  assert.throws(() => parseXmpBytes("<not><valid", "broken"));
});

test("parseXmpBytes throws when there's no rdf:Description", () => {
  assert.throws(() => parseXmpBytes("<root/>", "empty"), /no rdf:Description/);
});
