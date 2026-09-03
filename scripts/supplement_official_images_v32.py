#!/usr/bin/env python3
import hashlib,json,re,shutil,tempfile,time,urllib.request,zipfile
from pathlib import Path

import lz4.block
import UnityPy
from UnityPy.enums.BundleFile import CompressionFlags
from UnityPy.helpers import CompressionHelper

ROOT=Path(__file__).resolve().parents[1]
AS=ROOT/'app/src/main/assets'
INDEX=AS/'media_index.json'
OUT=AS/'media/images'
media=json.load(open(INDEX,encoding='utf-8'))
chars=media.setdefault('images',{}).setdefault('character',{})
OUT.mkdir(parents=True,exist_ok=True)

# Arknights current Android bundles use the game's custom LZ4AK stream in the LZHAM slot.
def _extra(data,pos,end):
    n=0
    while pos<end:
        b=data[pos]; n+=b; pos+=1
        if b!=0xff: break
    return n,pos

def decompress_lz4ak(src,uncompressed_size):
    ip=op=0; buf=bytearray(src); end=len(buf)
    while ip<end:
        literal=buf[ip]&0xf; match=(buf[ip]>>4)&0xf
        buf[ip]=(literal<<4)|match; ip+=1
        if literal==0xf:
            x,ip=_extra(buf,ip,end); literal+=x
        ip+=literal; op+=literal
        if op>=uncompressed_size: break
        if ip+1>=end: break
        offset=(buf[ip]<<8)|buf[ip+1]
        buf[ip]=offset&0xff; buf[ip+1]=(offset>>8)&0xff; ip+=2
        if match==0xf:
            x,ip=_extra(buf,ip,end); match+=x
        match+=4; op+=match
    return lz4.block.decompress(buf,uncompressed_size=uncompressed_size)
CompressionHelper.DECOMPRESSION_MAP[CompressionFlags.LZHAM]=decompress_lz4ak

def gj(url,timeout=90):
    q=urllib.request.Request(url,headers={'User-Agent':'RhodesReaderKR-v3.2-image-build'})
    with urllib.request.urlopen(q,timeout=timeout) as r:return json.load(r)

def fetch(url,dest):
    last=None
    for n in range(4):
        try:
            q=urllib.request.Request(url,headers={'User-Agent':'RhodesReaderKR-v3.2-image-build'})
            with urllib.request.urlopen(q,timeout=180) as r,open(dest,'wb') as f:shutil.copyfileobj(r,f,1024*1024)
            if dest.stat().st_size:return True
        except Exception as e:
            last=e; dest.unlink(missing_ok=True); time.sleep(1+n)
    print('DOWNLOAD_ERROR',url,last)
    return False

def dat_name(name):return name.replace('/','_').replace('#','__').rsplit('.',1)[0]+'.dat'

def clean(v):
    if v is None:return ''
    v=str(v).strip().strip('"').strip("'")
    if v.startswith('$'):v=v[1:]
    return v.strip()

def numnorm(s):
    # #01$01 and #1$1 are the same selector in AVG bundle object names.
    return re.sub(r'(?<![A-Za-z0-9])0+(\d+)',lambda m:str(int(m.group(1))),s)

def key_parts(key):
    if '#' in key:
        base,suffix=key.split('#',1)
    else:
        base,suffix=key,''
    return base,numnorm(suffix)

def candidates(key,names):
    base,suffix=key_parts(key)
    low={n.lower():n for n in names}
    guesses=[]
    def add(x):
        if x and x.lower() not in [g.lower() for g in guesses]:guesses.append(x)
    add(key); add(numnorm(key))
    if suffix:
        add(suffix)
        if '$' in suffix:
            expr,layer=suffix.split('$',1)
            add(expr+'$'+layer)
            add(base+'$'+layer)
        add(base+'$1')
        add(base)
    else:
        add(base); add(base+'$1')
    for g in guesses:
        if g.lower() in low:return low[g.lower()],guesses
    # Last safe fallback: when a bundle has exactly one renderable sprite, it is the intended base pose.
    if len(names)==1:return names[0],guesses
    return None,guesses

def save_pil(img,key):
    digest=hashlib.sha1(('official-kr-char\0'+key).encode()).hexdigest()[:24]
    dest=OUT/(digest+'.png')
    img.save(dest,'PNG')
    return dest.relative_to(AS).as_posix()

# Only retry keys the existing multi-source pack still misses.
requested=[]
for fp in (AS/'story').rglob('*.json'):
    try:d=json.load(open(fp,encoding='utf-8'))
    except Exception:continue
    for line in d.get('storyList',[]):
        if not isinstance(line,dict):continue
        a=line.get('attributes') or {}
        if not isinstance(a,dict):a={}
        if str(line.get('prop') or '').lower()=='character':
            for f in ('name','name2'):
                k=clean(a.get(f))
                if k and 'focus=' not in k and not k.startswith(','):requested.append(k)
        fig=clean(line.get('figure_art'))
        if fig and 'focus=' not in fig:requested.append(fig)
requested=sorted(set(requested))
missing=[k for k in requested if not chars.get(k)]
print('OFFICIAL_CHARACTER_MISSING_BEFORE',len(missing))

outer=gj('https://ak-conf.arknights.kr/config/prod/official/network_config')
conf=json.loads(outer['content']); net=conf['configs'][conf['funcVer']]['network']
ver=gj(net['hv'].replace('{0}','Android')); res=ver['resVersion']; baseurl=f"{net['hu']}/Android/assets/{res}"
hot=gj(baseurl+'/hot_update_list.json')
manifest={str(x.get('name') or '').lower():str(x.get('name') or '') for x in hot.get('abInfos',[])}

bybundle={}
for key in missing:
    stem=key_parts(key)[0]
    wanted=('avg/characters/'+stem+'.ab').lower()
    bundle=manifest.get(wanted)
    if bundle:bybundle.setdefault(bundle,[]).append(key)

report={'resVersion':res,'missingBefore':len(missing),'bundles':len(bybundle),'recovered':{},'unresolved':{},'bundleErrors':[]}
with tempfile.TemporaryDirectory(prefix='rhodes-v32-images-') as td:
    td=Path(td)
    for i,(bundle,keys) in enumerate(sorted(bybundle.items()),1):
        dat=td/'b.dat'; unpack=td/'u'; dat.unlink(missing_ok=True)
        if unpack.exists():shutil.rmtree(unpack)
        if not fetch(baseurl+'/'+dat_name(bundle),dat):
            report['bundleErrors'].append(bundle);continue
        try:
            with zipfile.ZipFile(dat) as z:z.extractall(unpack)
            render={}
            # Prefer Sprite objects over raw textures because Sprite respects atlas cropping.
            for ab in unpack.rglob('*.ab'):
                env=UnityPy.load(str(ab))
                objs=list(env.objects)
                for pass_type in ('Sprite','Texture2D'):
                    for obj in objs:
                        if obj.type.name!=pass_type:continue
                        try:data=obj.parse_as_object()
                        except Exception:continue
                        name=str(getattr(data,'m_Name','') or '')
                        if not name or name.lower() in render:continue
                        try:img=getattr(data,'image',None)
                        except Exception:img=None
                        if img is not None:render[name.lower()]=(name,img)
            names=[v[0] for v in render.values()]
            for key in keys:
                chosen,guesses=candidates(key,names)
                if not chosen:
                    report['unresolved'][key]={'bundle':bundle,'objects':names[:80],'guesses':guesses}
                    continue
                try:rel=save_pil(render[chosen.lower()][1],key)
                except Exception as e:
                    report['unresolved'][key]={'bundle':bundle,'chosen':chosen,'error':repr(e)};continue
                chars[key]=rel
                report['recovered'][key]={'bundle':bundle,'object':chosen,'asset':rel}
                print('RECOVERED_OFFICIAL_CHARACTER',key,'<-',bundle,'::',chosen)
        except Exception as e:
            report['bundleErrors'].append(bundle+': '+repr(e))
        finally:
            dat.unlink(missing_ok=True)
            if unpack.exists():shutil.rmtree(unpack)
        if i%25==0 or i==len(bybundle):print('OFFICIAL_CHARACTER_PROGRESS',i,'/',len(bybundle),'recovered',len(report['recovered']))

found=sum(1 for k in requested if chars.get(k))
stats=media.setdefault('stats',{})
stats['v32OfficialKrImageResVersion']=res
stats['v32_characterRequested']=len(requested)
stats['v32_characterFound']=found
stats['v32_characterMissing']=len(requested)-found
stats['v32OfficialCharacterRecovered']=len(report['recovered'])
stats['v32OfficialCharacterBundleErrors']=report['bundleErrors']
json.dump(media,open(INDEX,'w',encoding='utf-8'),ensure_ascii=False,separators=(',',':'))
report['foundAfter']=found;report['requested']=len(requested);report['missingAfter']=len(requested)-found
json.dump(report,open(ROOT/'v32-official-image-report.json','w',encoding='utf-8'),ensure_ascii=False,indent=2)
print(json.dumps({'resVersion':res,'requested':len(requested),'found':found,'missing':len(requested)-found,'recovered':len(report['recovered']),'unresolved':len(report['unresolved']),'bundleErrors':len(report['bundleErrors'])},ensure_ascii=False,indent=2))
