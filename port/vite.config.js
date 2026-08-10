import { defineConfig } from "vite";
import { resolve } from "node:path";

// publicDir points at presets/builtin specifically, NOT presets/ as a
// whole -- presets/user/ holds the desktop app's real local imports
// (gitignored, machine-specific) and must never end up copied verbatim
// into a web build. Its contents get served at the site root (Vite's
// publicDir convention), so presets/builtin/fujixweekly/X.json becomes
// /fujixweekly/X.json -- see bundled_presets.js's baseUrl default.
export default defineConfig({
  // GitHub Pages serves this as a project site under /open_looks/, not
  // repo root -- Vite's default base ("/") makes built asset references
  // absolute-root ("/assets/main-....js"), which 404s under a subpath.
  // "./" makes them relative to index.html's own location instead, so
  // this works unchanged whether it's deployed under a GitHub Pages
  // project subpath, a custom domain, or anywhere else -- no need to
  // hardcode the repo name and re-break if it's ever renamed.
  base: "./",
  publicDir: resolve(import.meta.dirname, "../presets/builtin"),
  build: {
    rollupOptions: {
      input: {
        main: resolve(import.meta.dirname, "index.html"),
        preview: resolve(import.meta.dirname, "preview.html"),
        opfsCheck: resolve(import.meta.dirname, "opfs_check.html"),
      },
    },
  },
});
