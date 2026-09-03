#!/usr/bin/env python3
import hashlib,json,re,shutil,subprocess,sys,time,urllib.parse,urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path

if len(sys.argv)!=5: raise SystemExit('usage: supplement_media_v31.py <fexli> <aceship> <assets2-cn> <audio-main>')
fexli,aceship,assets2,audio=map(lambda x:Path(x).resolve(),sys.argv[1:])
ROOT=Path(__file__).resolve().parents[1]; AS=ROOT/'app/src/main/assets'; STORY=AS/'story'; INDEX=AS/'media_index.json'; IM=AS/'media/images'; AU=AS/'media/audio'
media=json.load(open(INDEX,encoding='utf-8'))
IMGEXT={'.png','.jpg','.jpeg','.webp'}; AUDEXT={'.wav','.mp3','.ogg','.m4a','.flac'}
def clean(v):
    if v is None:return ''
    v=str(v).strip().strip('"').strip("'")
    if v.startswith('$'):v=v[1:]
    return v.strip()
def norm(v):return re.sub(r'[^a-z0-9]+','',v.lower())
def variants(k):
    out=[k,re.sub(r'[#\$]+','_',k)]
    if '/' in k or '\\' in k:out.append(Path(k.replace('\\','/')).name)
    return list(dict.fromkeys(x for x in out if x))
def paths(repo,prefix=None):
    cmd=['git','-C',str(repo),'ls-tree','-r','--name-only','HEAD']
    if prefix:cmd+=['--',prefix]
    return subprocess.check_output(cmd,text=True,encoding='utf-8',errors='replace').splitlines()
def index(ps,exts):
    ex=defaultdict(list); no=defaultdict(list)
    for p in ps:
        q=Path(p)
        if q.suffix.lower() not in exts:continue
        ex[q.stem.lower()].append(p);no[norm(q.stem)].append(p)
    return ex,no
fex,fn=index(paths(fexli,'avgs'),IMGEXT); ace,an=index(paths(aceship,'avg'),IMGEXT); a2,a2n=index(paths(assets2),IMGEXT); aud,audn=index(paths(audio),AUDEXT)
# aliases for internal Wwise/bank prefixes
audalias=defaultdict(list)
rx=re.compile(r'^(?:m_(?:sys\d*|avg|bat\d*|dia)_|d_avg_|a_(?:avg|bat)_|b_(?:char|ui|enemy)_|e_(?:atk|skill)_|p_(?:skill|atk|aoe|char)_|g_ui_)',re.I)
for stem,ps in aud.items():
    toks=stem.split('_'); aliases={stem,norm(stem)}
    for i in range(1,min(4,len(toks)-1)):
        s='_'.join(toks[i:])
        if len(norm(s))>=5:aliases|={s,norm(s)}
    cur=stem
    for _ in range(3):
        nxt=rx.sub('',cur)
        if nxt==cur:break
        cur=nxt;aliases|={cur,norm(cur)}
    for a in aliases:audalias[a]+=ps

reqi={'background':set(),'image':set(),'character':set()};reqa={'music':set(),'sfx':set()}
for p in STORY.rglob('*.json'):
    try:d=json.load(open(p,encoding='utf-8'))
    except:continue
    for line in d.get('storyList',[]):
        if not isinstance(line,dict):continue
        prop=str(line.get('prop') or '').lower();a=line.get('attributes') or {}
        if not isinstance(a,dict):a={}
        im=clean(a.get('image'))
        if im:reqi['background' if prop in ('background','backgroundtween') else 'image'].add(im)
        if prop=='character':
            for f in ('name','name2'):
                k=clean(a.get(f))
                if k and 'focus=' not in k and not k.startswith(','):reqi['character'].add(k)
        fig=clean(line.get('figure_art'))
        if fig and 'focus=' not in fig:reqi['character'].add(fig)
        if prop=='playmusic':
            for f in ('key','intro'):
                for q in clean(a.get(f)).split(';'):
                    if clean(q):reqa['music'].add(clean(q))
        elif prop=='playsound':
            for f,v in a.items():
                if 'key' in str(f).lower():
                    for q in clean(v).split(';'):
                        if clean(q):reqa['sfx'].add(clean(q))

def imgpick(kind,key):
    # raw-expression sources first; they preserve #expression/$layer exactly
    for v in variants(key):
        for ex,src,branch in ((a2,'ArknightsAssets/ArknightsAssets2','cn'),(fex,'fexli/ArknightsResource','main'),(ace,'Aceship/Arknight-Images','main')):
            c=ex.get(v.lower(),[])
            if c:
                # prefer AVG directories over unrelated duplicate thumbnails
                c=sorted(c,key=lambda p:(0 if '/avg/' in ('/'+p.lower()) or p.lower().startswith('avgs/') else 1,len(p)))
                return src,branch,c[0]
    nk=norm(key)
    for no,src,branch in ((a2n,'ArknightsAssets/ArknightsAssets2','cn'),(fn,'fexli/ArknightsResource','main'),(an,'Aceship/Arknight-Images','main')):
        c=no.get(nk,[])
        if len(c)==1:return src,branch,c[0]
    return None

def audpick(kind,key):
    for v in variants(key):
        c=aud.get(v.lower(),[])
        if c:return 'PseudoMon/arknights-audio','main',sorted(c,key=lambda p:(0 if (kind=='music' and p.lower().startswith('music/')) else 1,len(p)))[0]
    cand=[]
    for v in variants(key):
        cand+=audalias.get(v.lower(),[])+audalias.get(norm(v),[])
    cand=list(dict.fromkeys(cand))
    if cand:
        if kind=='music':cand.sort(key=lambda p:(0 if p.lower().startswith('music/') else 1,len(p)))
        else:cand.sort(key=lambda p:(1 if p.lower().startswith('music/') else 0,len(p)))
        return 'PseudoMon/arknights-audio','main',cand[0]
    return None

def raw(src,branch,path):return f'https://raw.githubusercontent.com/{src}/{branch}/{urllib.parse.quote(path,safe="/")}'
def dest(src,branch,path,folder):
    h=hashlib.sha1((src+'@'+branch+'\0'+path).encode()).hexdigest()[:24]
    return folder/(h+Path(path).suffix.lower())
def dl(url,d):
    if d.exists() and d.stat().st_size:return True,None
    d.parent.mkdir(parents=True,exist_ok=True)
    for n in range(4):
        try:
            r=urllib.request.Request(url,headers={'User-Agent':'RhodesReaderKR-v3.1-build'})
            with urllib.request.urlopen(r,timeout=90) as x,open(d,'wb') as o:shutil.copyfileobj(x,o,1024*1024)
            if d.stat().st_size:return True,None
        except Exception as e:
            err=e;d.unlink(missing_ok=True);time.sleep(1+n)
    return False,str(err)

jobs={};plans=[];stats={'imagesAdded':{},'audioAdded':{}}
for kind,keys in reqi.items():
    added=0
    for k in sorted(keys):
        if media.get('images',{}).get(kind,{}).get(k):continue
        hit=imgpick(kind,k)
        if not hit:continue
        src,br,p=hit;d=dest(src,br,p,IM);u=raw(src,br,p);jobs[(u,d)]=None;plans.append(('image',kind,k,u,d,src,p));added+=1
    stats['imagesAdded'][kind]=added
for kind,keys in reqa.items():
    added=0
    for k in sorted(keys):
        if media.get('audio',{}).get(kind,{}).get(k):continue
        hit=audpick(kind,k)
        if not hit:continue
        src,br,p=hit;d=dest(src,br,p,AU);u=raw(src,br,p);jobs[(u,d)]=None;plans.append(('audio',kind,k,u,d,src,p));added+=1
    stats['audioAdded'][kind]=added
print('Supplement downloads',len(jobs),stats)
res={}
with ThreadPoolExecutor(max_workers=20) as pool:
    fs={pool.submit(dl,u,d):(u,d) for u,d in jobs}
    for i,f in enumerate(as_completed(fs),1):
        u,d=fs[f];res[(u,d)]=f.result()
        if i%100==0 or i==len(fs):print(' supplemental',i,'/',len(fs))
for typ,kind,k,u,d,src,p in plans:
    ok,err=res.get((u,d),(False,'no result'))
    if ok:
        rel=d.relative_to(AS).as_posix()
        media[('images' if typ=='image' else 'audio')][kind][k]=rel

s=media.setdefault('stats',{})
s['v31MultiSource']=True;s['v31Sources']=['fexli/ArknightsResource','Aceship/Arknight-Images','ArknightsAssets/ArknightsAssets2@cn','PseudoMon/arknights-audio@main']
for kind,keys in reqi.items():
    found=sum(1 for k in keys if media['images'][kind].get(k));s['v31_'+kind+'Requested']=len(keys);s['v31_'+kind+'Found']=found;s['v31_'+kind+'Missing']=len(keys)-found
for kind,keys in reqa.items():
    found=sum(1 for k in keys if media['audio'][kind].get(k));s['v31_'+kind+'Requested']=len(keys);s['v31_'+kind+'Found']=found;s['v31_'+kind+'Missing']=len(keys)-found
json.dump(media,open(INDEX,'w',encoding='utf-8'),ensure_ascii=False,separators=(',',':'))
print(json.dumps({k:v for k,v in s.items() if k.startswith('v31_')},ensure_ascii=False,indent=2))
