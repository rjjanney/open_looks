// Tests registry.js's logic (hidden/order/merge-precedence/import
// dispatch/save/delete) against an in-memory storage fake -- OPFS itself
// (opfs_storage.js) has no Node equivalent to test against, so this
// verifies everything storage-adapter-shaped up to the adapter boundary;
// opfs_storage.js itself needs a real browser to check (see preview.html's
// own verification approach).
//
// Run with: node --test port/registry.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { DOMParser } from "@xmldom/xmldom";

globalThis.DOMParser = DOMParser;

const {
  loadHidden,
  hideLook,
  unhideLook,
  loadOrder,
  saveOrder,
  buildAll,
  buildRegistry,
  buildRegistryIncludingHidden,
  importLook,
  saveImportedLook,
  deleteImportedLook,
} = await import("./registry.js");
const { FUJI_RECIPES } = await import("./fuji_recipes.js");

function createMemoryStorage() {
  // A real filesystem (and opfs_storage.js) stores just bytes -- readText
  // and readBytes are two views of the same content, not separate tracks,
  // so a file written via writeBytes must still read back correctly via
  // readText (this is exactly what deleteImportedLook relies on for a
  // .cube-backed look: saved with writeBytes, matched later via readText).
  const files = new Map(); // path -> string | Uint8Array
  return {
    async readText(path) {
      const v = files.get(path);
      if (v === undefined) return null;
      return v instanceof Uint8Array ? new TextDecoder().decode(v) : v;
    },
    async writeText(path, text) {
      files.set(path, text);
    },
    async readBytes(path) {
      const v = files.get(path);
      if (v === undefined) return null;
      return v instanceof Uint8Array ? v : new TextEncoder().encode(v);
    },
    async writeBytes(path, bytes) {
      files.set(path, bytes);
    },
    async deleteFile(path) {
      return files.delete(path);
    },
    async listFiles(dirPath) {
      const prefix = dirPath ? `${dirPath}/` : "";
      const names = [];
      for (const key of files.keys()) {
        if (key.startsWith(prefix) && !key.slice(prefix.length).includes("/")) {
          names.push(key.slice(prefix.length));
        }
      }
      return names;
    },
    _files: files, // test-only escape hatch
  };
}

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

test("hideLook/unhideLook round trip through loadHidden", async () => {
  const storage = createMemoryStorage();
  assert.deepEqual(await loadHidden(storage), new Set());
  await hideLook(storage, "Fuji Velvia");
  await hideLook(storage, "Fuji Acros");
  assert.deepEqual(await loadHidden(storage), new Set(["Fuji Acros", "Fuji Velvia"]));
  await unhideLook(storage, "Fuji Velvia");
  assert.deepEqual(await loadHidden(storage), new Set(["Fuji Acros"]));
});

test("saveOrder round trips through loadOrder", async () => {
  const storage = createMemoryStorage();
  assert.deepEqual(await loadOrder(storage), []);
  await saveOrder(storage, ["Fuji Provia", "Fuji Velvia"]);
  assert.deepEqual(await loadOrder(storage), ["Fuji Provia", "Fuji Velvia"]);
});

test("buildAll merges FUJI_RECIPES < bundled < user, later wins on name collision", async () => {
  const storage = createMemoryStorage();
  await storage.writeText(
    "user/My Look.json",
    JSON.stringify({ preset_name: "My Look", Contrast2012: 99 })
  );
  // A user-imported look with the same name as a bundled one overrides it.
  await storage.writeText(
    "user/Overridden.json",
    JSON.stringify({ preset_name: "Bundled Thing", Contrast2012: 5 })
  );
  const bundled = { "Bundled Thing": { preset_name: "Bundled Thing", Contrast2012: 1 } };

  const all = await buildAll(storage, bundled);
  assert.equal(all["Fuji Velvia"], FUJI_RECIPES["Fuji Velvia"]);
  assert.equal(all["My Look"].Contrast2012, 99);
  assert.equal(all["Bundled Thing"].Contrast2012, 5); // user copy won
});

test("buildAll with a stored order: ordered names first, rest appended after", async () => {
  const storage = createMemoryStorage();
  await saveOrder(storage, ["Fuji Provia", "Fuji Acros"]);
  const all = await buildAll(storage, {});
  const names = Object.keys(all);
  assert.deepEqual(names.slice(0, 2), ["Fuji Provia", "Fuji Acros"]);
  assert.ok(names.includes("Fuji Velvia")); // present, just not in the ordered prefix
});

test("buildRegistry excludes hidden looks, buildRegistryIncludingHidden doesn't", async () => {
  const storage = createMemoryStorage();
  await hideLook(storage, "Fuji Acros");
  const active = await buildRegistry(storage, {});
  const all = await buildRegistryIncludingHidden(storage, {});
  assert.ok(!("Fuji Acros" in active));
  assert.ok("Fuji Acros" in all);
});

test("importLook dispatches by extension and throws on unrecognized types", async () => {
  const xmpText = `<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about="" xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/" crs:Contrast2012="20"/>
 </rdf:RDF>
</x:xmpmeta>`;
  const xmpResult = await importLook(new FakeFile("MyPreset.xmp", xmpText));
  assert.deepEqual(Object.keys(xmpResult), ["MyPreset"]);
  assert.equal(xmpResult.MyPreset.Contrast2012, 20);

  const cubeText = 'TITLE "My LUT"\nLUT_3D_SIZE 2\n' + "0 0 0\n".repeat(8);
  const cubeResult = await importLook(new FakeFile("thing.cube", cubeText));
  assert.deepEqual(Object.keys(cubeResult), ["My LUT"]);
  assert.ok(cubeResult["My LUT"]._lut3d);

  await assert.rejects(() => importLook(new FakeFile("photo.png", "")), /unrecognized preset file type/);
});

test("saveImportedLook + deleteImportedLook round trip for a JSON-backed look", async () => {
  const storage = createMemoryStorage();
  const recipe = { preset_name: "My Look!", Contrast2012: 10 };
  const path = await saveImportedLook(storage, "My Look!", recipe);
  assert.equal(path, "user/My Look_.json"); // "!" isn't in the safe-char set
  assert.equal(await storage.readText(path), JSON.stringify(recipe, null, 2));

  const removed = await deleteImportedLook(storage, "My Look!", recipe);
  assert.equal(removed, true);
  assert.equal(await storage.readText(path), null);
});

test("saveImportedLook + deleteImportedLook round trip for a .cube-backed look", async () => {
  const storage = createMemoryStorage();
  const cubeText = 'TITLE "Cube Look"\nLUT_3D_SIZE 2\n' + "0.1 0.2 0.3\n".repeat(8);
  const sourceFile = new FakeFile("cube_look.cube", cubeText);
  const found = await importLook(sourceFile);
  const [name, recipe] = Object.entries(found)[0];

  const path = await saveImportedLook(storage, name, recipe, sourceFile);
  assert.equal(path, "user/luts/cube_look.cube");
  const savedBytes = await storage.readBytes(path);
  assert.equal(new TextDecoder().decode(savedBytes), cubeText);

  const removed = await deleteImportedLook(storage, name, recipe);
  assert.equal(removed, true);
  assert.equal(await storage.readBytes(path), null);
});
