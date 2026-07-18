"""The unified list of available looks: our own hand-written recipes, the
bundled seed presets (Fuji X Weekly-derived JSON), plus whatever a user
imports at runtime from a loose .xmp or .cube file. See
presets/ATTRIBUTION.md for where the bundled ones came from.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPTS_DIR.parent
PRESETS_DIR = PROJECT_ROOT / "presets" / "builtin"

sys.path.insert(0, str(SCRIPTS_DIR))

from fuji_recipes import FUJI_RECIPES  # noqa: E402
from xmp_importer import load_xmp_file, load_xmp_folder, load_xmp_zip  # noqa: E402
from lut_engine import load_cube  # noqa: E402


def _appdata_dir(app_name: str) -> Path:
    """Per-user data directory (%APPDATA%\\<app_name>\\ on Windows, falling
    back to the home directory elsewhere) -- deliberately NOT relative to
    the executable or repo. A onefile packaged build extracts to a fresh
    temp directory on every launch and deletes it on exit, so anything
    written relative to that (or to PROJECT_ROOT if it resolved there when
    frozen, matching the sibling pics_apply_looks project) would silently
    vanish the next time the app opens instead of persisting."""
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home()
    return base / app_name


USER_PRESETS_DIR = _appdata_dir("open_looks")  # your own imports -- never bundled/redistributed
HIDDEN_FILE = USER_PRESETS_DIR / "hidden.json"  # built-in looks you've removed from your view
ORDER_FILE = USER_PRESETS_DIR / "order.json"  # your preferred look order, if you've rearranged anything


def _migrate_legacy_user_dir() -> None:
    """One-time carry-over of presets/user/ from the old repo-relative
    location (before this became an AppData folder) into the new spot, so
    switching didn't strand anyone's existing hidden/order/imported-look
    state. No-op once USER_PRESETS_DIR already exists."""
    if USER_PRESETS_DIR.exists():
        return
    legacy_dir = PROJECT_ROOT / "presets" / "user"
    if not legacy_dir.is_dir():
        return
    try:
        shutil.copytree(legacy_dir, USER_PRESETS_DIR)
    except Exception:
        pass


_migrate_legacy_user_dir()


def _load_builtin_json(folder: Path) -> dict[str, dict[str, Any]]:
    presets = {}
    for path in folder.glob("*.json"):
        try:
            recipe = json.loads(path.read_text(encoding="utf-8"))
            presets[recipe.get("preset_name", path.stem)] = recipe
        except Exception:
            continue
    return presets


def load_hidden() -> set[str]:
    if not HIDDEN_FILE.is_file():
        return set()
    try:
        return set(json.loads(HIDDEN_FILE.read_text(encoding="utf-8")))
    except Exception:
        return set()


def hide_look(name: str) -> None:
    """Remove a *built-in* look from view without touching the bundled
    file it came from -- reversible with unhide_look() below. (A
    user-imported look should be actually deleted instead -- see
    delete_imported_look() -- since there's no bundled original to lose.)"""
    USER_PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    hidden = load_hidden()
    hidden.add(name)
    HIDDEN_FILE.write_text(json.dumps(sorted(hidden), indent=2), encoding="utf-8")


def unhide_look(name: str) -> None:
    hidden = load_hidden()
    hidden.discard(name)
    HIDDEN_FILE.write_text(json.dumps(sorted(hidden), indent=2), encoding="utf-8")


def load_order() -> list[str]:
    if not ORDER_FILE.is_file():
        return []
    try:
        return json.loads(ORDER_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_order(order: list[str]) -> None:
    USER_PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    ORDER_FILE.write_text(json.dumps(order, indent=2), encoding="utf-8")


def _build_all(apply_order: bool = True) -> dict[str, dict[str, Any]]:
    """Every look regardless of hidden state -- build_registry() below
    filters hidden ones out for actually rendering; build_registry_including_
    hidden() doesn't, for the Manage Looks list, which needs to show
    everything so a hidden look can be found again to unhide it."""
    registry: dict[str, dict[str, Any]] = {}
    registry.update(FUJI_RECIPES)
    registry.update(_load_builtin_json(PRESETS_DIR / "fujixweekly"))

    if USER_PRESETS_DIR.is_dir():
        registry.update(_load_builtin_json(USER_PRESETS_DIR))
        for cube_path in (USER_PRESETS_DIR / "luts").glob("*.cube"):
            try:
                lut = load_cube(cube_path)
                name = lut.title or cube_path.stem
                registry[name] = {"preset_name": name, "_lut3d": lut}
            except Exception:
                continue

    if apply_order:
        order = load_order()
        if order:
            ordered: dict[str, dict[str, Any]] = {}
            for name in order:
                if name in registry:
                    ordered[name] = registry.pop(name)
            ordered.update(registry)  # anything not in the stored order goes last
            registry = ordered

    return registry


def build_registry() -> dict[str, dict[str, Any]]:
    """Active looks only (hidden ones excluded) -- what actually gets
    rendered/previewed/applied."""
    registry = _build_all()
    hidden = load_hidden()
    for name in hidden:
        registry.pop(name, None)
    return registry


def build_registry_including_hidden() -> dict[str, dict[str, Any]]:
    """Everything, hidden looks included -- for the Manage Looks list."""
    return _build_all()


# -- user-facing import: one entry point regardless of file type -----------

def import_look(path: str | Path) -> dict[str, dict[str, Any]]:
    """Import a look (or several, for a folder/zip/multi-preset file) from
    a path the user picked. Returns {name: recipe}. Raises ValueError for
    an unrecognized file type."""
    path = Path(path)
    suffix = path.suffix.lower()

    if path.is_dir():
        return load_xmp_folder(path)

    if suffix == ".xmp":
        recipe = load_xmp_file(path)
        return {recipe["preset_name"]: recipe}
    if suffix == ".zip":
        return load_xmp_zip(path)
    if suffix == ".cube":
        lut = load_cube(path)
        name = lut.title or path.stem
        return {name: {"preset_name": name, "_lut3d": lut}}

    raise ValueError(f"unrecognized preset file type: {path.suffix} ({path})")


def save_imported_look(name: str, recipe: dict[str, Any], source_path: str | Path | None = None) -> Path:
    """Persist an imported look to presets/user/ so it's available on future
    runs without re-importing. A .cube-backed look (has "_lut3d") copies the
    original .cube file instead of trying to serialize the LUT table to
    JSON -- it gets re-parsed at registry build time."""
    USER_PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in name).strip()

    if "_lut3d" in recipe:
        if source_path is None:
            raise ValueError("saving a .cube-backed look requires source_path")
        luts_dir = USER_PRESETS_DIR / "luts"
        luts_dir.mkdir(exist_ok=True)
        dest = luts_dir / Path(source_path).name
        dest.write_bytes(Path(source_path).read_bytes())
        return dest

    dest = USER_PRESETS_DIR / f"{safe_name}.json"
    dest.write_text(json.dumps(recipe, indent=2), encoding="utf-8")
    return dest


def delete_imported_look(name: str, recipe: dict[str, Any]) -> bool:
    """Actually remove a user-imported look's file(s) under presets/user/
    (there's no bundled original to fall back on, unlike a built-in --
    see hide_look() for that case). Returns whether anything was found to
    remove."""
    safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in name).strip()
    removed = False

    json_path = USER_PRESETS_DIR / f"{safe_name}.json"
    if json_path.is_file():
        json_path.unlink()
        removed = True

    if "_lut3d" in recipe:
        # Re-derive each candidate file's own display name (same rule as at
        # registry-build time: title-if-set, else filename stem) and only
        # delete the one that actually matches -- comparing against
        # recipe["_lut3d"].title here instead would be loop-invariant (that
        # title doesn't change per file), so whenever the target look's LUT
        # has a real TITLE field, *every* .cube in the folder would match
        # and get deleted, not just the intended one.
        for cube_path in (USER_PRESETS_DIR / "luts").glob("*.cube"):
            try:
                candidate_name = load_cube(cube_path).title or cube_path.stem
            except Exception:
                continue
            if candidate_name == name:
                cube_path.unlink()
                removed = True
                break

    return removed


if __name__ == "__main__":
    registry = build_registry()
    print(f"{len(registry)} looks available:\n")
    for name in sorted(registry):
        print(" -", name)
