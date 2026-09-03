#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "app" / "src" / "main" / "assets"
INDEX = ASSETS / "media_index.json"

if not INDEX.is_file():
    raise SystemExit("media_index.json not found")

with INDEX.open("r", encoding="utf-8") as f:
    media = json.load(f)


def file_bytes(root: Path):
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file()) if root.exists() else 0


def optimize_image_job(args):
    rel, kind = args
    src = ASSETS / rel
    if not src.is_file():
        return rel, rel, 0, 0, "missing"
    dst = src.with_suffix(".webp")
    before = src.stat().st_size
    try:
        with Image.open(src) as im:
            im.load()
            max_dim = 1400 if kind == "character" else 1600
            if max(im.size) > max_dim:
                im.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
            if im.mode not in ("RGB", "RGBA"):
                if "A" in im.getbands():
                    im = im.convert("RGBA")
                else:
                    im = im.convert("RGB")
            quality = 80 if kind == "character" else 76
            im.save(dst, "WEBP", quality=quality, method=4, exact=True)
        after = dst.stat().st_size
        if dst != src:
            src.unlink(missing_ok=True)
        return rel, dst.relative_to(ASSETS).as_posix(), before, after, "ok"
    except Exception as exc:
        try:
            if dst.exists() and dst != src:
                dst.unlink()
        except Exception:
            pass
        return rel, rel, before, before, f"error:{exc}"


def optimize_audio_job(rel):
    src = ASSETS / rel
    if not src.is_file():
        return rel, rel, 0, 0, "missing"
    dst = src.with_suffix(".ogg")
    if dst == src:
        dst = src.with_name(src.stem + ".optimized.ogg")
    before = src.stat().st_size
    cmd = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(src), "-vn", "-c:a", "libvorbis", "-q:a", "2",
        "-map_metadata", "-1", str(dst)
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        after = dst.stat().st_size
        src.unlink(missing_ok=True)
        return rel, dst.relative_to(ASSETS).as_posix(), before, after, "ok"
    except Exception as exc:
        try:
            if dst.exists():
                dst.unlink()
        except Exception:
            pass
        return rel, rel, before, before, f"error:{exc}"


image_refs = {}
image_jobs = {}
for kind, mapping in media.get("images", {}).items():
    for key, rel in list(mapping.items()):
        if rel:
            image_jobs.setdefault(rel, kind)

# Banners are also image assets. They are not yet shown by the v3 UI, but keep them optimized for future use.
for key, rel in list(media.get("banners", {}).items()):
    if rel:
        image_jobs.setdefault(rel, "banner")

print(f"Optimizing {len(image_jobs)} unique images...")
image_before = image_after = 0
image_errors = []
workers = max(2, min(6, (os.cpu_count() or 4)))
with ProcessPoolExecutor(max_workers=workers) as pool:
    futures = [pool.submit(optimize_image_job, item) for item in image_jobs.items()]
    done = 0
    for fut in as_completed(futures):
        old, new, before, after, status = fut.result()
        image_refs[old] = new
        image_before += before
        image_after += after
        if status != "ok":
            image_errors.append((old, status))
        done += 1
        if done % 1000 == 0:
            print(f"  images {done}/{len(image_jobs)}")

for kind, mapping in media.get("images", {}).items():
    for key, rel in list(mapping.items()):
        mapping[key] = image_refs.get(rel, rel)
for key, rel in list(media.get("banners", {}).items()):
    media["banners"][key] = image_refs.get(rel, rel)


audio_refs = {}
audio_jobs = set()
for kind, mapping in media.get("audio", {}).items():
    for key, rel in mapping.items():
        if rel:
            audio_jobs.add(rel)

print(f"Optimizing {len(audio_jobs)} unique audio files...")
audio_before = audio_after = 0
audio_errors = []
with ProcessPoolExecutor(max_workers=max(2, min(4, (os.cpu_count() or 4)))) as pool:
    futures = [pool.submit(optimize_audio_job, rel) for rel in sorted(audio_jobs)]
    done = 0
    for fut in as_completed(futures):
        old, new, before, after, status = fut.result()
        audio_refs[old] = new
        audio_before += before
        audio_after += after
        if status != "ok":
            audio_errors.append((old, status))
        done += 1
        if done % 100 == 0:
            print(f"  audio {done}/{len(audio_jobs)}")

for kind, mapping in media.get("audio", {}).items():
    for key, rel in list(mapping.items()):
        mapping[key] = audio_refs.get(rel, rel)

stats = media.setdefault("stats", {})
stats["optimizedForApk"] = True
stats["imageEncoding"] = "WebP lossy q76/q80, max 1600/1400px"
stats["audioEncoding"] = "Ogg Vorbis q2"
stats["imageBytesBeforeOptimization"] = image_before
stats["imageBytesAfterOptimization"] = image_after
stats["audioBytesBeforeOptimization"] = audio_before
stats["audioBytesAfterOptimization"] = audio_after
stats["imageOptimizationErrors"] = image_errors[:100]
stats["audioOptimizationErrors"] = audio_errors[:100]
stats["totalAssetBytesAfterOptimization"] = file_bytes(ASSETS)

with INDEX.open("w", encoding="utf-8") as f:
    json.dump(media, f, ensure_ascii=False, separators=(",", ":"))

print(f"Images: {image_before/1024/1024:.1f} MiB -> {image_after/1024/1024:.1f} MiB")
print(f"Audio:  {audio_before/1024/1024:.1f} MiB -> {audio_after/1024/1024:.1f} MiB")
print(f"Total assets after optimization: {stats['totalAssetBytesAfterOptimization']/1024/1024/1024:.2f} GiB")
print(f"Optimization errors: images={len(image_errors)}, audio={len(audio_errors)}")

# Keep healthy headroom below the classic APK ZIP32 4 GiB boundary.
if stats["totalAssetBytesAfterOptimization"] >= 3_600_000_000:
    raise SystemExit("optimized assets are still too large for a reliable single APK")
