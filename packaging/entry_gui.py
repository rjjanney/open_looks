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

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP_DIR))

from api import main

main()
