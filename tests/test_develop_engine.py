import numpy as np
from PIL import Image

from develop_engine import apply_recipe, apply_vignette


def _flat_image(size=64):
    return np.full((size, size, 3), 0.6, dtype=np.float32)


def test_no_vignette_when_amount_is_zero():
    img = _flat_image()
    out = apply_vignette(img, {})
    np.testing.assert_array_equal(out, img)


def test_roundness_zero_matches_original_aspect_ellipse():
    """roundness == 0 must reproduce the original fixed-p=2, cx/cy-radii
    formula exactly -- this is a no-behavior-change guarantee for every
    existing preset that doesn't set PostCropVignetteRoundness."""
    img = _flat_image()
    recipe = {"PostCropVignetteAmount": -60, "PostCropVignetteMidpoint": 40}
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cy, cx = h / 2.0, w / 2.0
    expected_dist = np.sqrt(((xx - cx) / cx) ** 2 + ((yy - cy) / cy) ** 2) / np.sqrt(2)
    feather = 0.5
    expected_falloff = np.clip((expected_dist - 0.4) / feather, 0, 1)
    expected_factor = 1.0 + (-0.6) * expected_falloff * 0.7
    expected = np.clip(img * expected_factor[..., None], 0, 1)

    out = apply_vignette(img, recipe)
    np.testing.assert_allclose(out, expected, atol=1e-5)


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
