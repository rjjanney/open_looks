// Web port of app/web/app.js -- same state machine, event wiring, and
// render functions (see docs/cross-platform-port.md's UI-reuse
// assessment: that shape was already fine, only the bodies of the
// functions that called window.pywebview.api.* needed new
// implementations). Deliberately a SEPARATE file, not an edit to
// app/web/app.js -- that one is the real desktop app's frontend, still
// shipping, and must not be touched by this prototype.
//
// ponytail: applyToFolder() processes photos one at a time on the main
// thread (applyRecipe's per-photo work is synchronous) -- a big folder
// will visibly freeze the UI for the duration. Upgrade path: move
// applyRecipe into a Web Worker if that turns out to matter in practice;
// not worth the complexity speculatively.
"use strict";

import { applyRecipe } from "./engine.js";
import { imageDataToRgb, rgbToImageData } from "./canvas_glue.js";
import { opfsStorage } from "./opfs_storage.js";
import * as registry from "./registry.js";
import { loadBundledPresets } from "./bundled_presets.js";
import { FUJI_RECIPES } from "./fuji_recipes.js";
import { CAPTIONS } from "./look_captions.js";
import { downloadResult, downloadResultsAsZip } from "./export_glue.js";

const PREVIEW_WIDTH = 448; // matches app/api.py's own PREVIEW_WIDTH
const PREVIEW_QUALITY = 0.72;
const THUMB_WIDTH = 220;
const THUMB_QUALITY = 0.65;
const IMAGE_EXTS = [".jpg", ".jpeg", ".png"];

// Deterministic per-filename seed so a photo's grain looks the same in
// the preview grid and the full-res download. Doesn't need to match
// Python's CRC32-based grain_seed_for() -- engine.js's grain already
// doesn't match numpy's RNG (see the ponytail: comment on applyGrain in
// engine.js), only needs to be stable within this app.
function grainSeedFor(filename) {
  let hash = 0x811c9dc5;
  for (let i = 0; i < filename.length; i++) {
    hash ^= filename.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

let currentFiles = new Map(); // filename -> File
let rotations = new Map(); // filename -> degrees (0/90/180/270), missing = 0
let bundledPresets = {};
let builtinNames = new Set();
let activeRegistry = {}; // active (non-hidden) looks, name -> recipe
let activePhoto = null;
let selectedLook = null;
let previewsForActivePhoto = null;
let previewCache = new Map(); // filename -> {lookName: dataURI}
let manageLookMeta = [];
let selectedManageLook = null;

const el = {
  folderPath: document.getElementById("folderPath"),
  chooseFolderBtn: document.getElementById("chooseFolderBtn"),
  folderInput: document.getElementById("folderInput"),
  choosePhotosBtn: document.getElementById("choosePhotosBtn"),
  photosInput: document.getElementById("photosInput"),
  filmstrip: document.getElementById("filmstrip"),
  rotateLeftBtn: document.getElementById("rotateLeftBtn"),
  rotate180Btn: document.getElementById("rotate180Btn"),
  rotateRightBtn: document.getElementById("rotateRightBtn"),
  mainPreview: document.getElementById("mainPreview"),
  mainPreviewHint: document.getElementById("mainPreviewHint"),
  lookGrid: document.getElementById("lookGrid"),
  lookGridStatus: document.getElementById("lookGridStatus"),
  lookGridStatusText: document.getElementById("lookGridStatusText"),
  selectedLookLabel: document.getElementById("selectedLookLabel"),
  actionStatus: document.getElementById("actionStatus"),
  applyPhotoBtn: document.getElementById("applyPhotoBtn"),
  applyFolderBtn: document.getElementById("applyFolderBtn"),
  importLookBtn: document.getElementById("importLookBtn"),
  importInput: document.getElementById("importInput"),
  manageLooksBtn: document.getElementById("manageLooksBtn"),
  manageModal: document.getElementById("manageModal"),
  manageModalClose: document.getElementById("manageModalClose"),
  manageLookList: document.getElementById("manageLookList"),
};

function setActionStatus(text, isError) {
  el.actionStatus.textContent = text || "";
  el.actionStatus.style.color = isError ? "var(--danger)" : "var(--text-dim)";
}

function showMainPreview(uri) {
  el.mainPreview.src = uri;
  el.mainPreview.hidden = false;
  el.mainPreviewHint.hidden = true;
}

async function reloadRegistry() {
  activeRegistry = await registry.buildRegistry(opfsStorage, bundledPresets);
  previewCache.clear();
}

// -- canvas helpers -------------------------------------------------------

// Draws `file` into a canvas at up to maxWidth (no upscaling), rotated by
// rotationDeg (0/90/180/270, clockwise), and returns both the canvas and
// its ImageData, since callers need one or the other (or both --
// applyToPhoto/applyToFolder need the pixels, not a data URI). A 90/270
// rotation swaps width and height, so maxWidth caps the POST-rotation
// width, matching what the user actually sees.
async function fileToCanvas(file, maxWidth, rotationDeg = 0) {
  const bitmap = await createImageBitmap(file);
  const rotation = ((rotationDeg % 360) + 360) % 360;
  const swapped = rotation === 90 || rotation === 270;

  const rotatedW = swapped ? bitmap.height : bitmap.width;
  const rotatedH = swapped ? bitmap.width : bitmap.height;
  const scale = maxWidth ? Math.min(1, maxWidth / rotatedW) : 1;
  const w = Math.round(rotatedW * scale);
  const h = Math.round(rotatedH * scale);

  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  ctx.translate(w / 2, h / 2);
  ctx.rotate((rotation * Math.PI) / 180);
  // Draw at the PRE-rotation (scaled) dimensions -- the rotate() above is
  // what actually places it correctly into the (possibly swapped) canvas.
  const drawW = swapped ? h : w;
  const drawH = swapped ? w : h;
  ctx.drawImage(bitmap, -drawW / 2, -drawH / 2, drawW, drawH);

  return { canvas, imageData: ctx.getImageData(0, 0, w, h) };
}

async function fileToDataUri(file, maxWidth, quality, rotationDeg = 0) {
  const { canvas } = await fileToCanvas(file, maxWidth, rotationDeg);
  return canvas.toDataURL("image/jpeg", quality);
}

function renderRecipeToCanvas(srcImageData, recipe, seed) {
  const { rgb, alpha, width, height } = imageDataToRgb(srcImageData);
  const outRgb = applyRecipe(rgb, width, height, recipe, seed);
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  canvas.getContext("2d").putImageData(rgbToImageData(outRgb, width, height, alpha), 0, 0);
  return canvas;
}

// -- folder / filmstrip ----------------------------------------------------

// Shared by both pickers below -- replaces the whole working set (not an
// add-to-existing-set merge), same as the old folder-only behavior, just
// now reachable two ways.
async function setCurrentFiles(files) {
  currentFiles = new Map(files.map((f) => [f.name, f]));
  rotations = new Map();
  activePhoto = null;
  selectedLook = null;
  previewCache.clear();
  el.folderPath.textContent = currentFiles.size ? `${currentFiles.size} photo(s) loaded` : "No photos found";
  el.folderPath.title = "";
  updateActionBar();
  await loadPhotos();
}

async function onFolderInputChange() {
  // webkitdirectory hands back every file under the chosen folder,
  // recursively -- Python's list_photos only scans the top level
  // (p.iterdir(), not p.rglob()), so filter to direct children only for
  // the same behavior. webkitRelativePath looks like "FolderName/x.jpg"
  // for a top-level file, "FolderName/sub/x.jpg" for a nested one.
  const files = Array.from(el.folderInput.files).filter((f) => {
    const isTopLevel = (f.webkitRelativePath || "").split("/").length === 2;
    const isImage = IMAGE_EXTS.some((ext) => f.name.toLowerCase().endsWith(ext));
    return isTopLevel && isImage;
  });
  await setCurrentFiles(files);
}

async function onPhotosInputChange() {
  const files = Array.from(el.photosInput.files).filter((f) =>
    IMAGE_EXTS.some((ext) => f.name.toLowerCase().endsWith(ext))
  );
  await setCurrentFiles(files);
  el.photosInput.value = ""; // allow re-picking the same filename(s) later
}

async function loadPhotos() {
  el.filmstrip.innerHTML = "";
  if (!currentFiles.size) {
    el.filmstrip.innerHTML = '<p class="empty-hint">No .jpg/.png photos found.</p>';
    return;
  }
  for (const [name, file] of currentFiles) {
    const thumb = await fileToDataUri(file, THUMB_WIDTH, THUMB_QUALITY, rotations.get(name) || 0);
    const item = document.createElement("div");
    item.className = "filmstrip-item";
    item.dataset.name = name;
    item.innerHTML = `<img src="${thumb}" alt="${name}" loading="lazy"><span class="fname">${name}</span>`;
    item.addEventListener("click", () => selectPhoto(name));
    el.filmstrip.appendChild(item);
  }
}

async function refreshFilmstripThumbnail(filename) {
  const file = currentFiles.get(filename);
  if (!file) return;
  const thumb = await fileToDataUri(file, THUMB_WIDTH, THUMB_QUALITY, rotations.get(filename) || 0);
  for (const item of document.querySelectorAll(".filmstrip-item")) {
    if (item.dataset.name === filename) {
      item.querySelector("img").src = thumb;
      break;
    }
  }
}

// deltaDeg: -90/180/+90, applied cumulatively to whatever rotation the
// active photo already has (so -90 then 180 lands on +90 total, etc.) --
// matches how rotate buttons behave in real photo tools.
async function rotateActivePhoto(deltaDeg) {
  if (!activePhoto) return;
  const current = rotations.get(activePhoto) || 0;
  rotations.set(activePhoto, (((current + deltaDeg) % 360) + 360) % 360);
  previewCache.delete(activePhoto);
  await refreshFilmstripThumbnail(activePhoto);
  await selectPhoto(activePhoto);
}

// -- photo selection / preview rendering --------------------------------

async function selectPhoto(filename) {
  activePhoto = filename;
  selectedLook = null;
  previewsForActivePhoto = null;
  updateActionBar();

  document.querySelectorAll(".filmstrip-item").forEach((n) => {
    n.classList.toggle("active", n.dataset.name === filename);
  });

  el.lookGrid.innerHTML = "";
  el.lookGridStatusText.textContent = "Rendering previews…";
  el.lookGridStatus.hidden = false;

  try {
    previewsForActivePhoto = await renderPreviews(filename);
    showMainPreview(previewsForActivePhoto["Original"]);
    renderLookGrid();
  } catch (e) {
    el.lookGrid.innerHTML = `<p class="empty-hint">${e.message || e}</p>`;
  } finally {
    el.lookGridStatus.hidden = true;
  }
}

async function renderPreviews(filename) {
  if (previewCache.has(filename)) return previewCache.get(filename);

  const file = currentFiles.get(filename);
  const { canvas, imageData } = await fileToCanvas(file, PREVIEW_WIDTH, rotations.get(filename) || 0);
  const seed = grainSeedFor(filename);

  const previews = { Original: canvas.toDataURL("image/jpeg", PREVIEW_QUALITY) };
  for (const [lookName, recipe] of Object.entries(activeRegistry)) {
    const outCanvas = renderRecipeToCanvas(imageData, recipe, seed);
    previews[lookName] = outCanvas.toDataURL("image/jpeg", PREVIEW_QUALITY);
    // Confirmed by testing: rendering a full look grid (a dozen-plus
    // looks) back-to-back with zero yield points blocks the main thread
    // long enough that the tab visibly stops responding -- this yield
    // doesn't reduce total render time, but lets the spinner animate and
    // keeps the page responsive instead of looking hung.
    await new Promise((r) => setTimeout(r, 0));
  }

  previewCache.set(filename, previews);
  return previews;
}

function renderLookGrid() {
  el.lookGrid.innerHTML = "";
  const tiles = [
    { name: "Original", caption: "Unedited source" },
    ...Object.keys(activeRegistry).map((name) => ({ name, caption: CAPTIONS[name] || "" })),
  ];
  for (const look of tiles) {
    const uri = previewsForActivePhoto[look.name];
    if (!uri) continue;
    const tile = document.createElement("figure");
    tile.className = "look-tile";
    tile.dataset.name = look.name;
    tile.innerHTML = `
      <img src="${uri}" alt="${look.name}">
      <figcaption>
        <span class="look-name">${look.name}</span>
        <span class="look-caption">${look.caption || ""}</span>
      </figcaption>`;
    tile.addEventListener("click", () => selectLook(look.name, uri));
    el.lookGrid.appendChild(tile);
  }
}

function selectLook(name, uri) {
  selectedLook = name;
  showMainPreview(uri);
  document.querySelectorAll(".look-tile").forEach((n) => {
    n.classList.toggle("selected", n.dataset.name === name);
  });
  updateActionBar();
}

function updateActionBar() {
  const applicable = selectedLook && selectedLook !== "Original";
  el.selectedLookLabel.textContent = selectedLook ? selectedLook : "No look selected";
  el.applyPhotoBtn.disabled = !applicable;
  el.applyFolderBtn.disabled = !applicable;
  el.rotateLeftBtn.disabled = !activePhoto;
  el.rotate180Btn.disabled = !activePhoto;
  el.rotateRightBtn.disabled = !activePhoto;
  setActionStatus("");
}

// -- apply -----------------------------------------------------------------

async function applyToPhoto() {
  if (!selectedLook || !activePhoto) return;
  el.applyPhotoBtn.disabled = true;
  setActionStatus("Rendering full-resolution photo…");
  try {
    const t0 = performance.now();
    const file = currentFiles.get(activePhoto);
    const { imageData } = await fileToCanvas(file, null, rotations.get(activePhoto) || 0); // full res
    const outCanvas = renderRecipeToCanvas(imageData, activeRegistry[selectedLook], grainSeedFor(activePhoto));
    await downloadResult(outCanvas, activePhoto, { quality: 0.92 });
    setActionStatus(`Downloaded in ${((performance.now() - t0) / 1000).toFixed(1)}s`);
  } catch (e) {
    setActionStatus(e.message || "Failed", true);
  } finally {
    el.applyPhotoBtn.disabled = false;
  }
}

async function applyToFolder() {
  if (!selectedLook) return;
  el.applyFolderBtn.disabled = true;
  setActionStatus(`Applying "${selectedLook}" to ${currentFiles.size} photo(s)… this may take a while`);
  try {
    const t0 = performance.now();
    const recipe = activeRegistry[selectedLook];
    const entries = [];
    for (const [filename, file] of currentFiles) {
      const { imageData } = await fileToCanvas(file, null, rotations.get(filename) || 0);
      entries.push({ filename, canvas: renderRecipeToCanvas(imageData, recipe, grainSeedFor(filename)) });
    }
    await downloadResultsAsZip(entries, `${registry.safeName(selectedLook)}.zip`, { quality: 0.92 });
    setActionStatus(`${entries.length} photos in ${((performance.now() - t0) / 1000).toFixed(1)}s`);
  } catch (e) {
    setActionStatus(e.message || "Failed", true);
  } finally {
    el.applyFolderBtn.disabled = false;
  }
}

// -- keyboard navigation ------------------------------------------------

function stepLook(delta) {
  const tiles = Array.from(document.querySelectorAll(".look-tile"));
  if (!tiles.length) return;
  const idx = tiles.findIndex((t) => t.dataset.name === selectedLook);
  const next = tiles[idx === -1 ? 0 : (idx + delta + tiles.length) % tiles.length];
  const img = next.querySelector("img");
  selectLook(next.dataset.name, img.src);
  next.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function onKeyDown(e) {
  if (!el.manageModal.hidden) {
    if (e.key === "Escape") {
      closeManageModal();
      return;
    }
    if (!selectedManageLook) return;
    if (e.key === "ArrowUp") {
      e.preventDefault();
      moveSelectedManageLook(-1);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      moveSelectedManageLook(1);
    }
    return;
  }

  if (!selectedLook) return;
  if (e.key === "ArrowRight") {
    e.preventDefault();
    stepLook(1);
  } else if (e.key === "ArrowLeft") {
    e.preventDefault();
    stepLook(-1);
  }
}

// -- import / manage looks -----------------------------------------------

async function onImportInputChange() {
  const files = Array.from(el.importInput.files);
  if (!files.length) return;

  el.importLookBtn.disabled = true;
  const imported = [];
  const failed = [];
  const warnings = {};
  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    setActionStatus(`Importing ${i + 1}/${files.length}…`);
    try {
      const found = await registry.importLook(file);
      for (const [name, recipe] of Object.entries(found)) {
        await registry.saveImportedLook(opfsStorage, name, recipe, file);
        imported.push(name);
        if (recipe._import_warnings) warnings[name] = recipe._import_warnings;
      }
    } catch (e) {
      failed.push(`${file.name} (${e.message || "failed"})`);
    }
  }
  el.importLookBtn.disabled = false;
  el.importInput.value = ""; // allow re-picking the same filename later

  await reloadRegistry();
  if (imported.length) {
    const failSuffix = failed.length ? ` -- ${failed.length} failed: ${failed.join(", ")}` : "";
    const warnNames = Object.keys(warnings);
    const warnSuffix = warnNames.length
      ? ` -- warnings: ${warnNames.map((n) => `${n} (${warnings[n].join("; ")})`).join(" | ")}`
      : "";
    setActionStatus(`Imported: ${imported.join(", ")}${failSuffix}${warnSuffix}`, failed.length > 0);
  } else {
    setActionStatus(failed.join(", ") || "Import failed", true);
  }

  if (activePhoto) await selectPhoto(activePhoto);
}

async function refreshManageLookMeta() {
  const all = await registry.buildRegistryIncludingHidden(opfsStorage, bundledPresets);
  const hidden = await registry.loadHidden(opfsStorage);
  const visible = [], hiddenEntries = [];
  for (const name of Object.keys(all)) {
    const entry = { name, caption: CAPTIONS[name] || "", user_imported: !builtinNames.has(name), hidden: hidden.has(name) };
    (entry.hidden ? hiddenEntries : visible).push(entry);
  }
  manageLookMeta = [...visible, ...hiddenEntries];
}

function renderManageList() {
  el.manageLookList.innerHTML = "";
  for (const look of manageLookMeta) {
    const item = document.createElement("li");
    item.className = "manage-list-item";
    if (look.hidden) item.classList.add("is-hidden");
    if (look.name === selectedManageLook) item.classList.add("selected");

    const badgeClass = look.user_imported ? "imported" : "builtin";
    const badgeText = look.user_imported ? "Imported" : "Built-in";

    let actionBtn;
    if (look.hidden) {
      actionBtn = '<button class="manage-list-unhide">Unhide</button>';
    } else {
      const label = look.user_imported ? "Delete" : "Hide";
      actionBtn = `<button class="manage-list-delete">${label}</button>`;
    }

    item.innerHTML = `
      <span class="manage-list-name">${look.name}</span>
      <span class="manage-list-badge ${badgeClass}">${badgeText}</span>
      ${actionBtn}`;

    if (look.hidden) {
      item.querySelector(".manage-list-unhide").addEventListener("click", () => unhideLookClick(look.name));
    } else {
      item.querySelector(".manage-list-delete").addEventListener("click", (e) => {
        e.stopPropagation();
        removeLook(look.name);
      });
      item.addEventListener("click", () => {
        selectedManageLook = selectedManageLook === look.name ? null : look.name;
        renderManageList();
      });
    }
    el.manageLookList.appendChild(item);
  }
}

async function removeLook(name) {
  try {
    if (builtinNames.has(name)) {
      await registry.hideLook(opfsStorage, name);
    } else {
      const all = await registry.buildRegistryIncludingHidden(opfsStorage, bundledPresets);
      const removed = await registry.deleteImportedLook(opfsStorage, name, all[name]);
      if (!removed) {
        setActionStatus(`couldn't find a file for "${name}"`, true);
        return;
      }
    }
  } catch (e) {
    setActionStatus(e.message || "Remove failed", true);
    return;
  }
  if (selectedManageLook === name) selectedManageLook = null;
  await reloadRegistry();
  await refreshManageLookMeta();
  renderManageList();
  setActionStatus(`Removed: ${name}`);
  if (activePhoto) await selectPhoto(activePhoto);
}

async function unhideLookClick(name) {
  await registry.unhideLook(opfsStorage, name);
  await reloadRegistry();
  await refreshManageLookMeta();
  renderManageList();
  setActionStatus(`Unhidden: ${name}`);
  if (activePhoto) await selectPhoto(activePhoto);
}

async function moveSelectedManageLook(direction) {
  const order = manageLookMeta.filter((l) => !l.hidden).map((l) => l.name);
  const idx = order.indexOf(selectedManageLook);
  const target = idx + direction;
  if (idx === -1 || target < 0 || target >= order.length) return;
  [order[idx], order[target]] = [order[target], order[idx]];

  await registry.saveOrder(opfsStorage, order);
  await reloadRegistry();
  await refreshManageLookMeta();
  renderManageList();
  if (activePhoto) await selectPhoto(activePhoto);
}

function openManageModal() {
  selectedManageLook = null;
  refreshManageLookMeta().then(renderManageList);
  el.manageModal.hidden = false;
}

function closeManageModal() {
  el.manageModal.hidden = true;
}

// -- init ------------------------------------------------------------

async function init() {
  el.chooseFolderBtn.addEventListener("click", () => el.folderInput.click());
  el.folderInput.addEventListener("change", onFolderInputChange);
  el.choosePhotosBtn.addEventListener("click", () => el.photosInput.click());
  el.photosInput.addEventListener("change", onPhotosInputChange);
  el.rotateLeftBtn.addEventListener("click", () => rotateActivePhoto(-90));
  el.rotate180Btn.addEventListener("click", () => rotateActivePhoto(180));
  el.rotateRightBtn.addEventListener("click", () => rotateActivePhoto(90));
  el.applyPhotoBtn.addEventListener("click", applyToPhoto);
  el.applyFolderBtn.addEventListener("click", applyToFolder);
  el.importLookBtn.addEventListener("click", () => el.importInput.click());
  el.importInput.addEventListener("change", onImportInputChange);
  el.manageLooksBtn.addEventListener("click", openManageModal);
  el.manageModalClose.addEventListener("click", closeManageModal);
  el.manageModal.addEventListener("click", (e) => {
    if (e.target === el.manageModal) closeManageModal();
  });
  document.addEventListener("keydown", onKeyDown);

  setActionStatus("Loading looks…");
  bundledPresets = await loadBundledPresets();
  builtinNames = new Set([...Object.keys(FUJI_RECIPES), ...Object.keys(bundledPresets)]);
  await reloadRegistry();
  setActionStatus("");
}

init();
