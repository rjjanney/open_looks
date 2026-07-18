# open_looks

A small, offline, MIT-licensed tool for applying film-style photo looks to
JPEGs -- and importing more looks from other places, instead of being locked
to whatever ships in the box.

This is the freely-distributable sibling of a private project that used a
paid Lightroom preset pack. Everything here is either original work or
openly-licensed, with sources documented in `presets/ATTRIBUTION.md`.

## What this is

- A from-scratch develop engine (`scripts/develop_engine.py`): tone curves,
  a grayscale channel mixer, split toning, film grain, sharpening, vignette
  -- plain Pillow/NumPy/OpenCV, no external image-processing library doing
  the actual work.
- 13 bundled looks: 4 original Fuji-style recipes, plus 9 recipes
  transcribed from published Fuji X Weekly community settings. Full
  breakdown and credits in `presets/ATTRIBUTION.md`.
- Import your own looks from **.xmp** (Lightroom/ACR develop presets -- the
  biggest, most-supported ecosystem) or **.cube** (3D LUTs, trilinear
  interpolation) -- both full-fidelity, no partial translation involved.
  Multi-select is supported, so you can import a whole folder of presets at
  once.
- A desktop app (pywebview) with live before/after previews of every look
  side by side, and a CLI for scripting/batch work.

## What this isn't

Not a Lightroom competitor, and not trying to be. If you already live in a
full raw-editing suite, keep using it -- this is for applying a look to a
folder of JPEGs without installing anything heavier, for people who want a
single small tool.

## Getting it

**Prebuilt binaries** (Windows / macOS / Linux) are attached to each
[Release](../../releases) -- download the one for your OS and run it, no
Python required. Every push also runs through
[`.github/workflows/build.yml`](.github/workflows/build.yml), so `main` is
always known to package cleanly on all three platforms.

**Linux runtime requirement:** the prebuilt binary uses the system's
WebKit2GTK for rendering. Install it once if you haven't already:

```bash
# Ubuntu / Debian
sudo apt install gir1.2-webkit2-4.1

# Fedora / RHEL
sudo dnf install webkit2gtk4.1
```

**From source**, either the desktop app or the CLI:

```powershell
python -m venv .venv
.venv\Scripts\pip.exe install -r requirements.txt

# Desktop app
.venv\Scripts\python.exe -m app.api

# CLI
.venv\Scripts\python.exe scripts\apply_look.py --list
.venv\Scripts\python.exe scripts\apply_look.py --look "Fuji Acros" --input Source --output Output
.venv\Scripts\python.exe scripts\apply_look.py --all
```

(On macOS/Linux, use `.venv/bin/pip` and `.venv/bin/python` instead --
Linux additionally needs the system WebKit2GTK packages listed in
`requirements.txt` for the desktop app specifically; the CLI has no GUI
dependency at all.)

## Importing and managing looks

In the desktop app: **Import Look...** opens a file picker (multi-select
works) for `.xmp` or `.cube` files. **Manage Looks...** lists everything,
built-in and imported -- click a row then use &uarr;/&darr; to reorder it,
Hide a built-in look you don't want cluttering the grid (reversible, the
bundled file is untouched), or Delete an imported one outright.

Your imports, hidden state, and custom ordering live in a per-user data
folder (`%APPDATA%\open_looks\` on Windows), not next to the app itself --
that way a prebuilt binary keeps your state across updates, and moving or
reinstalling the app doesn't lose it.

## Building the desktop app yourself

```powershell
.venv\Scripts\pip.exe install -r packaging\requirements-build.txt
.venv\Scripts\pyinstaller packaging\gui.spec --clean --noconfirm
```

`packaging/gui.spec` branches on the OS it's run on -- PyInstaller can't
cross-compile, so building a macOS app requires actually running this on a
Mac, same for Linux. That's what the GitHub Actions matrix build is for;
see the comment at the top of the spec file for the full per-platform
breakdown (onefile on Windows/Linux, a proper `.app` bundle on macOS).

## Project layout

```
app/
  api.py                the pywebview bridge (Api class, exposed as window.pywebview.api)
  web/                    the desktop app's UI (HTML/CSS/JS)
packaging/
  entry_gui.py           PyInstaller entry point
  gui.spec                cross-platform build spec (see above)
scripts/
  develop_engine.py     the actual image pipeline
  lut_engine.py           .cube parsing + application
  xmp_importer.py          .xmp parsing (Lightroom/ACR develop presets)
  fuji_recipes.py            our 4 original hand-written recipes
  fuji_menu_convert.py        Fuji-camera-menu-settings -> our schema
  registry.py                  combines everything into one look list, plus
                                  hide/unhide/reorder/import for imported looks
  apply_look.py                  the CLI
presets/
  ATTRIBUTION.md          where every bundled look came from
  builtin/                 bundled looks (see ATTRIBUTION.md)
Source/                        a few sample photos to try things on
```
