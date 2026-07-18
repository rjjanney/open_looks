"""Hand-coded approximations of a few famous Fujifilm film simulations.

These are NOT derived from Fuji's actual color science (which is
proprietary and baked into their sensor/processor pipeline) -- there's no
real Fuji preset in this project to reverse-engineer, unlike the Olympus
Art Filters. They're built from commonly published descriptions of each
stock's character (contrast, saturation, characteristic color shifts,
grain) and use the exact same recipe schema as the parsed Olympus XMP
presets, so develop_engine.apply_recipe() drives both identically.

Treat these as a starting point to tune once you see them on real photos,
not a faithful reproduction.
"""
from __future__ import annotations

from typing import Any

FUJI_RECIPES: dict[str, dict[str, Any]] = {
    "Fuji Classic Chrome": {
        "preset_name": "Fuji Classic Chrome",
        "ConvertToGrayscale": False,
        "Contrast2012": 15,
        "Saturation": -15,
        "Vibrance": -12,
        "Shadows2012": 8,
        "Blacks2012": -5,
        "Highlights2012": -12,
        "ParametricShadows": 8,
        "ParametricDarks": 4,
        "ParametricLights": -4,
        "ParametricHighlights": -10,
        "ParametricShadowSplit": 25,
        "ParametricMidtoneSplit": 50,
        "ParametricHighlightSplit": 75,
        "SaturationAdjustmentGreen": -18,
        "SaturationAdjustmentYellow": -12,
        "SaturationAdjustmentOrange": -8,
        "SaturationAdjustmentRed": -5,
        "HueAdjustmentOrange": -4,
        "HueAdjustmentYellow": 4,
        "LuminanceAdjustmentGreen": -6,
        "SplitToningShadowHue": 205,
        "SplitToningShadowSaturation": 10,
        "SplitToningHighlightHue": 45,
        "SplitToningHighlightSaturation": 8,
        "SplitToningBalance": -10,
        "Sharpness": 30,
        "SharpenRadius": 1.0,
        "GrainAmount": 14,
        "GrainSize": 22,
        "GrainFrequency": 55,
    },
    "Fuji Velvia": {
        "preset_name": "Fuji Velvia",
        "ConvertToGrayscale": False,
        "Contrast2012": 18,
        "Saturation": 15,
        "Vibrance": 14,
        "Shadows2012": -6,
        "Blacks2012": -6,
        "Highlights2012": 5,
        "ParametricShadows": -10,
        "ParametricHighlights": 6,
        "ParametricShadowSplit": 25,
        "ParametricMidtoneSplit": 50,
        "ParametricHighlightSplit": 75,
        "SaturationAdjustmentGreen": 16,
        "SaturationAdjustmentBlue": 18,
        "SaturationAdjustmentAqua": 10,
        "SaturationAdjustmentRed": 8,
        "SaturationAdjustmentOrange": 5,
        "LuminanceAdjustmentBlue": -8,
        "LuminanceAdjustmentGreen": -4,
        "SplitToningShadowHue": 220,
        "SplitToningShadowSaturation": 6,
        "SplitToningHighlightHue": 40,
        "SplitToningHighlightSaturation": 4,
        "Sharpness": 35,
        "SharpenRadius": 1.0,
        "GrainAmount": 6,
        "GrainSize": 18,
        "GrainFrequency": 55,
    },
    "Fuji Acros": {
        "preset_name": "Fuji Acros",
        "ConvertToGrayscale": True,
        "GrayMixerRed": 12,
        "GrayMixerOrange": 8,
        "GrayMixerYellow": 2,
        "GrayMixerGreen": -12,
        "GrayMixerAqua": -8,
        "GrayMixerBlue": -18,
        "GrayMixerPurple": -4,
        "GrayMixerMagenta": 0,
        "Contrast2012": 20,
        "Shadows2012": -4,
        "Blacks2012": -6,
        "Highlights2012": 4,
        "ParametricShadows": -12,
        "ParametricDarks": 4,
        "ParametricLights": 4,
        "ParametricHighlights": 6,
        "ParametricShadowSplit": 25,
        "ParametricMidtoneSplit": 50,
        "ParametricHighlightSplit": 75,
        "Sharpness": 30,
        "SharpenRadius": 0.8,
        "GrainAmount": 12,
        "GrainSize": 14,
        "GrainFrequency": 60,
    },
    "Fuji Provia": {
        "preset_name": "Fuji Provia",
        "ConvertToGrayscale": False,
        "Contrast2012": 8,
        "Saturation": 5,
        "Vibrance": 8,
        "ParametricShadows": -4,
        "ParametricHighlights": 2,
        "ParametricShadowSplit": 25,
        "ParametricMidtoneSplit": 50,
        "ParametricHighlightSplit": 75,
        "SaturationAdjustmentBlue": 4,
        "SaturationAdjustmentGreen": 4,
        "Sharpness": 25,
        "SharpenRadius": 1.0,
        "GrainAmount": 5,
        "GrainSize": 20,
        "GrainFrequency": 50,
    },
}


def get_recipe(name: str) -> dict[str, Any]:
    return FUJI_RECIPES[name]


if __name__ == "__main__":
    for name in FUJI_RECIPES:
        print(name)
