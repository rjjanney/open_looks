(function () {
  "use strict";

  let currentFolder = null;
  let photos = [];
  let lookMeta = [];
  let activePhoto = null;
  let selectedLook = null;
  let previewsForActivePhoto = null;
  let manageLookMeta = [];       // all looks incl. hidden, for the Manage Looks modal
  let selectedManageLook = null; // click a row, then Up/Down to reorder it

  const el = {
    folderPath: document.getElementById("folderPath"),
    chooseFolderBtn: document.getElementById("chooseFolderBtn"),
    filmstrip: document.getElementById("filmstrip"),
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

  // -- folder / filmstrip ------------------------------------------------

  async function chooseFolder() {
    const res = await window.pywebview.api.pick_folder();
    if (!res || !res.folder) return;
    currentFolder = res.folder;
    el.folderPath.textContent = currentFolder;
    el.folderPath.title = currentFolder;
    await loadPhotos();
  }

  async function loadPhotos() {
    el.filmstrip.innerHTML = '<p class="empty-hint">Loading photos&hellip;</p>';
    const res = await window.pywebview.api.list_photos(currentFolder);
    if (res.error) {
      el.filmstrip.innerHTML = `<p class="empty-hint">${res.error}</p>`;
      return;
    }
    photos = res.photos;
    if (!photos.length) {
      el.filmstrip.innerHTML = '<p class="empty-hint">No .jpg photos found in this folder.</p>';
      return;
    }
    el.filmstrip.innerHTML = "";
    for (const photo of photos) {
      const item = document.createElement("div");
      item.className = "filmstrip-item";
      item.dataset.name = photo.name;
      item.innerHTML = `<img src="${photo.thumb}" alt="${photo.name}" loading="lazy"><span class="fname">${photo.name}</span>`;
      item.addEventListener("click", () => selectPhoto(photo.name));
      el.filmstrip.appendChild(item);
    }
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

    const res = await window.pywebview.api.render_previews(currentFolder, filename);
    el.lookGridStatus.hidden = true;

    if (res.error) {
      el.lookGrid.innerHTML = `<p class="empty-hint">${res.error}</p>`;
      return;
    }
    previewsForActivePhoto = res.previews;
    showMainPreview(res.previews["Original"]);
    renderLookGrid();
  }

  function renderLookGrid() {
    el.lookGrid.innerHTML = "";

    const tiles = [{ name: "Original", caption: "Unedited source" }, ...lookMeta];
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
    setActionStatus("");
  }

  // -- apply ---------------------------------------------------------------

  async function applyToPhoto() {
    if (!selectedLook || !activePhoto) return;
    el.applyPhotoBtn.disabled = true;
    setActionStatus("Applying to this photo…");
    const res = await window.pywebview.api.apply_to_photo(currentFolder, activePhoto, selectedLook);
    el.applyPhotoBtn.disabled = false;
    if (res.ok) {
      setActionStatus(`Saved in ${res.elapsed.toFixed(1)}s → ${res.output_path}`);
    } else {
      setActionStatus(res.error || "Failed", true);
    }
  }

  async function applyToFolder() {
    if (!selectedLook) return;
    el.applyFolderBtn.disabled = true;
    setActionStatus(`Applying "${selectedLook}" to the whole folder… this may take a while`);
    const res = await window.pywebview.api.apply_to_folder(currentFolder, selectedLook);
    el.applyFolderBtn.disabled = false;
    if (res.ok) {
      setActionStatus(`${res.count} photos in ${res.elapsed.toFixed(1)}s → ${res.output_dir}`);
    } else {
      setActionStatus(res.error || "Failed", true);
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

  async function refreshLookMeta() {
    lookMeta = await window.pywebview.api.list_looks();
  }

  async function importLook() {
    const picked = await window.pywebview.api.pick_look_file();
    if (!picked || !picked.paths || !picked.paths.length) return;

    el.importLookBtn.disabled = true;
    const imported = [];
    const failed = [];
    for (const path of picked.paths) {
      setActionStatus(`Importing ${imported.length + failed.length + 1}/${picked.paths.length}…`);
      const res = await window.pywebview.api.import_look_file(path);
      if (res.ok) {
        imported.push(...res.imported);
      } else {
        const base = path.split(/[\\/]/).pop();
        failed.push(`${base} (${res.error || "failed"})`);
      }
    }
    el.importLookBtn.disabled = false;

    await refreshLookMeta();
    if (imported.length) {
      const suffix = failed.length ? ` -- ${failed.length} failed: ${failed.join(", ")}` : "";
      setActionStatus(`Imported: ${imported.join(", ")}${suffix}`, failed.length > 0);
    } else {
      setActionStatus(failed.join(", ") || "Import failed", true);
    }

    // Previews are cached server-side per photo; a registry reload clears
    // that cache, so re-rendering now picks up the newly imported look(s).
    if (activePhoto) {
      previewsForActivePhoto = null;
      await selectPhoto(activePhoto);
    }
  }

  async function refreshManageLookMeta() {
    manageLookMeta = await window.pywebview.api.list_all_looks();
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
        item.querySelector(".manage-list-unhide").addEventListener("click", () => unhideLook(look.name));
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
    const res = await window.pywebview.api.remove_look(name);
    if (!res.ok) {
      setActionStatus(res.error || "Remove failed", true);
      return;
    }
    if (selectedManageLook === name) selectedManageLook = null;
    await refreshLookMeta();
    await refreshManageLookMeta();
    renderManageList();
    setActionStatus(`Removed: ${name}`);
    if (activePhoto) {
      previewsForActivePhoto = null;
      await selectPhoto(activePhoto);
    }
  }

  async function unhideLook(name) {
    const res = await window.pywebview.api.unhide_look(name);
    if (!res.ok) {
      setActionStatus(res.error || "Unhide failed", true);
      return;
    }
    await refreshLookMeta();
    await refreshManageLookMeta();
    renderManageList();
    setActionStatus(`Unhidden: ${name}`);
    if (activePhoto) {
      previewsForActivePhoto = null;
      await selectPhoto(activePhoto);
    }
  }

  async function moveSelectedManageLook(direction) {
    const order = manageLookMeta.filter((l) => !l.hidden).map((l) => l.name);
    const idx = order.indexOf(selectedManageLook);
    const target = idx + direction;
    if (idx === -1 || target < 0 || target >= order.length) return;
    [order[idx], order[target]] = [order[target], order[idx]];

    await window.pywebview.api.reorder_looks(order);
    await refreshLookMeta();
    await refreshManageLookMeta();
    renderManageList();
    if (activePhoto) renderLookGrid();
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
    el.chooseFolderBtn.addEventListener("click", chooseFolder);
    el.applyPhotoBtn.addEventListener("click", applyToPhoto);
    document.addEventListener("keydown", onKeyDown);
    el.applyFolderBtn.addEventListener("click", applyToFolder);
    el.importLookBtn.addEventListener("click", importLook);
    el.manageLooksBtn.addEventListener("click", openManageModal);
    el.manageModalClose.addEventListener("click", closeManageModal);
    el.manageModal.addEventListener("click", (e) => {
      if (e.target === el.manageModal) closeManageModal();
    });

    await refreshLookMeta();
  }

  window.addEventListener("pywebviewready", init);
})();
