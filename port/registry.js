// Port of scripts/registry.py -- the unified list of available looks: our
// own hand-written recipes (fuji_recipes.js), the bundled seed presets,
// plus whatever a user imports at runtime. See docs/cross-platform-port.md
// for why this module (unlike engine.js/xmp_importer.js/lut_engine.js,
// which are pure functions) needs a real storage adapter: there's no
// %APPDATA% equivalent on web/mobile.
//
// Every function here takes a `storage` object as its first argument
// (readText/writeText/readBytes/writeBytes/deleteFile/listFiles, see
// opfs_storage.js) rather than hard-coding one -- opfs_storage.js is the
// real browser backend; a Capacitor Filesystem backend would be a second
// implementation of the same shape when mobile packaging happens, and an
// in-memory fake (registry.test.mjs) is the third, which is what makes
// this module's logic testable in plain Node without OPFS.
//
// PyInstaller's sys._MEIPASS / frozen-executable path resolution and the
// legacy presets/user/ migration have no web/mobile equivalent -- omitted
// entirely, not carried over as dead code.

import { FUJI_RECIPES } from "./fuji_recipes.js";
import { parseCube } from "./lut_engine.js";
import { loadXmpFile, loadXmpZipBytes } from "./xmp_importer.js";

const HIDDEN_FILE = "hidden.json";
const ORDER_FILE = "order.json";

export async function loadHidden(storage) {
  const text = await storage.readText(HIDDEN_FILE);
  if (!text) return new Set();
  try {
    return new Set(JSON.parse(text));
  } catch {
    return new Set();
  }
}

export async function hideLook(storage, name) {
  const hidden = await loadHidden(storage);
  hidden.add(name);
  await storage.writeText(HIDDEN_FILE, JSON.stringify([...hidden].sort()));
}

export async function unhideLook(storage, name) {
  const hidden = await loadHidden(storage);
  hidden.delete(name);
  await storage.writeText(HIDDEN_FILE, JSON.stringify([...hidden].sort()));
}

export async function loadOrder(storage) {
  const text = await storage.readText(ORDER_FILE);
  if (!text) return [];
  try {
    return JSON.parse(text);
  } catch {
    return [];
  }
}

export async function saveOrder(storage, order) {
  await storage.writeText(ORDER_FILE, JSON.stringify(order));
}

// user/*.json recipes + user/luts/*.cube LUT-backed recipes -- the
// equivalent of _load_builtin_json(USER_PRESETS_DIR) plus the inline
// luts/*.cube glob in Python's _build_all().
async function loadUserPresets(storage) {
  const presets = {};

  for (const filename of await storage.listFiles("user")) {
    if (!filename.toLowerCase().endsWith(".json")) continue;
    const text = await storage.readText(`user/${filename}`);
    try {
      const recipe = JSON.parse(text);
      presets[recipe.preset_name || filename.replace(/\.json$/i, "")] = recipe;
    } catch {
      continue;
    }
  }

  for (const filename of await storage.listFiles("user/luts")) {
    if (!filename.toLowerCase().endsWith(".cube")) continue;
    const text = await storage.readText(`user/luts/${filename}`);
    try {
      const lut = parseCube(text);
      const name = lut.title || filename.replace(/\.cube$/i, "");
      presets[name] = { preset_name: name, _lut3d: lut };
    } catch {
      continue;
    }
  }

  return presets;
}

// bundledPresets: {name: recipe} for the fujixweekly-derived JSON presets.
// registry.js doesn't know how to list them itself -- there's no
// build-time manifest yet (see docs/cross-platform-port.md), so the
// caller loads them (fetch in a browser, fs.readdir in Node) and passes
// the result in, same spirit as _builtin_names()/PRESETS_DIR in api.py.
export async function buildAll(storage, bundledPresets, { applyOrder = true } = {}) {
  let registry = { ...FUJI_RECIPES, ...bundledPresets, ...(await loadUserPresets(storage)) };

  if (applyOrder) {
    const order = await loadOrder(storage);
    if (order.length) {
      const ordered = {};
      for (const name of order) {
        if (name in registry) {
          ordered[name] = registry[name];
          delete registry[name];
        }
      }
      registry = { ...ordered, ...registry }; // anything not in the stored order goes last
    }
  }

  return registry;
}

// Active looks only (hidden ones excluded) -- what actually gets rendered.
export async function buildRegistry(storage, bundledPresets) {
  const all = await buildAll(storage, bundledPresets);
  const hidden = await loadHidden(storage);
  for (const name of hidden) delete all[name];
  return all;
}

// Everything, hidden looks included -- for a Manage Looks UI.
export async function buildRegistryIncludingHidden(storage, bundledPresets) {
  return buildAll(storage, bundledPresets);
}

// -- user-facing import: one entry point regardless of file type ----------

// file: a browser File object the user picked (.xmp/.zip/.cube). Returns
// {name: recipe}. No directory case -- browsers hand back a flat FileList
// from a multi-file picker/drag-drop, not a folder to walk; loop callers
// over that and call importLook() per file instead.
export async function importLook(file) {
  const suffix = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();

  if (suffix === ".xmp") {
    const recipe = await loadXmpFile(file);
    return { [recipe.preset_name]: recipe };
  }
  if (suffix === ".zip") {
    return loadXmpZipBytes(new Uint8Array(await file.arrayBuffer()));
  }
  if (suffix === ".cube") {
    const lut = parseCube(await file.text());
    const name = lut.title || file.name.replace(/\.[^.]+$/, "");
    return { [name]: { preset_name: name, _lut3d: lut } };
  }
  throw new Error(`unrecognized preset file type: ${suffix} (${file.name})`);
}

export function safeName(name) {
  return Array.from(name)
    .map((c) => (/[a-zA-Z0-9 \-_]/.test(c) ? c : "_"))
    .join("")
    .trim();
}

// sourceFile is required for a .cube-backed look (recipe._lut3d set) --
// the original file's bytes get copied verbatim, same as Python copying
// source_path rather than re-serializing the parsed LUT table.
export async function saveImportedLook(storage, name, recipe, sourceFile) {
  if (recipe._lut3d) {
    if (!sourceFile) throw new Error("saving a .cube-backed look requires sourceFile");
    const bytes = new Uint8Array(await sourceFile.arrayBuffer());
    const path = `user/luts/${sourceFile.name}`;
    await storage.writeBytes(path, bytes);
    return path;
  }
  const path = `user/${safeName(name)}.json`;
  await storage.writeText(path, JSON.stringify(recipe, null, 2));
  return path;
}

// Actually removes a user-imported look's file(s) -- there's no bundled
// original to fall back on, unlike a built-in (see hideLook() for that
// case). Returns whether anything was found to remove.
export async function deleteImportedLook(storage, name, recipe) {
  let removed = false;

  if (await storage.deleteFile(`user/${safeName(name)}.json`)) removed = true;

  if (recipe._lut3d) {
    for (const filename of await storage.listFiles("user/luts")) {
      if (!filename.toLowerCase().endsWith(".cube")) continue;
      let candidateName;
      try {
        const lut = parseCube(await storage.readText(`user/luts/${filename}`));
        candidateName = lut.title || filename.replace(/\.cube$/i, "");
      } catch {
        continue;
      }
      if (candidateName === name) {
        await storage.deleteFile(`user/luts/${filename}`);
        removed = true;
        break;
      }
    }
  }

  return removed;
}
