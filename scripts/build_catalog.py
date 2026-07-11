#!/usr/bin/env python3
"""전 대사 블록 권위 포인터 카탈로그 통합.
- 오라클: 각 블록 메시지 시작 집합(종료자 워크)
- 소스: (1) 인라인 즉치 LDA#ptr/STA slot, (2) ROM 포인터 테이블(연속 런, 고유율 필터)
산출: assets/translations/pointer_catalog.json + tmp/trace/pointer_catalog.md"""
import struct,sys,json,os
sys.path.insert(0,'scripts')
from decode_script import decode,render,load_tbl
rom=open("roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc",'rb').read()
tbl=load_tbl("assets/translation_guide/glyph_table.tsv")
def foff(bank,addr): return ((bank&0x3F)<<16)|addr
BLOCKS={'c7_race':(0xC7,0x89E2,0xA001),'d0_story':(0xD0,0xC80B,0xE828),'c1_ui':(0xC1,0xC868,0xD183)}

def walk(bank,start,end):
    o=foff(bank,start);fe=foff(bank,end);S=[]
    while o<fe:
        S.append(o&0xFFFF)
        while o<fe and rom[o]!=0x00:
            b=rom[o];o+=2 if(1<=b<=4 or b==7) else 1
        o+=1
    return S
oracle={n:set(walk(*b)) for n,b in BLOCKS.items()}

def find_tables(S):
    runs=[];i=0
    while i+2<=len(rom):
        j=i;cnt=0
        while j+2<=len(rom) and (rom[j]|(rom[j+1]<<8)) in S:
            cnt+=1;j+=2
        if cnt>=4:
            vals=[rom[i+2*k]|(rom[i+2*k+1]<<8) for k in range(cnt)]
            uniq=len(set(vals))
            if uniq>=4 and uniq/cnt>=0.6 and max(vals)-min(vals)>0x20:
                runs.append((i,cnt,vals))
            i=j
        else:
            i+=1
    return runs

def scan_inline(bank):
    """LDA #imm16 ; STA <slot>. slot 판정 없이 뱅크별 즉치 포인터 후보를 오라클로 필터."""
    S=oracle_by_bank[bank]; out=set()
    # generic: any A9 lo hi where value in S and followed within 6 bytes by a STA(8F/8D/9F/85)
    i=0
    while i<len(rom)-6:
        if rom[i]==0xA9:
            v=rom[i+1]|(rom[i+2]<<8)
            if v in S:
                w=rom[i+3:i+9]
                if any(w[k] in (0x8F,0x8D,0x9F,0x85,0x9D) for k in range(len(w))):
                    out.add(v)
        i+=1
    return out
oracle_by_bank={0xC7:oracle['c7_race'],0xD0:oracle['d0_story'],0xC1:oracle['c1_ui']}

cat={}
for n,(bank,st,en) in BLOCKS.items():
    S=oracle[n]
    tables=[(o,c,v) for (o,c,v) in find_tables(S)]
    inl=scan_inline(bank)
    tbl_ptrs=set()
    for o,c,v in tables: tbl_ptrs|=set(v)
    covered=inl|tbl_ptrs
    cat[n]={'bank':bank,'start':st,'end':en,'n_messages':len(S),
            'inline':sorted(inl),'tables':[{'at':f"{0xC0|(o>>16):02X}:{o&0xFFFF:04X}",'file':o,'count':c,'ptrs':v} for o,c,v in tables],
            'covered':sorted(covered),'uncovered_starts':sorted(S-covered)}

os.makedirs('assets/translations',exist_ok=True)
json.dump(cat,open('assets/translations/pointer_catalog.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)

for n,(bank,st,en) in BLOCKS.items():
    c=cat[n]; nt=sum(t['count'] for t in c['tables'])
    print(f"\n### {n}  ${bank:02X}:{st:04X}..{en:04X}  ({c['n_messages']} msgs)")
    print(f"   inline immediates: {len(c['inline'])}")
    print(f"   pointer tables: {len(c['tables'])} ({nt} entries)")
    for t in c['tables']:
        print(f"     - {t['at']} x{t['count']}: {t['ptrs'][0]:04X}..{max(t['ptrs']):04X}")
    print(f"   distinct covered starts: {len(c['covered'])}/{c['n_messages']}  (uncovered {len(c['uncovered_starts'])})")
