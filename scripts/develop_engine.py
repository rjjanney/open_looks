"""A small approximation of an Adobe Camera Raw / Lightroom develop pipeline,
built on Pillow + numpy + OpenCV (OpenCV is used only for its fast C++
Gaussian blur -- everything else stays plain numpy).

It is NOT a pixel-perfect reimplementation of Adobe's proprietary math -- the
exact curve shaping, highlight recovery and B&W-mixer hue-band formulas are
undocumented. It reproduces the *shape* of what each control does (parametric
regions, hue-banded gray mixer, split toning, grain, sharpening, vignette)
driven by the exact slider values pulled from the real presets, which is
where most of the visual character actually comes from.

Recipes are plain dicts using Adobe's crs: field names (see xmp_importer.py).
xmp_importer.py normalizes Lightroom presets into this same schema, so this
one engine drives presets regardless of where they came from -- Lightroom
.xmp, hand-written recipes, or a 3D .cube LUT layered on top.
"""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image, ImageFilter

from lut_engine import Lut3D  # noqa: F401 -- re-exported for callers building recipes


def gaussian_blur(arr: np.ndarray, radius: float) -> np.ndarray:
    """Blur a float array (2D or 3D) with OpenCV -- much faster than PIL's
    GaussianBlur for the array sizes/radii used here, and works directly on
    float data with no uint8/PIL round-trip."""
    return cv2.GaussianBlur(arr, (0, 0), sigmaX=radius, sigmaY=radius, borderType=cv2.BORDER_REFLECT)

# ---------------------------------------------------------------------------
# color space helpers (vectorized, numpy-only)
# ---------------------------------------------------------------------------

def rgb_to_hsv(rgb: np.ndarray) -> np.ndarray:
    """rgb: (...,3) float in [0,1] -> hsv: (...,3), h in [0,360), s,v in [0,1].

    Delegates to OpenCV's cvtColor -- ~65x faster than the hand-rolled numpy
    version (a chain of a dozen-plus full-array np.where/np.select temporaries)
    for the same result to within float precision. Reshaped to (N,1,3) so it
    works uniformly on both a full (H,W,3) image and a handful of loose
    (N,3) colors (e.g. split-toning's single-pixel hue lookup)."""
    orig_shape = rgb.shape
    arr = rgb.astype(np.float32, copy=False).reshape(-1, 1, 3)
    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)
    return hsv.reshape(orig_shape)


def hsv_to_rgb(hsv: np.ndarray) -> np.ndarray:
    """Inverse of rgb_to_hsv, same OpenCV-backed approach."""
    orig_shape = hsv.shape
    arr = hsv.astype(np.float32, copy=False).reshape(-1, 1, 3)
    rgb = cv2.cvtColor(arr, cv2.COLOR_HSV2RGB)
    return rgb.reshape(orig_shape)


def luminance(rgb: np.ndarray) -> np.ndarray:
    return rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114


# ---------------------------------------------------------------------------
# hue-band helpers, shared by the gray mixer and the 8-band HSL sliders
# ---------------------------------------------------------------------------

# Anchor hues (degrees) for Adobe's 8 color bands, standard color-wheel
# positions -- close enough to Adobe's real (undocumented) anchors for our
# purposes since the curve/grain/split-tone are doing most of the work.
_BAND_HUES = {
    "Red": 0,
    "Orange": 30,
    "Yellow": 60,
    "Green": 120,
    "Aqua": 180,
    "Blue": 240,
    "Purple": 275,
    "Magenta": 315,
}
_BAND_ORDER = ["Red", "Orange", "Yellow", "Green", "Aqua", "Blue", "Purple", "Magenta"]


def hue_band_weights(hue_deg: np.ndarray, values: dict[str, float]) -> np.ndarray:
    """Circularly interpolate the 8 per-band slider values across a hue array."""
    anchors_h = np.array([_BAND_HUES[b] for b in _BAND_ORDER], dtype=float)
    anchors_v = np.array([values.get(b, 0.0) for b in _BAND_ORDER], dtype=float)
    # wrap for circular interpolation
    anchors_h = np.concatenate([anchors_h - 360, anchors_h, anchors_h + 360])
    anchors_v = np.concatenate([anchors_v, anchors_v, anchors_v])
    # np.interp always returns float64; cast back down so it doesn't silently
    # upcast the float32 image arrays it gets multiplied into downstream.
    return np.interp(hue_deg, anchors_h, anchors_v).astype(np.float32)


# ---------------------------------------------------------------------------
# tone curve construction
# ---------------------------------------------------------------------------

def parametric_curve_lut(recipe: dict) -> np.ndarray:
    shadows = recipe.get("ParametricShadows", 0) / 100.0
    darks = recipe.get("ParametricDarks", 0) / 100.0
    lights = recipe.get("ParametricLights", 0) / 100.0
    highlights = recipe.get("ParametricHighlights", 0) / 100.0
    ss = recipe.get("ParametricShadowSplit", 25) / 100.0
    ms = recipe.get("ParametricMidtoneSplit", 50) / 100.0
    hs = recipe.get("ParametricHighlightSplit", 75) / 100.0

    if shadows == darks == lights == highlights == 0:
        return np.linspace(0, 1, 256, dtype=np.float32)

    strength = 0.35  # how far a slider at +/-100 pushes its anchor
    xs = np.array([0.0, ss, ms, hs, 1.0])
    ys = np.array(
        [
            0.0 + shadows * strength,
            ss + darks * strength,
            ms,
            hs + lights * strength,
            1.0 + highlights * strength,
        ]
    )
    xs, order = np.unique(xs, return_index=True)
    ys = ys[order]
    lut_x = np.linspace(0, 1, 256)
    lut = np.interp(lut_x, xs, ys).astype(np.float32)
    return np.clip(lut, 0, 1)


def point_curve_lut(points: list[tuple[float, float]] | None) -> np.ndarray:
    lut_x = np.linspace(0, 255, 256, dtype=np.float32)
    if not points or len(points) < 2:
        return lut_x / 255.0
    pts = sorted(points)
    xs = np.array([p[0] for p in pts])
    ys = np.array([p[1] for p in pts])
    lut = np.interp(lut_x, xs, ys).astype(np.float32)
    return np.clip(lut / 255.0, 0, 1)


def apply_lut(channel: np.ndarray, lut: np.ndarray) -> np.ndarray:
    idx = np.clip((channel * 255).astype(np.int32), 0, 255)
    return lut[idx]


# ---------------------------------------------------------------------------
# basic tone controls
# ---------------------------------------------------------------------------

TEXTURE_REFERENCE_WIDTH = 640  # the width Texture's blur radius was tuned against (see below)
TEXTURE_BLUR_RADIUS = 1.6
TEXTURE_STRENGTH = 0.4

# Dehaze gamma/saturation coefficients below were fit against real Lightroom
# Classic exports (isolated Dehaze -100/-50/+50/+100 presets vs. a plain
# reset render of the same photo): binning by input luminance and fitting
# out = in**gamma matched Lightroom's actual per-level tone curve to within
# ~0.5-3% luminance across the whole range. Positive/negative use separate
# quadratics because Lightroom's response is visibly asymmetric -- negative
# Dehaze (adding haze) departs from gamma=1 faster than positive Dehaze
# (removing haze) does. sat_boost is an additional saturation multiplier on
# top of gamma's own (much weaker) implicit saturation shift, needed because
# per-channel gamma alone undershot Lightroom's real saturation change at
# every level tested.
DEHAZE_POS_GAMMA = (0.273, 0.278)   # gamma = 1 + a*d + b*d**2, d = dehaze/100
DEHAZE_NEG_GAMMA = (0.861, 0.218)   # gamma = 1 - a*e + b*e**2, e = -dehaze/100
DEHAZE_POS_SAT = (0.271, 0.014)     # sat_boost = a*d + b*d**2
DEHAZE_NEG_SAT = (0.057, 0.33)      # sat_boost = -(a*e + b*e**2)


def apply_dehaze(img: np.ndarray, dehaze: float) -> np.ndarray:
    d = dehaze / 100.0
    if d >= 0:
        a, b = DEHAZE_POS_GAMMA
        gamma = 1.0 + a * d + b * d * d
        a, b = DEHAZE_POS_SAT
        sat_boost = a * d + b * d * d
    else:
        e = -d
        a, b = DEHAZE_NEG_GAMMA
        gamma = 1.0 - a * e + b * e * e
        a, b = DEHAZE_NEG_SAT
        sat_boost = -(a * e + b * e * e)

    img = np.clip(img, 0.0, 1.0) ** gamma
    if sat_boost:
        lum = luminance(img)[..., None]
        img = lum + (img - lum) * (1.0 + sat_boost)
    return img


def apply_basic_tone(img: np.ndarray, recipe: dict) -> np.ndarray:
    exposure = recipe.get("Exposure2012", 0.0)
    if exposure:
        img = img * (2.0 ** exposure)

    contrast = recipe.get("Contrast2012", 0) / 100.0
    if contrast:
        img = 0.5 + (img - 0.5) * (1 + contrast)

    blacks = recipe.get("Blacks2012", 0) / 100.0
    whites = recipe.get("Whites2012", 0) / 100.0
    lo = np.clip(0.0 + blacks * 0.2, -0.5, 0.9)
    hi = np.clip(1.0 + whites * 0.2, 0.1, 1.5)
    if lo != 0.0 or hi != 1.0:
        img = (img - lo) / max(hi - lo, 1e-6)

    lum = luminance(img)[..., None]
    shadows = recipe.get("Shadows2012", 0) / 100.0
    if shadows:
        mask = np.clip(1.0 - lum / 0.5, 0, 1) ** 1.5
        img = img + shadows * 0.4 * mask
    highlights = recipe.get("Highlights2012", 0) / 100.0
    if highlights:
        mask = np.clip((lum - 0.5) / 0.5, 0, 1) ** 1.5
        img = img + highlights * 0.4 * mask

    texture = recipe.get("Texture", 0) / 100.0
    if texture:
        lum = luminance(img)
        radius = max(TEXTURE_BLUR_RADIUS * (img.shape[1] / TEXTURE_REFERENCE_WIDTH), 0.15)
        fine_blur = gaussian_blur(lum, radius=radius)
        fine_detail = (lum - fine_blur)[..., None]
        img = img + fine_detail * texture * TEXTURE_STRENGTH

    clarity = recipe.get("Clarity2012", 0) / 100.0
    if clarity:
        lum = luminance(img)
        blurred = gaussian_blur(lum, radius=25)
        detail = (lum - blurred)[..., None]
        img = img + detail * clarity * 1.2

    dehaze = recipe.get("Dehaze", 0)
    if dehaze:
        img = apply_dehaze(img, dehaze)

    return np.clip(img, 0, 1)


# ---------------------------------------------------------------------------
# grayscale conversion (Adobe-style B&W mixer)
# ---------------------------------------------------------------------------

def apply_grayscale_mixer(img: np.ndarray, recipe: dict) -> np.ndarray:
    hsv = rgb_to_hsv(img)
    hue, sat = hsv[..., 0], hsv[..., 1]
    mixer = {b: recipe.get(f"GrayMixer{b}", 0) for b in _BAND_ORDER}
    weight = hue_band_weights(hue, mixer)  # -100..100
    base = luminance(img)
    gray = base * (1.0 + (weight / 100.0) * sat * 1.1)
    gray = np.clip(gray, 0, 1)
    return np.stack([gray, gray, gray], axis=-1)


# ---------------------------------------------------------------------------
# HSL hue/saturation/luminance 8-band adjustments (color looks)
# ---------------------------------------------------------------------------

def apply_hsl_bands(img: np.ndarray, recipe: dict) -> np.ndarray:
    keys = [f"HueAdjustment{b}" for b in _BAND_ORDER] + [
        f"SaturationAdjustment{b}" for b in _BAND_ORDER
    ] + [f"LuminanceAdjustment{b}" for b in _BAND_ORDER]
    if not any(recipe.get(k, 0) for k in keys):
        return img

    hsv = rgb_to_hsv(img)
    hue, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]

    hue_vals = {b: recipe.get(f"HueAdjustment{b}", 0) for b in _BAND_ORDER}
    sat_vals = {b: recipe.get(f"SaturationAdjustment{b}", 0) for b in _BAND_ORDER}
    lum_vals = {b: recipe.get(f"LuminanceAdjustment{b}", 0) for b in _BAND_ORDER}

    hue_shift = hue_band_weights(hue, hue_vals)  # -100..100 -> up to +-100 degrees is too strong; scale down
    sat_shift = hue_band_weights(hue, sat_vals)
    lum_shift = hue_band_weights(hue, lum_vals)

    new_hue = (hue + hue_shift * 0.3) % 360
    new_sat = np.clip(sat * (1 + sat_shift / 100.0), 0, 1)
    new_val = np.clip(val * (1 + lum_shift / 100.0 * 0.5), 0, 1)

    out = hsv_to_rgb(np.stack([new_hue, new_sat, new_val], axis=-1))
    return np.clip(out, 0, 1)


# ---------------------------------------------------------------------------
# saturation / vibrance
# ---------------------------------------------------------------------------

def apply_saturation_vibrance(img: np.ndarray, recipe: dict) -> np.ndarray:
    saturation = recipe.get("Saturation", 0) / 100.0
    vibrance = recipe.get("Vibrance", 0) / 100.0
    if not saturation and not vibrance:
        return img
    hsv = rgb_to_hsv(img)
    sat = hsv[..., 1]
    if saturation:
        sat = sat * (1 + saturation)
    if vibrance:
        protect = 1.0 - sat  # push low-sat pixels harder, protect already-saturated ones
        sat = sat + vibrance * protect * sat.clip(0, 1) * 1.5
    hsv[..., 1] = np.clip(sat, 0, 1)
    return np.clip(hsv_to_rgb(hsv), 0, 1)


# ---------------------------------------------------------------------------
# split toning
# ---------------------------------------------------------------------------

def apply_split_toning(img: np.ndarray, recipe: dict) -> np.ndarray:
    sh_hue = recipe.get("SplitToningShadowHue", 0)
    sh_sat = recipe.get("SplitToningShadowSaturation", 0)
    hi_hue = recipe.get("SplitToningHighlightHue", 0)
    hi_sat = recipe.get("SplitToningHighlightSaturation", 0)
    balance = recipe.get("SplitToningBalance", 0) / 100.0
    if not sh_sat and not hi_sat:
        return img

    lum = luminance(img)
    mid = 0.5 + balance * 0.3
    shadow_w = np.clip(1.0 - lum / max(mid, 1e-3), 0, 1)[..., None]
    highlight_w = np.clip((lum - mid) / max(1 - mid, 1e-3), 0, 1)[..., None]

    def hue_to_rgb(h):
        hsv = np.array([[h, 1.0, 1.0]])
        return hsv_to_rgb(hsv)[0]

    out = img.copy()
    if sh_sat:
        color = hue_to_rgb(sh_hue)
        out = out + shadow_w * (color - 0.5) * (sh_sat / 100.0) * 0.6
    if hi_sat:
        color = hue_to_rgb(hi_hue)
        out = out + highlight_w * (color - 0.5) * (hi_sat / 100.0) * 0.6
    return np.clip(out, 0, 1)


# ---------------------------------------------------------------------------
# grain
# ---------------------------------------------------------------------------

# blur_radius below was tuned by eye against full-resolution (~4096px-wide)
# renders -- that's the reference this scales relative to. Applying that
# same *absolute* pixel radius unscaled to a much smaller render (like the
# app's 448px preview) makes the grain clumps relatively much bigger and
# coarser than intended, since they're a bigger fraction of a smaller
# image -- that's the "shimmery" chunky look at preview size. Scaling the
# radius down proportionally for smaller renders keeps the *apparent*
# grain size consistent with the full-res look this was actually tuned
# against, instead of full-res being the odd one out.
GRAIN_REFERENCE_WIDTH = 4096
GRAIN_SIZE_SCALE = 0.85  # global 15% trim on grain clump size, tuned by eye


def apply_grain(img: np.ndarray, recipe: dict, seed: int | None = None) -> np.ndarray:
    amount = recipe.get("GrainAmount", 0) / 100.0
    if not amount:
        return img
    size = max(recipe.get("GrainSize", 25), 1)
    frequency = recipe.get("GrainFrequency", 50)

    h, w = img.shape[:2]
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, 1, size=(h, w)).astype(np.float32)

    blur_radius = (0.3 + (size / 100.0) * 1.6) * GRAIN_SIZE_SCALE * (w / GRAIN_REFERENCE_WIDTH)
    blur_radius = max(blur_radius, 0.15)  # cv2.GaussianBlur needs a positive radius
    noise = gaussian_blur(noise, radius=blur_radius)
    noise = (noise - noise.mean()) / (noise.std() + 1e-9)

    detail_scale = 0.6 + (frequency / 100.0) * 0.8
    grain_layer = noise * detail_scale

    out = img + grain_layer[..., None] * amount * 0.12
    return np.clip(out, 0, 1)


# ---------------------------------------------------------------------------
# vignette
# ---------------------------------------------------------------------------

def _vignette_distance(xx: np.ndarray, yy: np.ndarray, cx: float, cy: float, roundness: float) -> np.ndarray:
    """Distance-from-center field for the vignette falloff, shaped by
    roundness (-1..1). 0 reproduces the original aspect-matched ellipse
    (a plain p=2 norm with radii cx/cy). Positive roundness blends the
    radii toward equal (min(cx, cy)) so it approaches a true circle at
    +1. Negative roundness raises the norm's exponent instead, which
    flattens the ellipse toward a rounded rectangle/"squircle" -- there's
    no separate radius to shrink toward for a *more* rectangular shape,
    so the exponent is the only knob available."""
    if roundness >= 0:
        p = 2.0
        r = min(cx, cy)
        rx = cx + (r - cx) * roundness
        ry = cy + (r - cy) * roundness
    else:
        p = 2.0 + 4.0 * (-roundness)  # up to 6 at roundness == -1
        rx, ry = cx, cy

    dx = np.abs(xx - cx) / rx
    dy = np.abs(yy - cy) / ry
    dist = (dx**p + dy**p) ** (1.0 / p)
    corner = ((cx / rx) ** p + (cy / ry) ** p) ** (1.0 / p)
    return dist / corner


# Calibrated against real Lightroom Classic exports at Amount=-80 (Midpoint
# 50, Feather 50, Roundness 0): binning pixels by `falloff` and comparing
# their actual corner/base brightness ratio showed the previous flat
# "amount * falloff * 0.7" model badly undershot the real effect (predicted
# corners ~3x brighter than Lightroom's, e.g. 62/255 vs. an actual 18/255).
# The real curve is `floor + (1-floor)*(1-falloff)**shape`, and critically
# `floor` (the fully-darkened corner brightness) drops much faster than
# Amount's own percentage would suggest -- Amount=-80 already lands within
# ~5% of full black, not 80%. There is no equivalent Lightroom export at a
# positive Amount, so the brightening branch below keeps the original
# unvalidated linear approximation rather than extrapolating this curve into
# untested territory.
VIGNETTE_FLOOR_CURVE = 1.8      # how fast the corner floor -> 0 as |Amount| -> 100
VIGNETTE_FALLOFF_SHAPE = 2.0    # shape of the brightness transition across the falloff band
VIGNETTE_PAINT_STRENGTH = 0.94  # Paint Overlay darkens measurably less than the other styles at the same Amount


def apply_vignette(img: np.ndarray, recipe: dict) -> np.ndarray:
    amount = recipe.get("PostCropVignetteAmount", 0) or recipe.get("VignetteAmount", 0)
    amount_frac = amount / 100.0
    if not amount_frac:
        return img
    midpoint = recipe.get("PostCropVignetteMidpoint", 50) / 100.0
    feather = max(recipe.get("PostCropVignetteFeather", 50), 1) / 100.0
    roundness = np.clip(recipe.get("PostCropVignetteRoundness", 0) / 100.0, -1.0, 1.0)
    highlight_contrast = recipe.get("PostCropVignetteHighlightContrast", 0) / 100.0
    # 1=Highlight Priority, 2=Color Priority, 3=Paint Overlay; Adobe's own
    # default when a vignette has no explicit style is Highlight Priority.
    style = recipe.get("PostCropVignetteStyle", 0) or 1

    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cy, cx = h / 2.0, w / 2.0
    dist = _vignette_distance(xx, yy, cx, cy, roundness)
    falloff = np.clip((dist - midpoint) / max(feather, 1e-3), 0, 1)

    if amount_frac < 0:
        strength = -amount_frac
        if style == 3:
            strength *= VIGNETTE_PAINT_STRENGTH
        floor = (1.0 - strength) ** VIGNETTE_FLOOR_CURVE
        factor = floor + (1.0 - floor) * (1.0 - falloff) ** VIGNETTE_FALLOFF_SHAPE
    else:
        factor = 1.0 + amount_frac * falloff * 0.7
    factor = factor.astype(np.float32)
    out = img * factor[..., None]

    # Highlight/Color Priority differentiation below is best-effort, per
    # Adobe's documented behavior rather than measurement -- the reference
    # photo's corners were too dark/desaturated to actually distinguish the
    # two styles (they produced byte-identical output there).
    if style == 1 and amount_frac < 0:
        # Highlight Priority: protect already-bright pixels from being
        # darkened as hard inside the vignette.
        bright = np.clip((luminance(img) - 0.7) / 0.3, 0, 1)[..., None]
        out = out + (img - out) * bright * falloff[..., None] * 0.3
    elif style == 2:
        # Color Priority: resist the vignetted region flattening toward gray.
        lum = luminance(out)[..., None]
        out = lum + (out - lum) * (1.0 + falloff[..., None] * 0.25)

    if highlight_contrast:
        # Extra contrast confined to the vignetted falloff region, so
        # the darkened corners don't just flatten toward mud -- weighted
        # by the same falloff mask used for the darkening itself.
        out = out + (out - 0.5) * highlight_contrast * falloff[..., None] * 0.5

    return np.clip(out, 0, 1)


# ---------------------------------------------------------------------------
# sharpening
# ---------------------------------------------------------------------------

def apply_sharpen(pil_img: Image.Image, recipe: dict) -> Image.Image:
    sharpness = recipe.get("Sharpness", 0)
    if not sharpness:
        return pil_img
    radius = recipe.get("SharpenRadius", 1.0)
    percent = int(min(sharpness * 3, 250))
    return pil_img.filter(ImageFilter.UnsharpMask(radius=radius, percent=percent, threshold=2))


# ---------------------------------------------------------------------------
# top level
# ---------------------------------------------------------------------------

def apply_recipe(pil_img: Image.Image, recipe: dict, grain_seed: int | None = None) -> Image.Image:
    # A source PNG's alpha channel would otherwise be silently dropped by
    # convert("RGB") below and never come back -- carry it around and
    # reattach it at the end instead. Everything in between (grain,
    # vignette, blur-based Clarity/sharpen) only ever touches RGB, so
    # transparent pixels' arbitrary underlying RGB can bleed slightly into
    # opaque edges through those blur steps -- a known, accepted
    # approximation here, not a full premultiplied-alpha pipeline.
    alpha = pil_img.getchannel("A") if "A" in pil_img.getbands() else None
    img = np.asarray(pil_img.convert("RGB")).astype(np.float32) / 255.0

    img = apply_basic_tone(img, recipe)

    # A 3D .cube LUT, if this recipe has one attached (see lut_engine.py) --
    # a LUT is fundamentally a color-space remap, so it applies early,
    # before the parametric tone curve / grayscale / grain stages, letting
    # a LUT-based preset still layer grain or split-toning on top if the
    # recipe defines them.
    lut3d = recipe.get("_lut3d")
    if lut3d is not None:
        img = lut3d.apply(img)

    master_lut = parametric_curve_lut(recipe)
    point_lut = point_curve_lut(recipe.get("ToneCurvePV2012"))
    combined_lut = np.interp(master_lut, np.linspace(0, 1, 256, dtype=np.float32), point_lut).astype(np.float32)
    for c in range(3):
        img[..., c] = apply_lut(img[..., c], combined_lut)

    for c, key in enumerate(["ToneCurvePV2012Red", "ToneCurvePV2012Green", "ToneCurvePV2012Blue"]):
        pts = recipe.get(key)
        if pts and len(pts) > 2:
            lut = point_curve_lut(pts)
            img[..., c] = apply_lut(img[..., c], lut)

    if not recipe.get("ConvertToGrayscale"):
        img = apply_hsl_bands(img, recipe)
        img = apply_saturation_vibrance(img, recipe)

    if recipe.get("ConvertToGrayscale"):
        img = apply_grayscale_mixer(img, recipe)

    img = apply_split_toning(img, recipe)
    img = apply_grain(img, recipe, seed=grain_seed)
    img = apply_vignette(img, recipe)

    out = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    out = apply_sharpen(out, recipe)
    if alpha is not None:
        out = out.convert("RGBA")
        out.putalpha(alpha)
    return out
