"""Generate ground-truth values from the real Python engine (scripts/develop_engine.py)
for port/engine.test.mjs to check the JS port's numeric output against -- pixel-level
pass/fail instead of eyeballing preview.html. Run with the Python 3.10 interpreter that
has cv2/numpy installed:

    python port/gen_fixtures.py

Writes port/fixtures.json. Re-run whenever develop_engine.py's ported functions change.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from develop_engine import (  # noqa: E402
    apply_basic_tone,
    apply_grayscale_mixer,
    apply_hsl_bands,
    apply_recipe,
    apply_saturation_vibrance,
    apply_sharpen,
    apply_split_toning,
    apply_vignette,
    gaussian_blur,
    hsv_to_rgb,
    parametric_curve_lut,
    point_curve_lut,
    rgb_to_hsv,
)
from lut_engine import load_cube  # noqa: E402
from lut_engine import Lut3D  # noqa: E402

rng = np.random.default_rng(42)
fixtures = {}

# ---------------------------------------------------------------------------
# color space / blur (unchanged from step 2)
# ---------------------------------------------------------------------------

named_colors = [
    [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0],
    [1.0, 1.0, 0.0], [0.0, 1.0, 1.0], [1.0, 0.0, 1.0],
    [0.5, 0.5, 0.5], [0.0, 0.0, 0.0], [1.0, 1.0, 1.0],
    [0.2, 0.6, 0.8], [0.83, 0.41, 0.15], [0.05, 0.05, 0.06],
]
random_colors = rng.uniform(0, 1, size=(40, 3)).round(4).tolist()
rgb_samples = named_colors + random_colors

rgb_arr = np.array(rgb_samples, dtype=np.float32).reshape(-1, 1, 3)
hsv_arr = rgb_to_hsv(rgb_arr)
roundtrip_arr = hsv_to_rgb(hsv_arr)

fixtures["rgbSamples"] = rgb_samples
fixtures["hsvExpected"] = hsv_arr.reshape(-1, 3).tolist()
fixtures["roundtripExpected"] = roundtrip_arr.reshape(-1, 3).tolist()

flat_blur = np.full((12, 12), 0.6, dtype=np.float32)
noise_blur = rng.uniform(0, 1, size=(24, 24)).astype(np.float32)
fixtures["blur"] = [
    {"input": flat_blur.flatten().tolist(), "width": 12, "height": 12, "sigma": 1.5,
     "expected": gaussian_blur(flat_blur, radius=1.5).flatten().tolist()},
    {"input": noise_blur.flatten().tolist(), "width": 24, "height": 24, "sigma": 8.0,
     "expected": gaussian_blur(noise_blur, radius=8.0).flatten().tolist()},
]

# ---------------------------------------------------------------------------
# shared test images -- small, deterministic, same spirit as the pytest
# suite's own 64x64 synthetic arrays
# ---------------------------------------------------------------------------

# 64, matching tests/test_develop_engine.py's own default size -- big enough
# that Clarity's fixed radius=25 blur (unlike Texture, not scaled to image
# width) isn't wildly oversized relative to the image, which is what a
# smaller test size showed as an inflated blur-mismatch that isn't
# representative of real usage (previews are 448px wide).
SIZE = 64


def flat_image(value=0.5):
    return np.full((SIZE, SIZE, 3), value, dtype=np.float32)


def gray_gradient():
    """Horizontal luminance ramp 0..1 -- gives basic-tone/texture/clarity/
    dehaze real detail to respond to, same idea as the pytest edge tests."""
    ramp = np.linspace(0, 1, SIZE, dtype=np.float32)
    return np.repeat(ramp[None, :], SIZE, axis=0)[..., None].repeat(3, axis=2)


def colorful_image():
    """A grid of varied hues/saturations -- exercises the HSL-band/
    grayscale-mixer/saturation-vibrance/split-toning hue-dependent math."""
    img = np.zeros((SIZE, SIZE, 3), dtype=np.float32)
    for y in range(SIZE):
        for x in range(SIZE):
            hue = (x / SIZE) * 360.0
            sat = 0.3 + 0.6 * (y / SIZE)
            hsv = np.array([[[hue, sat, 0.8]]], dtype=np.float32)
            img[y, x] = hsv_to_rgb(hsv)[0, 0]
    return img


def edge_image():
    """Half dark, half light -- mirrors the pytest texture-sharpens-a-fine-
    edge test, good for sharpen/texture/clarity edge-response checks."""
    img = np.full((SIZE, SIZE, 3), 0.3, dtype=np.float32)
    img[:, SIZE // 2:] = 0.7
    return img


def dump_case(name, img, recipe, out, **extra):
    fixtures.setdefault(name, [])
    fixtures[name].append({
        "input": img.flatten().tolist(),
        "width": img.shape[1],
        "height": img.shape[0],
        "recipe": recipe,
        "expected": np.asarray(out).flatten().tolist(),
        **extra,
    })


# ---------------------------------------------------------------------------
# tone curves
# ---------------------------------------------------------------------------

curve_recipes = [
    {},
    {"ParametricShadows": 40, "ParametricHighlights": -30},
    {"ParametricShadows": -50, "ParametricDarks": 20, "ParametricLights": -20, "ParametricHighlights": 60,
     "ParametricShadowSplit": 20, "ParametricMidtoneSplit": 55, "ParametricHighlightSplit": 80},
]
fixtures["parametricCurveLut"] = [
    {"recipe": r, "expected": parametric_curve_lut(r).tolist()} for r in curve_recipes
]

point_curve_cases = [
    None,
    [(0, 0), (128, 160), (255, 255)],
    [(0, 30), (64, 50), (192, 220), (255, 240)],
]
fixtures["pointCurveLut"] = [
    {"points": pts, "expected": point_curve_lut(pts).tolist()} for pts in point_curve_cases
]

# ---------------------------------------------------------------------------
# basic tone (exposure/contrast/blacks/whites/shadows/highlights/texture/
# clarity/dehaze, all via apply_basic_tone)
# ---------------------------------------------------------------------------

basic_tone_recipes = [
    {"Exposure2012": 0.8},
    {"Contrast2012": 40},
    {"Blacks2012": -30, "Whites2012": 20},
    {"Shadows2012": 50, "Highlights2012": -40},
    {"Texture": 80},
    {"Clarity2012": 60},
    {"Dehaze": 70},
    {"Dehaze": -70},
    {"Exposure2012": 0.3, "Contrast2012": 15, "Shadows2012": 20, "Texture": 30, "Clarity2012": 20, "Dehaze": 25},
]
for recipe in basic_tone_recipes:
    img = gray_gradient()
    out = apply_basic_tone(img.copy(), recipe)
    dump_case("applyBasicTone", img, recipe, out)

# ---------------------------------------------------------------------------
# grayscale mixer
# ---------------------------------------------------------------------------

gray_mixer_recipes = [
    {"GrayMixerRed": 60, "GrayMixerBlue": -40},
    {"GrayMixerYellow": -80, "GrayMixerGreen": 50, "GrayMixerAqua": 30},
]
for recipe in gray_mixer_recipes:
    img = colorful_image()
    out = apply_grayscale_mixer(img.copy(), recipe)
    dump_case("applyGrayscaleMixer", img, recipe, out)

# ---------------------------------------------------------------------------
# HSL bands
# ---------------------------------------------------------------------------

hsl_recipes = [
    {"HueAdjustmentRed": 40, "SaturationAdjustmentBlue": -50, "LuminanceAdjustmentGreen": 30},
    {"HueAdjustmentOrange": -60, "HueAdjustmentAqua": 70, "SaturationAdjustmentMagenta": 60},
]
for recipe in hsl_recipes:
    img = colorful_image()
    out = apply_hsl_bands(img.copy(), recipe)
    dump_case("applyHslBands", img, recipe, out)

# ---------------------------------------------------------------------------
# saturation / vibrance
# ---------------------------------------------------------------------------

sat_vib_recipes = [
    {"Saturation": 40},
    {"Saturation": -60},
    {"Vibrance": 70},
    {"Saturation": 30, "Vibrance": -40},
]
for recipe in sat_vib_recipes:
    img = colorful_image()
    out = apply_saturation_vibrance(img.copy(), recipe)
    dump_case("applySaturationVibrance", img, recipe, out)

# ---------------------------------------------------------------------------
# split toning
# ---------------------------------------------------------------------------

split_tone_recipes = [
    {"SplitToningShadowHue": 210, "SplitToningShadowSaturation": 40,
     "SplitToningHighlightHue": 40, "SplitToningHighlightSaturation": 30},
    {"SplitToningShadowHue": 30, "SplitToningShadowSaturation": 60, "SplitToningBalance": -40},
]
for recipe in split_tone_recipes:
    img = gray_gradient()
    out = apply_split_toning(img.copy(), recipe)
    dump_case("applySplitToning", img, recipe, out)

# ---------------------------------------------------------------------------
# vignette -- reuses the same real-Lightroom-calibrated cases the pytest
# suite itself checks (see tests/test_develop_engine.py)
# ---------------------------------------------------------------------------

vignette_recipes = [
    {"PostCropVignetteAmount": -60, "PostCropVignetteMidpoint": 40},
    {"PostCropVignetteAmount": -80, "PostCropVignetteMidpoint": 50, "PostCropVignetteFeather": 50},
    {"PostCropVignetteAmount": -80, "PostCropVignetteMidpoint": 50, "PostCropVignetteFeather": 50,
     "PostCropVignetteStyle": 3},
    {"PostCropVignetteAmount": -80, "PostCropVignetteMidpoint": 30, "PostCropVignetteRoundness": 100},
    {"PostCropVignetteAmount": -70, "PostCropVignetteMidpoint": 30, "PostCropVignetteRoundness": -100},
    {"PostCropVignetteAmount": -80, "PostCropVignetteMidpoint": 20, "PostCropVignetteHighlightContrast": 100},
    {"PostCropVignetteAmount": 50, "PostCropVignetteMidpoint": 40},
]
for recipe in vignette_recipes:
    img = flat_image(0.6)
    out = apply_vignette(img.copy(), recipe)
    dump_case("applyVignette", img, recipe, out)

# ---------------------------------------------------------------------------
# sharpen -- the other flagged numeric-risk spot (PIL's own internal blur,
# not cv2). apply_sharpen takes/returns a PIL Image in 0..255 uint8.
# ---------------------------------------------------------------------------

sharpen_recipes = [
    {"Sharpness": 40},
    {"Sharpness": 80, "SharpenRadius": 2.0},
]
for recipe in sharpen_recipes:
    img_f = edge_image()
    pil_img = Image.fromarray((img_f * 255).astype(np.uint8))
    out_pil = apply_sharpen(pil_img, recipe)
    out_f = np.asarray(out_pil).astype(np.float32) / 255.0
    dump_case("applySharpen", img_f, recipe, out_f)

# ---------------------------------------------------------------------------
# full pipeline (apply_recipe) -- catches orchestration/ordering bugs a
# unit-level match on each stage wouldn't
# ---------------------------------------------------------------------------

full_pipeline_recipes = [
    {"Exposure2012": 0.3, "Contrast2012": 20, "Saturation": 20,
     "PostCropVignetteAmount": -50, "PostCropVignetteMidpoint": 40},
    {"Shadows2012": 30, "Texture": 40, "Clarity2012": 20, "Dehaze": 30,
     "SplitToningShadowHue": 210, "SplitToningShadowSaturation": 30,
     "SplitToningHighlightHue": 40, "SplitToningHighlightSaturation": 20},
    {"HueAdjustmentOrange": 30, "SaturationAdjustmentAqua": -40, "Sharpness": 50},
]
fixtures["applyRecipe"] = []
for recipe in full_pipeline_recipes:
    img_f = colorful_image()
    pil_img = Image.fromarray((img_f * 255).astype(np.uint8))
    out_pil = apply_recipe(pil_img, recipe, grain_seed=1)
    out_f = np.asarray(out_pil).astype(np.float32) / 255.0
    fixtures["applyRecipe"].append({
        "input": img_f.flatten().tolist(),
        "width": SIZE,
        "height": SIZE,
        "recipe": recipe,
        "expected": out_f.flatten().tolist(),
    })

# ---------------------------------------------------------------------------
# lut_engine.py -- Lut3D.apply's trilinear interpolation, and load_cube's
# .cube text parsing (round-tripped through a real .cube file on disk, same
# as tests/test_lut_engine.py's own axis-order test)
# ---------------------------------------------------------------------------

lut_size = 3
lut_rng = np.random.default_rng(7)
lut_table = lut_rng.uniform(0, 1, size=(lut_size, lut_size, lut_size, 3)).astype(np.float32)

lut_test_colors = [[0, 0, 0], [1, 1, 1], [0.5, 0.5, 0.5], [0.2, 0.7, 0.9], [0.9, 0.1, 0.4], [0.33, 0.66, 0.1]]
lut_input = np.array(lut_test_colors, dtype=np.float32).reshape(-1, 1, 3)

fixtures["lut3dApply"] = []
for domain_min, domain_max in [((0, 0, 0), (1, 1, 1)), ((-0.05, -0.05, -0.05), (1.05, 1.05, 1.05))]:
    lut = Lut3D(lut_table, domain_min=domain_min, domain_max=domain_max, title="test")
    out = lut.apply(lut_input).reshape(-1, 3)
    fixtures["lut3dApply"].append({
        "size": lut_size,
        # table.flatten() on a (size,size,size,3) array is exactly the
        # [r,g,b,c]-indexed flat layout lut_engine.js's Lut3D expects --
        # no reshaping needed on the JS side.
        "table": lut_table.flatten().tolist(),
        "domainMin": list(domain_min),
        "domainMax": list(domain_max),
        "colors": lut_test_colors,
        "expected": out.tolist(),
    })

# .cube text written in the real R-fastest-then-G-then-B data-line order,
# encoding the same lut_table above -- a correct parseCube() should recover
# it exactly.
cube_lines = ['TITLE "Test LUT"', f"LUT_3D_SIZE {lut_size}"]
for b in range(lut_size):
    for g in range(lut_size):
        for r in range(lut_size):
            v = lut_table[r, g, b]
            cube_lines.append(f"{v[0]} {v[1]} {v[2]}")
cube_text = "\n".join(cube_lines)
cube_path = Path(__file__).resolve().parent / "_test.cube"
cube_path.write_text(cube_text, encoding="utf-8")
loaded = load_cube(cube_path)
cube_path.unlink()

fixtures["loadCube"] = {
    "text": cube_text,
    "expectedSize": loaded.size,
    "expectedTitle": loaded.title,
    "expectedTable": loaded.table.flatten().tolist(),
}

out_path = Path(__file__).resolve().parent / "fixtures.json"
out_path.write_text(json.dumps(fixtures))
print(f"wrote {out_path} ({out_path.stat().st_size} bytes)")
