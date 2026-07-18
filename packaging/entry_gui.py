"""PyInstaller entry point for the open_looks desktop app.

freeze_support() must be the first thing that runs, unconditionally, at the
top of the actual frozen entry script (not merely inside app/api.py's own
`if __name__ == "__main__":`) -- apply_to_folder's ProcessPoolExecutor spawns
new processes that re-run this same executable, and without this, each
spawned worker would re-enter and open another window instead of just
running its assigned job. Matches the sibling pics_apply_looks project's
packaging/entry_gui.py.
"""
import multiprocessing

multiprocessing.freeze_support()

import os
import sys
from pathlib import Path

# PyInstaller's gi hook sets GI_TYPELIB_PATH to the bundled gi_typelibs/
# directory, but WebKit2 isn't bundled (it's a system library). Append
# common system typelib paths so gi can find WebKit2 on any distro after
# the bundled typelibs are already in the search path.
if sys.platform == "linux":
    # PyInstaller's gi hook sets GDK_PIXBUF_MODULEDIR to the bundle's
    # extraction dir and GI_TYPELIB_PATH to the bundled typelibs. We strip
    # out system GTK/GLib libs from the bundle so the OS supplies them,
    # which means we must also let the OS supply gdk-pixbuf loaders instead
    # of the (now incomplete) bundled set. Clear the redirect so system
    # gdk-pixbuf finds its own loaders.
    for _var in ("GDK_PIXBUF_MODULEDIR", "GDK_PIXBUF_MODULE_FILE"):
        os.environ.pop(_var, None)

    # Append system typelib dirs to whatever GI_TYPELIB_PATH the gi hook
    # set (bundled typelibs for GLib/Gtk/Pango etc.), so gi can also find
    # WebKit2 which is never bundled.
    _system_typelib_dirs = [
        "/usr/lib64/girepository-1.0",                 # Fedora / RHEL / openSUSE
        "/usr/lib/x86_64-linux-gnu/girepository-1.0",  # Ubuntu / Debian x86-64
        "/usr/lib/aarch64-linux-gnu/girepository-1.0", # Ubuntu / Debian arm64
        "/usr/lib/girepository-1.0",                   # generic fallback
    ]
    _existing = os.environ.get("GI_TYPELIB_PATH", "")
    _extra = ":".join(d for d in _system_typelib_dirs if os.path.isdir(d))
    os.environ["GI_TYPELIB_PATH"] = ":".join(filter(None, [_existing, _extra]))

APP_DIR = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP_DIR))

from api import main

main()
