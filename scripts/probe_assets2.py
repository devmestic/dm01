#!/usr/bin/env python3
import json,re,subprocess,sys
from collections import defaultdict
from pathlib import Path
story=Path(sys.argv[1]); repo=Path(sys.argv[2])
root=story/'ko_KR'/'gamedata'/'story'
def clean(v):
    if v is None:return ''
    v=str(v).strip().strip('"').strip("'")
    if v.startswith('$'):v=v[1:]
    return v.strip()
def norm(v):return re.sub(r'[^a-z0-9]+','',v.lower())
reqi={'background':set(),'image':set(),'character':set()}; reqa={'music':set(),'sfx':set()}
for p in root.rglob('*.json'):
    try:d=json.load(open(p,encoding='utf-8'))
    except:continue
    for x in d.get('storyList',[]):
        if not isinstance(x,dict):continue
        prop=str(x.get('prop') or '').lower(); a=x.get('attributes') or {}
        if not isinstance(a,dict):a={}
        im=clean(a.get('image'))
        if im:reqi['background' if prop in ('background','backgroundtween') else 'image'].add(im)
        if prop=='character':
            for f in ('name','name2'):
                k=clean(a.get(f))
                if k and 'focus=' not in k and not k.startswith(','):reqi['character'].add(k)
        fig=clean(x.get('figure_art'))
        if fig:reqi['character'].add(fig)
        if prop=='playmusic':
            for f in ('key','intro'):
                for q in clean(a.get(f)).split(';'):
                    if clean(q):reqa['music'].add(clean(q))
        elif prop=='playsound':
            for f,v in a.items():
                if 'key' in str(f).lower():
                    for q in clean(v).split(';'):
                        if clean(q):reqa['sfx'].add(clean(q))
paths=subprocess.check_output(['git','-C',str(repo),'ls-tree','-r','--name-only','HEAD'],text=True,encoding='utf-8',errors='replace').splitlines()
imgext={'.png','.jpg','.jpeg','.webp'}; audext={'.wav','.mp3','.ogg','.m4a','.flac'}
ie=defaultdict(list); ine=defaultdict(list); ae=defaultdict(list); ane=defaultdict(list)
for path in paths:
    p=Path(path); st=p.stem
    if p.suffix.lower() in imgext:ie[st.lower()].append(path);ine[norm(st)].append(path)
    if p.suffix.lower() in audext:ae[st.lower()].append(path);ane[norm(st)].append(path)
print('TREE',len(paths),'IMAGES',sum(map(len,ie.values())),'AUDIO',sum(map(len,ae.values())))
def variants(k):
    v=[k,re.sub(r'[#\$]+','_',k)]
    if '/' in k:v.append(Path(k).name)
    return list(dict.fromkeys(v))
def hit(idx,nidx,k):
    for v in variants(k):
        if idx.get(v.lower()):return idx[v.lower()][0]
        c=nidx.get(norm(v),[])
        if len(c)==1:return c[0]
    return None
out={'images':{},'audio':{},'treePaths':len(paths),'imageFiles':sum(map(len,ie.values())),'audioFiles':sum(map(len,ae.values()))}
for kind,ks in reqi.items():
    found={};miss=[]
    for k in sorted(ks):
        h=hit(ie,ine,k)
        if h:found[k]=h
        else:miss.append(k)
    out['images'][kind]={'requested':len(ks),'found':len(found),'missing':len(miss),'samples':list(found.items())[:20]}
for kind,ks in reqa.items():
    found={};miss=[]
    for k in sorted(ks):
        h=hit(ae,ane,k)
        if h:found[k]=h
        else:
            # common bank prefixes
            nk=norm(k); cand=[]
            for sk,ps in ane.items():
                if len(nk)>=6 and (nk in sk or sk in nk):cand+=ps
            cand=list(dict.fromkeys(cand))
            if len(cand)==1:found[k]=cand[0]
            else:miss.append(k)
    out['audio'][kind]={'requested':len(ks),'found':len(found),'missing':len(miss),'samples':list(found.items())[:20]}
print(json.dumps(out,ensure_ascii=False,indent=2));open('assets2-probe.json','w').write(json.dumps(out,ensure_ascii=False,indent=2))
