# Attribution

This project's own code is MIT-licensed (see `../LICENSE`). The looks bundled
under `presets/builtin/` come from two places, documented here -- crediting
the actual people who made these is the right thing to do either way.

If you're checking whether something here is safe to keep using: the code
that *applies* a look (`scripts/develop_engine.py`, `scripts/xmp_importer.py`,
`scripts/lut_engine.py`) is ours either way. What varies is where the
specific *numbers* for a given preset came from.

---

## Original recipes -- ours, no external source

`scripts/fuji_recipes.py`: **Classic Chrome, Velvia, Acros, Provia**.
Hand-written from general published descriptions of what each Fujifilm film
simulation looks like (contrast, saturation, characteristic color shifts) --
not derived from any Fuji software, LUT, ICC profile, or file. See that
module's docstring. Covered by this project's MIT license, free to use, no
attribution needed (though "inspired by Fujifilm's film simulations" is an
accurate, fair description -- these aren't official Fuji products or
affiliated with Fujifilm).

## Fuji X Weekly community recipes -- transcribed, attributed per-recipe

`presets/builtin/fujixweekly/*.json` (9 recipes). [Fuji X Weekly](https://fujixweekly.com/)
is a community hub of published Fujifilm in-camera JPEG "recipes" -- text
parameter lists (Film Simulation base, Highlight/Shadow, Color, Grain,
White Balance shift, etc.), explicitly shared by their authors for others to
use, reimplement, and build on. These aren't files or software, just
published settings, transcribed here and run through `scripts/
fuji_menu_convert.py` -- our own heuristic mapping from Fuji's menu-setting
vocabulary into this engine's parameter schema. It's a creative
reinterpretation, not a certified translation; expect family resemblance to
the original recipe, not a pixel-identical match. See `fujixweekly_manifest.
json` in this folder for the exact source URL, author, and original Fuji
menu settings behind each one. Accessed 2026-07-18.

| Recipe | Original author | Source |
|---|---|---|
| FXW Kodak Tri-X 400 | Ritchie Roesch | [fujixweekly.com](https://fujixweekly.com/2020/06/18/fujifilm-x100v-film-simulation-recipe-kodak-tri-x-400/) |
| FXW Kodak Portra 400 | Ritchie Roesch | [fujixweekly.com](https://fujixweekly.com/2020/06/10/fujifilm-x100v-film-simulation-kodak-portra-400/) |
| FXW Classic Negative | Luis Costa (original), Ritchie Roesch (modified) | [fujixweekly.com](https://fujixweekly.com/2020/06/01/not-my-fujifilm-x100v-classic-negative-film-simulation-recipe/) |
| FXW The Rockwell (Velvia) | Ritchie Roesch | [fujixweekly.com](https://fujixweekly.com/2020/07/18/fujifilm-x100v-film-simulation-recipe-the-rockwell-velvia/) |
| FXW CineStill 800T | Ritchie Roesch | [fujixweekly.com](https://fujixweekly.com/2020/10/06/fujifilm-x100v-film-simulation-recipe-cinestill-800t/) |
| FXW Sepia | Ritchie Roesch | [fujixweekly.com](https://fujixweekly.com/2020/07/01/sepia-the-forgotten-film-simulation/) |
| FXW Kodachrome 64 | Ritchie Roesch | [fujixweekly.com](https://fujixweekly.com/2020/05/27/my-fujifilm-x100v-kodachrome-64-film-simulation-recipe/) |
| FXW Agfa Vista 100 | Ritchie Roesch | [fujixweekly.com](https://fujixweekly.com/2020/09/28/fujifilm-x100v-film-simulation-recipe-agfa-vista-100/) |
| FXW Ilford HP5 Plus 400 | Anders Lindborg | [fujixweekly.com](https://fujixweekly.com/2022/03/23/fujifilm-x-trans-iv-film-simulation-recipe-ilford-hp5-plus-400/) |

---

## If you add more presets

Please add a row to whichever table above fits (or a new section), even for
CC0/public-domain sources where it's not legally required -- the point is a
future reader (including us) being able to tell at a glance where every
number in this repo came from.
