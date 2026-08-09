// zipEntries is the only DOM-free part of export_glue.js -- everything
// else (canvasToBlob, downloadBlob) touches Canvas/Blob/URL/document and
// only really runs in a browser (no automated check here: triggering an
// actual file download is an explicit-permission action, not something to
// do unattended -- see preview.html for the same-spirit manual approach
// used for the other browser-only pieces).
//
// Run with: node --test port/export_glue.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { unzipSync, strFromU8 } from "fflate";
import { zipEntries } from "./export_glue.js";

test("zipEntries produces a zip unzipSync can read back byte-for-byte", () => {
  const entries = [
    { filename: "a.jpg", bytes: new Uint8Array([1, 2, 3, 4]) },
    { filename: "sub/b.txt", bytes: new TextEncoder().encode("hello") },
  ];
  const zipped = zipEntries(entries);
  const unzipped = unzipSync(zipped);

  assert.deepEqual(new Set(Object.keys(unzipped)), new Set(["a.jpg", "sub/b.txt"]));
  assert.deepEqual(unzipped["a.jpg"], entries[0].bytes);
  assert.equal(strFromU8(unzipped["sub/b.txt"]), "hello");
});

test("zipEntries on an empty list produces a valid (empty) zip", () => {
  const zipped = zipEntries([]);
  assert.deepEqual(unzipSync(zipped), {});
});
