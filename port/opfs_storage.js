// Origin Private File System storage adapter for registry.js -- the
// browser-side answer to "where does hidden.json/order.json/imported
// looks live without %APPDATA%" (see docs/cross-platform-port.md). Real
// file-like storage with the same directory-of-files shape
// scripts/registry.py already assumes, so registry.js's logic didn't need
// reshaping around a key-value store the way IndexedDB/localStorage would
// have forced.
//
// Paths are POSIX-style relative paths, e.g. "hidden.json" or
// "user/luts/look.cube" -- intermediate directories are created on write
// as needed.

async function resolveParent(path, { create = false } = {}) {
  const parts = path.split("/").filter(Boolean);
  const name = parts.pop();
  let dir = await navigator.storage.getDirectory();
  for (const part of parts) {
    dir = await dir.getDirectoryHandle(part, { create });
  }
  return { dir, name };
}

async function readFile(path) {
  try {
    const { dir, name } = await resolveParent(path);
    const handle = await dir.getFileHandle(name);
    return await handle.getFile();
  } catch (e) {
    if (e.name === "NotFoundError") return null;
    throw e;
  }
}

export const opfsStorage = {
  async readText(path) {
    const file = await readFile(path);
    return file ? file.text() : null;
  },

  async writeText(path, text) {
    const { dir, name } = await resolveParent(path, { create: true });
    const handle = await dir.getFileHandle(name, { create: true });
    const writable = await handle.createWritable();
    await writable.write(text);
    await writable.close();
  },

  async readBytes(path) {
    const file = await readFile(path);
    return file ? new Uint8Array(await file.arrayBuffer()) : null;
  },

  async writeBytes(path, bytes) {
    const { dir, name } = await resolveParent(path, { create: true });
    const handle = await dir.getFileHandle(name, { create: true });
    const writable = await handle.createWritable();
    await writable.write(bytes);
    await writable.close();
  },

  async deleteFile(path) {
    try {
      const { dir, name } = await resolveParent(path);
      await dir.removeEntry(name);
      return true;
    } catch (e) {
      if (e.name === "NotFoundError") return false;
      throw e;
    }
  },

  // Non-recursive -- filenames only, no subdirectories.
  async listFiles(dirPath) {
    let dir;
    try {
      const parts = dirPath.split("/").filter(Boolean);
      dir = await navigator.storage.getDirectory();
      for (const part of parts) dir = await dir.getDirectoryHandle(part);
    } catch (e) {
      if (e.name === "NotFoundError") return [];
      throw e;
    }
    const names = [];
    for await (const [name, handle] of dir.entries()) {
      if (handle.kind === "file") names.push(name);
    }
    return names;
  },
};
