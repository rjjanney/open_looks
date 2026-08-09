// Port of scripts/xmp_importer.py -- parses Adobe Camera Raw (crs:) .xmp
// develop presets into the same plain-dict recipe schema develop_engine.js
// consumes. See docs/cross-platform-port.md: this is the "easier than the
// engine" module (string/XML parsing, no numeric-mismatch risk) -- the
// browser's native DOMParser covers the namespace-aware attribute/element
// lookups scripts/xmp_importer.py uses xml.etree.ElementTree for.
//
// load_xmp_folder's recursive directory walk has no browser equivalent --
// loadXmpFiles() below takes a flat list of File objects instead (from a
// multi-file picker or drag-and-drop), which is what that walk fed into
// anyway.

import { unzipSync, strFromU8 } from "fflate";

export const NS = {
  x: "adobe:ns:meta/",
  rdf: "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
  crs: "http://ns.adobe.com/camera-raw-settings/1.0/",
};

const NUM_RE = /^[+-]?\d+(\.\d+)?$/;

function coerce(value) {
  if (value === "True" || value === "False") return value === "True";
  if (NUM_RE.test(value)) return value.includes(".") ? parseFloat(value) : parseInt(value, 10);
  return value;
}

// crs: fields real preset exports write on every preset with a fixed no-op
// value regardless of whether that preset actually touches the control --
// only flag one that's set away from its no-op default (see the Python
// docstring on _IGNORED_SCALAR_DEFAULTS for the ON1-pack example).
const IGNORED_SCALAR_DEFAULTS = {
  Temperature: 0,
  Tint: 0,
  ColorGradeShadowHue: 0,
  ColorGradeShadowSat: 0,
  ColorGradeShadowLum: 0,
  ColorGradeMidtoneHue: 0,
  ColorGradeMidtoneSat: 0,
  ColorGradeMidtoneLum: 0,
  ColorGradeHighlightHue: 0,
  ColorGradeHighlightSat: 0,
  ColorGradeHighlightLum: 0,
  ColorGradeGlobalHue: 0,
  ColorGradeGlobalSat: 0,
  ColorGradeGlobalLum: 0,
};

const LOCAL_ADJUSTMENT_FIELDS = new Set([
  "MaskGroupBasedCorrections",
  "PaintBasedCorrections",
  "GradientBasedCorrections",
  "CircularGradientBasedCorrections",
]);

// ElementTree's find("rdf:Seq") only matches a DIRECT child -- not
// getElementsByTagNameNS, which searches all descendants.
function directChild(el, ns, localName) {
  for (const child of el.children) {
    if (child.namespaceURI === ns && child.localName === localName) return child;
  }
  return null;
}

function hasRealPointColors(elem) {
  for (const li of elem.getElementsByTagNameNS(NS.rdf, "li")) {
    for (const rawToken of (li.textContent || "").split(",")) {
      const token = rawToken.trim();
      if (!token) continue;
      const num = Number(token);
      if (Number.isNaN(num) || num !== -1.0) return true;
    }
  }
  return false;
}

function describeUnsupported(desc) {
  const warnings = [];
  for (const [field, def] of Object.entries(IGNORED_SCALAR_DEFAULTS)) {
    const raw = desc.getAttributeNS(NS.crs, field);
    if (raw !== null && coerce(raw) !== def) {
      warnings.push(`${field} is set but not rendered (ignored)`);
    }
  }
  for (const elem of desc.getElementsByTagNameNS(NS.crs, "*")) {
    const field = elem.localName;
    if (LOCAL_ADJUSTMENT_FIELDS.has(field) && elem.getElementsByTagNameNS(NS.rdf, "li").length > 0) {
      warnings.push(`${field} (local mask/gradient adjustment) is not rendered`);
    } else if (field === "PointColors" && hasRealPointColors(elem)) {
      warnings.push("PointColors (Point Color grading) is not rendered");
    }
  }
  return warnings;
}

function parseSeqPoints(elem) {
  const points = [];
  const seq = directChild(elem, NS.rdf, "Seq");
  if (!seq) return points;
  for (const li of seq.children) {
    if (!(li.namespaceURI === NS.rdf && li.localName === "li")) continue;
    const text = (li.textContent || "").trim();
    if ((text.match(/,/g) || []).length !== 1) continue; // same guard as the Python: skip anything but a plain "x, y" pair
    const [xStr, yStr] = text.split(",");
    points.push([parseFloat(xStr.trim()), parseFloat(yStr.trim())]);
  }
  return points;
}

export function parseXmpBytes(text, name) {
  const doc = new DOMParser().parseFromString(text, "application/xml");
  if (doc.getElementsByTagName("parsererror").length > 0) {
    throw new Error(`${name}: not valid XML`);
  }
  const desc = doc.getElementsByTagNameNS(NS.rdf, "Description")[0];
  if (!desc) throw new Error(`${name}: no rdf:Description found -- not a Camera Raw .xmp preset`);

  const recipe = { preset_name: name };
  for (const attr of desc.attributes) {
    if (attr.namespaceURI === NS.crs) recipe[attr.localName] = coerce(attr.value);
  }
  for (const child of desc.children) {
    if (child.namespaceURI !== NS.crs) continue;
    const field = child.localName;
    if (directChild(child, NS.rdf, "Seq") && !(field in recipe)) {
      const points = parseSeqPoints(child);
      if (points.length) recipe[field] = points;
    }
  }

  const warnings = describeUnsupported(desc);
  if (warnings.length) recipe._import_warnings = warnings;
  return recipe;
}

function stem(filename) {
  return filename.replace(/^.*[/\\]/, "").replace(/\.[^.]+$/, "");
}

// file: a browser File/Blob (anything with async .text() and a .name).
export async function loadXmpFile(file) {
  const text = await file.text();
  return parseXmpBytes(text, stem(file.name));
}

// files: an iterable of File objects -- the multi-file-picker/drag-and-drop
// replacement for load_xmp_folder's recursive walk (see module docstring).
export async function loadXmpFiles(files) {
  const presets = {};
  for (const file of files) {
    if (!file.name.toLowerCase().endsWith(".xmp")) continue;
    try {
      const recipe = await loadXmpFile(file);
      presets[recipe.preset_name] = recipe;
    } catch {
      continue; // not actually a Camera Raw preset -- skip, not fatal
    }
  }
  return presets;
}

// zipBytes: a Uint8Array of the whole .zip file's contents.
export function loadXmpZipBytes(zipBytes) {
  const unzipped = unzipSync(zipBytes, {
    filter: (file) => file.name.toLowerCase().endsWith(".xmp"),
  });
  const presets = {};
  for (const [filename, bytes] of Object.entries(unzipped)) {
    const name = stem(filename);
    try {
      presets[name] = parseXmpBytes(strFromU8(bytes), name);
    } catch {
      continue;
    }
  }
  return presets;
}

export async function loadXmpZipFile(file) {
  return loadXmpZipBytes(new Uint8Array(await file.arrayBuffer()));
}
