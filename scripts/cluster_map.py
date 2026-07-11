#!/usr/bin/env python3
"""각 텍스트 뱅크를 워크하며 미정의op(0x08-0F)·과도한 빈메시지로 텍스트/데이터 분절.
텍스트 클러스터 경계를 권위 있게 확정."""
import sys
sys.path.insert(0,'scripts')
from decode_script import decode,render,load_tbl
rom=open("roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc",'rb').read()
tbl=load_tbl("assets/translation_guide/glyph_table.tsv")
def foff(b,a):return((b&0x3F)<<16)|a

def scan(bank,st,en,name):
    o=foff(bank,st);fe=foff(bank,en)
    msgs=[]
    while o<fe:
        s=o
        while o<fe and rom[o]!=0x00:
            b=rom[o];o+=2 if(1<=b<=4 or b==7) else 1
        raw=rom[s:o+1];o+=1
        toks=decode(raw)
        badop=any(t[0]=='ctrl' and t[1].startswith('op') for t in toks)
        ng=sum(1 for t in toks if t[0]=='glyph')
        empty=(len(raw)==1)
        msgs.append((s&0xFFFF,ng,badop,empty,render(toks,tbl)))
    # segment: text-run = consecutive msgs with no badop and not (long empty run)
    print(f"\n### {name} ${bank:02X}:{st:04X}..{en:04X}  ({len(msgs)} raw segs)")
    clusters=[];cur=None;emptyrun=0
    for addr,ng,badop,empty,txt in msgs:
        isdata = badop
        if empty: emptyrun+=1
        else: emptyrun=0
        # a run of >2 empties or a badop breaks a text cluster
        breaker = badop or emptyrun>2
        if not breaker and ng>0:
            if cur is None: cur=[addr,addr,0]
            cur[1]=addr;cur[2]+=1
        else:
            if cur: clusters.append(tuple(cur));cur=None
    if cur: clusters.append(tuple(cur))
    tot=0
    for a0,a1,cnt in clusters:
        if cnt>=2:  # ignore singletons in data
            print(f"   cluster ${a0:04X}..${a1:04X}  ~{cnt} msgs")
            tot+=cnt
    print(f"   -> {sum(1 for c in clusters if c[2]>=2)} clusters, ~{tot} text msgs")
    return msgs

scan(0xC7,0x89E2,0xA020,"c7_race")
scan(0xD0,0xC80B,0xE850,"d0_story")
scan(0xC1,0xC868,0xD190,"c1_ui")
