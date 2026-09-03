#!/usr/bin/env python3
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

if len(sys.argv) != 4:
    raise SystemExit("usage: prepare_full_assets.py <ArknightsStoryJson> <ArknightsResource-git> <arknights-audio-git>")

story_repo = Path(sys.argv[1]).resolve()
image_repo = Path(sys.argv[2]).resolve()
audio_repo = Path(sys.argv[3]).resolve()

story_source = story_repo / "ko_KR" / "gamedata" / "story"
banner_source = story_repo / "img" / "banners"

project_root = Path(__file__).resolve().parents[1]
out_root = project_root / "app" / "src" / "main" / "assets"
out_story = out_root / "story"
out_media = out_root / "media"
out_images = out_media / "images"
out_audio = out_media / "audio"
out_banners = out_media / "banners"

if not story_source.is_dir():
    raise SystemExit(f"story source not found: {story_source}")
for repo in (image_repo, audio_repo):
    if not (repo / ".git").is_dir():
        raise SystemExit(f"filtered git repository not found: {repo}")

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
            for field in ("name", "name2"):
                value = clean_key(attrs.get(field))
                if value:
                    image_requests["character"].add(value)

        figure = clean_key(line.get("figure_art"))
        if figure:
            image_requests["character"].add(figure)

        if prop == "playmusic":
            add_audio("music", attrs.get("key"))
            add_audio("music", attrs.get("intro"))
        elif prop == "playsound":
            for field, value in attrs.items():
                if "key" in str(field).lower():
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

with (out_root / "story_index.json").open("w", encoding="utf-8") as f:
    json.dump({"lang": "ko_KR", "storyCount": len(stories), "stories": stories},
              f, ensure_ascii=False, separators=(",", ":"))


def git_paths(repo, prefixes):
    cmd = ["git", "-C", str(repo), "ls-tree", "-r", "--name-only", "HEAD", "--"] + list(prefixes)
    text = subprocess.check_output(cmd, text=True, encoding="utf-8", errors="replace")
    return [line.strip() for line in text.splitlines() if line.strip()]


def norm(value):
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def index_paths(paths, extensions):
    exact = defaultdict(list)
    normalized = defaultdict(list)
    usable = []
    for raw in paths:
        p = Path(raw)
        if p.suffix.lower() not in extensions:
            continue
        usable.append(raw)
        exact[p.stem.lower()].append(raw)
        n = norm(p.stem)
        if n:
            normalized[n].append(raw)
    return usable, exact, normalized


print("Indexing image/audio trees without downloading repository blobs...")
image_paths, image_exact, image_norm = index_paths(
    git_paths(image_repo, ["avgs"]), {".png", ".jpg", ".jpeg", ".webp"})
audio_paths, audio_exact, audio_norm = index_paths(
    git_paths(audio_repo, ["music", "avg", "player"]), {".mp3", ".ogg", ".wav", ".m4a"})
print(f"Indexed paths: images={len(image_paths)} audio={len(audio_paths)}")


def rank_image(path, kind, key):
    p = path.lower()
    stem = Path(path).stem
    score = 0
    if stem.lower() == key.lower():
        score -= 1000
    if kind == "background":
        if "/bg/" in p:
            score -= 400
        if "background" in p:
            score -= 50
    elif kind == "character":
        if "char" in stem.lower() or "npc" in stem.lower():
            score -= 180
        if "/bg/" in p:
            score += 400
    else:
        if "/bg/" in p:
            score += 250
    return score + path.count("/")


def find_image(kind, key):
    candidates = list(image_exact.get(key.lower(), []))
    if not candidates:
        variants = [
            key.replace("#", "_"),
            key.replace("$", "_"),
            key.replace("#", "_0"),
        ]
        for value in variants:
            candidates.extend(image_exact.get(value.lower(), []))
    if not candidates:
        candidates = list(image_norm.get(norm(key), []))
    if not candidates:
        return None
    return sorted(set(candidates), key=lambda p: rank_image(p, kind, key))[0]


def rank_audio(path, kind, key):
    p = path.lower()
    score = 0
    if Path(path).stem.lower() == key.lower():
        score -= 1000
    if kind == "music":
        if p.startswith("music/"):
            score -= 400
    else:
        if p.startswith("avg/"):
            score -= 400
        elif p.startswith("player/"):
            score -= 200
        if p.startswith("music/"):
            score += 150
    return score + path.count("/")


def find_audio(kind, key):
    candidates = list(audio_exact.get(key.lower(), []))
    if not candidates:
        candidates = list(audio_norm.get(norm(key), []))
    if not candidates:
        n = norm(key)
        fuzzy = []
        if len(n) >= 6:
            for stem_norm, paths in audio_norm.items():
                if n in stem_norm or stem_norm in n:
                    fuzzy.extend(paths)
                    if len(fuzzy) > 20:
                        break
        if fuzzy:
            distinct = {Path(p).stem.lower() for p in fuzzy}
            if len(distinct) == 1 or len(fuzzy) <= 3:
                candidates = fuzzy
    if not candidates:
        return None
    return sorted(set(candidates), key=lambda p: rank_audio(p, kind, key))[0]


def raw_url(repo_slug, ref, path):
    quoted = urllib.parse.quote(path, safe="/")
    return f"https://raw.githubusercontent.com/{repo_slug}/{ref}/{quoted}"


def dest_for(source_id, source_path, media_dir):
    digest = hashlib.sha1((source_id + "\0" + source_path).encode("utf-8")).hexdigest()[:24]
    return media_dir / f"{digest}{Path(source_path).suffix.lower()}"


media = {
    "version": 3,
    "images": {"background": {}, "image": {}, "character": {}},
    "audio": {"music": {}, "sfx": {}},
    "banners": {},
    "stats": {},
}
missing_images = {kind: [] for kind in image_requests}
missing_audio = {kind: [] for kind in audio_requests}
assignments = []

for kind in ("background", "image", "character"):
    for key in sorted(image_requests[kind]):
        source_path = find_image(kind, key)
        if source_path is None:
            missing_images[kind].append(key)
            continue
        dest = dest_for("fexli/ArknightsResource@main", source_path, out_images)
        assignments.append(("image", kind, key, source_path,
                            raw_url("fexli/ArknightsResource", "main", source_path), dest))

for kind in ("music", "sfx"):
    for key in sorted(audio_requests[kind]):
        source_path = find_audio(kind, key)
        if source_path is None:
            missing_audio[kind].append(key)
            continue
        dest = dest_for("PseudoMon/arknights-audio@global-server-voices", source_path, out_audio)
        assignments.append(("audio", kind, key, source_path,
                            raw_url("PseudoMon/arknights-audio", "global-server-voices", source_path), dest))


def download_one(url, dest):
    if dest.exists() and dest.stat().st_size > 0:
        return True, None
    dest.parent.mkdir(parents=True, exist_ok=True)
    last = None
    for attempt in range(4):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "RhodesReaderKR-build/3.0"})
            with urllib.request.urlopen(request, timeout=90) as response, dest.open("wb") as out:
                shutil.copyfileobj(response, out, 1024 * 1024)
            if dest.stat().st_size <= 0:
                raise IOError("downloaded file is empty")
            return True, None
        except Exception as exc:
            last = exc
            try:
                dest.unlink(missing_ok=True)
            except Exception:
                pass
            time.sleep(1.5 * (attempt + 1))
    return False, str(last)


unique = {}
for assignment in assignments:
    unique[(assignment[4], assignment[5])] = None
print(f"Downloading {len(unique)} unique story-referenced media files...")
results = {}
with ThreadPoolExecutor(max_workers=20) as pool:
    futures = {pool.submit(download_one, url, dest): (url, dest) for url, dest in unique}
    done = 0
    for future in as_completed(futures):
        url, dest = futures[future]
        ok, error = future.result()
        results[(url, dest)] = (ok, error)
        done += 1
        if done % 100 == 0 or done == len(futures):
            print(f"  media downloads {done}/{len(futures)}")

for media_type, kind, key, source_path, url, dest in assignments:
    ok, error = results.get((url, dest), (False, "missing download result"))
    if ok:
        rel = dest.relative_to(out_root).as_posix()
        if media_type == "image":
            media["images"][kind][key] = rel
        else:
            media["audio"][kind][key] = rel
    else:
        if media_type == "image":
            if key not in missing_images[kind]:
                missing_images[kind].append(key)
        else:
            if key not in missing_audio[kind]:
                missing_audio[kind].append(key)
        print(f"WARN download failed: {source_path}: {error}", file=sys.stderr)

if banner_source.is_dir():
    banner_index = {p.stem: p for p in banner_source.glob("*.png")}
    for event_id in sorted(event_ids):
        src = banner_index.get(event_id)
        if src:
            dest = dest_for("050644zf/ArknightsStoryJson@main", f"img/banners/{src.name}", out_banners)
            if not dest.exists():
                shutil.copy2(src, dest)
            media["banners"][event_id] = dest.relative_to(out_root).as_posix()

story_size = sum(p.stat().st_size for p in out_story.rglob("*.json"))
image_size = sum(p.stat().st_size for p in out_images.rglob("*") if p.is_file())
audio_size = sum(p.stat().st_size for p in out_audio.rglob("*") if p.is_file())
banner_size = sum(p.stat().st_size for p in out_banners.rglob("*") if p.is_file())

media["stats"] = {
    "storyCount": len(stories),
    "imageSourceFilesIndexed": len(image_paths),
    "audioSourceFilesIndexed": len(audio_paths),
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
    "missingBackground": sorted(missing_images["background"])[:200],
    "missingImage": sorted(missing_images["image"])[:200],
    "missingCharacter": sorted(missing_images["character"])[:200],
    "missingMusic": sorted(missing_audio["music"])[:200],
    "missingSfx": sorted(missing_audio["sfx"])[:200],
}

with (out_root / "media_index.json").open("w", encoding="utf-8") as f:
    json.dump(media, f, ensure_ascii=False, separators=(",", ":"))


def pct(found, requested):
    return 100.0 if requested == 0 else found * 100.0 / requested

print(f"Stories: {len(stories)} ({story_size / 1024 / 1024:.1f} MiB raw JSON)")
for kind in ("background", "image", "character"):
    requested = len(image_requests[kind])
    found = len(media["images"][kind])
    print(f"Images {kind}: {found}/{requested} ({pct(found, requested):.1f}%)")
for kind in ("music", "sfx"):
    requested = len(audio_requests[kind])
    found = len(media["audio"][kind])
    print(f"Audio {kind}: {found}/{requested} ({pct(found, requested):.1f}%)")
print(f"Banners: {len(media['banners'])}")
print(f"Packaged media: images={image_size/1024/1024:.1f} MiB audio={audio_size/1024/1024:.1f} MiB banners={banner_size/1024/1024:.1f} MiB")
if errors:
    print(f"Skipped {len(errors)} unreadable story files", file=sys.stderr)
