#!/usr/bin/env python3
import hashlib, json, re, subprocess, sys
from pathlib import Path

if len(sys.argv) != 4:
    raise SystemExit('usage: finalize_media_v32.py <assets2-cn> <assets2-history> <official-audio-report.json>')

A2 = Path(sys.argv[1]).resolve()
HIST = Path(sys.argv[2]).resolve()
REPORT = Path(sys.argv[3]).resolve()
ROOT = Path(__file__).resolve().parents[1]
AS = ROOT / 'app/src/main/assets'
STORY = AS / 'story'
INDEX = AS / 'media_index.json'
IM = AS / 'media/images'
AU = AS / 'media/audio'
media = json.load(open(INDEX, encoding='utf-8'))


def git_bytes(repo, spec):
    return subprocess.check_output(['git', '-C', str(repo), 'show', spec])

def materialize_current(path, outdir):
    data = git_bytes(A2, 'HEAD:' + path)
    ext = Path(path).suffix.lower()
    h = hashlib.sha1(('ArknightsAssets2@cn\0' + path).encode()).hexdigest()[:24]
    dest = outdir / (h + ext)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return dest.relative_to(AS).as_posix()

chars = media.setdefault('images', {}).setdefault('character', {})
# In AVG bundles #1 means the default face. These three are stored as base$1 PNGs.
base_aliases = {
    'avg_npc_602_1#1$1': 'assets/dyn/avg/characters/avg_npc_602_1$1.png',
    'avg_npc_764_1#1$1': 'assets/dyn/avg/characters/avg_npc_764_1$1.png',
    'avg_npc_765_1#1$1': 'assets/dyn/avg/characters/avg_npc_765_1$1.png',
}
for key, path in base_aliases.items():
    if not chars.get(key):
        chars[key] = materialize_current(path, IM)
        print('IMAGE DEFAULT ALIAS', key, '<-', path)

# Mayer's AVG bundle intentionally has no bare sprite; #2 is the neutral/default asset used by the story renderer fallback.
if not chars.get('char_242_mayer'):
    rel = chars.get('char_242_mayer#2')
    if not rel:
        rel = materialize_current('assets/dyn/avg/characters/char_242_mayer/char_242_mayer#2.png', IM)
    chars['char_242_mayer'] = rel
    print('IMAGE DEFAULT FALLBACK char_242_mayer <- char_242_mayer#2')

# Recover audio that disappeared from live Hot Update (notably act24side) from Assets2 Git history.
report = json.load(open(REPORT, encoding='utf-8'))
missing = report.get('missing', {})
print('AUDIO TO RECOVER', {k: len(v) for k, v in missing.items()})
log_paths = subprocess.check_output(
    ['git', '-C', str(HIST), 'log', '--all', '--name-only', '--pretty=format:'],
    text=True, encoding='utf-8', errors='replace'
).splitlines()
by_stem = {}
for p in log_paths:
    low = p.lower()
    if '/audio/' not in low or Path(p).suffix.lower() not in {'.mp3','.wav','.ogg','.flac','.m4a'}:
        continue
    by_stem.setdefault(Path(p).stem.lower(), []).append(p)

recovered = 0
for kind in ('music', 'sfx'):
    amap = media.setdefault('audio', {}).setdefault(kind, {})
    for item in missing.get(kind, []):
        key = str(item.get('key') or '')
        if amap.get(key):
            continue
        clip = str(item.get('clip') or '').strip()
        candidates = [clip]
        if clip.lower().startswith('sys_friend_'):
            candidates.insert(0, 'm_' + clip)
        paths = []
        for cand in candidates:
            paths += by_stem.get(cand.lower(), [])
        paths = list(dict.fromkeys(paths))
        if not paths:
            print('AUDIO HISTORY MISS', kind, key, clip)
            continue
        # Prefer sound_beta_2 and act24side#retro when applicable.
        paths.sort(key=lambda p: (
            0 if 'sound_beta_2' in p.lower() else 1,
            0 if ('act24side#retro' in p.lower() and 'act24side' in clip.lower()) else 1,
            len(p)
        ))
        path = paths[0]
        commit = subprocess.check_output(
            ['git', '-C', str(HIST), 'log', '--all', '-n', '1', '--format=%H', '--', path],
            text=True, encoding='utf-8', errors='replace'
        ).strip()
        if not commit:
            print('AUDIO NO COMMIT', path)
            continue
        data = git_bytes(HIST, commit + ':' + path)
        ext = Path(path).suffix.lower()
        h = hashlib.sha1((commit + '\0' + path).encode()).hexdigest()[:24]
        dest = AU / (h + ext)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        amap[key] = dest.relative_to(AS).as_posix()
        recovered += 1
        print('AUDIO HISTORY RECOVER', kind, key, '<-', path)
print('AUDIO RECOVERED', recovered)

# Recompute requirements using renderer semantics. ImageTween/hideCGItem reference an existing slot, not a new bitmap.
def clean(v):
    if v is None: return ''
    v = str(v).strip().strip('"').strip("'")
    if v.startswith('$'): v = v[1:]
    return v.strip()

reqi = {'background': set(), 'image': set(), 'character': set()}
reqa = {'music': set(), 'sfx': set()}
for fp in STORY.rglob('*.json'):
    try: d = json.load(open(fp, encoding='utf-8'))
    except Exception: continue
    for line in d.get('storyList', []):
        if not isinstance(line, dict): continue
        prop = str(line.get('prop') or '').lower()
        a = line.get('attributes') or {}
        if not isinstance(a, dict): a = {}
        image = clean(a.get('image'))
        if image:
            if prop in ('background','backgroundtween'):
                reqi['background'].add(image)
            elif prop not in ('imagetween','hidecgitem'):
                reqi['image'].add(image)
        if prop == 'character':
            for f in ('name','name2'):
                k = clean(a.get(f))
                if k and 'focus=' not in k and not k.startswith(','):
                    reqi['character'].add(k)
        fig = clean(line.get('figure_art'))
        if fig and 'focus=' not in fig:
            reqi['character'].add(fig)
        if prop == 'playmusic':
            for f in ('key','intro'):
                for q in clean(a.get(f)).split(';'):
                    if clean(q): reqa['music'].add(clean(q))
        elif prop == 'playsound':
            for f, v in a.items():
                if 'key' in str(f).lower():
                    for q in clean(v).split(';'):
                        if clean(q): reqa['sfx'].add(clean(q))

stats = media.setdefault('stats', {})
stats['v32Finalized'] = True
for kind, keys in reqi.items():
    found = sum(1 for k in keys if media['images'][kind].get(k))
    stats[f'v32_{kind}Requested'] = len(keys)
    stats[f'v32_{kind}Found'] = found
    stats[f'v32_{kind}Missing'] = len(keys)-found
for kind, keys in reqa.items():
    found = sum(1 for k in keys if media['audio'][kind].get(k))
    stats[f'v32_{kind}Requested'] = len(keys)
    stats[f'v32_{kind}Found'] = found
    stats[f'v32_{kind}Missing'] = len(keys)-found

json.dump(media, open(INDEX,'w',encoding='utf-8'), ensure_ascii=False, separators=(',',':'))
summary = {k:v for k,v in stats.items() if k.startswith('v32_')}
print(json.dumps(summary, ensure_ascii=False, indent=2))

for kind in ('background','image','character'):
    assert stats[f'v32_{kind}Found'] == stats[f'v32_{kind}Requested'], f'image coverage incomplete: {kind}'
for kind in ('music','sfx'):
    assert stats[f'v32_{kind}Found'] == stats[f'v32_{kind}Requested'], f'audio coverage incomplete: {kind}'
print('V3.2 MEDIA COVERAGE 100%')
