// Runs applyRecipe() off the main thread. Full-resolution photos (a real
// camera/phone photo, not the small preview) can take many seconds of
// pure computation -- see docs/cross-platform-port.md -- and without
// this, that work runs on the same thread that draws the page, so the
// whole UI (spinner, status text, buttons) visibly freezes for the
// duration. This does NOT make the computation itself faster -- same
// math, same time -- it only keeps the page responsive while it happens.
import { applyRecipe } from "./engine.js";

self.onmessage = (e) => {
  const { id, rgb, width, height, recipe, seed } = e.data;
  const outRgb = applyRecipe(rgb, width, height, recipe, seed);
  self.postMessage({ id, outRgb }, [outRgb.buffer]);
};
