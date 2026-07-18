# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: open_looks, a windowed desktop build for Windows,
macOS, and Linux.

PyInstaller can't cross-compile -- this spec produces a build for whatever
OS it's run on, which is why .github/workflows/build.yml runs it separately
on windows-latest / macos-latest / ubuntu-latest rather than building all
three from one machine.

Windows and Linux both ship as onefile -- the runtime self-extracts to a
temp dir on launch, single binary to hand someone (see
pics_apply_looks/packaging/gui.spec for the fuller onefile-vs-onedir
tradeoff writeup). macOS instead gets a proper onedir + BUNDLE() into
open_looks.app, since that's what "double-click to run" actually means on
that OS -- a bare onefile Unix executable works but isn't a real Mac app
(no icon, no Finder integration, and Gatekeeper is unhappier with it).

Each platform's pywebview backend is a separate optional dependency that
PyInstaller's static analysis can't see coming (pywebview picks the backend
at runtime), so it has to be listed explicitly per OS below -- see
requirements.txt for the matching install-time dependency.

Build (from the repo root, inside the venv):
    pyinstaller packaging/gui.spec --clean --noconfirm

Output:
    Windows -> dist/open_looks.exe
    Linux   -> dist/open_looks         (single executable)
    macOS   -> dist/open_looks.app
"""
import sys
from pathlib import Path

REPO = Path(SPECPATH).resolve().parent
APP_DIR = REPO / "app"
SCRIPTS_DIR = REPO / "scripts"
WEB_DIR = APP_DIR / "web"
PRESETS_DIR = REPO / "presets" / "builtin"

if sys.platform == "win32":
    platform_hiddenimports = ["webview.platforms.winforms", "clr_loader", "clr"]
    platform_runtime_hooks = []
elif sys.platform == "darwin":
    platform_hiddenimports = ["webview.platforms.cocoa"]
    platform_runtime_hooks = []
else:
    platform_hiddenimports = ["webview.platforms.gtk"]
    platform_runtime_hooks = []

a = Analysis(
    [str(REPO / "packaging" / "entry_gui.py")],
    pathex=[str(APP_DIR), str(SCRIPTS_DIR)],
    binaries=[],
    datas=[
        (str(WEB_DIR), "app/web"),
        (str(PRESETS_DIR), "presets/builtin"),
    ],
    hiddenimports=platform_hiddenimports,
    runtime_hooks=platform_runtime_hooks,
    noarchive=False,
)

if sys.platform == "linux":
    # On Linux, PyInstaller bundles shared libraries from the build machine.
    # System libraries vary in version across distros, and bundling them
    # causes ABI conflicts at runtime (e.g. Fedora's libgio.so requires a
    # newer libmount than Ubuntu's bundled copy). The safe rule: any lib
    # whose name contains a package-mangled hash (8+ lowercase hex chars
    # after a separator) is owned by a Python package (opencv, numpy, etc.)
    # and safe to bundle. Everything else is a system library and must come
    # from the OS. A small explicit keep-list covers pywebview's private
    # libs that don't follow the hash convention.
    import re as _re
    _HASH = _re.compile(r'[-_][0-9a-f]{8,}')
    _KEEP = ("libpython", "libduktape", "libpxbackend")

    def _bundlable(name):
        if not name.startswith("lib"):
            return True                           # Python extension (.so)
        if any(name.startswith(k) for k in _KEEP):
            return True                           # pywebview private libs
        return bool(_HASH.search(name))           # mangled = python-pkg lib

    a.binaries = [b for b in a.binaries if _bundlable(b[0])]

pyz = PYZ(a.pure)

if sys.platform == "darwin":
    # onedir here, not onefile -- BUNDLE() below needs the unpacked form to
    # assemble a real .app bundle around it.
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="open_looks",
        console=False,
    )
    coll = COLLECT(exe, a.binaries, a.datas, name="open_looks")
    app = BUNDLE(
        coll,
        name="open_looks.app",
        bundle_identifier="com.randyjanney.openlooks",
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="open_looks",
        console=False,
    )
