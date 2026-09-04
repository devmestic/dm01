#!/usr/bin/env python3
import hashlib, json, re, shutil, tempfile, time, urllib.request, zipfile
from collections import defaultdict
from pathlib import Path

import lz4.block
import UnityPy
from UnityPy.enums.BundleFile import CompressionFlags
from UnityPy.helpers import CompressionHelper

ROOT=Path(__file__).resolve().parents[1]
AS=ROOT/'app/src/main/assets'; STORY=AS/'story'; INDEX=AS/'media_index.json'; OUT=AS/'media/images'
media=json.load(open(INDEX,encoding='utf-8')); chars=media.setdefault('images',{}).setdefault('character',{})

def _extra(data,pos,end):
    n=0
    while pos<end:
        b=data[pos]; n+=b; pos+=1
        if b!=0xFF: break
    return n,pos

def decompress_lz4ak(src,uncompressed_size):
    ip=op=0; buf=bytearray(src); end=len(buf)
    while ip<end:
        literal=buf[ip]&0xF; match=(buf[ip]>>4)&0xF; buf[ip]=(literal<<4)|match; ip+=1
        if literal==0xF:
            x,ip=_extra(buf,ip,end); literal+=x
        ip+=literal; op+=literal
        if op>=uncompressed_size: break
        offset=(buf[ip]<<8)|buf[ip+1]; buf[ip]=offset&0xFF; buf[ip+1]=(offset>>8)&0xFF; ip+=2
        if match==0xF:
            x,ip=_extra(buf,ip,end); match+=x
        match+=4; op+=match
    return lz4.block.decompress(buf,uncompressed_size=uncompressed_size)
CompressionHelper.DECOMPRESSION_MAP[CompressionFlags.LZHAM]=decompress_lz4ak

def gj(url,timeout=90):
    req=urllib.request.Request(url,headers={'User-Agent':'RhodesReaderKR-v3.2-private-build'})
    with urllib.request.urlopen(req,timeout=timeout) as r:return json.load(r)

def clean(v):
    if v is None:return ''
    v=str(v).strip().strip('"').strip("'")
    if v.startswith('$'):v=v[1:]
    return v.strip()

def requested_keys():
    req=set()
    for fp in STORY.rglob('*.json'):
        try:d=json.load(open(fp,encoding='utf-8'))
        except:continue
        for line in d.get('storyList',[]):
            if not isinstance(line,dict):continue
            a=line.get('attributes') or {}
            if not isinstance(a,dict):a={}
            if str(line.get('prop') or '').lower()=='character':
                for f in ('name','name2'):
                    k=clean(a.get(f))
                    if k and 'focus=' not in k and not k.startswith(','):req.add(k)
            k=clean(line.get('figure_art'))
            if k and 'focus=' not in k:req.add(k)
    return req

def base_of(k):return re.split(r'[#\$]',k,1)[0]
def norm_expr(k):
    return re.sub(r'#0+(\d+)',lambda m:'#'+str(int(m.group(1))),k)
def norm_loose(v):return re.sub(r'[^a-z0-9]+','',v.lower())

def aliases(k):
    out=[k,norm_expr(k)]
    b=base_of(k)
    m=re.match(r'^(.*?)(?:#([^$]+))?(?:\$(.+))?$',k)
    expr=(m.group(2) if m else None); layer=(m.group(3) if m else None)
    if expr:
        try: ex=str(int(expr))
        except: ex=expr
        out += [f'{b}#{ex}'+(f'${layer}' if layer else '')]
        if ex=='1':
            out += [b+(f'${layer}' if layer else ''),b]
    if layer:
        out += [f'{b}${layer}']
    if not expr and not layer:
        out += [f'{b}#1',f'{b}$1',f'{b}#1$1',f'{b}_1',f'{b}_1#1',f'{b}_1#1$1']
    # legacy char_/avg_ prefixes occasionally differ only by case or avg prefix
    if b.startswith('char_'):
        out += [x.replace('char_','avg_',1) for x in list(out) if x.startswith('char_')]
    return list(dict.fromkeys(x for x in out if x))

def dat_name(ab):return ab.replace('/','_').replace('#','__').rsplit('.',1)[0]+'.dat'
def fetch_file(url,dest):
    last=None
    for n in range(4):
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'RhodesReaderKR-v3.2-private-build'})
            with urllib.request.urlopen(req,timeout=180) as r,open(dest,'wb') as f:shutil.copyfileobj(r,f,1024*1024)
            if dest.stat().st_size:return True
        except Exception as e:
            last=e; dest.unlink(missing_ok=True); time.sleep(1+n)
    print('DOWNLOAD FAIL',url,last); return False

req=requested_keys(); missing=sorted(k for k in req if not chars.get(k))
print('CHARACTER REQUESTED',len(req),'MISSING BEFORE OFFICIAL',len(missing))
outer=gj('https://ak-conf.arknights.kr/config/prod/official/network_config'); conf=json.loads(outer['content']); net=conf['configs'][conf['funcVer']]['network']; ver=gj(net['hv'].replace('{0}','Android')); rv=ver['resVersion']; baseurl=f"{net['hu']}/Android/assets/{rv}"; hot=gj(baseurl+'/hot_update_list.json')
infos={str(x.get('name') or '').lower():x for x in hot['abInfos']}
avg_names=[str(x.get('name') or '') for x in hot['abInfos'] if str(x.get('name') or '').lower().startswith('avg/characters/')]

def bundle_for(base):
    wants=[f'avg/characters/{base}.ab']
    if not re.search(r'_\d+$',base):wants.append(f'avg/characters/{base}_1.ab')
    for w in wants:
        if w.lower() in infos:return str(infos[w.lower()]['name'])
    near=[]
    for n in avg_names:
        stem=Path(n).stem.lower(); bl=base.lower()
        if stem==bl or stem.startswith(bl+'_'):near.append(n)
    if near:
        near.sort(key=lambda x:(len(Path(x).stem),x.lower()))
        return near[0]
    return None

by_bundle=defaultdict(list); no_bundle=[]
for k in missing:
    b=bundle_for(base_of(k))
    if b:by_bundle[b].append(k)
    else:no_bundle.append(k)
print('OFFICIAL BUNDLES NEEDED',len(by_bundle),'NO BUNDLE',len(no_bundle))
print('NO BUNDLE SAMPLE',no_bundle[:50])

saved=0; errors=[]; unresolved=[]; download_bytes=0
OUT.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='rhodes-v32-img-') as td:
    td=Path(td)
    for idx,(ab_name,keys) in enumerate(sorted(by_bundle.items()),1):
        dat=td/'bundle.dat'; unpack=td/'unpack'; dat.unlink(missing_ok=True)
        if unpack.exists():shutil.rmtree(unpack)
        if not fetch_file(baseurl+'/'+dat_name(ab_name),dat):
            unresolved.extend(keys); continue
        download_bytes+=dat.stat().st_size
        try:
            with zipfile.ZipFile(dat) as z:z.extractall(unpack)
            abs_found=list(unpack.rglob('*.ab'))
            objects=[]
            for ab in abs_found:
                env=UnityPy.load(str(ab))
                for obj in env.objects:
                    if obj.type.name not in ('Sprite','Texture2D'):continue
                    try:
                        data=obj.parse_as_object(); name=str(getattr(data,'m_Name','') or getattr(data,'name','') or '')
                        if not name:continue
                        image=getattr(data,'image',None)
                        if image is None:continue
                        objects.append((0 if obj.type.name=='Sprite' else 1,name,image.copy()))
                    except Exception as e:errors.append(f'{ab_name}:{obj.type.name}:{e}')
            exact=defaultdict(list); loose=defaultdict(list)
            for pri,name,img in objects:
                exact[name.lower()].append((pri,name,img)); loose[norm_loose(name)].append((pri,name,img))
            for key in keys:
                hit=None; used=None
                for a in aliases(key):
                    c=exact.get(a.lower(),[])
                    if c:
                        c.sort(key=lambda x:(x[0],-x[2].width*x[2].height)); hit=c[0]; used=a; break
                if hit is None:
                    for a in aliases(key):
                        c=loose.get(norm_loose(a),[])
                        if len(c)==1:hit=c[0]; used=a; break
                if hit is None:
                    unresolved.append(key)
                    print('OFFICIAL IMAGE MISS',repr(key),'BUNDLE',ab_name,'NAMES',[x[1] for x in objects[:30]])
                    continue
                _,objname,img=hit
                h=hashlib.sha1((rv+'\0'+ab_name+'\0'+objname).encode()).hexdigest()[:24]; dest=OUT/(h+'.png')
                if not dest.exists():img.save(dest,'PNG')
                chars[key]=dest.relative_to(AS).as_posix(); saved+=1
                print('OFFICIAL IMAGE',key,'<-',objname,'via',used)
        except Exception as e:
            errors.append(f'{ab_name}:{e}'); unresolved.extend(keys)
        finally:
            dat.unlink(missing_ok=True)
            if unpack.exists():shutil.rmtree(unpack)
        if idx%20==0 or idx==len(by_bundle):print('progress',idx,'/',len(by_bundle),'saved',saved)

stats=media.setdefault('stats',{}); stats['v32OfficialKrImages']=True; stats['v32OfficialKrImageResVersion']=rv; stats['v32OfficialImageBundles']=len(by_bundle); stats['v32OfficialImageDownloadBytes']=download_bytes; stats['v32OfficialImageSaved']=saved; stats['v32OfficialImageErrors']=errors
json.dump(media,open(INDEX,'w',encoding='utf-8'),ensure_ascii=False,separators=(',',':'))
left=sorted(k for k in req if not chars.get(k))
report={'resVersion':rv,'saved':saved,'requested':len(req),'missingBefore':len(missing),'missingAfter':len(left),'missing':left,'noBundle':no_bundle,'errors':errors}
json.dump(report,open(ROOT/'v32-official-image-report.json','w',encoding='utf-8'),ensure_ascii=False,indent=2)
print(json.dumps({k:v for k,v in report.items() if k not in ('missing','noBundle','errors')},ensure_ascii=False,indent=2)); print('LEFT',left[:250]); print('ERRORS',len(errors))
