#!/usr/bin/env python3
import hashlib,json,shutil,tempfile,time,urllib.request,zipfile
from pathlib import Path

import lz4.block
import UnityPy
from UnityPy.enums.BundleFile import CompressionFlags
from UnityPy.helpers import CompressionHelper

ROOT=Path(__file__).resolve().parents[1]
AS=ROOT/'app/src/main/assets'
INDEX=AS/'media_index.json'
OUT=AS/'media/audio'
media=json.load(open(INDEX,encoding='utf-8'))
music=media.setdefault('audio',{}).setdefault('music',{})

# Two story aliases are absent from the KR variable table under these exact keys,
# but point to the same official AudioClips already extracted for friend_intro/loop.
aliases={'sys_friend_intro':'friend_intro','sys_friend_loop':'friend_loop'}
for dst,src in aliases.items():
    if not music.get(dst) and music.get(src):
        music[dst]=music[src]

KEY_BY_CLIP={
 'm_bat_act24side_01_intro':'MH_bat_act24side_01_intro',
 'm_bat_act24side_01_loop':'MH_bat_act24side_01_loop',
 'm_bat_act24side_02_intro':'MH_bat_act24side_02_intro',
 'm_bat_act24side_02_loop':'MH_bat_act24side_02_loop',
}
BUNDLES={
 'audio/sound_beta_2/music/act24side/m_bat_act24side_01.ab',
 'audio/sound_beta_2/music/act24side/m_bat_act24side_02.ab',
}

def _extra(data,pos,end):
    n=0
    while pos<end:
        b=data[pos];n+=b;pos+=1
        if b!=0xff:break
    return n,pos

def decompress_lz4ak(src,uncompressed_size):
    ip=op=0;buf=bytearray(src);end=len(buf)
    while ip<end:
        literal=buf[ip]&0xF;match=(buf[ip]>>4)&0xF
        buf[ip]=(literal<<4)|match;ip+=1
        if literal==0xF:
            x,ip=_extra(buf,ip,end);literal+=x
        ip+=literal;op+=literal
        if op>=uncompressed_size:break
        offset=(buf[ip]<<8)|buf[ip+1]
        buf[ip]=offset&0xff;buf[ip+1]=(offset>>8)&0xff;ip+=2
        if match==0xF:
            x,ip=_extra(buf,ip,end);match+=x
        match+=4;op+=match
    return lz4.block.decompress(buf,uncompressed_size=uncompressed_size)

CompressionHelper.DECOMPRESSION_MAP[CompressionFlags.LZHAM]=decompress_lz4ak

def gj(url):
    q=urllib.request.Request(url,headers={'User-Agent':'RhodesReaderKR-v3.2-private'})
    with urllib.request.urlopen(q,timeout=90) as r:return json.load(r)

def dat_name(name):return name.replace('/','_').replace('#','__').rsplit('.',1)[0]+'.dat'

def fetch(url,dest):
    last=None
    for attempt in range(4):
        try:
            q=urllib.request.Request(url,headers={'User-Agent':'RhodesReaderKR-v3.2-private'})
            with urllib.request.urlopen(q,timeout=180) as r,open(dest,'wb') as f:shutil.copyfileobj(r,f)
            if dest.stat().st_size:return
        except Exception as e:
            last=e;dest.unlink(missing_ok=True);time.sleep(1+attempt)
    raise RuntimeError(f'download failed {url}: {last}')

def save_clip(name,clip):
    samples=list(clip.samples.items())
    if not samples:return None
    sample_name,payload=max(samples,key=lambda x:len(x[1]))
    suffix=Path(sample_name).suffix.lower() or '.wav'
    digest=hashlib.sha1(('cn-legacy\0'+name.lower()).encode()).hexdigest()[:24]
    dest=OUT/(digest+suffix);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_bytes(payload)
    return dest.relative_to(AS).as_posix()

outer=gj('https://ak-conf.hypergryph.com/config/prod/official/network_config')
conf=json.loads(outer['content']);net=conf['configs'][conf['funcVer']]['network']
ver=gj(net['hv'].replace('{0}','Android'));res=ver['resVersion'];base=f"{net['hu']}/Android/assets/{res}"
hot=gj(base+'/hot_update_list.json')
manifest={str(x.get('name') or ''):x for x in hot.get('abInfos',[])}
found={}
with tempfile.TemporaryDirectory(prefix='rhodes-v32-legacy-') as td:
    td=Path(td)
    for name in sorted(BUNDLES):
        if name not in manifest:continue
        dat=td/'bundle.dat';unpack=td/'unpack';dat.unlink(missing_ok=True)
        if unpack.exists():shutil.rmtree(unpack)
        fetch(base+'/'+dat_name(name),dat)
        with zipfile.ZipFile(dat) as z:z.extractall(unpack)
        for ab in unpack.rglob('*.ab'):
            env=UnityPy.load(str(ab))
            for obj in env.objects:
                if obj.type.name!='AudioClip':continue
                clip=obj.parse_as_object();cname=str(clip.m_Name or '')
                if cname.lower() not in KEY_BY_CLIP:continue
                rel=save_clip(cname,clip)
                if rel:
                    key=KEY_BY_CLIP[cname.lower()];music[key]=rel;found[key]=rel

stats=media.setdefault('stats',{})
stats['v32LegacyCnResVersion']=res
stats['v32LegacyAliasesAdded']=sum(1 for k in aliases if music.get(k))
stats['v32LegacyMhMusicAdded']=len(found)
json.dump(media,open(INDEX,'w',encoding='utf-8'),ensure_ascii=False,separators=(',',':'))
report={'cnResVersion':res,'aliases':{k:music.get(k) for k in aliases},'mhMusic':found}
json.dump(report,open(ROOT/'v32-legacy-audio-report.json','w',encoding='utf-8'),ensure_ascii=False,indent=2)
print(json.dumps(report,ensure_ascii=False,indent=2))
assert all(music.get(k) for k in aliases), 'friend aliases not resolved'
assert len(found)==4, f'expected 4 surviving CN Monster Hunter BGM clips, got {len(found)}'
