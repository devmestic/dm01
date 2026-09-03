#!/usr/bin/env python3
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'app/src/main/assets'
INDEX = ASSETS / 'media_index.json'
OUT = ASSETS / 'media/audio'
TARGETS = ROOT / 'scripts/v32_historical_mh_targets.json'

media = json.load(open(INDEX, encoding='utf-8'))
targets = json.load(open(TARGETS, encoding='utf-8'))
audio = media.setdefault('audio', {})
audio.setdefault('music', {})
audio.setdefault('sfx', {})
OUT.mkdir(parents=True, exist_ok=True)


def run(args, cwd=None, text=True, check=True):
    return subprocess.run(args, cwd=cwd, check=check, capture_output=True, text=text)


def first_existing_commit(repo: Path, path: str):
    commits = run(['git', 'log', '--all', '--format=%H', '--', path], cwd=repo).stdout.splitlines()
    for sha in commits:
        probe = subprocess.run(['git', 'cat-file', '-e', f'{sha}:{path}'], cwd=repo,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if probe.returncode == 0:
            return sha
    return None


def save_bytes(kind: str, key: str, clip: str, payload: bytes):
    digest = hashlib.sha1(('history-mh\0' + kind + '\0' + key).encode('utf-8')).hexdigest()[:24]
    dest = OUT / (digest + '.mp3')
    dest.write_bytes(payload)
    rel = dest.relative_to(ASSETS).as_posix()
    audio[kind][key] = rel
    return rel

report = {'repository': 'ArknightsAssets/ArknightsAssets2', 'recovered': {'music': {}, 'sfx': {}}, 'missing': {'music': {}, 'sfx': {}}, 'historyPaths': 0}

with tempfile.TemporaryDirectory(prefix='rhodes-mh-history-') as td:
    repo = Path(td) / 'ArknightsAssets2'
    subprocess.run([
        'git', 'clone', '--filter=blob:none', '--no-checkout',
        'https://github.com/ArknightsAssets/ArknightsAssets2.git', str(repo)
    ], check=True)
    # Ensure every branch tip is available; the old audio lived on asset-history branches.
    subprocess.run([
        'git', 'fetch', 'origin', '+refs/heads/*:refs/remotes/origin/*'
    ], cwd=repo, check=True)

    history = run([
        'git', 'log', '--all', '--name-only', '--pretty=format:', '--',
        'assets/dyn/audio/sound_beta_2'
    ], cwd=repo).stdout
    paths = sorted({line.strip() for line in history.splitlines()
                    if line.strip().lower().endswith('.mp3') and '/audio/sound_beta_2/' in line.lower()})
    report['historyPaths'] = len(paths)
    by_name = {}
    for path in paths:
        by_name.setdefault(Path(path).name.lower(), []).append(path)

    for kind in ('music', 'sfx'):
        for key, clip in targets[kind].items():
            if audio[kind].get(key):
                continue
            wanted = (clip + '.mp3').lower()
            candidates = by_name.get(wanted, [])
            if kind == 'sfx':
                candidates = sorted(candidates, key=lambda p: ('#retro' not in p.lower(), len(p)))
            else:
                candidates = sorted(candidates, key=lambda p: ('/music/act24side/' not in p.lower(), len(p)))
            recovered = False
            attempts = []
            for path in candidates:
                sha = first_existing_commit(repo, path)
                attempts.append({'path': path, 'commit': sha})
                if not sha:
                    continue
                try:
                    payload = run(['git', 'show', f'{sha}:{path}'], cwd=repo, text=False).stdout
                except subprocess.CalledProcessError:
                    continue
                if not payload:
                    continue
                rel = save_bytes(kind, key, clip, payload)
                report['recovered'][kind][key] = {
                    'clip': clip, 'path': path, 'commit': sha, 'asset': rel, 'bytes': len(payload)
                }
                print('RECOVERED', kind, key, clip, '<-', path, sha[:12], len(payload))
                recovered = True
                break
            if not recovered:
                report['missing'][kind][key] = {'clip': clip, 'candidates': attempts}
                print('MISSING_HISTORY', kind, key, clip, 'candidates', len(candidates))

stats = media.setdefault('stats', {})
stats['v32HistoricalMhMusicRecovered'] = len(report['recovered']['music'])
stats['v32HistoricalMhSfxRecovered'] = len(report['recovered']['sfx'])
stats['v32HistoricalMhMusicMissing'] = len(report['missing']['music'])
stats['v32HistoricalMhSfxMissing'] = len(report['missing']['sfx'])
json.dump(media, open(INDEX, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
json.dump(report, open(ROOT / 'v32-historical-mh-audio-report.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print(json.dumps({
    'recoveredMusic': len(report['recovered']['music']),
    'recoveredSfx': len(report['recovered']['sfx']),
    'missingMusic': len(report['missing']['music']),
    'missingSfx': len(report['missing']['sfx']),
    'historyPaths': report['historyPaths'],
}, ensure_ascii=False, indent=2))

# These historical files were verified in the repository history before this recovery step.
# Fail hard rather than silently branding an incomplete audio pack as complete.
assert not report['missing']['music'], report['missing']['music']
assert not report['missing']['sfx'], report['missing']['sfx']
