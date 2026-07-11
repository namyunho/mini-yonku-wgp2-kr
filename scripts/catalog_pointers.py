#!/usr/bin/env python3
"""전 대사 블록 포인터 카탈로그(권위). 세 정적 텍스트 뱅크 $C7/$D0/$C1.
근거: 파서 $C1:9554 도달 경로 7개 전수 역추적(docs/07). 각 경로의 포인터 소스를 스캔."""
import struct
rom=open("roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc",'rb').read()

def find_all(pat,lo=0,hi=None):
    hi=hi or len(rom); out=[];i=lo
    while True:
        j=rom.find(pat,i)
        if j<0 or j>=hi:break
        out.append(j);i=j+1
    return out

def imm_before_sta(sta_off):
    """STA(8F/8D) 직전 근접 LDA #imm16(A9)를 백트래킹."""
    for back in range(3,9):
        p=sta_off-back
        if p>=0 and rom[p]==0xA9:
            return rom[p+1]|(rom[p+2]<<8)
    return None

# --- C7: VM opcodes EF CB / D4 CB (bank C3) -> $C7 pointer ---
c7=set()
for opx in ('EFCB','D4CB'):
    op=bytes.fromhex(opx)
    for j in find_all(op,0x030000,0x040000):
        p=struct.unpack_from('<H',rom,j+2)[0]
        c7.add(p)

# --- C1: channel immediate writers (bank/ptr paired) + CF90 table ---
# ptr-slots: A=E8647F B=188E7F C=44807F  ; bank-slots parallel
c1=set()
c1_by_ch={}
CH={'A':('E8647F','EA647F'),'B':('188E7F','1A8E7F'),'C':('44807F','46807F')}
for ch,(ps,bs) in CH.items():
    for j in find_all(bytes.fromhex(ps)):
        if rom[j-1]!=0x8F: continue
        sta=j-1
        ptr=imm_before_sta(sta)
        # find matching bank: nearest bank-slot store within +-16 bytes
        bank=None
        for k in find_all(bytes.fromhex(bs),sta-24,sta+24):
            if rom[k-1]==0x8F:
                b=imm_before_sta(k-1)
                if b is not None: bank=b&0xFF; break
        if ptr is None: continue
        if bank==0xC1 and 0xC800<=ptr<=0xD1FF:
            c1.add(ptr); c1_by_ch.setdefault(ch,set()).add(ptr)
# CF90 table
tbl=[]
b=0x01CF90
for k in range(32):
    v=struct.unpack_from('<H',rom,b+2*k)[0]
    if v==0xFFFF: break
    tbl.append(v); c1.add(v)

# --- D0: LDA #imm16 ; STA $1268 (8D 68 12) in bank D0 ---
d0=set()
for j in find_all(bytes.fromhex('681 2'.replace(' ','')),0x100000,0x110000):
    pass
for j in find_all(bytes.fromhex('6812'),0x100000,0x110000):
    if rom[j-1]==0x8D and rom[j-4]==0xA9:  # STA $1268 preceded by LDA #imm16
        ptr=rom[j-3]|(rom[j-2]<<8)
        if 0xC000<=ptr<=0xF000: d0.add(ptr)
# D0:5066 (A-passed, bank D0) callers: LDA #imm ; JSR/…; JSL $D05066? scan JSL 66 50 D0
for j in find_all(bytes.fromhex('6650D0')):
    if rom[j-1]==0x22:  # JSL $D05066
        ptr=imm_before_sta(j-1)  # nearest LDA #imm
        if ptr and 0xC000<=ptr<=0xF000: d0.add(ptr)

def rng(s): return (f"${min(s):04X}..${max(s):04X}" if s else "-")
print(f"C7 pointers: {len(c7)}  range {rng(c7)}")
print(f"C1 pointers: {len(c1)}  range {rng(c1)}  (table CF90: {len(tbl)} entries)")
print("   by channel:",{k:len(v) for k,v in c1_by_ch.items()})
print(f"D0 pointers: {len(d0)}  range {rng(d0)}")
print("\nC1 sorted:", " ".join(f"{x:04X}" for x in sorted(c1)))
print("\nCF90 table:", " ".join(f"{x:04X}" for x in tbl))
print("\nD0 sorted:", " ".join(f"{x:04X}" for x in sorted(d0)))
