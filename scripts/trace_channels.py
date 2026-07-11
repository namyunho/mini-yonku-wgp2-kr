#!/usr/bin/env python3
"""파서 $C1:9554 도달 텍스트 뱅크·포인터의 권위 카탈로그.
각 메시지 채널의 (bank-slot, ptr-slot) 기록자를 스캔, 직전 LDA #imm 백트래킹."""
import struct
ROM="roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
rom=open(ROM,'rb').read()

def find_all(pat):
    out=[];i=0
    while True:
        j=rom.find(pat,i)
        if j<0:break
        out.append(j);i=j+1
    return out

# channel: name, ptr-slot operand bytes, bank-slot operand bytes
CH=[
 ("A","E8647F","EA647F"),
 ("B","188E7F","1A8E7F"),
 ("C","44807F","46807F"),
]

def backtrack_imm(sta_off, slot_bytes):
    """sta_off = file offset of STA opcode (8F). Find nearest preceding LDA #imm (A9) within 16 bytes
       whose value plausibly feeds this store. Return (imm16 or None)."""
    # store is 8F <3 operand bytes>. The A that is stored was set by an LDA #imm shortly before.
    for back in range(3, 20):
        p=sta_off-back
        if p<0: continue
        if rom[p]==0xA9:  # LDA #imm16 (assume 16-bit M)
            # ensure the bytes between are 'clean-ish' (a single store or two)
            return rom[p+1]|(rom[p+2]<<8), p
    return None,None

print("=== bank-slot writers (authoritative text banks) ===")
banks_seen={}
for name,ps,bs in CH:
    bpat=bytes.fromhex(bs)
    print(f"\n-- channel {name} bank-slot ${bs[4:6]}{bs[2:4]}{bs[0:2]} --")
    for j in find_all(bpat):
        op=rom[j-1]
        if op!=0x8F:  # only STA long writers
            continue
        sta=j-1
        imm,ip=backtrack_imm(sta,bpat)
        b=0xC0|(sta>>16); a=sta&0xFFFF
        if imm is not None:
            bank=imm&0xFF
            banks_seen.setdefault(name,set()).add(bank)
            print(f"  {b:02X}:{a:04X}  bank=${bank:02X}")
        else:
            print(f"  {b:02X}:{a:04X}  bank=<dynamic/non-imm>")

print("\n=== ptr-slot writers (pointer catalog per channel) ===")
for name,ps,bs in CH:
    ppat=bytes.fromhex(ps)
    print(f"\n-- channel {name} ptr-slot --")
    for j in find_all(ppat):
        op=rom[j-1]
        if op!=0x8F: continue
        sta=j-1
        imm,ip=backtrack_imm(sta,ppat)
        b=0xC0|(sta>>16); a=sta&0xFFFF
        if imm is not None:
            print(f"  {b:02X}:{a:04X}  ptr=${imm:04X}")
        else:
            print(f"  {b:02X}:{a:04X}  ptr=<dynamic/table>")

print("\n=== summary: distinct immediate banks per channel ===")
for k,v in banks_seen.items():
    print(f"  channel {k}: "+", ".join(f"${x:02X}" for x in sorted(v)))
