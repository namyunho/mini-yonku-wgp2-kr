import sys
sys.path.insert(0,'scripts')
from decode_script import decode,render,parse,encode,load_tbl
rom=open("roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc",'rb').read()
tbl=load_tbl("assets/translation_guide/glyph_table.tsv")
def foff(b,a):return((b&0x3F)<<16)|a
# candidate bounds (tightened garage to CF1E, machine to C9C0)
CL=[("setting_save",0xC868,0xC980),("machine_names",0xC981,0xC9C0),
    ("garage_grid",0xCE53,0xCF1E),("formation",0xCFDC,0xD183)]
total=0;rt_ok=0;rt_bad=0
for nm,a0,a1 in CL:
    o=foff(0xC1,a0);fe=foff(0xC1,a1);n=0
    print(f"\n### {nm}  $C1:{a0:04X}..{a1:04X}")
    while o<fe:
        s=o
        while o<fe and rom[o]!=0x00:
            b=rom[o];o+=2 if(1<=b<=4 or b==7) else 1
        raw=bytes(rom[s:o+1]);o+=1;n+=1;total+=1
        toks=decode(raw)
        badop=any(t[0]=='ctrl' and t[1].startswith('op') for t in toks)
        # roundtrip: encode(parse(render(decode(raw)))) == raw
        rt = encode(parse(render(toks)))==raw
        rt_ok+=rt; rt_bad+= (not rt)
        mark=(' !!BADOP' if badop else '')+('' if rt else ' !!RT-FAIL')
        print(f"  ${s&0xFFFF:04X} ({len(raw)}b){mark}  {render(toks,tbl)[:50]}")
    print(f"  -> {n} msgs")
print(f"\nTOTAL c1 dialogue = {total} | roundtrip ok {rt_ok}, fail {rt_bad}")
