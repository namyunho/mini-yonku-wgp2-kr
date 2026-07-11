import sys
sys.path.insert(0,'scripts')
from decode_script import decode,render,load_tbl
rom=open("roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc",'rb').read()
tbl=load_tbl("assets/translation_guide/glyph_table.tsv")
def foff(bank,addr): return ((bank&0x3F)<<16)|addr
def walk(bank,start,end,limit=40):
    o=foff(bank,start); fe=foff(bank,end); n=0
    print(f"\n### walk ${bank:02X}:{start:04X}..{end:04X}")
    while o<fe and n<limit:
        s=o
        while o<fe and rom[o]!=0x00:
            b=rom[o]; o+=2 if(1<=b<=4 or b==7) else 1
        raw=rom[s:o+1]; o+=1; n+=1
        toks=decode(raw)
        un=sum(1 for t in toks if t[0]=='glyph' and t[1] not in tbl)
        addr=(s&0xFFFF)
        mark=' !!UNMAPPED' if un else ''
        t=render(toks,tbl)
        print(f"  ${bank:02X}:{addr:04X} ({len(raw)}b){mark}  {t[:60]}")
# d0 start region
walk(0xD0,0xC80B,0xCC40,limit=30)
# c1 gaps
walk(0xC1,0xC868,0xC9A0,limit=20)
print("\n--- c1 gap C96A..CE53 raw bytes (first 48) ---")
o=foff(0xC1,0xC97C)
print(' '.join(f'{rom[o+k]:02X}' for k in range(48)))
walk(0xC1,0xCE53,0xCF20,limit=20)
