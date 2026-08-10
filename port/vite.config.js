import { defineConfig } from "vite";
import { resolve } from "node:path";

// publicDir points at presets/builtin specifically, NOT presets/ as a
// whole -- presets/user/ holds the desktop app's real local imports
// (gitignored, machine-specific) and must never end up copied verbatim
// into a web build. Its contents get served at the site root (Vite's
// publicDir convention), so presets/builtin/fujixweekly/X.json becomes
// /fujixweekly/X.json -- see bundled_presets.js's baseUrl default.
export default defineConfig({
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
