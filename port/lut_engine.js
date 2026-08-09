// Port of scripts/lut_engine.py -- trilinear interpolation through a 3D
// .cube LUT, plus parsing the .cube text format. Pure math + string
// parsing, no cross-library numeric risk (no cv2/PIL equivalent needed
// here), unlike engine.js's blur/sharpen. See docs/cross-platform-port.md.
//
// table is a flat Float32Array of length size**3 * 3, indexed [r,g,b,c] as
// ((r*size+g)*size+b)*3+c -- the same C-order layout Python's table.flatten()
// produces for its (size,size,size,3) array, so ground-truth fixtures can be
// dumped/loaded without any extra reshaping on either side.
export class Lut3D {
  constructor(table, size, domainMin = [0, 0, 0], domainMax = [1, 1, 1], title = "") {
    this.table = table;
    this.size = size;
    this.domainMin = domainMin;
    this.domainMax = domainMax;
    this.title = title;
  }

  // img: flat RGB Float32Array (H*W*3), values nominally in [0,1] (or
  // within domainMin/domainMax). Returns the same shape.
  apply(img) {
    const n = this.size;
    const t = this.table;
    const [dMinR, dMinG, dMinB] = this.domainMin;
    const [dMaxR, dMaxG, dMaxB] = this.domainMax;
    const spanR = Math.max(dMaxR - dMinR, 1e-6);
    const spanG = Math.max(dMaxG - dMinG, 1e-6);
    const spanB = Math.max(dMaxB - dMinB, 1e-6);

    const numPixels = img.length / 3;
    const out = new Float32Array(img.length);
    const idx = (r, g, b) => ((r * n + g) * n + b) * 3;

    for (let p = 0; p < numPixels; p++) {
      const rn = Math.min(1, Math.max(0, (img[p * 3] - dMinR) / spanR));
      const gn = Math.min(1, Math.max(0, (img[p * 3 + 1] - dMinG) / spanG));
      const bn = Math.min(1, Math.max(0, (img[p * 3 + 2] - dMinB) / spanB));

      const rg = rn * (n - 1), gg = gn * (n - 1), bg = bn * (n - 1);
      const r0 = Math.min(n - 1, Math.max(0, Math.floor(rg)));
      const g0 = Math.min(n - 1, Math.max(0, Math.floor(gg)));
      const b0 = Math.min(n - 1, Math.max(0, Math.floor(bg)));
      const r1 = Math.min(n - 1, r0 + 1);
      const g1 = Math.min(n - 1, g0 + 1);
      const b1 = Math.min(n - 1, b0 + 1);
      const fr = rg - r0, fg = gg - g0, fb = bg - b0;

      for (let c = 0; c < 3; c++) {
        const c000 = t[idx(r0, g0, b0) + c], c100 = t[idx(r1, g0, b0) + c];
        const c010 = t[idx(r0, g1, b0) + c], c110 = t[idx(r1, g1, b0) + c];
        const c001 = t[idx(r0, g0, b1) + c], c101 = t[idx(r1, g0, b1) + c];
        const c011 = t[idx(r0, g1, b1) + c], c111 = t[idx(r1, g1, b1) + c];

        const c00 = c000 * (1 - fr) + c100 * fr;
        const c10 = c010 * (1 - fr) + c110 * fr;
        const c01 = c001 * (1 - fr) + c101 * fr;
        const c11 = c011 * (1 - fr) + c111 * fr;

        const cc0 = c00 * (1 - fg) + c10 * fg;
        const cc1 = c01 * (1 - fg) + c11 * fg;

        out[p * 3 + c] = Math.min(1, Math.max(0, cc0 * (1 - fb) + cc1 * fb));
      }
    }
    return out;
  }
}

// Only 3D LUTs (LUT_3D_SIZE) -- 1D LUTs are a different, simpler mechanism
// and aren't what people mean by a "film look" LUT (matches
// scripts/lut_engine.py's own restriction).
export function parseCube(text) {
  const lines = text.split(/\r?\n/);
  let size = null;
  let domainMin = [0, 0, 0];
  let domainMax = [1, 1, 1];
  let title = "";
  const values = [];

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const parts = line.split(/\s+/);
    const key = parts[0].toUpperCase();

    if (key === "TITLE") {
      const m = line.match(/^\S+\s+(.*)$/);
      title = m ? m[1].trim().replace(/^"|"$/g, "") : "";
    } else if (key === "LUT_3D_SIZE") {
      size = parseInt(parts[1], 10);
    } else if (key === "LUT_1D_SIZE") {
      throw new Error("1D .cube LUTs aren't supported, only 3D (LUT_3D_SIZE)");
    } else if (key === "DOMAIN_MIN") {
      domainMin = parts.slice(1, 4).map(Number);
    } else if (key === "DOMAIN_MAX") {
      domainMax = parts.slice(1, 4).map(Number);
    } else {
      const nums = parts.slice(0, 3).map(Number);
      if (nums.length === 3 && nums.every((x) => !Number.isNaN(x))) values.push(nums);
      // unrecognized line -- skip rather than hard-fail, matching Python
    }
  }

  if (size === null) throw new Error("no LUT_3D_SIZE found -- not a valid 3D .cube file");
  const expected = size ** 3;
  if (values.length !== expected) {
    throw new Error(`expected ${expected} data lines for LUT_3D_SIZE ${size}, found ${values.length}`);
  }

  // .cube data-line order: R varies fastest, then G, then B -- values[i]
  // is table[r,g,b] where i = (b*size+g)*size+r.
  const table = new Float32Array(size * size * size * 3);
  for (let i = 0; i < values.length; i++) {
    const r = i % size;
    const g = Math.floor(i / size) % size;
    const b = Math.floor(i / (size * size));
    const idx = ((r * size + g) * size + b) * 3;
    table[idx] = values[i][0];
    table[idx + 1] = values[i][1];
    table[idx + 2] = values[i][2];
  }

  return new Lut3D(table, size, domainMin, domainMax, title);
}
