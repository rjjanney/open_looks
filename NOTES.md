# Cross-platform build/release status

Working notes on getting `open_looks` distributed as prebuilt binaries for
Windows, macOS, and Linux. Picks up from the point the app itself (desktop
GUI, import/manage looks, AppData-based user state) was already working --
this covers packaging it for people who don't want to run it from source.

## How it works

- `packaging/gui.spec` -- one PyInstaller spec, branches on `sys.platform`.
  Onefile for Windows/Linux; a proper `onedir` + `BUNDLE()` into
  `open_looks.app` for macOS (a bare onefile Unix binary isn't a real,
  double-clickable Mac app).
- `packaging/entry_gui.py` -- the actual entry point PyInstaller builds.
  This is also where all the Linux runtime env-var fixes below live.
- `.github/workflows/build.yml` -- matrix build across
  `windows-latest` / `macos-latest` / `ubuntu-latest` (PyInstaller can't
  cross-compile, so each platform's binary has to actually be built on
  that OS). Every push to `main` builds all three as a smoke test; pushing
  a `v*` tag additionally creates a GitHub Release and attaches the three
  binaries to it.

## Release history and what each one fixed

| Tag | Fix |
|---|---|
| v0.1.0 | First working release: repo scaffolding, matrix build, Windows/macOS built clean immediately. Linux needed two follow-up fixes same day: missing `libcairo2-dev`/`pkg-config` for building `pycairo` in CI, and `permissions: contents: write` so the workflow could actually create the Release. |
| v0.1.1 | Pinned `pywebview` to `6.2.1` (tries the WebKit2 4.1 typelib first). |
| v0.1.2 | First attempt at fixing cross-distro `.typelib` lookup via a PyInstaller runtime hook -- didn't work, PyInstaller's own `gi` hook ran after it and overwrote the env var. |
| v0.1.3 | Real fix for the above: moved the `GI_TYPELIB_PATH` append into `entry_gui.py` itself, which runs after all hooks. Fixed Fedora/RHEL failing to find the WebKit2 typelib (bundle was built on Ubuntu, whose typelib path differs). |
| v0.1.4 | PyInstaller was bundling the *build machine's* GTK/GLib shared libraries. Those are system libraries that vary by distro, and shipping Ubuntu's copies caused ABI conflicts on Fedora (e.g. a `libgio.so` requiring a newer `libmount` than the bundled one). Excluded them from the bundle by name so the OS supplies its own at runtime. |
| v0.1.5 | The v0.1.4 exclusion list was name-based and incomplete; switched to a hash-based heuristic (Python-package-owned `.so` files have a mangled hash in the filename, real system libs don't) plus cleared `GDK_PIXBUF_MODULEDIR`/`GDK_PIXBUF_MODULE_FILE` so gdk-pixbuf also falls back to the system's own loaders. **Confirmed working cross-distro on Fedora 42 with no user-side config.** |
| v0.1.6 | Housekeeping: deleted `packaging/hook_gi_typelib_path.py` (the v0.1.2 attempt -- dead code once v0.1.3 moved that fix into `entry_gui.py`; `gui.spec` never wired it back in as a runtime hook). |
| v0.1.7 | Ubuntu/GNOME-Wayland hit a *different* failure than Fedora did: a blank white window. Root cause was two things -- native Wayland crashes in this webview/GTK/WebKit2 combination, and even routed through XWayland, WebKit2's GPU compositing path failed to get a GBM buffer. Fixed by defaulting `GDK_BACKEND=x11` and `WEBKIT_DISABLE_COMPOSITING_MODE=1` in `entry_gui.py` (via `setdefault()`, so still overridable). **Confirmed working on Ubuntu.** |

All of the Linux fixes live in the same `if sys.platform == "linux":` block
in `entry_gui.py` and the same `if sys.platform == "linux":` block in
`gui.spec` -- there's one Linux binary, not per-distro builds, so Fedora
and Ubuntu both get every fix above unconditionally.

## Current verified status

- **Windows**: built and run-tested locally (this machine). Working.
- **Linux**: built in CI, run-tested on both Fedora 42 and Ubuntu. Working,
  no manual flags/env vars required from the user.
- **macOS**: builds clean in CI (BUNDLE() into `open_looks.app` succeeds
  every run) but has **not been launched on real Mac hardware yet** --
  unlike Linux, nothing here has actually confirmed the window renders.
  That's tomorrow's task.

## Known follow-ups

- **macOS verification** -- the actual next step. Also expect a Gatekeeper
  prompt on first launch (unsigned/unnotarized app) -- right-click "Open"
  instead of double-clicking the first time.
- Consider code-signing/notarizing the macOS build (and possibly signing
  the Windows exe too, to avoid a SmartScreen warning) if this is going to
  be handed to people other than us -- not done yet, no Apple
  Developer/Windows code-signing cert in the loop.
- `main` and the latest tag (`v0.1.7`) are in sync as of this writing --
  no untagged commits waiting.
