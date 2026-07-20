# XMP import: what's actually supported

`open_looks` parses Adobe Camera Raw (`crs:`) `.xmp` develop presets --
the format Lightroom Classic and ACR use, and what most free/paid preset
packs on the web are actually distributed as. The parser
(`scripts/xmp_importer.py`) is permissive: it captures every `crs:`
attribute it finds. The render engine (`scripts/develop_engine.py`) is
not -- it only actually applies a fixed, global-controls-only subset.

This is the honest breakdown of that gap. Import-time warnings
(`recipe['_import_warnings']`, printed by the CLI and shown in the GUI's
import status) are generated from the same field lists documented here.

`.cube` 3D LUTs are a separate, much simpler path (`scripts/lut_engine.py`)
and are applied full-fidelity with trilinear interpolation -- everything
below is about `.xmp` only.

## Supported (rendered)

Global tone and color controls, applied by `develop_engine.py`:

- **Basic tone**: `Exposure2012`, `Contrast2012`, `Blacks2012`,
  `Whites2012`, `Shadows2012`, `Highlights2012`, `Clarity2012`
- **Parametric tone curve**: `ParametricShadows/Darks/Lights/Highlights`
  and the three split points
- **Point tone curve**: `ToneCurvePV2012` plus the per-channel
  `ToneCurvePV2012Red/Green/Blue` curves
- **8-band HSL color mixer**: `HueAdjustment{Band}`,
  `SaturationAdjustment{Band}`, `LuminanceAdjustment{Band}` for all 8
  Adobe color bands (Red/Orange/Yellow/Green/Aqua/Blue/Purple/Magenta)
- **B&W conversion**: `ConvertToGrayscale` + `GrayMixer{Band}` (same 8
  bands, hue-weighted gray mix)
- **Saturation / Vibrance**
- **Split toning**: shadow/highlight hue, saturation, balance
- **Grain**: amount, size, frequency
- **Vignette**: `PostCropVignetteAmount`, `Midpoint`, `Feather`,
  `Roundness`, `HighlightContrast` (legacy `VignetteAmount` too)
- **Sharpening**: amount, radius
- **A `.cube` LUT layered into the same recipe** (`_lut3d`)

If a preset only uses the above, import is effectively full-fidelity
(modulo the approximations below).

## Approximated, not pixel-perfect

Adobe's actual curve/mixer/vignette math is undocumented. Every control
above reproduces the *shape* of what the real slider does, driven by the
preset's real values -- it is not a bit-exact reimplementation of ACR.
See the module docstring in `develop_engine.py`.

## Parsed but not rendered (warned when non-default)

These are captured into the recipe dict (nothing crashes), but
`develop_engine.py` never reads them. Many preset tools (ON1, PK Edits,
Lightroom exports) write these on *every* preset with a fixed no-op
value regardless of whether it's actually used, so a warning only fires
when a preset sets one away from that default:

- `Dehaze`, `Texture`
- `Temperature`, `Tint` (white balance)
- `ColorGrade{Shadow,Midtone,Highlight,Global}{Hue,Sat,Lum}` (3-way/4-way
  color grading)
- `PostCropVignetteStyle` -- Adobe's 3 distinct blend modes (Highlight
  Priority / Color Priority / Paint Overlay) aren't reproduced; the
  vignette still renders via Amount/Midpoint/Feather/Roundness/
  HighlightContrast, just always with the same blend approach

## Unsupported structures (warned when present)

No global-control equivalent exists for these at all -- they describe
local/masked edits or per-swatch color grading, and are silently dropped
before this ever reaches `develop_engine.py`:

- `MaskGroupBasedCorrections`, `PaintBasedCorrections`,
  `GradientBasedCorrections`, `CircularGradientBasedCorrections` --
  brush masks, linear gradients, radial gradients, range masks
- `PointColors` -- Point Color grading (sampled-color hue/sat/lum
  offsets with adjustable falloff). Adobe's internal field layout here
  is undocumented; even the warning is best-effort (see
  `_has_real_point_colors` in `xmp_importer.py`)

## Known gaps in the diagnostics themselves

The warning list above is deliberately scoped to fields real preset
packs actually set in practice (checked against ON1 Signature
Collection and PK Edits YT 50+) -- it is not an exhaustive scan of every
possible Adobe field. Fields parsed but not currently flagged at all
include `CameraProfile`, lens/profile corrections, calibration, and
perspective/upright corrections. If you hit a preset that looks visibly
wrong and doesn't produce a warning, that's a gap in this list, not
proof the preset only uses supported fields.

## Why not just clone Lightroom

Local masks/gradients are a real feature project, not a quick add: it
would mean parsing nested mask trees, rasterizing linear/radial/brush
masks, applying separate parameter stacks per mask in the right order,
and handling crop/orientation interactions. `open_looks` is a small
offline JPEG look tool, not a Lightroom competitor -- the goal here is
to be honest about that boundary, not to erase it.
