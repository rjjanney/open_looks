"""Convert a Fujifilm in-camera JPEG "recipe" (the menu-setting format
published by the Fuji X Weekly community: Film Simulation base, Highlight/
Shadow, Color, Clarity, Sharpening, Grain, White Balance shift, ...) into
our engine's recipe schema.

This is a best-effort creative translation, the same spirit as the
hand-tuned fuji_recipes.py originals, just applied programmatically across
several published recipes instead of by hand one at a time. The numeric
scale factors below are tuned by eye against a few sample photos, not
derived from Fuji's actual color science (which we don't have access to
either way -- see fuji_recipes.py's docstring).
"""
from __future__ import annotations

from typing import Any, TypedDict


class FujiMenu(TypedDict, total=False):
    film_simulation: str  # Provia | Velvia | Astia | ClassicChrome | ClassicNeg | Eterna | Acros | Monochrome | Sepia
    highlight: float       # -2..+4
    shadow: float           # -2..+4
    color: float             # -4..+4 (ignored for B&W bases)
    clarity: float           # -5..+5
    sharpening: float       # -4..+4
    grain_strength: str      # "Off" | "Weak" | "Strong"
    grain_size: str          # "Small" | "Large"
    color_chrome: str        # "Off" | "Weak" | "Strong"
    wb_red: float             # WB shift, roughly -9..+9
    wb_blue: float            # WB shift, roughly -9..+9


# Baseline character per Film Simulation, expressed directly in our recipe
# schema -- the menu sliders above are added on top of this.
_BASE: dict[str, dict[str, Any]] = {
    "Provia": {"Contrast2012": 8, "Saturation": 5},
    "Velvia": {"Contrast2012": 18, "Saturation": 15, "SaturationAdjustmentGreen": 12, "SaturationAdjustmentBlue": 14},
    "Astia": {"Contrast2012": -5, "Saturation": -5, "Shadows2012": 6},
    "ClassicChrome": {
        "Contrast2012": 12, "Saturation": -15, "SaturationAdjustmentGreen": -15,
        "SplitToningShadowHue": 205, "SplitToningShadowSaturation": 8, "SplitToningBalance": -10,
    },
    "ClassicNeg": {
        "Contrast2012": 4, "Saturation": -6, "SaturationAdjustmentYellow": -8,
        "SplitToningShadowHue": 140, "SplitToningShadowSaturation": 10,
        "SplitToningHighlightHue": 45, "SplitToningHighlightSaturation": 8,
    },
    "Eterna": {"Contrast2012": -14, "Saturation": -22, "Shadows2012": 10, "Highlights2012": -8},
    "Acros": {
        "ConvertToGrayscale": True, "Contrast2012": 14,
        "GrayMixerRed": 15, "GrayMixerOrange": 8, "GrayMixerBlue": -12,
    },
    "Monochrome": {"ConvertToGrayscale": True, "Contrast2012": 6},
    "Sepia": {
        "ConvertToGrayscale": True, "Contrast2012": 4,
        "SplitToningShadowHue": 40, "SplitToningShadowSaturation": 22,
        "SplitToningHighlightHue": 45, "SplitToningHighlightSaturation": 18,
    },
}

_GRAIN_AMOUNT = {"Off": 0, "Weak": 14, "Strong": 45}
_GRAIN_SIZE = {"Small": 22, "Large": 55}


def convert(name: str, menu: FujiMenu) -> dict[str, Any]:
    base = _BASE.get(menu.get("film_simulation", "Provia"), _BASE["Provia"])
    recipe: dict[str, Any] = {"preset_name": name, **base}

    highlight = menu.get("highlight", 0)
    shadow = menu.get("shadow", 0)
    if highlight:
        recipe["Highlights2012"] = round(recipe.get("Highlights2012", 0) + highlight * 12)
    if shadow:
        recipe["Shadows2012"] = round(recipe.get("Shadows2012", 0) + shadow * 12)

    color = menu.get("color", 0)
    if color and not recipe.get("ConvertToGrayscale"):
        recipe["Saturation"] = round(recipe.get("Saturation", 0) + color * 6)
        recipe["Vibrance"] = round(color * 5)

    clarity = menu.get("clarity", 0)
    if clarity:
        recipe["Clarity2012"] = round(clarity * 8)

    sharpening = menu.get("sharpening", 0)
    recipe["Sharpness"] = max(0, min(100, round(25 + sharpening * 7)))
    recipe["SharpenRadius"] = 1.0

    grain_amount = _GRAIN_AMOUNT.get(menu.get("grain_strength", "Off"), 0)
    if grain_amount:
        recipe["GrainAmount"] = grain_amount
        recipe["GrainSize"] = _GRAIN_SIZE.get(menu.get("grain_size", "Small"), 25)
        recipe["GrainFrequency"] = 55

    # Color Chrome Effect deepens/desaturates already-saturated colors,
    # mainly visible in highlights -- approximated as a mild highlight
    # saturation pullback rather than modeled precisely.
    cce = menu.get("color_chrome", "Off")
    if cce != "Off" and not recipe.get("ConvertToGrayscale"):
        pullback = -6 if cce == "Weak" else -12
        recipe["SaturationAdjustmentRed"] = recipe.get("SaturationAdjustmentRed", 0) + pullback // 2
        recipe["SaturationAdjustmentOrange"] = recipe.get("SaturationAdjustmentOrange", 0) + pullback // 2

    # White balance shift folded in as a whole-image warm/cool split tone
    # rather than a true white-balance temperature/tint adjustment, which
    # our engine doesn't model (these presets start from an already-shot,
    # already-white-balanced JPEG, not a raw file).
    wb_red = menu.get("wb_red", 0)
    wb_blue = menu.get("wb_blue", 0)
    if wb_red or wb_blue:
        net_warm = wb_red - wb_blue  # positive = warmer
        if not recipe.get("SplitToningHighlightSaturation"):
            recipe["SplitToningHighlightHue"] = 45 if net_warm >= 0 else 215
            recipe["SplitToningHighlightSaturation"] = min(15, abs(net_warm) * 1.2)

    return recipe
