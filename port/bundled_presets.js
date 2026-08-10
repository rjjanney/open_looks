// The bundled fujixweekly-derived presets registry.js expects as its
// `bundledPresets` argument. registry.js doesn't know how to list these
// itself -- there's no build-time manifest yet (see
// docs/cross-platform-port.md's registry.py assessment), so this is a
// hand-maintained filename list, fetched at runtime relative to the page
// that imports this module. Matches presets/builtin/fujixweekly/*.json.
export const BUNDLED_PRESET_FILES = [
  "FXW_Agfa_Vista_100.json",
  "FXW_CineStill_800T.json",
  "FXW_Classic_Negative.json",
  "FXW_Ilford_HP5_Plus_400.json",
  "FXW_Kodachrome_64.json",
  "FXW_Kodak_Portra_400.json",
  "FXW_Kodak_Tri-X_400.json",
  "FXW_Sepia.json",
  "FXW_The_Rockwell_Velvia.json",
];

// baseUrl: directory containing fujixweekly/*.json. Defaults to "" (site
// root) -- vite.config.js's publicDir serves presets/builtin's contents
// at the root, so the default is correct for both `vite dev`/`vite
// build` output and needs no override there.
export async function loadBundledPresets(baseUrl = "") {
  const presets = {};
  for (const filename of BUNDLED_PRESET_FILES) {
    try {
      const res = await fetch(`${baseUrl}/fujixweekly/${filename}`);
      const recipe = await res.json();
      presets[recipe.preset_name || filename] = recipe;
    } catch (e) {
      console.error(`failed to load bundled preset ${filename}:`, e);
    }
  }
  return presets;
}
