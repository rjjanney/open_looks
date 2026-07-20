"""Parse Adobe Camera Raw (crs:) .xmp develop presets into plain-dict
recipes -- the same format Lightroom Classic and Adobe Camera Raw use for
"develop presets", which is what most free/paid preset packs across the web
are actually distributed as.

parse_xmp_bytes() is the only real logic here: every crs: attribute on the
rdf:Description element, plus the handful of settings Adobe stores as
nested rdf:Seq lists (tone curves, per-channel HSL arrays). Everything else
in this module is just "find .xmp files in X and run that parser on them" --
a loose file, a folder of them, or a zip someone shared a whole pack as.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any

import xml.etree.ElementTree as ET

NS = {
    "x": "adobe:ns:meta/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "crs": "http://ns.adobe.com/camera-raw-settings/1.0/",
}

_NUM_RE = re.compile(r"^[+-]?\d+(\.\d+)?$")


def _coerce(value: str) -> Any:
    """Turn an XMP attribute string into an int/float/bool/str."""
    if value in ("True", "False"):
        return value == "True"
    if _NUM_RE.match(value):
        return float(value) if "." in value else int(value)
    return value


# crs: fields that real preset exports (Lightroom, ON1, PK Edits, ...)
# write on every single preset with a fixed no-op value regardless of
# whether that preset actually touches the control -- e.g. ON1's whole
# Signature Collection pack writes Dehaze="0" on all 60 presets, including
# ones that obviously never used haze removal. develop_engine.py doesn't
# render any of these, but warning about every one of them on every import
# would just be noise; only flag a preset that set one away from its
# no-op default.
_IGNORED_SCALAR_DEFAULTS: dict[str, float] = {
    "Dehaze": 0,
    "Texture": 0,
    "Temperature": 0,
    "Tint": 0,
    "ColorGradeShadowHue": 0,
    "ColorGradeShadowSat": 0,
    "ColorGradeShadowLum": 0,
    "ColorGradeMidtoneHue": 0,
    "ColorGradeMidtoneSat": 0,
    "ColorGradeMidtoneLum": 0,
    "ColorGradeHighlightHue": 0,
    "ColorGradeHighlightSat": 0,
    "ColorGradeHighlightLum": 0,
    "ColorGradeGlobalHue": 0,
    "ColorGradeGlobalSat": 0,
    "ColorGradeGlobalLum": 0,
    "PostCropVignetteStyle": 0,
    "PostCropVignetteRoundness": 0,
    "PostCropVignetteHighlightContrast": 0,
}

# Nested crs: fields holding local/masked adjustments (brush masks, linear
# and radial gradients, range masks). Unlike the scalars above, there's no
# meaningful "default" for these -- if one is present with actual entries,
# a real local edit exists and develop_engine.py (global-only) drops it.
_LOCAL_ADJUSTMENT_FIELDS = {
    "MaskGroupBasedCorrections",
    "PaintBasedCorrections",
    "GradientBasedCorrections",
    "CircularGradientBasedCorrections",
}


def _has_real_point_colors(elem: ET.Element) -> bool:
    """PointColors (Point Color grading) is written by every preset tool
    we've seen as a fixed block of -1 sentinels when unused. Only treat it
    as real, unsupported content if some value actually differs."""
    for li in elem.iter("{" + NS["rdf"] + "}li"):
        for token in (li.text or "").split(","):
            token = token.strip()
            if not token:
                continue
            try:
                if float(token) != -1.0:
                    return True
            except ValueError:
                return True
    return False


def _describe_unsupported(desc: ET.Element) -> list[str]:
    """Best-effort scan for develop settings this app parses but can't
    render -- not exhaustive, just the fields real preset packs (ON1, PK
    Edits, Lightroom exports) actually set in practice."""
    warnings: list[str] = []
    crs_tag = "{" + NS["crs"] + "}"

    for field, default in _IGNORED_SCALAR_DEFAULTS.items():
        raw = desc.get(crs_tag + field)
        if raw is not None and _coerce(raw) != default:
            warnings.append(f"{field} is set but not rendered (ignored)")

    for elem in desc.iter():
        if not elem.tag.startswith(crs_tag):
            continue
        field = elem.tag.split("}", 1)[1]
        if field in _LOCAL_ADJUSTMENT_FIELDS and elem.find(".//rdf:li", NS) is not None:
            warnings.append(f"{field} (local mask/gradient adjustment) is not rendered")
        elif field == "PointColors" and _has_real_point_colors(elem):
            warnings.append("PointColors (Point Color grading) is not rendered")

    return warnings


def _parse_seq_points(elem: ET.Element) -> list[tuple[float, float]]:
    """Parse a <crs:ToneCurvePV2012>/<rdf:Seq><rdf:li>x, y</rdf:li>...</rdf:Seq> block.

    Some newer crs: fields (e.g. PointColors) also nest an rdf:Seq but pack
    many comma-separated values into each rdf:li instead of a plain x, y
    pair -- skip those entries rather than mis-parsing them as a 2-tuple."""
    points = []
    seq = elem.find("rdf:Seq", NS)
    if seq is None:
        return points
    for li in seq.findall("rdf:li", NS):
        text = (li.text or "").strip()
        if text.count(",") != 1:
            continue
        x_str, y_str = text.split(",", 1)
        points.append((float(x_str.strip()), float(y_str.strip())))
    return points


def parse_xmp_bytes(data: bytes, name: str) -> dict[str, Any]:
    root = ET.fromstring(data)
    desc = root.find(".//rdf:Description", NS)
    if desc is None:
        raise ValueError(f"{name}: no rdf:Description found -- not a Camera Raw .xmp preset")

    recipe: dict[str, Any] = {"preset_name": name}

    for key, value in desc.attrib.items():
        if key.startswith("{" + NS["crs"] + "}"):
            field = key.split("}", 1)[1]
            recipe[field] = _coerce(value)

    crs_tag = "{" + NS["crs"] + "}"
    for child in desc:
        if not child.tag.startswith(crs_tag):
            continue
        field = child.tag.split("}", 1)[1]
        if child.find("rdf:Seq", NS) is not None and field not in recipe:
            points = _parse_seq_points(child)
            if points:
                recipe[field] = points

    warnings = _describe_unsupported(desc)
    if warnings:
        recipe["_import_warnings"] = warnings

    return recipe


def load_xmp_file(path: str | Path) -> dict[str, Any]:
    """Parse a single loose .xmp file."""
    path = Path(path)
    return parse_xmp_bytes(path.read_bytes(), path.stem)


def load_xmp_folder(folder: str | Path, recursive: bool = True) -> dict[str, dict[str, Any]]:
    """Parse every .xmp file directly in (or, by default, anywhere under) a
    folder. Returns {preset_name: recipe_dict}; a file that fails to parse
    (not actually a Camera Raw preset) is skipped, not fatal."""
    folder = Path(folder)
    pattern = "**/*.xmp" if recursive else "*.xmp"
    presets: dict[str, dict[str, Any]] = {}
    for path in folder.glob(pattern):
        try:
            presets[path.stem] = load_xmp_file(path)
        except Exception:
            continue
    return presets


def load_xmp_zip(zip_path: str | Path) -> dict[str, dict[str, Any]]:
    """Parse every .xmp file inside a zip archive (common distribution
    format for shared preset packs) without extracting it to disk first."""
    presets: dict[str, dict[str, Any]] = {}
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if not info.filename.lower().endswith(".xmp"):
                continue
            name = Path(info.filename).stem
            with zf.open(info) as f:
                data = f.read()
            try:
                presets[name] = parse_xmp_bytes(data, name)
            except Exception:
                continue
    return presets


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("usage: python xmp_importer.py <file.xmp | folder | pack.zip> [preset_name_to_dump]")
        raise SystemExit(1)

    target = Path(sys.argv[1])
    if target.is_dir():
        presets = load_xmp_folder(target)
    elif target.suffix.lower() == ".zip":
        presets = load_xmp_zip(target)
    else:
        presets = {target.stem: load_xmp_file(target)}

    print(f"Parsed {len(presets)} preset(s):")
    for name in sorted(presets):
        print(" -", name)

    if len(sys.argv) > 2:
        print(json.dumps(presets[sys.argv[2]], indent=2))
