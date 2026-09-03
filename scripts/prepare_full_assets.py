#!/usr/bin/env python3
import hashlib
import json
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

if len(sys.argv) != 4:
    raise SystemExit("usage: prepare_full_assets.py <ArknightsStoryJson> <ArknightsResource> <arknights-audio>")

story_repo = Path(sys.argv[1]).resolve()
image_repo = Path(sys.argv[2]).resolve()
audio_repo = Path(sys.argv[3]).resolve()

story_source = story_repo / "ko_KR" / "gamedata" / "story"
banner_source = story_repo / "img" / "banners"
image_source = image_repo / "avgs"
audio_roots = [audio_repo / "music", audio_repo / "avg", audio_repo / "player"]

project_root = Path(__file__).resolve().parents[1]
out_root = project_root / "app" / "src" / "main" / "assets"
out_story = out_root / "story"
out_media = out_root / "media"
out_images = out_media / "images"
out_audio = out_media / "audio"
out_banners = out_media / "banners"

for required in (story_source, image_source):
    if not required.is_dir():
        raise SystemExit(f"required source not found: {required}")
if not any(p.is_dir() for p in audio_roots):
    raise SystemExit(f"audio source not found below: {audio_repo}")

for path in (out_story, out_media):
    if path.exists():
        shutil.rmtree(path)
out_story.mkdir(parents=True, exist_ok=True)
out_images.mkdir(parents=True, exist_ok=True)
out_audio.mkdir(parents=True, exist_ok=True)
out_banners.mkdir(parents=True, exist_ok=True)

stories = []
errors = []
image_requests = {"background": set(), "image": set(), "character": set()}
audio_requests = {"music": set(), "sfx": set()}
event_ids = set()

def clean_key(value):
    if value is None:
        return ""
    value = str(value).strip().strip('"').strip("'")
    if value.startswith("$"):
        value = value[1:]
    return value.strip()

def add_audio(kind, raw):
    key = clean_key(raw)
    if not key:
        return
    for part in key.split(";"):
        part = clean_key(part)
        if part:
            audio_requests[kind].add(part)

def inspect_story(data):
    for line in data.get("storyList", []):
        if not isinstance(line, dict):
            continue
        prop = str(line.get("prop") or "").lower()
        attrs = line.get("attributes") or {}
        if not isinstance(attrs, dict):
            attrs = {}

        image = clean_key(attrs.get("image"))
        if image:
            if prop in ("background", "backgroundtween"):
                image_requests["background"].add(image)
            else:
                image_requests["image"].add(image)

        if prop == "character":
            for k in ("name", "name2"):
                value = clean_key(attrs.get(k))
                if value:
                    image_requests["character"].add(value)

        figure = clean_key(line.get("figure_art"))
        if figure:
            image_requests["character"].add(figure)

        if prop == "playmusic":
            add_audio("music", attrs.get("key"))
            add_audio("music", attrs.get("intro"))
        elif prop == "playsound":
            for k, value in attrs.items():
                if "key" in str(k).lower():
                    add_audio("sfx", value)

for src in sorted(story_source.rglob("*.json")):
    rel = src.relative_to(story_source).as_posix()
    try:
        with src.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or not isinstance(data.get("storyList"), list):
            continue
        dest = out_story / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

        event_id = str(data.get("eventid") or "")
        if event_id:
            event_ids.add(event_id)
        stories.append({
            "path": rel,
            "eventId": event_id,
            "eventName": str(data.get("eventName") or "기타 스토리"),
            "entryType": str(data.get("entryType") or "STORY"),
            "storyCode": str(data.get("storyCode") or ""),
            "avgTag": str(data.get("avgTag") or ""),
            "storyName": str(data.get("storyName") or data.get("storyCode") or rel),
            "storyInfo": str(data.get("storyInfo") or ""),
        })
        inspect_story(data)
    except Exception as exc:
        errors.append(f"{rel}: {exc}")

if not stories:
    raise SystemExit("no story JSON files were packaged")

index = {
    "lang": "ko_KR",
    "storyCount": len(stories),
    "stories": stories,
}
with (out_root / "story_index.json").open("w", encoding="utf-8") as f:
    json.dump(index, f, ensure_ascii=False, separators=(",", ":"))

def norm(value):
    return re.sub(r"[^a-z0-9]+", "", value.lower())

def index_files(roots, extensions):
    exact = defaultdict(list)
    normalized = defaultdict(list)
    files = []
    for root in roots:
        if not root.is_dir():
            continue
        for p in root.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in extensions:
                continue
            files.append(p)
            exact[p.stem.lower()].append(p)
            n = norm(p.stem)
            if n:
                normalized[n].append(p)
    return files, exact, normalized

image_files, image_exact, image_norm = index_files([image_source], {".png", ".jpg", ".jpeg", ".webp"})
audio_files, audio_exact, audio_norm = index_files(audio_roots, {".mp3", ".ogg", ".wav", ".m4a"})

def rank_image(path, kind, key):
    p = path.as_posix().lower()
    score = 0
    if path.stem.lower() == key.lower():
        score -= 1000
    if kind == "background":
        if "/bg/" in p:
            score -= 300
        if "background" in p:
            score -= 50
    elif kind == "character":
        if "char" in path.stem.lower() or "npc" in path.stem.lower():
            score -= 150
        if "/bg/" in p:
            score += 300
    else:
        if "/bg/" in p:
            score += 200
    score += len(path.parts)
    return score

def find_image(kind, key):
    candidates = list(image_exact.get(key.lower(), []))
    if not candidates:
        variants = [
            key.replace("#", "_"),
            key.replace("$", "_"),
            key.replace("#", "_0"),
        ]
        for v in variants:
            candidates.extend(image_exact.get(v.lower(), []))
    if not candidates:
        candidates = list(image_norm.get(norm(key), []))
    if not candidates:
        return None
    return sorted(set(candidates), key=lambda p: rank_image(p, kind, key))[0]

def rank_audio(path, kind, key):
    p = path.as_posix().lower()
    score = 0
    if path.stem.lower() == key.lower():
        score -= 1000
    if kind == "music":
        if "/music/" in p:
            score -= 300
    else:
        if "/avg/" in p:
            score -= 300
        elif "/player/" in p:
            score -= 150
        if "/music/" in p:
            score += 100
    score += len(path.parts)
    return score

def find_audio(kind, key):
    candidates = list(audio_exact.get(key.lower(), []))
    if not candidates:
        n = norm(key)
        candidates = list(audio_norm.get(n, []))
    if not candidates:
        n = norm(key)
        fuzzy = []
        if len(n) >= 6:
            for stem_norm, paths in audio_norm.items():
                if n in stem_norm or stem_norm in n:
                    fuzzy.extend(paths)
                    if len(fuzzy) > 12:
                        break
        if len(fuzzy) == 1:
            candidates = fuzzy
        elif fuzzy:
            stems = {p.stem.lower() for p in fuzzy}
            if len(stems) == 1:
                candidates = fuzzy
    if not candidates:
        return None
    return sorted(set(candidates), key=lambda p: rank_audio(p, kind, key))[0]

def copy_asset(src, dest_dir, namespace, key):
    digest = hashlib.sha1((namespace + "\0" + key + "\0" + src.as_posix()).encode("utf-8")).hexdigest()[:20]
    dest = dest_dir / f"{digest}{src.suffix.lower()}"
    if not dest.exists():
        shutil.copy2(src, dest)
    return dest.relative_to(out_root).as_posix()

media = {
    "version": 3,
    "images": {"background": {}, "image": {}, "character": {}},
    "audio": {"music": {}, "sfx": {}},
    "banners": {},
    "stats": {},
}
missing_images = {k: [] for k in image_requests}
missing_audio = {k: [] for k in audio_requests}

for kind in ("background", "image", "character"):
    for key in sorted(image_requests[kind]):
        src = find_image(kind, key)
        if src:
            media["images"][kind][key] = copy_asset(src, out_images, f"image:{kind}", key)
        else:
            missing_images[kind].append(key)

for kind in ("music", "sfx"):
    for key in sorted(audio_requests[kind]):
        src = find_audio(kind, key)
        if src:
            media["audio"][kind][key] = copy_asset(src, out_audio, f"audio:{kind}", key)
        else:
            missing_audio[kind].append(key)

if banner_source.is_dir():
    banner_index = {p.stem: p for p in banner_source.glob("*.png")}
    for event_id in sorted(event_ids):
        src = banner_index.get(event_id)
        if src:
            media["banners"][event_id] = copy_asset(src, out_banners, "banner", event_id)

story_size = sum(p.stat().st_size for p in out_story.rglob("*.json"))
image_size = sum(p.stat().st_size for p in out_images.rglob("*") if p.is_file())
audio_size = sum(p.stat().st_size for p in out_audio.rglob("*") if p.is_file())
banner_size = sum(p.stat().st_size for p in out_banners.rglob("*") if p.is_file())

media["stats"] = {
    "storyCount": len(stories),
    "imageSourceFilesIndexed": len(image_files),
    "audioSourceFilesIndexed": len(audio_files),
    "backgroundRequested": len(image_requests["background"]),
    "backgroundFound": len(media["images"]["background"]),
    "imageRequested": len(image_requests["image"]),
    "imageFound": len(media["images"]["image"]),
    "characterRequested": len(image_requests["character"]),
    "characterFound": len(media["images"]["character"]),
    "musicRequested": len(audio_requests["music"]),
    "musicFound": len(media["audio"]["music"]),
    "sfxRequested": len(audio_requests["sfx"]),
    "sfxFound": len(media["audio"]["sfx"]),
    "bannerFound": len(media["banners"]),
    "storyBytes": story_size,
    "imageBytes": image_size,
    "audioBytes": audio_size,
    "bannerBytes": banner_size,
    "missingBackground": missing_images["background"][:100],
    "missingImage": missing_images["image"][:100],
    "missingCharacter": missing_images["character"][:100],
    "missingMusic": missing_audio["music"][:100],
    "missingSfx": missing_audio["sfx"][:100],
}

with (out_root / "media_index.json").open("w", encoding="utf-8") as f:
    json.dump(media, f, ensure_ascii=False, separators=(",", ":"))

def pct(found, requested):
    return 100.0 if requested == 0 else found * 100.0 / requested

print(f"Stories: {len(stories)} ({story_size / 1024 / 1024:.1f} MiB raw JSON)")
for kind in ("background", "image", "character"):
    req = len(image_requests[kind])
    found = len(media["images"][kind])
    print(f"Images {kind}: {found}/{req} ({pct(found, req):.1f}%)")
for kind in ("music", "sfx"):
    req = len(audio_requests[kind])
    found = len(media["audio"][kind])
    print(f"Audio {kind}: {found}/{req} ({pct(found, req):.1f}%)")
print(f"Banners: {len(media['banners'])}")
print(f"Packaged media: images={image_size/1024/1024:.1f} MiB audio={audio_size/1024/1024:.1f} MiB banners={banner_size/1024/1024:.1f} MiB")
if errors:
    print(f"Skipped {len(errors)} unreadable story files", file=sys.stderr)
