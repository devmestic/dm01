#!/usr/bin/env python3
import json, re, subprocess, sys
from collections import defaultdict
from pathlib import Path

if len(sys.argv) != 5:
    raise SystemExit('usage: coverage_v31.py <story> <fexli> <aceship> <audio>')
story_repo, fexli_repo, aceship_repo, audio_repo = map(lambda x: Path(x).resolve(), sys.argv[1:])
story_root = story_repo / 'ko_KR' / 'gamedata' / 'story'
IMG_EXT={'.png','.jpg','.jpeg','.webp'}
AUD_EXT={'.mp3','.ogg','.wav','.m4a','.flac'}

def clean(v):
    if v is None: return ''
    v=str(v).strip().strip('"').strip("'")
    if v.startswith('$'): v=v[1:]
    return v.strip()

def norm(v): return re.sub(r'[^a-z0-9]+','',v.lower())
def stem_variants(k):
    k=clean(k); out=[k,re.sub(r'[#\$]+','_',k)]
    if '/' in k or '\\' in k: out.append(Path(k.replace('\\','/')).name)
    return [x for x in dict.fromkeys(out) if x]
def char_variants(k):
    out=[]
    for raw in stem_variants(k):
        out.append(raw)
        if re.match(r'^avg_',raw,re.I): out.append(re.sub(r'^avg_','avgnew_',raw,flags=re.I))
        if re.match(r'^avgnew_',raw,re.I): out.append(re.sub(r'^avgnew_','avg_',raw,flags=re.I))
    return [x for x in dict.fromkeys(out) if x]

def git_paths(repo, prefixes=None):
    cmd=['git','-C',str(repo),'ls-tree','-r','--name-only','HEAD']
    if prefixes: cmd += ['--'] + list(prefixes)
    return [x for x in subprocess.check_output(cmd,text=True,encoding='utf-8',errors='replace').splitlines() if x]
def make_index(paths, exts):
    exact=defaultdict(list); normalized=defaultdict(list); usable=[]
    for p in paths:
        pp=Path(p)
        if pp.suffix.lower() not in exts: continue
        usable.append(p); exact[pp.stem.lower()].append(p); normalized[norm(pp.stem)].append(p)
    return usable,exact,normalized

req_img={'background':set(),'image':set(),'character':set()}; req_aud={'music':set(),'sfx':set()}; stories=0
for p in sorted(story_root.rglob('*.json')):
    try: d=json.load(open(p,encoding='utf-8'))
    except Exception: continue
    if not isinstance(d,dict) or not isinstance(d.get('storyList'),list): continue
    stories+=1
    for line in d['storyList']:
        if not isinstance(line,dict): continue
        prop=str(line.get('prop') or '').lower(); a=line.get('attributes') or {}
        if not isinstance(a,dict): a={}
        im=clean(a.get('image'))
        if im: req_img['background' if prop in ('background','backgroundtween') else 'image'].add(im)
        if prop=='character':
            for f in ('name','name2'):
                k=clean(a.get(f))
                if k and 'focus=' not in k and not k.startswith(','): req_img['character'].add(k)
        fig=clean(line.get('figure_art'))
        if fig and 'focus=' not in fig: req_img['character'].add(fig)
        if prop=='playmusic':
            for f in ('key','intro'):
                for q in clean(a.get(f)).split(';'):
                    if clean(q): req_aud['music'].add(clean(q))
        elif prop=='playsound':
            for f,v in a.items():
                if 'key' in str(f).lower():
                    for q in clean(v).split(';'):
                        if clean(q): req_aud['sfx'].add(clean(q))

f_paths,f_exact,f_norm=make_index(git_paths(fexli_repo,['avgs']),IMG_EXT)
a_paths,a_exact,a_norm=make_index(git_paths(aceship_repo,['avg']),IMG_EXT)
aud_paths,aud_exact,aud_norm=make_index(git_paths(audio_repo),AUD_EXT)
try: summary=json.loads(subprocess.check_output(['git','-C',str(fexli_repo),'show','HEAD:avgs/npcs/summary.json'],text=True,encoding='utf-8'))
except Exception: summary={}
summary_items=set()
for base,meta in summary.items():
    items=(meta or {}).get('items') or {}
    if isinstance(items,dict): summary_items |= {x.lower() for x in items}

# Audio bank filenames carry engine category prefixes that story commands often omit.
aud_alias=defaultdict(list)
for p in aud_paths:
    st=Path(p).stem.lower(); toks=st.split('_')
    aliases={st,norm(st)}
    # progressively index suffixes: m_sys_act15_loop -> act15_loop, d_avg_x -> x
    for i in range(1,min(4,len(toks)-1)):
        suffix='_'.join(toks[i:])
        if len(norm(suffix))>=5: aliases.add(suffix); aliases.add(norm(suffix))
    # explicit common prefixes, repeatedly removable
    cur=st
    rx=re.compile(r'^(?:m_(?:sys\d*|avg|bat\d*|dia)_|d_avg_|a_(?:avg|bat)_|b_(?:char|ui|enemy)_|e_(?:atk|skill)_|p_(?:skill|atk|aoe|char)_|g_ui_)',re.I)
    for _ in range(3):
        nxt=rx.sub('',cur)
        if nxt==cur: break
        cur=nxt; aliases.add(cur); aliases.add(norm(cur))
    for al in aliases: aud_alias[al].append(p)

def pick_image(kind,key):
    vars=char_variants(key) if kind=='character' else stem_variants(key)
    for v in vars:
        c=f_exact.get(v.lower(),[])
        if c: return ('exact' if v==key else 'transformed'),c[0],'fexli'
        c=a_exact.get(v.lower(),[])
        if c: return ('exact' if v==key else 'transformed'),c[0],'aceship'
    if kind=='character':
        for v in char_variants(key):
            if v.lower() in summary_items:
                cv=re.sub(r'[#\$]+','_',v).lower()
                if f_exact.get(cv): return 'transformed',f_exact[cv][0],'fexli-summary'
        base=re.split(r'[#\$]',key,1)[0]
        for b in char_variants(base):
            if f_exact.get(b.lower()): return 'base',f_exact[b.lower()][0],'fexli'
            if a_exact.get(b.lower()): return 'base',a_exact[b.lower()][0],'aceship'
    nk=norm(key); c=f_norm.get(nk,[])+a_norm.get(nk,[])
    if len(c)==1: return 'normalized',c[0],'normalized'
    return 'missing',None,None

def rank_audio(p,kind,key):
    low=p.lower(); score=p.count('/')
    if Path(p).stem.lower()==key.lower(): score-=1000
    if kind=='music':
        if low.startswith('music/'): score-=500
    else:
        for pre in ('avg/','battle/','enemy/','player/','skill/'):
            if low.startswith(pre): score-=300
        if low.startswith('music/'): score+=400
    return score

def pick_audio(kind,key):
    vals=stem_variants(key)
    for v in vals:
        c=aud_exact.get(v.lower(),[])
        if c: return 'exact',sorted(c,key=lambda p:rank_audio(p,kind,v))[0]
    for v in vals:
        candidates=[]
        for al in (v.lower(),norm(v)):
            candidates += aud_alias.get(al,[])
        candidates=list(dict.fromkeys(candidates))
        if candidates: return 'alias',sorted(candidates,key=lambda p:rank_audio(p,kind,v))[0]
    for v in vals:
        c=aud_norm.get(norm(v),[])
        if c: return 'normalized',sorted(c,key=lambda p:rank_audio(p,kind,v))[0]
    n=norm(Path(key.replace('\\','/')).name)
    if len(n)>=6:
        fuzzy=[]
        for sn,ps in aud_norm.items():
            if n in sn or sn in n: fuzzy.extend(ps)
        fuzzy=list(dict.fromkeys(fuzzy))
        if fuzzy:
            # choose only if the best candidate contains the entire normalized story key
            safe=[p for p in fuzzy if n in norm(Path(p).stem)]
            if safe: return 'fuzzy',sorted(safe,key=lambda p:rank_audio(p,kind,key))[0]
    return 'missing',None

report={'storyCount':stories,'indexed':{'fexliImages':len(f_paths),'aceshipImages':len(a_paths),'audioMain':len(aud_paths)},'images':{},'audio':{}}
for kind,keys in req_img.items():
    counts=defaultdict(int); missing=[]; samples=[]
    for k in sorted(keys):
        st,p,src=pick_image(kind,k); counts[st]+=1
        if st=='missing': missing.append(k)
        elif len(samples)<10 and st!='exact': samples.append({'key':k,'status':st,'path':p,'source':src})
    report['images'][kind]={'requested':len(keys),**dict(counts),'found':len(keys)-len(missing),'missingCount':len(missing),'missing':missing[:300],'fallbackSamples':samples}
for kind,keys in req_aud.items():
    counts=defaultdict(int); missing=[]; samples=[]
    for k in sorted(keys):
        st,p=pick_audio(kind,k); counts[st]+=1
        if st=='missing': missing.append(k)
        elif len(samples)<10 and st!='exact': samples.append({'key':k,'status':st,'path':p})
    report['audio'][kind]={'requested':len(keys),**dict(counts),'found':len(keys)-len(missing),'missingCount':len(missing),'missing':missing[:300],'fallbackSamples':samples}
open('coverage-v31.json','w',encoding='utf-8').write(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
for group in ('images','audio'):
    for kind,x in report[group].items():
        print(f"COVERAGE {group}/{kind}: {x['found']}/{x['requested']} = {(100*x['found']/max(1,x['requested'])):.2f}% missing={x['missingCount']}")
