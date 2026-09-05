#!/usr/bin/env python3
import hashlib, json, re, subprocess, sys, urllib.request
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

def materialize_external_png(url):
    req = urllib.request.Request(url, headers={'User-Agent':'RhodesReaderKR-v3.2-finalizer'})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise RuntimeError('legacy image is not PNG: ' + url)
    h = hashlib.sha1(('PRTS\0' + url).encode()).hexdigest()[:24]
    dest = IM / (h + '.png')
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

# Four removed legacy expressions still exist in the PRTS historical asset archive.
legacy_exact = {
    'char_1502_crowns#2': 'https://media.prts.wiki/b/bf/Avg_avg_1502_crosly_1-2%241.png',
    'char_201_moeshd#8': 'https://media.prts.wiki/7/7a/Avg_avg_201_moeshd_1-8%241.png',
    'char_219_meteo_1#7': 'https://media.prts.wiki/2/28/Avg_avg_219_meteo_1-7%241.png',
    'char_242_mayer#1': 'https://media.prts.wiki/0/0c/Avg_avg_242_otter_1-1%241.png',
}
legacy_exact_ok = []
legacy_exact_errors = []
for key, url in legacy_exact.items():
    if chars.get(key):
        continue
    try:
        chars[key] = materialize_external_png(url)
        legacy_exact_ok.append(key)
        print('IMAGE LEGACY EXACT', key, '<-', url)
    except Exception as e:
        legacy_exact_errors.append(f'{key}:{e}')
        print('IMAGE LEGACY EXACT ERROR', key, repr(e))

# Three story-era expression numbers have disappeared from both the current KR bundle and public archives.
# Keep the renderer non-blank by aliasing to the nearest surviving expression of the same character.
legacy_compat = {
    'char_148_nearl_1#8': ('assets/dyn/avg/characters/char_148_nearl_1/char_148_nearl_7.png', 'char_148_nearl_1#7'),
    'char_259_Jessica_1#3': ('assets/dyn/avg/characters/char_259_jessica_1/char_259_jessica_2.png', 'char_259_Jessica_1#2'),
    'char_259_Jessica_1#7': ('assets/dyn/avg/characters/char_259_jessica_1/char_259_jessica_6.png', 'char_259_Jessica_1#6'),
}
legacy_compat_used = []
for key, (path, alias_key) in legacy_compat.items():
    if chars.get(key):
        continue
    rel = chars.get(alias_key)
    if not rel:
        rel = materialize_current(path, IM)
    chars[key] = rel
    legacy_compat_used.append({'key':key,'alias':alias_key,'path':path})
    print('IMAGE LEGACY COMPAT', key, '<-', alias_key, path)

# If the historical mirror is temporarily unavailable, preserve no-blank behavior for the four exact legacy keys too.
legacy_exact_fallback = {
    'char_1502_crowns#2': ('char_1502_crowns', None),
    'char_201_moeshd#8': ('char_201_moeshd#7', 'assets/dyn/avg/characters/char_201_moeshd/char_201_moeshd_7.png'),
    'char_219_meteo_1#7': ('char_219_meteo_1#5', 'assets/dyn/avg/characters/char_219_meteo_1/char_219_meteo_5.png'),
    'char_242_mayer#1': ('char_242_mayer#2', 'assets/dyn/avg/characters/char_242_mayer/char_242_mayer#2.png'),
}
for key, (alias_key, path) in legacy_exact_fallback.items():
    if chars.get(key):
        continue
    rel = chars.get(alias_key)
    if not rel and path:
        rel = materialize_current(path, IM)
    if not rel:
        raise RuntimeError('cannot resolve legacy fallback: ' + key)
    chars[key] = rel
    legacy_compat_used.append({'key':key,'alias':alias_key,'path':path,'reason':'archive-download-failed'})
    print('IMAGE LEGACY ARCHIVE FALLBACK', key, '<-', alias_key)

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
stats['v32LegacyExactRecovered'] = legacy_exact_ok
stats['v32LegacyExactErrors'] = legacy_exact_errors
stats['v32LegacyCompatAliases'] = legacy_compat_used
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
