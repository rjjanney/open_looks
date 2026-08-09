# Android / iOS / web port: research notes

Status: **actively being built.** `port/` has a working JS engine
(`engine.js`, `lut_engine.js`, `xmp_importer.js`, `registry.js`) validated
against the real Python implementation, plus a real end-to-end preview
(`port/preview.html`). See "Progress" below for the current state -- this
file is kept up to date as the port moves forward, not a stale plan.

## The question

Can `open_looks` ship on Android, iOS, and the web, on top of the
existing Python engine (`scripts/develop_engine.py`, `scripts/lut_engine.py`)?

## Finding: no JS equivalent of Pillow/numpy/OpenCV -- port, don't wrap

There's no drop-in "Pillow for JS." The realistic targets:

- **Pillow's role** (decode/resize/crop/save) -> Canvas `ImageData`
  (`Uint8ClampedArray`), which browsers/WebViews provide natively.
- **numpy's role** (vectorized array math) -> no direct equivalent worth
  using; plain `Float32Array` + a handful of hand-written elementwise
  helper functions (`clip`, `scale`, `blend`, `applyLUT`) covers it, and
  is simpler than pulling in a general ndarray library.
- **OpenCV's role** (`cv2.GaussianBlur`, `cv2.cvtColor` RGB<->HSV) ->
  **`opencv.js`**, the official OpenCV WASM build, is the one real
  like-for-like match -- or hand-roll a separable Gaussian blur and the
  standard HSV formulas (small, well-documented, ~100 lines total)
  instead of pulling in an ~8MB WASM dependency.

## Recommended architecture

Port the engine to JS/TS once, targeting Canvas/typed arrays, then reuse
that single JS codebase three ways instead of three native rewrites:

- **Web**: runs directly (PWA-installable).
- **Android/iOS**: wrap the same web code with Capacitor (or Tauri
  mobile) to get app-store-distributable builds, rather than a separate
  Kotlin/Swift reimplementation.

## `develop_engine.py` port assessment (541 lines) + `lut_engine.py` (116 lines)

Read in full for this assessment. It's a favorable porting target: pure
stateless functions over `(H,W,3)` float arrays, no classes, no complex
control flow, every tuned constant already a plain number in the code.

**Mechanical, not hard (~60% of the file)**: tone curve LUTs, basic tone
(exposure/contrast/blacks/whites/shadows/highlights), grayscale mixer,
HSL bands, saturation/vibrance, split toning, dehaze, vignette. Each is
15-50 lines of numpy broadcasting that becomes an explicit loop or a
small set of reusable `Float32Array` helpers. Tedious, not clever.

**Needs real care (3 spots, risk of subtle numeric mismatch)**:
- `cv2.GaussianBlur` (used by Texture, Clarity, grain)
- `cv2.cvtColor` RGB<->HSV (used by grayscale mixer, HSL bands,
  saturation/vibrance, split toning)
- PIL's `ImageFilter.UnsharpMask` (final sharpen step) -- blur + subtract
  + threshold, same category of risk

**De-risking already in place**: the pytest suite
(`tests/test_develop_engine.py`, 27 tests) plus the real Lightroom
export fixture pairs in `Source/LR_EXPORT_AND_LOOKS/` (used to fit the
Dehaze/Texture/vignette constants -- see
[[calibration_workflow]] in memory) are ground truth. Porting those same
assertions to a JS test runner (vitest/jest) makes correctness
pixel-checkable against known-good output instead of eyeballed.

**Estimate**: ~2-4 focused days for `develop_engine.py` + `lut_engine.py`
core numerics, running against Canvas `ImageData`, with test parity
restored. That figure is the engine only -- it excludes:

- `scripts/xmp_importer.py` (226 lines, XML parsing -- likely *easier*
  in JS via native `DOMParser`, not yet assessed in depth)
- `scripts/registry.py` (look list, hide/unhide/reorder/import state --
  not yet assessed)
- Actual UI (`app/web/` already exists as HTML/CSS/JS for the desktop
  pywebview shell -- how much is reusable vs. needs a new
  mobile/responsive layout is unassessed)
- Capacitor/Tauri mobile packaging and app-store submission mechanics
- Re-validating ported output against `Source/LR_EXPORT_AND_LOOKS/`
  fixtures once the port exists

## `xmp_importer.py` port assessment (226 lines)

Read in full. Confirms the earlier hunch: easier than the engine, no
numeric-mismatch risk anywhere -- this is string/XML parsing, not float
math, so there's no cv2-style "close enough" question to resolve.

**Mechanical, no real risk (~85% of the file)**: `xml.etree.ElementTree`'s
namespace-qualified attribute/element lookups (`crs:Field="value"` on
`rdf:Description`, nested `rdf:Seq`/`rdf:li` for tone curves) map directly
onto the browser's native `DOMParser` + `getElementsByTagNameNS`/
`getAttributeNS` -- available in every real target (browsers, and
Capacitor/Tauri webviews on mobile) with zero dependencies. The numeric
coercion regex (`_NUM_RE`), the no-op-default scalar filter
(`_IGNORED_SCALAR_DEFAULTS`), the local-adjustment/PointColors
unsupported-field warnings, and `_parse_seq_points` are all straight
line-for-line translations -- plain string/regex/array logic, nothing
Python-specific.

**One real decision, not a hard problem**: `load_xmp_zip` (parsing a shared
preset pack distributed as a `.zip`) has no browser-native equivalent --
unlike separable Gaussian blur, DEFLATE decompression isn't "small and
well-documented enough to hand-roll safely." This is the one spot in the
whole port where pulling in a small trusted library (e.g. `fflate`, ~8KB)
is the right call over hand-rolling, once there's an actual npm project to
add it to.

**Doesn't need porting, needs different UX**: `load_xmp_folder`'s recursive
directory walk (`pathlib.Path.glob("**/*.xmp")`) has no browser equivalent
-- pages can't walk an arbitrary filesystem path. But the underlying user
need ("import a folder of presets someone shared") is fully covered by a
`<input type="file" multiple webkitdirectory>` picker or drag-and-drop
handing back a flat `FileList` to loop over -- simpler than the recursive
walk it replaces, not a gap.

**Testing caveat**: unlike `engine.js`, this module's target API
(`DOMParser`) doesn't exist in plain Node, so the `node:test` +
fixture-JSON pattern used for `engine.test.mjs` won't directly apply --
needs either a lightweight DOM shim (e.g. `linkedom`) for Node-side tests,
or running the tests in an actual browser context.

**Estimate**: parsing core (attributes, `rdf:Seq`, coercion, warnings) is
half a day, no surprises expected. Zip support depends on the
library-vs-hand-roll call above -- another chunk of time either way. Folder
mode isn't a porting task, it's a UI decision (file picker vs.
drag-and-drop) deferred to the UI-reuse assessment.

## `registry.py` port assessment (250 lines)

Read in full, plus `fuji_recipes.py` (140 lines, the module it depends on).
Different shape of problem than the previous two: no numeric-mismatch risk
(xmp_importer) and no missing browser API to swap in for a Python one
(the engine's cv2). The real question here is persistence architecture --
where does "a user's own imported looks, hidden list, and sort order"
*live* when there's no `%APPDATA%`? That's genuine design work, not
mechanical translation, even though the file is shorter than the engine.

**Trivial, zero risk**: `fuji_recipes.py` is pure data (a dict of recipe
dicts, same schema `xmp_importer.py` produces) -- becomes a JSON file or JS
object literal with no logic to port at all. `safe_name` sanitization,
hidden-set add/remove, and the `import_look` suffix dispatch
(`.xmp`/`.zip`/`.cube` -> the already-scoped importers) are straight
line-for-line translations once their storage reads/writes exist.

**Delete outright, doesn't apply**: the `sys._MEIPASS`/frozen-executable
path resolution and `_migrate_legacy_user_dir()` are PyInstaller-packaging
and this-app's-own-history concerns specific to the desktop build. No web
or mobile equivalent, nothing to port -- a fresh JS registry module just
doesn't have this code.

**Changes mechanism, not hard**: `_load_builtin_json`'s runtime
`folder.glob("*.json")` over the bundled `presets/builtin/fujixweekly/`
directory has no browser equivalent -- pages can't list a directory of
static assets at runtime. Becomes a build-time-generated manifest (a
bundler's glob import, e.g. Vite's `import.meta.glob`, or a plain
generated `index.json` listing filenames) instead of a runtime scan. Same
end result, different mechanism, resolved once at build time rather than
every app launch.

**The real decision: where user data lives.** `USER_PRESETS_DIR`
(`hidden.json`, `order.json`, imported `.json` recipes, imported `.cube`
files under `luts/`) needs a genuine per-platform storage backend, since
nothing plays the role `%APPDATA%` does on desktop:

- **Web**: Origin Private File System (`navigator.storage.getDirectory()`)
  is the closest analog -- real file-like storage with the same
  directory-of-files shape this code already assumes (`hidden.json`,
  `order.json`, a `luts/` subfolder), so the port stays close to the
  original structure instead of reshaping it around a key-value store like
  IndexedDB/localStorage. OPFS isn't universal (weakest on older Safari) --
  worth a fallback if that audience matters, not worth solving speculatively
  now.
- **Mobile (Capacitor)**: the `Filesystem` plugin gives real native
  per-app-private file storage with a `mkdir`/`writeFile`/`readFile`/
  `deleteFile` API -- close to a 1:1 swap for `pathlib`'s calls here.
- Recommend one small storage-adapter interface (`readFile`/`writeFile`/
  `listFiles`/`deleteFile`/`mkdir`) that `registry.js` calls, with two thin
  backends (OPFS, Capacitor Filesystem) selected at init -- this is the one
  spot in the whole port that needs a real platform abstraction, unlike the
  engine or `xmp_importer.py`, which are pure functions with no I/O of
  their own.

**Estimate**: the pure logic (dispatch, sanitization, hidden/order
list-juggling) is an hour or two once the storage primitives exist. The
storage-adapter layer -- picking OPFS vs. a wrapper library, writing the
two backends, handling the "not supported" fallback -- is the actual time
sink, and is closer to the engine port's effort level than the line count
suggests, because it's new design work rather than translation. Hard to
pin down precisely before OPFS vs. alternatives gets tried against a real
Capacitor build.

## `app/web/` UI reuse assessment (index.html 75 + app.js 377 + app.css 344
lines; `app/api.py`'s 327 lines is the contract being replaced)

Read all four in full. Good news first: `app.js` is already cleanly
separated -- every single async function is a thin proxy to
`window.pywebview.api.*`, and does zero image processing or file I/O
itself. That split is exactly what this port needs, and it's already
there, not something to build.

**Reusable close to as-is**: `index.html`'s structure/IDs, almost all of
`app.css` (CSS custom-property theme, flex/grid layout, modal, spinner --
none of it assumes a native window), and `app.js`'s state machine
(`currentFolder`/`photos`/`selectedLook`/etc.), event wiring, and render
functions (`renderLookGrid`, `renderManageList`, `stepLook`, keyboard nav).
None of that shape changes -- only the bodies of the functions that
currently `await window.pywebview.api.X(...)` need new implementations.

**One responsive gap**: the fixed 230px left filmstrip sidebar
(`.filmstrip-panel`) assumes a desktop-width window (`api.py` even sets a
`min_size=(900,600)`). Needs one mobile breakpoint (filmstrip becomes a
horizontal strip or a drawer) -- a CSS addition, not a rewrite.

**Maps directly onto already-scoped work**: `list_looks`/`list_all_looks`/
`remove_look`/`unhide_look`/`reorder_looks` and `pick_look_file`/
`import_look_file` are pure `registry.js` + `xmp_importer.js` calls once
those exist (both already scoped above) plus swapping the native file
dialog for `<input type="file" multiple accept=".xmp,.cube,.zip">`.
`render_previews` is a loop calling `applyRecipe()` per look and drawing to
canvas -- trivial *once* `develop_engine.py`'s remaining stages are
ported (tone curves, HSL bands, dehaze, split toning, grain, vignette,
sharpen), which is the next item after this doc's scoping work anyway.
`list_photos`'s PIL thumbnailing becomes Canvas resize + `toDataURL`.

**The two genuinely open UX questions**, both about filesystem access none
of the previous modules needed:

- **`pick_folder` / batch folder browsing**: no browser API opens "a
  folder" the way a native dialog does. Chromium's File System Access API
  (`showDirectoryPicker()`) gets closest -- read+write access to a
  user-picked directory, no repeated per-file prompts -- but it's
  Chromium-only (no Firefox, no Safari/iOS as of this writing). The
  practical fallback everywhere else is `<input type="file" multiple
  webkitdirectory>` (read-only: hands back a `FileList`, good enough for
  browsing/previewing) -- so browsing works universally, but *writing back
  into that same folder* doesn't.
- **`apply_to_photo` / `apply_to_folder` (writing results back to disk)**:
  this is the real gap, not a syntax swap. Options, in order of how
  broadly they work:
  - A synthesized `<a download>` per result -- works everywhere, but
    `apply_to_folder`'s batch case means N downloads, and browsers
    throttle/prompt after a handful of automatic downloads in one action.
  - File System Access API's write handle on the picked directory --
    matches the current "writes into `Output/<look>/`" behavior exactly,
    but Chromium-only.
  - Mobile (Capacitor): the `Filesystem`/`Share` plugins write to a
    real location and can hand the result to the OS share sheet -- no
    equivalent gap there.
  - Simplest universal fallback: zip all outputs client-side (same
    `fflate` dependency already recommended for `xmp_importer.js`'s
    zip-pack import) and offer one `<a download>` for the whole batch.
  No single answer covers every browser identically -- this needs a
  decision (likely: File System Access API where available, zip-download
  fallback elsewhere) before `apply_to_photo`/`apply_to_folder` get built,
  the same way the storage-adapter decision blocks `registry.py`.

**Estimate**: once `develop_engine.js` and `registry.js` exist, wiring
`app.js`'s existing functions up to them is small -- the UI layer itself
needs little more than the responsive breakpoint. The real remaining work
is the folder-write decision above, which is UX/architecture, not
translation -- same category as `registry.py`'s storage-adapter call, not
more of the same kind of work as the engine or `xmp_importer.py` ports.

## Progress

1. **Done.** `port/engine.js` -- hand-rolled `clip`/`scale`/`blend`/`applyLut`/
   `luminance`/`rgbToHsv`/`hsvToRgb`/`gaussianBlur` on flat `Float32Array`
   RGB buffers, validated by eye in `port/preview.html` against several real
   `Source/LR_EXPORT_AND_LOOKS/` fixture photos (bright/textured, hazy
   low-saturation, dark vignetted -- no visible HSV round-trip or blur
   artifacts on any of them).
2. **Done.** `port/engine.test.mjs` (Node's built-in `node:test`, no
   vitest/jest needed for this) checks the JS output against ground truth
   computed by the real `scripts/develop_engine.py` (`port/gen_fixtures.py`
   dumps a local, gitignored `port/fixtures.json` from the actual
   cv2-backed functions -- regenerate with the Python 3.10 interpreter,
   not the default `python` on this machine, which lacks cv2). 14 tests
   pass: HSV matches cv2 to <1e-3 on sat/value, <1deg on hue; the
   hand-rolled blur matches `cv2.GaussianBlur` to within max diff 0.00024
   (mean 0.00006) on a 0..1 range.
3. **Done, decided by data.** Hand-rolled blur wins outright -- the measured
   gap above makes `opencv.js`'s ~8MB WASM dependency not worth it.
4. **Done.** `xmp_importer.py`, `registry.py`, and `app/web/` UI reuse all
   scoped. Every module in the app is now assessed at least at the
   research level -- nothing left unscoped before implementation starts.
5. **Done.** `develop_engine.py`'s full remaining pipeline ported into
   `port/engine.js`: `parametricCurveLut`/`pointCurveLut`/`combineLuts`
   (tone curves), `applyDehaze`, `applyBasicTone` (exposure/contrast/
   blacks/whites/shadows/highlights/texture/clarity/dehaze),
   `hueBandWeights`, `applyGrayscaleMixer`, `applyHslBands`,
   `applySaturationVibrance`, `applySplitToning`, `applyGrain`,
   `applyVignette`, `applySharpen`, and the top-level `applyRecipe`
   orchestrator. Also fixed a real bug found along the way: `applyLut`'s
   index was rounding instead of truncating, an off-by-one against
   Python's `.astype(np.int32)` near `.5` boundaries.
   `port/gen_fixtures.py` now generates ground truth for every stage
   (including a full-pipeline end-to-end fixture, to catch orchestration/
   ordering bugs a passing per-stage test wouldn't) -- 14/14 tests pass,
   all tolerances set from measured gaps, not guesses:
   - Tone curves, basic tone, grayscale mixer, HSL bands, saturation/
     vibrance, split toning, vignette: match to <1e-3, most far tighter
     (pure math, same formulas, no cross-library risk).
   - `applySharpen` (the other flagged numeric-risk spot -- PIL's own
     internal blur, not cv2): measured max diff ~0.0052 on a 0..1 range.
   - Full pipeline end-to-end: ~0.0213, dominated by the same
     sharpen/clarity blur gaps compounding.
   - `applyGrain` deliberately does *not* match numpy bit-for-bit (own
     seeded RNG, not PCG64) -- grain only needs the same statistical
     character (zero-mean, unit-std, correctly blurred), not pixel
     parity with the Python desktop build. See the `ponytail:` comment
     on it in `engine.js`.
6. **Done.** `lut_engine.py` ported to `port/lut_engine.js`
   (`Lut3D`/`parseCube`), and wired into `applyRecipe` via
   `recipe._lut3d` (duck-typed on an `.apply()` method, so `engine.js`
   doesn't need a hard import of `lut_engine.js`). As expected for pure
   math + text parsing with no cross-library equivalent to diverge
   against: `port/lut_engine.test.mjs`'s 5 tests match Python to <1e-4
   (`Lut3D.apply`, two domain-range cases) and exactly (`parseCube`'s
   axis-order recovery, plus three error-path checks -- 1D-LUT rejection,
   missing `LUT_3D_SIZE`, data-line count mismatch).
7. **Done.** Real end-to-end preview wired up: `port/canvas_glue.js`
   (`imageDataToRgb`/`rgbToImageData`, alpha extracted before the pipeline
   and reattached untouched after -- mirrors `apply_recipe()`'s own PIL
   alpha handling) connects Canvas `ImageData` to `applyRecipe`.
   `port/preview.html` replaced its HSV/blur-only sanity check with a real
   demo: pick a photo, pick from all 9 bundled
   `presets/builtin/fujixweekly/*.json` looks (fetched live, not
   duplicated into JS), see the actual rendered result. Verified in a real
   browser against a real photo: a color-film look (Kodachrome 64, ~840ms)
   and a `ConvertToGrayscale` look (Ilford HP5, ~196ms) both rendered
   correctly with no errors -- confirms the grayscale-mixer code path
   works end to end too, not just the color path the fixture tests
   exercise most. (Serving this now needs `python -m http.server` run
   from the repo root, not `port/`, so `preview.html`'s
   `../presets/...` fetch resolves -- a change from the step-1 setup.)

8. **Done.** `xmp_importer.py` ported to `port/xmp_importer.js`, tested
   against every real `.xmp` fixture in `Source/LR_EXPORT_AND_LOOKS/` plus
   synthetic cases for the tone-curve/warning paths those don't exercise
   (6/6 tests in `port/xmp_importer.test.mjs`, exact match -- no
   numeric-mismatch risk here, it's string/XML parsing). Zip-pack import
   uses `fflate` (~8KB), as recommended when this was scoped. Node-side
   testing needed a real namespace-aware XML `DOMParser`: **linkedom**
   (tried first) doesn't implement `getElementsByTagNameNS`/
   `namespaceURI` correctly for XML, so this uses **`@xmldom/xmldom`**
   instead, which does. `port/` is now a real npm project
   (`fflate` + dev dep `@xmldom/xmldom`); `node_modules/` is gitignored.
9. **Done.** `registry.py` ported to `port/registry.js` +
   `port/fuji_recipes.js` (pure data, byte-for-byte checked against the
   real Python dict). The storage-adapter decision got made, not left
   open: every registry function takes a `storage` argument
   (`readText`/`writeText`/`readBytes`/`writeBytes`/`deleteFile`/
   `listFiles`) rather than a hard-coded backend --
   **`port/opfs_storage.js`** implements it on the Origin Private File
   System (the real browser backend; a Capacitor `Filesystem` backend
   would be a second implementation of the same shape when mobile
   packaging happens). That dependency-injection shape is also what makes
   `registry.js`'s own logic (hidden/order/merge-precedence/import
   dispatch/save/delete) unit-testable in plain Node with an in-memory
   fake storage, without needing OPFS at all -- 8/8 tests pass in
   `port/registry.test.mjs`. The one thing that genuinely can't be
   Node-tested is `opfs_storage.js` itself (no OPFS in Node); verified
   separately with `port/opfs_check.html`, a small self-checking page, in
   a real browser -- all 5 checks (missing-file read, text round-trip
   with auto-created nested dirs, bytes round-trip, listing, delete) pass
   against real OPFS.

10. **Done, decided.** Folder read/write for `apply_to_photo`/
    `apply_to_folder`: **universal download, not the File System Access
    API.** `port/export_glue.js` -- single-file `<a download>` for
    `apply_to_photo`; client-side zip (`fflate`, already a dependency) +
    one `<a download>` for `apply_to_folder`'s batch case, instead of N
    automatic downloads (which browsers throttle/prompt after a handful).
    Rejected FSA API even as a Chromium-only enhancement: it still needs
    this same fallback for Firefox/Safari, so it would've meant two code
    paths for a narrower win than it looked like on paper -- one path
    covering every browser (this includes Firefox, the browser actually
    used to verify the port so far) beat "real folder writes, but only on
    Chromium." `zipEntries()` (the only DOM-free part -- `canvasToBlob`/
    `downloadBlob` need a real browser) is checked byte-for-byte via
    `unzipSync` round-trip, 2/2 tests in `port/export_glue.test.mjs`.
    Deliberately not verified by triggering a real download through
    automation -- that's an explicit-permission action, not something to
    do unattended.

That's the whole engine + data + export layer done: **35/35 tests pass**
across `port/*.test.mjs`.

11. **Done.** `app/web/app.js` wired up: `port/index.html` +
    `port/app.css` (copy, plus one added responsive breakpoint for the
    fixed-width filmstrip -- the gap flagged in the UI-reuse assessment)
    + `port/app.js` -- a genuinely **separate file from
    `app/web/app.js`**, not an edit to it, since that one is the real
    desktop app's shipping frontend and must not be touched by this
    prototype. Same state machine/event-wiring/render-function shape as
    the original, every `window.pywebview.api.*` call replaced with a
    real implementation against the ported modules. New small pieces this
    needed: `port/fuji_recipes.js` and `port/look_captions.js` (both pure
    data, checked byte-for-byte identical to the Python originals) and
    `port/bundled_presets.js` (the hand-maintained bundled-preset-filename
    manifest, factored out of `preview.html` so both pages share it).
    `chooseFolderBtn`/`importLookBtn` now trigger hidden
    `<input type="file">` elements (`webkitdirectory` for the folder case)
    instead of native dialogs -- the browser-native replacement already
    anticipated when `pick_folder`/`pick_look_file` were scoped.

    Verified end-to-end in a real browser (not just unit tests): loaded 3
    real photos via a simulated folder pick, filmstrip rendered correct
    thumbnails, selecting a photo rendered all 13 looks (4 `FUJI_RECIPES`
    + 9 bundled) correctly captioned with valid preview images, selecting
    a look correctly updated the action bar/main preview, Manage Looks
    hide/unhide round-tripped through real OPFS, and importing a real
    `.xmp` fixture correctly persisted to OPFS and appeared in both the
    look grid and the Manage Looks list with an "Imported" badge (cleaned
    up after). `applyToPhoto`/`applyToFolder` themselves (the two actions
    that trigger a real file download) were deliberately not exercised by
    automation, same reasoning as `export_glue.js`'s own tests.

    **Real bug caught by this browser testing, not by the unit tests**:
    `xmp_importer.js`/`export_glue.js`/`registry.js`'s
    `import ... from "fflate"` is a bare module specifier -- Node resolves
    that via `node_modules` automatically, but a browser loading these
    files directly (no bundler) can't, and failed with "Failed to resolve
    module specifier." All 35 `port/*.test.mjs` tests passed the whole
    time because Node-based tests never hit this path. Fixed with a
    `<script type="importmap">` in `index.html` pointing the bare
    `"fflate"` specifier at its actual browser-targeted ESM build
    (`node_modules/fflate/esm/browser.js`) -- zero changes needed to the
    already-tested module code itself. **Lesson for anything future that
    adds an npm dependency to this port: Node-passing tests don't prove a
    dependency is browser-loadable without a bundler -- check that
    separately.**

    **Real performance issue also caught by this testing**: rendering the
    full look grid (13 looks, no yield points between them) for one photo
    blocked the main thread long enough to blow past a 30-second
    screenshot-capture timeout -- a real "tab looks frozen" UX problem,
    not just an automation artifact. Added a `setTimeout(0)` yield between
    each look's render in `renderPreviews()`; doesn't reduce total render
    time but keeps the spinner animating and the page responsive instead
    of looking hung. If total wall-clock time itself becomes the
    complaint (not just responsiveness), the real fix is moving
    `applyRecipe` into a Web Worker -- flagged but deliberately not built
    speculatively (see the `ponytail:` comment at the top of `app.js`).

Every architecture decision the port needed has now been made and
implemented, and the whole stack has been verified against real Python
output, a real browser, or both. What's left is scope, not open
questions: mobile packaging (Capacitor/Tauri, a second storage-adapter
backend for `registry.js`), performance work if the Web-Worker gap above
turns out to matter in practice, and ordinary polish (loading states,
error surfacing, the bundled-presets manifest becoming a real build-time
step instead of a hand-maintained list).
