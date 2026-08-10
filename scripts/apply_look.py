"""CLI for open_looks.

Examples:
    python scripts/apply_look.py --list
    python scripts/apply_look.py --import "some_preset.xmp"
    python scripts/apply_look.py --import "cinematic_pack.cube"
    python scripts/apply_look.py --look "Fuji Acros" --input Source --output Output
    python scripts/apply_look.py --all
"""
from __future__ import annotations

import os

# Must be set before numpy/cv2 import (here, and again in each spawned
# worker process): both otherwise fan a single call out across every core
# via their own thread pool, which oversubscribes the machine once we're
# also parallel across worker *processes* -- see develop_engine.py.
for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

import argparse
import sys
import time
import zlib
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import cv2
from PIL import Image

from registry import build_registry, import_look, save_imported_look
from develop_engine import apply_recipe

PROJECT_ROOT = Path(__file__).resolve().parent.parent
IMAGE_EXTS = (".jpg", ".jpeg", ".png")


def safe_dirname(name: str) -> str:
    return "".join(c if c.isalnum() or c in " -_" else "_" for c in name).strip()


def grain_seed_for(filename: str) -> int:
    return zlib.crc32(filename.encode("utf-8")) & 0xFFFFFFFF


# EXIF orientation tag ID (0x0112 / 274) -- a camera-set value here tells a
# viewer to rotate the pixels on display. rotate_image() below rotates the
# actual pixel data instead, so a preserved EXIF blob with its original
# orientation would make viewers rotate our already-rotated pixels AGAIN.
# reset_exif_orientation() resets it to 1 (normal/no rotation) whenever we've
# manually rotated, so the two don't stack.
_EXIF_ORIENTATION_TAG = 0x0112


def rotate_image(img: Image.Image, degrees: int) -> Image.Image:
    """Rotate by a multiple of 90 degrees, clockwise. No-op at 0 (returns
    the same object, not a copy). PIL's own rotate() is counter-clockwise
    for positive angles -- negated here to match the clockwise convention
    used throughout the app (matches port/app.js's fileToCanvas rotation
    too; both were verified against the same marker-pixel test)."""
    if degrees % 360 == 0:
        return img
    return img.rotate(-degrees, expand=True)


def reset_exif_orientation(exif_bytes: bytes | None) -> bytes | None:
    if not exif_bytes:
        return exif_bytes
    exif = Image.Exif()
    exif.load(exif_bytes)
    exif[_EXIF_ORIENTATION_TAG] = 1
    return exif.tobytes()


def _worker_init() -> None:
    cv2.setNumThreads(1)


def _render_job(job: tuple[str, dict, str, str, int, int]) -> str:
    look_name, recipe, in_path_str, out_path_str, quality, rotation = job
    in_path = Path(in_path_str)
    out_path = Path(out_path_str)

    img = Image.open(in_path)
    exif = img.info.get("exif")
    img = rotate_image(img, rotation)
    if rotation % 360 != 0:
        exif = reset_exif_orientation(exif)
    seed = grain_seed_for(in_path.name)
    result = apply_recipe(img, recipe, grain_seed=seed)
    save_kwargs = {"quality": quality}
    if exif:
        save_kwargs["exif"] = exif
    result.save(out_path, **save_kwargs)
    return f"{look_name} / {in_path.name}"


def collect_jobs(looks: dict[str, dict], input_dir: Path, output_dir: Path, quality: int):
    images = sorted(p for p in input_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    if not images:
        print(f"No .jpg/.png files found in {input_dir}")
        return []

    jobs = []
    for look_name, recipe in looks.items():
        out_dir = output_dir / safe_dirname(look_name)
        out_dir.mkdir(parents=True, exist_ok=True)
        for path in images:
            # 0 -- the CLI batch path has no rotation concept, only the
            # interactive app (app/api.py) does.
            jobs.append((look_name, recipe, str(path), str(out_dir / path.name), quality, 0))
    return jobs


def run_jobs(jobs, workers: int) -> None:
    total = len(jobs)
    if not total:
        return
    started = time.monotonic()
    done = 0
    with ProcessPoolExecutor(max_workers=workers, initializer=_worker_init) as pool:
        futures = [pool.submit(_render_job, job) for job in jobs]
        for future in as_completed(futures):
            done += 1
            future.result()
            if done % 25 == 0 or done == total:
                elapsed = time.monotonic() - started
                print(f"  [{done}/{total}] {elapsed:5.1f}s elapsed")
    elapsed = time.monotonic() - started
    print(f"Done: {total} renders across {workers} workers in {elapsed:.1f}s ({total / elapsed:.1f} img/s)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--look", help="Look name to apply (see --list)")
    parser.add_argument("--all", action="store_true", help="Apply every available look")
    parser.add_argument("--list", action="store_true", help="List available look names and exit")
    parser.add_argument("--import", dest="import_path", help="Import a .xmp/.cube file (or folder) into presets/user/")
    parser.add_argument("--input", default=str(PROJECT_ROOT / "Source"), help="Input folder of .jpg/.png photos")
    parser.add_argument("--output", default=str(PROJECT_ROOT / "Output"), help="Output root folder")
    parser.add_argument("--quality", type=int, default=92, help="JPEG save quality (default 92)")
    default_workers = max(1, (os.cpu_count() or 4) // 2)
    parser.add_argument("--workers", type=int, default=default_workers, help=f"Parallel worker processes (default {default_workers})")
    args = parser.parse_args()

    if args.import_path:
        found = import_look(args.import_path)
        if not found:
            print(f"Nothing importable found in {args.import_path}")
            return
        print(f"Found {len(found)} look(s):")
        for name, recipe in found.items():
            dest = save_imported_look(name, recipe, source_path=args.import_path)
            print(f"  {name} -> {dest}")
            for warning in recipe.get("_import_warnings", []):
                print(f"    Warning: {warning}")
        return

    registry = build_registry()

    if args.list:
        print(f"{len(registry)} looks available:\n")
        for name in sorted(registry):
            print(" -", name)
        return

    input_dir = Path(args.input)
    output_dir = Path(args.output)

    if args.all:
        jobs = collect_jobs(registry, input_dir, output_dir, args.quality)
        print(f"Rendering {len(jobs)} (look, photo) pairs across {args.workers} workers...")
        run_jobs(jobs, args.workers)
        return

    if not args.look:
        parser.error("pass --look NAME, --all, --import PATH, or --list")

    if args.look not in registry:
        print(f"Unknown look: {args.look!r}", file=sys.stderr)
        print("Run with --list to see available names.", file=sys.stderr)
        sys.exit(1)

    jobs = collect_jobs({args.look: registry[args.look]}, input_dir, output_dir, args.quality)
    print(f"Rendering {len(jobs)} photos for {args.look!r} across {args.workers} workers...")
    run_jobs(jobs, args.workers)


if __name__ == "__main__":
    main()
