#!/usr/bin/env python3
import hashlib
import json
import re
import shutil
import sys
import tempfile
import time
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

import lz4.block
import UnityPy
from UnityPy.enums.BundleFile import CompressionFlags
from UnityPy.helpers import CompressionHelper

if len(sys.argv) != 3:
    raise SystemExit('usage: supplement_official_audio_v32.py <story_dir> <story_variables.json>')

STORY = Path(sys.argv[1]).resolve()
VARS = Path(sys.argv[2]).resolve()
ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'app/src/main/assets'
INDEX = ASSETS / 'media_index.json'
AUDIO_OUT = ASSETS / 'media/audio'

if not STORY.is_dir():
    raise SystemExit(f'story dir missing: {STORY}')
if not VARS.is_file():
    raise SystemExit(f'story variables missing: {VARS}')
if not INDEX.is_file():
    raise SystemExit(f'media index missing: {INDEX}')


def _extra(data, pos, end):
    n = 0
    while pos < end:
        b = data[pos]
        n += b
        pos += 1
        if b != 0xFF:
            break
    return n, pos


def decompress_lz4ak(src, uncompressed_size):
    ip = op = 0
    buf = bytearray(src)
    end = len(buf)
    while ip < end:
        literal = buf[ip] & 0xF
        match = (buf[ip] >> 4) & 0xF
        buf[ip] = (literal << 4) | match
        ip += 1
        if literal == 0xF:
            x, ip = _extra(buf, ip, end)
            literal += x
        ip += literal
        op += literal
        if op >= uncompressed_size:
            break
        offset = (buf[ip] << 8) | buf[ip + 1]
        buf[ip] = offset & 0xFF
        buf[ip + 1] = (offset >> 8) & 0xFF
        ip += 2
        if match == 0xF:
            x, ip = _extra(buf, ip, end)
            match += x
        match += 4
        op += match
    return lz4.block.decompress(buf, uncompressed_size=uncompressed_size)


CompressionHelper.DECOMPRESSION_MAP[CompressionFlags.LZHAM] = decompress_lz4ak


def get_json(url, timeout=90):
    req = urllib.request.Request(url, headers={'User-Agent': 'RhodesReaderKR-v3.2-private-build'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def clean(value):
    if value is None:
        return ''
    value = str(value).strip().strip('"').strip("'")
    if value.startswith('$'):
        value = value[1:]
    return value.strip()


def add_req(bucket, raw):
    value = clean(raw)
    if not value:
        return
    for part in value.split(';'):
        part = clean(part)
        if part:
            bucket.add(part)


requested = {'music': set(), 'sfx': set()}
for fp in STORY.rglob('*.json'):
    try:
        data = json.load(open(fp, encoding='utf-8'))
    except Exception:
        continue
    for line in data.get('storyList', []):
        if not isinstance(line, dict):
            continue
        prop = str(line.get('prop') or '').lower()
        attrs = line.get('attributes') or {}
        if not isinstance(attrs, dict):
            continue
        if prop == 'playmusic':
            add_req(requested['music'], attrs.get('key'))
            add_req(requested['music'], attrs.get('intro'))
        elif prop == 'playsound':
            for field, value in attrs.items():
                if 'key' in str(field).lower():
                    add_req(requested['sfx'], value)

raw_vars = json.load(open(VARS, encoding='utf-8'))
varmap = {str(k).lower(): v for k, v in raw_vars.items() if isinstance(v, str)}


def resolve(key):
    cur = key
    seen = set()
    for _ in range(5):
        low = cur.lower()
        if low in seen:
            break
        seen.add(low)
        value = varmap.get(low)
        if not value:
            break
        value = str(value).strip()
        if value.startswith('$'):
            value = value[1:]
        cur = value
    return cur


def clip_name(canonical):
    text = canonical.replace('\\', '/').rstrip('/')
    return text.rsplit('/', 1)[-1]


targets = {'music': defaultdict(list), 'sfx': defaultdict(list)}
resolved = {'music': {}, 'sfx': {}}
for kind in ('music', 'sfx'):
    for key in sorted(requested[kind]):
        canonical = resolve(key)
        cname = clip_name(canonical)
        if not cname:
            continue
        resolved[kind][key] = canonical
        targets[kind][cname.lower()].append(key)

all_target_names = set(targets['music']) | set(targets['sfx'])
print('REQUESTED', {k: len(v) for k, v in requested.items()})
print('UNIQUE CLIP NAMES', len(all_target_names))

outer = get_json('https://ak-conf.arknights.kr/config/prod/official/network_config')
conf = json.loads(outer['content'])
network = conf['configs'][conf['funcVer']]['network']
version = get_json(network['hv'].replace('{0}', 'Android'))
res_version = version['resVersion']
base = f"{network['hu']}/Android/assets/{res_version}"
hot = get_json(base + '/hot_update_list.json')
infos = hot['abInfos']


def is_voice(name):
    low = name.lower()
    return low.startswith('audio/sound_beta_2/voice')


def music_relevant(name):
    low = name.lower()
    if not low.startswith('audio/sound_beta_2/music/'):
        return True
    stem = Path(low).stem
    if stem in all_target_names:
        return True
    # Music bundles often group *_intro and *_loop under a common stem.
    for target in all_target_names:
        if target.startswith(stem + '_') or stem.startswith(target + '_'):
            return True
        base_target = re.sub(r'_(?:intro|loop)$', '', target)
        if base_target == stem:
            return True
    return False

bundles = []
for info in infos:
    name = str(info.get('name') or '')
    low = name.lower()
    if not low.startswith('audio/sound_beta_2/'):
        continue
    if is_voice(name):
        continue
    if not music_relevant(name):
        continue
    bundles.append(info)

print('KR resVersion', res_version)
print('candidate official bundles', len(bundles))

media = json.load(open(INDEX, encoding='utf-8'))
media.setdefault('audio', {})
media['audio']['music'] = {}
media['audio']['sfx'] = {}
if AUDIO_OUT.exists():
    shutil.rmtree(AUDIO_OUT)
AUDIO_OUT.mkdir(parents=True, exist_ok=True)

found_clip_path = {}
errors = []
scanned = 0
download_bytes = 0


def dat_name(ab_name):
    return ab_name.replace('/', '_').replace('#', '__').rsplit('.', 1)[0] + '.dat'


def fetch_file(url, dest):
    last = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'RhodesReaderKR-v3.2-private-build'})
            with urllib.request.urlopen(req, timeout=180) as r, open(dest, 'wb') as f:
                while True:
                    chunk = r.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
            if dest.stat().st_size:
                return True
        except Exception as exc:
            last = exc
            dest.unlink(missing_ok=True)
            time.sleep(1 + attempt)
    errors.append(f'download {url}: {last}')
    return False


def save_clip(cname, clip, sample_items):
    if not sample_items:
        return None
    # Usually one WAV per AudioClip. If Unity exposes multiple samples, retain the largest payload.
    sample_name, payload = max(sample_items, key=lambda item: len(item[1]))
    suffix = Path(sample_name).suffix.lower() or '.wav'
    digest = hashlib.sha1(cname.lower().encode('utf-8')).hexdigest()[:24]
    dest = AUDIO_OUT / (digest + suffix)
    if not dest.exists():
        dest.write_bytes(payload)
    return dest.relative_to(ASSETS).as_posix()

with tempfile.TemporaryDirectory(prefix='rhodes-v32-audio-') as td:
    td = Path(td)
    for idx, info in enumerate(bundles, 1):
        if len(found_clip_path) >= len(all_target_names):
            break
        ab_name = str(info['name'])
        dat = td / 'bundle.dat'
        unpack = td / 'unpack'
        if unpack.exists():
            shutil.rmtree(unpack)
        dat.unlink(missing_ok=True)
        url = base + '/' + dat_name(ab_name)
        if not fetch_file(url, dat):
            continue
        download_bytes += dat.stat().st_size
        try:
            with zipfile.ZipFile(dat) as z:
                z.extractall(unpack)
            abs_found = list(unpack.rglob('*.ab'))
            if not abs_found:
                errors.append(f'no ab in {ab_name}')
                continue
            for ab in abs_found:
                env = UnityPy.load(str(ab))
                for obj in env.objects:
                    if obj.type.name != 'AudioClip':
                        continue
                    clip = obj.parse_as_object()
                    cname = str(clip.m_Name or '')
                    low = cname.lower()
                    if low not in all_target_names or low in found_clip_path:
                        continue
                    try:
                        rel = save_clip(cname, clip, list(clip.samples.items()))
                    except Exception as exc:
                        errors.append(f'clip {cname} from {ab_name}: {exc}')
                        continue
                    if rel:
                        found_clip_path[low] = rel
                        print('FOUND', cname, '<-', ab_name)
            scanned += 1
        except Exception as exc:
            errors.append(f'extract {ab_name}: {exc}')
        finally:
            dat.unlink(missing_ok=True)
            if unpack.exists():
                shutil.rmtree(unpack)
        if idx % 25 == 0 or idx == len(bundles):
            fm = sum(1 for n in targets['music'] if n in found_clip_path)
            fs = sum(1 for n in targets['sfx'] if n in found_clip_path)
            print(f'progress {idx}/{len(bundles)} unique clips: music {fm}/{len(targets["music"])} sfx {fs}/{len(targets["sfx"])}')

for kind in ('music', 'sfx'):
    for cname, keys in targets[kind].items():
        rel = found_clip_path.get(cname)
        if not rel:
            continue
        for key in keys:
            media['audio'][kind][key] = rel

stats = media.setdefault('stats', {})
stats['v32OfficialKrAudio'] = True
stats['v32OfficialKrResVersion'] = res_version
stats['v32OfficialBundlesScanned'] = scanned
stats['v32OfficialDownloadBytes'] = download_bytes
stats['v32OfficialAudioErrors'] = errors
for kind in ('music', 'sfx'):
    found = sum(1 for key in requested[kind] if media['audio'][kind].get(key))
    stats[f'v32_{kind}Requested'] = len(requested[kind])
    stats[f'v32_{kind}Found'] = found
    stats[f'v32_{kind}Missing'] = len(requested[kind]) - found

missing = {'music': [], 'sfx': []}
for kind in ('music', 'sfx'):
    for key in sorted(requested[kind]):
        if not media['audio'][kind].get(key):
            missing[kind].append({'key': key, 'canonical': resolved[kind].get(key, key), 'clip': clip_name(resolved[kind].get(key, key))})

json.dump(media, open(INDEX, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
json.dump({'stats': {k: v for k, v in stats.items() if k.startswith('v32')}, 'missing': missing},
          open(ROOT / 'v32-official-audio-report.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

print(json.dumps({k: v for k, v in stats.items() if k.startswith('v32') and k != 'v32OfficialAudioErrors'}, ensure_ascii=False, indent=2))
print('errors', len(errors))
print('missing samples music', missing['music'][:25])
print('missing samples sfx', missing['sfx'][:50])
