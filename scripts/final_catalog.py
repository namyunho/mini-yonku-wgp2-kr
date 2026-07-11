#!/usr/bin/env python3
"""권위 대사 블록 열거 + 전 블록 포인터 카탈로그 (docs/07 SSOT 생성기).
근거: 파서 $C1:9554 단일 퍼널, 호출처 7개 전수 역추적(DBR 분석).
정적 텍스트 뱅크 = $C7/$D0/$C1 셋. 소스 = VM opcode / ROM 포인터 테이블 / 인라인 즉치."""
import struct,sys,json,os
sys.path.insert(0,'scripts')
from decode_script import decode,render,load_tbl
rom=open("roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc",'rb').read()
tbl=load_tbl("assets/translation_guide/glyph_table.tsv")
def foff(b,a):return((b&0x3F)<<16)|a
def find_all(pat,lo=0,hi=None):
    hi=hi or len(rom);o=[];i=lo
    while True:
        j=rom.find(pat,i)
        if j<0 or j>=hi:break
        o.append(j);i=j+1
    return o

# ---- message-start oracle per bank (full walk) ----
def starts(bank,st,en):
    o=foff(bank,st);fe=foff(bank,en);S=set()
    while o<fe:
        S.add(o&0xFFFF)
        while o<fe and rom[o]!=0x00:
            b=rom[o];o+=2 if(1<=b<=4 or b==7) else 1
        o+=1
    return S
# generous walk ranges (whole plausible span); clusters refined below
RANGE={0xC7:(0x89E2,0xA002),0xD0:(0xC80B,0xE828),0xC1:(0xC800,0xD190)}
ORA={b:starts(b,*RANGE[b]) for b in RANGE}

def is_msg(bank,addr): return addr in ORA[bank]

# ---- pointer sources ----
def c7_vm():
    ps={}
    for opx in('EFCB','D4CB'):
        for j in find_all(bytes.fromhex(opx),0x030000,0x040000):
            p=struct.unpack_from('<H',rom,j+2)[0]; ps.setdefault(p,[]).append(j)
    return ps
def tables_for(bank):
    S=ORA[bank];res=[];i=0
    while i+8<=len(rom):
        j=i;cnt=0
        while j+2<=len(rom) and (rom[j]|(rom[j+1]<<8)) in S:
            cnt+=1;j+=2
        if cnt>=4:
            vals=[rom[i+2*k]|(rom[i+2*k+1]<<8) for k in range(cnt)]
            u=len(set(vals))
            if u>=4 and u/cnt>=0.6 and max(vals)-min(vals)>0x20:
                res.append((i,cnt,vals))
            i=j
        else: i+=1
    return res
def inline_for(bank):
    S=ORA[bank];out={}
    for i in range(len(rom)-8):
        if rom[i]==0xA9:
            v=rom[i+1]|(rom[i+2]<<8)
            if v in S and any(rom[i+3+k] in(0x8F,0x8D,0x9F,0x85,0x9D) for k in range(6)):
                out.setdefault(v,[]).append(i)
    return out

# ---- c1 real dialogue clusters (pointer-anchored; data noise excluded) ----
C1_CLUSTERS=[("setting_save",0xC868,0xC980),("machine_names",0xC981,0xC9C0),
             ("garage_grid",0xCE53,0xCF1E),("formation",0xCFDC,0xD183)]

def decode_msg(bank,addr):
    o=foff(bank,addr);s=o
    while rom[o]!=0x00:
        b=rom[o];o+=2 if(1<=b<=4 or b==7) else 1
    return render(decode(rom[s:o+1]),tbl)

cat={"parser":"$C1:9554","funnel":"single parser; all dialogue routed here",
     "call_sites":[
        {"site":"$C3:7899","dbr":"$C7 (PEA #$C700)","ptr_src":"slot $7EC58B,X (VM)","block":"c7_race"},
        {"site":"$C3:7F08","dbr":"$C7 (PEA #$C700)","ptr_src":"slot $7EC58B,X (VM)","block":"c7_race"},
        {"site":"$D0:506A","dbr":"$D0 (PHK/PLB)","ptr_src":"A (caller)","block":"d0_story"},
        {"site":"$D0:516A","dbr":"ambient $D0","ptr_src":"$1268","block":"d0_story"},
        {"site":"$C1:2248","dbr":"dyn $7F64EA -> $C1/$7E/$00","ptr_src":"$7F64E8 (chan A)","block":"c1_ui / WRAM"},
        {"site":"$C1:6E8B","dbr":"dyn $7F8E1A -> $C1/$00","ptr_src":"$7F8E18 (chan B)","block":"c1_ui"},
        {"site":"$C1:7D18","dbr":"dyn $7F8046 -> $C1/$00","ptr_src":"$7F8044 (chan C)","block":"c1_ui"},
     ],
     "non_static_sinks":{"$7E":"WRAM dynamic buffers (composed names/numbers, e.g. $7EA5E6)","$00":"empty/clear (no message)"},
     "blocks":{}}

# c7
vm=c7_vm(); c7t=tables_for(0xC7); c7i=inline_for(0xC7)
c7cov=set(vm)|{v for _,_,vv in c7t for v in vv}|set(c7i)
cat["blocks"]["c7_race"]={"bank":0xC7,"span":"$89E2..$A01D","n_messages":232,"contiguous":True,
  "sources":{"vm_opcodes":{"count":len(vm),"opcodes":"$C3 EF CB / D4 CB","range":f"${min(vm):04X}..${max(vm):04X}"},
             "tables":[{"at":f"C7:{o&0xFFFF:04X}","count":c,"range":f"${vv[0]:04X}..${max(vv):04X}"} for o,c,vv in c7t],
             "inline":len(c7i)},
  "distinct_entry_ptrs":len(c7cov)}
# d0
d0t=tables_for(0xD0); d0i=inline_for(0xD0)
d0cov={v for _,_,vv in d0t for v in vv}|set(d0i)
cat["blocks"]["d0_story"]={"bank":0xD0,"span":"$C80B..$E819","n_messages":404,"contiguous":True,
  "sources":{"tables":[{"at":f"D0:{o&0xFFFF:04X}","count":c,"range":f"${vv[0]:04X}..${max(vv):04X}"} for o,c,vv in d0t],
             "inline":{"count":len(d0i),"note":"LDA #ptr; STA $1268 (+auto-advance $C06699)"}},
  "distinct_entry_ptrs":len(d0cov)}
# c1
c1t=tables_for(0xC1); c1i=inline_for(0xC1)
c1clusters=[]
for nm,a0,a1 in C1_CLUSTERS:
    o=foff(0xC1,a0);fe=foff(0xC1,a1);msgs=[]
    while o<fe:
        s=o
        while o<fe and rom[o]!=0x00:
            b=rom[o];o+=2 if(1<=b<=4 or b==7) else 1
        msgs.append(s&0xFFFF);o+=1
    c1clusters.append({"name":nm,"span":f"${a0:04X}..${a1:04X}","n_messages":len(msgs),"starts":[f"{x:04X}" for x in msgs]})
cat["blocks"]["c1_ui"]={"bank":0xC1,"fragmented":True,"note":"dialogue clusters interleaved with binary data (single-glyph noise excluded)",
  "clusters":c1clusters,"n_dialogue_messages":sum(c["n_messages"] for c in c1clusters),
  "sources":{"tables":[{"at":f"C1:{o&0xFFFF:04X}","count":c,"range":f"${vv[0]:04X}..${max(vv):04X}"} for o,c,vv in c1t],
             "inline":len(c1i)}}

json.dump(cat,open('assets/translations/pointer_catalog.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
print("c7_race:",cat["blocks"]["c7_race"]["sources"])
print("  distinct entry ptrs:",len(c7cov))
print("d0_story tables:",len(d0t),"inline:",len(d0i),"distinct entry ptrs:",len(d0cov))
print("  d0 tables:",[(f'{o&0xFFFF:04X}',c) for o,c,_ in d0t])
print("c1_ui tables:",[(f'{o&0xFFFF:04X}',c) for o,c,_ in c1t],"inline:",len(c1i))
print("c1 clusters:",[(c["name"],c["span"],c["n_messages"]) for c in c1clusters])
print("c1 dialogue total:",cat["blocks"]["c1_ui"]["n_dialogue_messages"])
print("-> assets/translations/pointer_catalog.json")
