#!/usr/bin/env python3
import json
import shutil
import sys
from pathlib import Path

if len(sys.argv) != 2:
    raise SystemExit("usage: prepare_story_assets.py <ArknightsStoryJson checkout>")

repo = Path(sys.argv[1]).resolve()
source = repo / "ko_KR" / "gamedata" / "story"
out_root = Path(__file__).resolve().parents[1] / "app" / "src" / "main" / "assets"
out_story = out_root / "story"

if not source.is_dir():
    raise SystemExit(f"story source not found: {source}")

if out_story.exists():
    shutil.rmtree(out_story)
out_story.mkdir(parents=True, exist_ok=True)

stories = []
errors = []
for src in sorted(source.rglob("*.json")):
    rel = src.relative_to(source).as_posix()
    try:
        with src.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or not isinstance(data.get("storyList"), list):
            continue
        dest = out_story / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        stories.append({
            "path": rel,
            "eventId": str(data.get("eventid") or ""),
            "eventName": str(data.get("eventName") or "기타 스토리"),
            "entryType": str(data.get("entryType") or "STORY"),
            "storyCode": str(data.get("storyCode") or ""),
            "avgTag": str(data.get("avgTag") or ""),
            "storyName": str(data.get("storyName") or data.get("storyCode") or rel),
            "storyInfo": str(data.get("storyInfo") or ""),
        })
    except Exception as exc:
        errors.append(f"{rel}: {exc}")

if not stories:
    raise SystemExit("no story JSON files were packaged")

out_root.mkdir(parents=True, exist_ok=True)
index = {
    "lang": "ko_KR",
    "storyCount": len(stories),
    "stories": stories,
}
with (out_root / "story_index.json").open("w", encoding="utf-8") as f:
    json.dump(index, f, ensure_ascii=False, separators=(",", ":"))

size = sum(p.stat().st_size for p in out_story.rglob("*.json"))
print(f"Packaged {len(stories)} stories ({size / 1024 / 1024:.1f} MiB raw JSON)")
if errors:
    print(f"Skipped {len(errors)} unreadable files", file=sys.stderr)
    for e in errors[:20]:
        print(" -", e, file=sys.stderr)
