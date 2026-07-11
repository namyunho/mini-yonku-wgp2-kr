import sys
sys.path.insert(0,'scripts')
from decode_script import decode,render,load_tbl
rom=open("roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc",'rb').read()
tbl=load_tbl("assets/translation_guide/glyph_table.tsv")
def foff(b,a):return((b&0x3F)<<16)|a
def peek(bank,st,n):
    o=foff(bank,st)
    for _ in range(n):
        s=o
        while rom[o]!=0x00:
            b=rom[o];o+=2 if(1<=b<=4 or b==7) else 1
        raw=rom[s:o+1];o+=1
        print(f"  ${s&0xFFFF:04X}: {render(decode(raw),tbl)[:52]}")
for a in (0xCAC0,0xCB82,0xCBC9,0xCD71,0xCF58,0xCF80):
    print(f"\n-- ${a:04X} --"); peek(0xC1,a,8)
