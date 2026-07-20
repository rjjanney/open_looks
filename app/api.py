"""pywebview shell + JS<->Python bridge for the open_looks preview app.

Same pattern as the private pics_apply_looks sibling project (and
SearchTool before that): a plain `Api` class holds all the logic and stays
importable/testable without pywebview installed; `webview` itself is
imported lazily inside main(), the only place that needs it.

Unlike the sibling project, output goes to Output/<safe look name>/file.jpg
(the same convention scripts/apply_look.py's CLI already uses) rather than
a flat folder with a hand-curated nickname per look -- a user can import an
arbitrary look with an arbitrary name here, so there's no fixed nickname
table to maintain.
"""
from __future__ import annotations

import base64
import io
import os
import sys
import time
from pathlib import Path

from PIL import Image

APP_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = APP_DIR.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


def _bundle_root() -> Path:
    """Base directory for *data* files (app/web/*) -- not Python modules,
    which PyInstaller's importer finds on its own. See the sibling
    project's app/api.py for the fuller explanation of sys._MEIPASS."""
    meipass = getattr(sys, "_MEIPASS", None)
    return Path(meipass) if meipass else APP_DIR.parent


from registry import (  # noqa: E402
    build_registry,
    build_registry_including_hidden,
    import_look,
    save_imported_look,
    delete_imported_look,
    hide_look,
    unhide_look as _unhide_look,
    load_hidden,
    save_order,
    PRESETS_DIR,
)
from apply_look import run_jobs, safe_dirname, grain_seed_for  # noqa: E402
from develop_engine import apply_recipe  # noqa: E402
from look_captions import CAPTIONS  # noqa: E402

PREVIEW_WIDTH = 448  # matches what the UI actually displays it at -- see
# the sibling project's app/api.py for the full reasoning.
THUMB_WIDTH = 220
PREVIEW_QUALITY = 72
THUMB_QUALITY = 65

IMAGE_EXTS = (".jpg", ".jpeg")


def _to_data_uri(img: Image.Image, width: int, quality: int) -> str:
    if img.width > width:
        h = int(img.height * (width / img.width))
        img = img.resize((width, h), Image.LANCZOS)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=quality)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def _builtin_names() -> set[str]:
    """Look names that come from presets/builtin/ or fuji_recipes.py --
    used to tell the UI which looks are safe to delete (user-imported) vs
    not (built in)."""
    from fuji_recipes import FUJI_RECIPES

    names = set(FUJI_RECIPES.keys())
    for path in (PRESETS_DIR / "fujixweekly").glob("*.json"):
        import json

        try:
            names.add(json.loads(path.read_text(encoding="utf-8")).get("preset_name", path.stem))
        except Exception:
            continue
    return names


class Api:
    """Exposed to the page as `window.pywebview.api`."""

    def __init__(self) -> None:
        self._window = None
        self._builtin_names = _builtin_names()
        self._registry: dict = {}
        self._look_order: list[str] = []
        self._reload_registry()
        # (folder, filename) -> {look_name: preview_data_uri}
        self._preview_cache: dict[tuple[str, str], dict[str, str]] = {}

    def _reload_registry(self) -> None:
        self._registry = build_registry()
        self._look_order = list(self._registry.keys())
        self._preview_cache = {}

    def set_window(self, window) -> None:
        self._window = window

    # -- browsing -----------------------------------------------------

    def list_looks(self) -> list[dict]:
        """Active (non-hidden) looks only, in display order -- what the
        preview grid renders. See list_all_looks() for the Manage Looks
        modal, which needs hidden ones too."""
        return [
            {
                "name": name,
                "caption": CAPTIONS.get(name, ""),
                "user_imported": name not in self._builtin_names,
            }
            for name in self._look_order
        ]

    def list_all_looks(self) -> list[dict]:
        """Every look including hidden ones, active looks first (in
        display order) then hidden ones -- for the Manage Looks modal."""
        full = build_registry_including_hidden()
        hidden = load_hidden()
        visible, hidden_entries = [], []
        for name in full:
            entry = {
                "name": name,
                "caption": CAPTIONS.get(name, ""),
                "user_imported": name not in self._builtin_names,
                "hidden": name in hidden,
            }
            (hidden_entries if entry["hidden"] else visible).append(entry)
        return visible + hidden_entries

    def pick_folder(self) -> dict:
        import webview

        if self._window is None:
            return {"folder": None, "error": "window not ready"}
        result = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        folder = result[0] if result else None
        return {"folder": folder}

    def list_photos(self, folder: str) -> dict:
        p = Path(folder)
        if not p.is_dir():
            return {"error": f"not a folder: {folder}"}
        names = sorted(f.name for f in p.iterdir() if f.suffix.lower() in IMAGE_EXTS)
        photos = []
        for name in names:
            try:
                img = Image.open(p / name)
                thumb = _to_data_uri(img, THUMB_WIDTH, THUMB_QUALITY)
            except Exception:
                continue
            photos.append({"name": name, "thumb": thumb})
        return {"photos": photos}

    # -- preview --------------------------------------------------------

    def render_previews(self, folder: str, filename: str) -> dict:
        key = (folder, filename)
        if key in self._preview_cache:
            return {"previews": self._preview_cache[key], "cached": True}

        path = Path(folder) / filename
        if not path.is_file():
            return {"error": f"not found: {path}"}
        try:
            source = Image.open(path)
        except Exception as e:
            return {"error": str(e)}

        if source.width > PREVIEW_WIDTH:
            h = int(source.height * (PREVIEW_WIDTH / source.width))
            small_source = source.convert("RGB").resize((PREVIEW_WIDTH, h), Image.LANCZOS)
        else:
            small_source = source.convert("RGB")

        seed = grain_seed_for(filename)
        previews: dict[str, str] = {
            "Original": _to_data_uri(small_source, PREVIEW_WIDTH, PREVIEW_QUALITY)
        }
        for look_name, recipe in self._registry.items():
            rendered = apply_recipe(small_source, recipe, grain_seed=seed)
            previews[look_name] = _to_data_uri(rendered, PREVIEW_WIDTH, PREVIEW_QUALITY)

        self._preview_cache[key] = previews
        return {"previews": previews, "cached": False}

    # -- apply ------------------------------------------------------------

    def apply_to_photo(self, folder: str, filename: str, look_name: str) -> dict:
        if look_name not in self._registry:
            return {"ok": False, "error": f"unknown look: {look_name!r}"}
        in_path = Path(folder) / filename
        if not in_path.is_file():
            return {"ok": False, "error": f"not found: {in_path}"}

        out_dir = Path(folder) / "Output" / safe_dirname(look_name)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / filename

        t0 = time.monotonic()
        img = Image.open(in_path)
        exif = img.info.get("exif")
        seed = grain_seed_for(filename)
        result = apply_recipe(img, self._registry[look_name], grain_seed=seed)
        save_kwargs = {"quality": 92}
        if exif:
            save_kwargs["exif"] = exif
        result.save(out_path, **save_kwargs)
        elapsed = time.monotonic() - t0

        return {"ok": True, "output_path": str(out_path), "elapsed": elapsed}

    def apply_to_folder(self, folder: str, look_name: str) -> dict:
        if look_name not in self._registry:
            return {"ok": False, "error": f"unknown look: {look_name!r}"}
        input_dir = Path(folder)
        photos = sorted(f for f in input_dir.iterdir() if f.suffix.lower() in IMAGE_EXTS)
        if not photos:
            return {"ok": False, "error": "no .jpg photos found in that folder"}

        out_dir = input_dir / "Output" / safe_dirname(look_name)
        out_dir.mkdir(parents=True, exist_ok=True)
        recipe = self._registry[look_name]
        jobs = [(look_name, recipe, str(p), str(out_dir / p.name), 92) for p in photos]

        workers = max(1, (os.cpu_count() or 4) // 2)
        t0 = time.monotonic()
        run_jobs(jobs, workers=workers)
        elapsed = time.monotonic() - t0

        return {"ok": True, "count": len(jobs), "elapsed": elapsed, "output_dir": str(out_dir)}

    # -- import / manage ----------------------------------------------------

    def pick_look_file(self) -> dict:
        import webview

        if self._window is None:
            return {"paths": [], "error": "window not ready"}
        result = self._window.create_file_dialog(
            webview.FileDialog.OPEN,
            allow_multiple=True,
            file_types=("Look files (*.xmp;*.cube)", "All files (*.*)"),
        )
        return {"paths": list(result) if result else []}

    def import_look_file(self, path: str) -> dict:
        try:
            found = import_look(path)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        if not found:
            return {"ok": False, "error": "nothing importable found in that file"}

        imported = []
        warnings: dict[str, list[str]] = {}
        for name, recipe in found.items():
            save_imported_look(name, recipe, source_path=path)
            imported.append(name)
            if recipe.get("_import_warnings"):
                warnings[name] = recipe["_import_warnings"]

        self._reload_registry()
        return {"ok": True, "imported": imported, "warnings": warnings}

    def remove_look(self, name: str) -> dict:
        """Remove a look from the list -- a built-in is *hidden* (the
        bundled file it came from is untouched, undo with unhide_look()
        below), a user-imported one is actually deleted (there's no
        bundled original to fall back on)."""
        if name not in self._registry:
            return {"ok": False, "error": f"unknown look: {name!r}"}

        if name in self._builtin_names:
            hide_look(name)
        else:
            removed = delete_imported_look(name, self._registry[name])
            if not removed:
                return {"ok": False, "error": f"couldn't find a file for {name!r} under presets/user/"}

        self._reload_registry()
        return {"ok": True}

    def unhide_look(self, name: str) -> dict:
        _unhide_look(name)
        self._reload_registry()
        return {"ok": True}

    def reorder_looks(self, order: list[str]) -> dict:
        save_order(order)
        self._reload_registry()
        return {"ok": True}


def main() -> None:
    import webview  # lazy: only the GUI needs this installed

    api = Api()
    web_dir = _bundle_root() / "app" / "web"
    window = webview.create_window(
        "open_looks",
        str(web_dir / "index.html"),
        js_api=api,
        width=1280,
        height=860,
        min_size=(900, 600),
    )
    api.set_window(window)
    webview.start()


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    main()
