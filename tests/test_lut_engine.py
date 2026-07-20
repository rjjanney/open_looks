import numpy as np

from lut_engine import Lut3D, load_cube


def test_identity_lut_preserves_image_values():
    n = 4
    axis = np.linspace(0, 1, n, dtype=np.float32)
    table = np.zeros((n, n, n, 3), dtype=np.float32)
    for ri, r in enumerate(axis):
        for gi, g in enumerate(axis):
            for bi, b in enumerate(axis):
                table[ri, gi, bi] = (r, g, b)
    lut = Lut3D(table)

    rng = np.random.default_rng(0)
    img = rng.random((8, 8, 3)).astype(np.float32)
    out = lut.apply(img)
    np.testing.assert_allclose(out, img, atol=1e-5)


def test_load_cube_axis_order(tmp_path):
    """.cube data lines vary R fastest, then G, then B. Only the (r=1,
    g=0, b=0) corner gets a non-identity marker color, so a transpose
    bug in load_cube's reshape shows up as the marker landing at the
    wrong table index instead of table[1, 0, 0]."""
    marker = (0.9, 0.2, 0.1)
    corners = {
        (0, 0, 0): (0.0, 0.0, 0.0),
        (1, 0, 0): marker,
        (0, 1, 0): (0.0, 1.0, 0.0),
        (1, 1, 0): (1.0, 1.0, 0.0),
        (0, 0, 1): (0.0, 0.0, 1.0),
        (1, 0, 1): (1.0, 0.0, 1.0),
        (0, 1, 1): (0.0, 1.0, 1.0),
        (1, 1, 1): (1.0, 1.0, 1.0),
    }
    lines = ['TITLE "axis order test"', "LUT_3D_SIZE 2"]
    for b in (0, 1):
        for g in (0, 1):
            for r in (0, 1):
                rr, gg, bb = corners[(r, g, b)]
                lines.append(f"{rr} {gg} {bb}")
    cube_path = tmp_path / "test.cube"
    cube_path.write_text("\n".join(lines), encoding="utf-8")

    lut = load_cube(cube_path)
    assert lut.title == "axis order test"
    np.testing.assert_allclose(lut.table[1, 0, 0], marker, atol=1e-6)
    np.testing.assert_allclose(lut.table[0, 0, 0], (0.0, 0.0, 0.0), atol=1e-6)
    np.testing.assert_allclose(lut.table[1, 1, 1], (1.0, 1.0, 1.0), atol=1e-6)
