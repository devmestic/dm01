#!/usr/bin/env python3
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
AS=ROOT/'app/src/main/assets'
STORY=AS/'story'
INDEX=AS/'media_index.json'
media=json.load(open(INDEX,encoding='utf-8'))

def clean(v):
    if v is None:return ''
    v=str(v).strip().strip('"').strip("'")
    if v.startswith('$'):v=v[1:]
    return v.strip()

def add(bucket,v):
    v=clean(v)
    if not v:return
    for x in v.split(';'):
        x=clean(x)
        if x:bucket.add(x)

req={k:set() for k in ('background','image','character','music','sfx')}
ignored={'image_nonresource':{}}
for fp in STORY.rglob('*.json'):
    try:d=json.load(open(fp,encoding='utf-8'))
    except Exception:continue
    for line in d.get('storyList',[]):
        if not isinstance(line,dict):continue
        prop=str(line.get('prop') or '').lower()
        a=line.get('attributes') or {}
        if not isinstance(a,dict):a={}
        im=clean(a.get('image'))
        if im:
            if prop in ('background','backgroundtween'):
                req['background'].add(im)
            elif prop in ('imagetween','hidecgitem'):
                # ImageTween's image parameter is an already-created image/tween target id,
                # while hidecgitem only removes an existing CG item. Neither requests a file.
                ignored['image_nonresource'][im]=prop
            else:
                req['image'].add(im)
        if prop=='character':
            for f in ('name','name2'):
                k=clean(a.get(f))
                if k and 'focus=' not in k and not k.startswith(','):req['character'].add(k)
        fig=clean(line.get('figure_art'))
        if fig and 'focus=' not in fig:req['character'].add(fig)
        if prop=='playmusic':
            add(req['music'],a.get('key'));add(req['music'],a.get('intro'))
        elif prop=='playsound':
            for f,v in a.items():
                if 'key' in str(f).lower():add(req['sfx'],v)

maps={
 'background':media.get('images',{}).get('background',{}),
 'image':media.get('images',{}).get('image',{}),
 'character':media.get('images',{}).get('character',{}),
 'music':media.get('audio',{}).get('music',{}),
 'sfx':media.get('audio',{}).get('sfx',{}),
}
out={'requested':{},'found':{},'missing':{},'ignoredNonResourceImageIds':ignored['image_nonresource']}
for kind in req:
    out['requested'][kind]=len(req[kind])
    miss=[k for k in sorted(req[kind]) if not maps[kind].get(k)]
    out['missing'][kind]=miss
    out['found'][kind]=len(req[kind])-len(miss)
Path('v32-final-coverage.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'requested':out['requested'],'found':out['found'],'missingCounts':{k:len(v) for k,v in out['missing'].items()},'ignoredNonResourceImageIds':out['ignoredNonResourceImageIds']},ensure_ascii=False,indent=2))
for kind,miss in out['missing'].items():
    if miss:
        print('MISSING',kind,len(miss))
        for k in miss[:500]:print(' ',k)
# Final build is allowed to ship only when every renderable story media reference resolves.
assert all(not v for v in out['missing'].values()), 'renderable media coverage is not 100%'
