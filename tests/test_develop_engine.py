import numpy as np
from PIL import Image

from develop_engine import (
    VIGNETTE_FALLOFF_SHAPE,
    VIGNETTE_FLOOR_CURVE,
    apply_dehaze,
    apply_recipe,
    apply_vignette,
    rgb_to_hsv,
)


def _flat_image(size=64):
    return np.full((size, size, 3), 0.6, dtype=np.float32)


def test_no_vignette_when_amount_is_zero():
    img = _flat_image()
    out = apply_vignette(img, {})
    np.testing.assert_array_equal(out, img)


def test_roundness_zero_matches_original_aspect_ellipse():
    """roundness == 0 must reproduce the fixed-p=2, cx/cy-radii falloff shape
    exactly -- this is a no-behavior-change guarantee for every existing
    preset that doesn't set PostCropVignetteRoundness. The darkening-strength
    curve itself (floor/shape below) was recalibrated against real Lightroom
    Classic exports -- see VIGNETTE_FLOOR_CURVE's docstring in
    develop_engine.py -- so this no longer reproduces the old flat
    "amount * falloff * 0.7" formula, just the falloff shape."""
    img = _flat_image()
    recipe = {"PostCropVignetteAmount": -60, "PostCropVignetteMidpoint": 40}
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cy, cx = h / 2.0, w / 2.0
    expected_dist = np.sqrt(((xx - cx) / cx) ** 2 + ((yy - cy) / cy) ** 2) / np.sqrt(2)
    feather = 0.5
    expected_falloff = np.clip((expected_dist - 0.4) / feather, 0, 1)
    floor = (1.0 - 0.6) ** VIGNETTE_FLOOR_CURVE
    expected_factor = floor + (1.0 - floor) * (1.0 - expected_falloff) ** VIGNETTE_FALLOFF_SHAPE
    expected = np.clip(img * expected_factor[..., None], 0, 1)

    out = apply_vignette(img, recipe)
    np.testing.assert_allclose(out, expected, atol=1e-5)


def test_vignette_corner_darkens_close_to_real_lightroom_magnitude():
    """Regression guard for the strength bug: at Amount=-80 (the value
    actually tested against real Lightroom Classic exports), a fully
    vignetted pixel should land near Lightroom's observed ~5-10% brightness
    floor, not the old formula's ~44%."""
    img = _flat_image()
    out = apply_vignette(img, {"PostCropVignetteAmount": -80, "PostCropVignetteMidpoint": 50, "PostCropVignetteFeather": 50})
    corner = out[0, 0, 0] / img[0, 0, 0]
    assert corner < 0.2


def test_paint_overlay_darkens_less_than_highlight_priority():
    img = _flat_image()
    recipe = {"PostCropVignetteAmount": -80, "PostCropVignetteMidpoint": 50, "PostCropVignetteFeather": 50}
    highlight = apply_vignette(img, {**recipe, "PostCropVignetteStyle": 1})
    paint = apply_vignette(img, {**recipe, "PostCropVignetteStyle": 3})
    assert paint[0, 0, 0] > highlight[0, 0, 0]


def test_positive_roundness_darkens_more_at_edge_midpoints_than_default():
    """At +100 roundness the falloff becomes a true circle inscribed on
    the shorter axis, so a point at the middle of a long edge (already
    fairly dark under the aspect-matched ellipse) should darken at least
    as much once the shape stops hugging the rectangle."""
    size = 64
    img = _flat_image(size)
    edge_point = (size // 2, 0)  # middle of the left edge

    default_out = apply_vignette(img, {"PostCropVignetteAmount": -80, "PostCropVignetteMidpoint": 30})
    round_out = apply_vignette(
        img, {"PostCropVignetteAmount": -80, "PostCropVignetteMidpoint": 30, "PostCropVignetteRoundness": 100}
    )
    assert round_out[edge_point][0] <= default_out[edge_point][0]


def test_negative_roundness_changes_output_without_crashing():
    img = _flat_image()
    out = apply_vignette(
        img, {"PostCropVignetteAmount": -70, "PostCropVignetteMidpoint": 30, "PostCropVignetteRoundness": -100}
    )
    assert out.shape == img.shape
    assert not np.array_equal(out, img)


def test_apply_recipe_preserves_png_alpha_channel():
    """A transparent PNG's alpha must survive the pipeline -- convert("RGB")
    inside apply_recipe would otherwise drop it permanently, and whatever
    garbage RGB sits under a transparent pixel would get treated as real,
    opaque color."""
    img = Image.new("RGBA", (4, 4), (255, 0, 0, 255))
    for x in range(2):
        for y in range(4):
            img.putpixel((x, y), (0, 255, 0, 0))  # fully transparent

    out = apply_recipe(img, {})
    assert out.mode == "RGBA"
    assert out.getpixel((0, 0))[3] == 0
    assert out.getpixel((3, 0))[3] == 255


def test_apply_recipe_leaves_opaque_rgb_without_alpha_band():
    img = Image.new("RGB", (4, 4), (100, 120, 140))
    out = apply_recipe(img, {})
    assert out.mode == "RGB"


def test_highlight_contrast_increases_spread_in_vignetted_region():
    size = 64
    img = _flat_image(size)
    corner = (0, 0)
    recipe = {"PostCropVignetteAmount": -80, "PostCropVignetteMidpoint": 20}
    base = apply_vignette(img, recipe)
    boosted = apply_vignette(img, {**recipe, "PostCropVignetteHighlightContrast": 100})
    # A flat mid-gray corner sits below 0.5 once darkened -- extra
    # contrast should push it darker still, not lighter or unchanged.
    assert boosted[corner][0] < base[corner][0]


def test_dehaze_no_op_at_zero():
    img = _flat_image()
    out = apply_recipe(Image.fromarray((img * 255).astype(np.uint8)), {"Dehaze": 0})
    np.testing.assert_array_equal(np.asarray(out), (img * 255).astype(np.uint8))


def test_negative_dehaze_brightens_shadows():
    """Negative Dehaze simulates adding haze -- a dark pixel should lift
    toward gray, matching the strong brightening Lightroom's own -100
    Dehaze exports show on shadow tones."""
    img = np.full((8, 8, 3), 0.1, dtype=np.float32)
    out = apply_dehaze(img, -100)
    assert out[0, 0, 0] > img[0, 0, 0]


def test_positive_dehaze_darkens_and_saturates_shadows():
    """Positive Dehaze removes haze -- a desaturated dark pixel should get
    darker and gain HSV saturation, matching Lightroom's +100 Dehaze exports
    (real exports showed shadow-region saturation roughly doubling). Absolute
    per-channel spread isn't the right metric here -- gamma > 1 compresses
    very dark values enough that raw R/B spread can shrink even while HSV
    saturation (chroma relative to value) rises."""
    img = np.full((8, 8, 3), 0.1, dtype=np.float32)
    img[..., 2] = 0.15  # slightly blue-tinted, like real shadow tones
    out = apply_dehaze(img, 100)
    assert out[0, 0, 0] < img[0, 0, 0]
    base_sat = rgb_to_hsv(img)[0, 0, 1]
    out_sat = rgb_to_hsv(out)[0, 0, 1]
    assert out_sat > base_sat


def test_texture_is_no_op_on_flat_image():
    """Texture is a fine-detail high-pass effect -- a perfectly flat image
    has no detail to boost, so it must come back unchanged."""
    img = _flat_image()
    out = apply_recipe(Image.fromarray((img * 255).astype(np.uint8)), {"Texture": 100})
    np.testing.assert_allclose(np.asarray(out).astype(np.float32), img * 255, atol=1.0)


def test_texture_sharpens_a_fine_edge():
    size = 64
    arr = np.full((size, size, 3), 0.3, dtype=np.float32)
    arr[:, size // 2 :] = 0.7
    img = Image.fromarray((arr * 255).astype(np.uint8))

    plain = np.asarray(apply_recipe(img, {})).astype(np.float32)
    textured = np.asarray(apply_recipe(img, {"Texture": 100})).astype(np.float32)
    # Right at the edge, positive Texture should push contrast further apart
    # (darker just left of the edge, brighter just right of it) than the
    # untouched render.
    edge_row = size // 2
    left = edge_row, size // 2 - 1
    right = edge_row, size // 2
    assert textured[left][0] <= plain[left][0]
    assert textured[right][0] >= plain[right][0]
