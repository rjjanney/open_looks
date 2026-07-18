"""Short human-readable caption per look, keyed by preset/recipe name.
Purely cosmetic (shown in the app UI); a look not listed here just shows
its bare name. Anything imported at runtime (--import / the app's Import
Look button) won't have an entry -- that's expected, not a bug.
"""
from __future__ import annotations

CAPTIONS: dict[str, str] = {
    "Fuji Classic Chrome": "Muted, documentary-style color",
    "Fuji Velvia": "Vivid, punchy saturation (landscape film)",
    "Fuji Acros": "Smooth fine-grain B&W",
    "Fuji Provia": "Neutral, faithful standard color",
    "FXW Kodak Tri-X 400": "Contrasty B&W, visible grain -- Ritchie Roesch",
    "FXW Kodak Portra 400": "Warm, muted portrait color -- Ritchie Roesch",
    "FXW Classic Negative": "Faded warm color, green-leaning shadows -- Luis Costa / Ritchie Roesch",
    "FXW The Rockwell (Velvia)": "Bold, saturated landscape color -- Ritchie Roesch",
    "FXW CineStill 800T": "Flat, cinematic, tungsten-leaning -- Ritchie Roesch",
    "FXW Sepia": "Warm monochrome -- Ritchie Roesch",
    "FXW Kodachrome 64": "Punchy midcentury color -- Ritchie Roesch",
    "FXW Agfa Vista 100": "Faded consumer-film color -- Ritchie Roesch",
    "FXW Ilford HP5 Plus 400": "Soft, deep-shadow B&W -- Anders Lindborg",
}
