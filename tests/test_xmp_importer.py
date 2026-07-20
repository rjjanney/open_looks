import pytest

from xmp_importer import parse_xmp_bytes

XMP_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"
    {attrs}>
{body}
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
"""


def make_xmp(attrs: str = "", body: str = "") -> bytes:
    return XMP_TEMPLATE.format(attrs=attrs, body=body).encode("utf-8")


def _point_colors_body(values: list[str]) -> str:
    li_text = ", ".join(values)
    return f"""
    <crs:PointColors>
     <rdf:Seq>
      <rdf:li>{li_text}</rdf:li>
     </rdf:Seq>
    </crs:PointColors>
    """


def test_global_preset_parses_expected_fields():
    data = make_xmp(attrs='crs:Exposure2012="0.50" crs:Contrast2012="+25" crs:ConvertToGrayscale="False"')
    recipe = parse_xmp_bytes(data, "Simple Global")
    assert recipe["preset_name"] == "Simple Global"
    assert recipe["Exposure2012"] == 0.5
    assert recipe["Contrast2012"] == 25
    assert recipe["ConvertToGrayscale"] is False
    assert "_import_warnings" not in recipe


def test_tone_curve_parses_point_pairs():
    body = """
    <crs:ToneCurvePV2012>
     <rdf:Seq>
      <rdf:li>0, 0</rdf:li>
      <rdf:li>64, 80</rdf:li>
      <rdf:li>255, 255</rdf:li>
     </rdf:Seq>
    </crs:ToneCurvePV2012>
    """
    recipe = parse_xmp_bytes(make_xmp(body=body), "Curve")
    assert recipe["ToneCurvePV2012"] == [(0.0, 0.0), (64.0, 80.0), (255.0, 255.0)]


def test_point_colors_placeholder_does_not_crash_or_warn():
    """Every real-world preset we've checked (ON1, PK Edits) writes
    PointColors as 19 -1 sentinels when the feature is unused -- that
    must not crash the multi-value-per-li parsing and must not warn."""
    data = make_xmp(body=_point_colors_body(["-1.000000"] * 19))
    recipe = parse_xmp_bytes(data, "No Point Colors")
    assert "PointColors" not in recipe
    assert "_import_warnings" not in recipe


def test_point_colors_real_value_warns_without_crashing():
    values = ["-1.000000"] * 18 + ["45.0"]
    recipe = parse_xmp_bytes(make_xmp(body=_point_colors_body(values)), "Real Point Color")
    assert "PointColors" not in recipe  # still not mis-parsed as curve points
    assert any("PointColors" in w for w in recipe.get("_import_warnings", []))


def test_gradient_mask_produces_warning_and_does_not_crash():
    body = """
    <crs:GradientBasedCorrections>
     <rdf:Seq>
      <rdf:li rdf:parseType="Resource">
       <crs:What>Correction</crs:What>
       <crs:CorrectionAmount>1</crs:CorrectionAmount>
      </rdf:li>
     </rdf:Seq>
    </crs:GradientBasedCorrections>
    """
    recipe = parse_xmp_bytes(make_xmp(body=body), "Gradient Look")
    assert "GradientBasedCorrections" not in recipe
    assert any("GradientBasedCorrections" in w for w in recipe["_import_warnings"])


@pytest.mark.parametrize(
    "attrs,should_warn",
    [
        ('crs:Dehaze="0"', False),
        ('crs:Dehaze="25"', True),
        ('crs:Dehaze="-10"', True),
    ],
)
def test_dehaze_only_warns_when_non_default(attrs, should_warn):
    recipe = parse_xmp_bytes(make_xmp(attrs=attrs), "Dehaze Test")
    warnings = recipe.get("_import_warnings", [])
    assert any("Dehaze" in w for w in warnings) == should_warn


def test_vignette_style_warns_but_roundness_does_not():
    """PostCropVignetteStyle isn't rendered (Adobe's 3 blend modes aren't
    reproduced), but Roundness and HighlightContrast are actually applied
    by apply_vignette() now -- they must not be flagged as dropped."""
    attrs = (
        'crs:PostCropVignetteStyle="1" crs:PostCropVignetteRoundness="30" '
        'crs:PostCropVignetteHighlightContrast="40"'
    )
    warnings = parse_xmp_bytes(make_xmp(attrs=attrs), "Vignette Style").get("_import_warnings", [])
    assert any("PostCropVignetteStyle" in w for w in warnings)
    assert not any("PostCropVignetteRoundness" in w for w in warnings)
    assert not any("PostCropVignetteHighlightContrast" in w for w in warnings)
