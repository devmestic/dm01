#!/usr/bin/env python3
import hashlib
import json
import re
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'app/src/main/assets'
STORY = ASSETS / 'story'
INDEX = ASSETS / 'media_index.json'
OUT = ASSETS / 'media/images'
EXTS = {'.png', '.jpg', '.jpeg', '.webp'}

media = json.load(open(INDEX, encoding='utf-8'))
images = media.setdefault('images', {})
for k in ('background', 'image', 'character'):
    images.setdefault(k, {})
OUT.mkdir(parents=True, exist_ok=True)


def clean(v):
    if v is None: return ''
    v = str(v).strip().strip('"').strip("'")
    if v.startswith('$'): v = v[1:]
    return v.strip()


def norm(v):
    return re.sub(r'[^a-z0-9]+', '', v.lower())


def variants(k):
    out = [k, re.sub(r'[#\$]+', '_', k)]
    if '/' in k or '\\' in k:
        out.append(Path(k.replace('\\', '/')).name)
    return list(dict.fromkeys(x for x in out if x))

req = {'background': set(), 'image': set(), 'character': set()}
for fp in STORY.rglob('*.json'):
    try:
        data = json.load(open(fp, encoding='utf-8'))
    except Exception:
        continue
    for line in data.get('storyList', []):
        if not isinstance(line, dict): continue
        prop = str(line.get('prop') or '').lower()
        a = line.get('attributes') or {}
        if not isinstance(a, dict): a = {}
        im = clean(a.get('image'))
        if im:
            req['background' if prop in ('background', 'backgroundtween') else 'image'].add(im)
        if prop == 'character':
            for f in ('name', 'name2'):
                key = clean(a.get(f))
                if key and 'focus=' not in key and not key.startswith(','):
                    req['character'].add(key)
        fig = clean(line.get('figure_art'))
        if fig and 'focus=' not in fig:
            req['character'].add(fig)

missing_before = {kind: [k for k in sorted(keys) if not images[kind].get(k)] for kind, keys in req.items()}
print('MISSING_BEFORE', {k: len(v) for k, v in missing_before.items()})


def run(args, cwd=None, text=True, check=True):
    return subprocess.run(args, cwd=cwd, check=check, capture_output=True, text=text)


def first_existing_commit(repo, path):
    commits = run(['git', 'log', '--all', '--format=%H', '--', path], cwd=repo).stdout.splitlines()
    for sha in commits:
        p = subprocess.run(['git', 'cat-file', '-e', f'{sha}:{path}'], cwd=repo,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if p.returncode == 0:
            return sha
    return None

report = {'missingBefore': {k: len(v) for k, v in missing_before.items()}, 'recovered': {k: {} for k in req}, 'missing': {k: {} for k in req}, 'historyPaths': 0}
with tempfile.TemporaryDirectory(prefix='rhodes-image-history-') as td:
    repo = Path(td) / 'ArknightsAssets2'
    subprocess.run(['git', 'clone', '--filter=blob:none', '--no-checkout', 'https://github.com/ArknightsAssets/ArknightsAssets2.git', str(repo)], check=True)
    subprocess.run(['git', 'fetch', 'origin', '+refs/heads/*:refs/remotes/origin/*'], cwd=repo, check=True)
    history = run(['git', 'log', '--all', '--name-only', '--pretty=format:', '--', 'assets/dyn/avg'], cwd=repo).stdout
    paths = sorted({line.strip() for line in history.splitlines() if line.strip() and Path(line.strip()).suffix.lower() in EXTS})
    report['historyPaths'] = len(paths)
    exact = defaultdict(list); normalized = defaultdict(list)
    for p in paths:
        stem = Path(p).stem
        exact[stem.lower()].append(p)
        normalized[norm(stem)].append(p)

    for kind, keys in missing_before.items():
        for key in keys:
            candidates = []
            for v in variants(key):
                candidates.extend(exact.get(v.lower(), []))
            if not candidates:
                nc = normalized.get(norm(key), [])
                if len(nc) == 1:
                    candidates.extend(nc)
            candidates = list(dict.fromkeys(candidates))
            # Prefer the semantically correct AVG bucket.
            preferred = {'background': '/avg/backgrounds/', 'image': '/avg/images/', 'character': '/avg/characters/'}[kind]
            candidates.sort(key=lambda p: (0 if preferred in ('/' + p.lower()) else 1, len(p)))
            recovered = False
            attempts = []
            for path in candidates:
                sha = first_existing_commit(repo, path)
                attempts.append({'path': path, 'commit': sha})
                if not sha: continue
                try:
                    payload = run(['git', 'show', f'{sha}:{path}'], cwd=repo, text=False).stdout
                except subprocess.CalledProcessError:
                    continue
                if not payload: continue
                ext = Path(path).suffix.lower()
                digest = hashlib.sha1(('history-image\0' + kind + '\0' + key).encode('utf-8')).hexdigest()[:24]
                dest = OUT / (digest + ext)
                dest.write_bytes(payload)
                rel = dest.relative_to(ASSETS).as_posix()
                images[kind][key] = rel
                report['recovered'][kind][key] = {'path': path, 'commit': sha, 'asset': rel, 'bytes': len(payload)}
                print('RECOVERED_IMAGE', kind, key, '<-', path, sha[:12], len(payload))
                recovered = True
                break
            if not recovered:
                report['missing'][kind][key] = {'candidates': attempts}
                print('MISSING_IMAGE_HISTORY', kind, key, 'candidates', len(candidates))

stats = media.setdefault('stats', {})
for kind, keys in req.items():
    found = sum(1 for k in keys if images[kind].get(k))
    stats['v32_' + kind + 'Requested'] = len(keys)
    stats['v32_' + kind + 'Found'] = found
    stats['v32_' + kind + 'Missing'] = len(keys) - found
json.dump(media, open(INDEX, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
json.dump(report, open(ROOT / 'v32-historical-image-report.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('FINAL_IMAGES', {kind: (stats['v32_'+kind+'Found'], stats['v32_'+kind+'Requested']) for kind in req})
