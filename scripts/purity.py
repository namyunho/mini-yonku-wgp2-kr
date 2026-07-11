import sys
sys.path.insert(0,'scripts')
from decode_script import decode,render,load_tbl
rom=open("roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc",'rb').read()
tbl=load_tbl("assets/translation_guide/glyph_table.tsv")
def foff(b,a):return((b&0x3F)<<16)|a
def analyze(bank,st,en,name):
    o=foff(bank,st);fe=foff(bank,en);tot=0;bad=0;badstarts=[]
    while o<fe:
        s=o
        while o<fe and rom[o]!=0x00:
            b=rom[o];o+=2 if(1<=b<=4 or b==7) else 1
        raw=rom[s:o+1];o+=1;tot+=1
        toks=decode(raw)
        un=sum(1 for t in toks if t[0]=='glyph' and t[1] not in tbl)
        if un: bad+=1; badstarts.append(s&0xFFFF)
    print(f"{name} ${bank:02X}:{st:04X}..{en:04X}: {tot} msgs, {bad} with unmapped glyphs")
    if badstarts: print("   first bad starts:", " ".join(f"{x:04X}" for x in badstarts[:20]))
analyze(0xC7,0x89E2,0xA001,"c7_race")
analyze(0xD0,0xC80B,0xE828,"d0_story")
analyze(0xC1,0xC868,0xD183,"c1_ui")
# probe machine-name region C981..CE53 sample
print("\n-- c1 region C981.. sample (walk 30) --")
o=foff(0xC1,0xC981)
for _ in range(30):
    s=o
    while rom[o]!=0x00:
        b=rom[o];o+=2 if(1<=b<=4 or b==7) else 1
    raw=rom[s:o+1];o+=1
    print(f"  ${s&0xFFFF:04X}: {render(decode(raw),tbl)[:40]}")
