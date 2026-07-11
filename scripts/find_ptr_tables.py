#!/usr/bin/env python3
"""각 대사 블록의 메시지 시작 집합을 오라클로, ROM 전역에서 포인터 테이블(연속 런) 탐지."""
import struct,sys
sys.path.insert(0,'scripts')
rom=open("roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc",'rb').read()
def foff(bank,addr): return ((bank&0x3F)<<16)|addr
def starts(bank,start,end):
    o=foff(bank,start);fe=foff(bank,end);S=set()
    while o<fe:
        S.add(o&0xFFFF)
        while o<fe and rom[o]!=0x00:
            b=rom[o];o+=2 if(1<=b<=4 or b==7) else 1
        o+=1
    return S
BLOCKS={'c7_race':(0xC7,0x89E2,0xA001),'d0_story':(0xD0,0xC80B,0xE828),'c1_ui':(0xC1,0xC868,0xD183)}
oracle={n:starts(*b) for n,b in BLOCKS.items()}
for n,s in oracle.items(): print(f"{n}: {len(s)} message-starts")

# scan whole ROM for runs of >=3 consecutive 16-bit LE values that are all message-starts of one block
print("\n=== pointer-table runs (>=3 consecutive block-starts) ===")
for n,(bank,st,en) in BLOCKS.items():
    S=oracle[n]
    runs=[]; i=0
    while i+2<=len(rom)-1:
        # try start a run here
        j=i; cnt=0
        while j+2<=len(rom):
            v=rom[j]|(rom[j+1]<<8)
            if v in S: cnt+=1; j+=2
            else: break
        if cnt>=3:
            runs.append((i,cnt)); i=j
        else:
            i+=1
    # merge/report; filter runs not inside the block's own bank code (tables usually elsewhere)
    print(f"\n-- {n}: {len(runs)} runs --")
    for off,cnt in runs:
        b=0xC0|(off>>16);a=off&0xFFFF
        vals=[rom[off+2*k]|(rom[off+2*k+1]<<8) for k in range(cnt)]
        print(f"  table @ {b:02X}:{a:04X} (file 0x{off:06X}) x{cnt}: "+" ".join(f"{v:04X}" for v in vals[:12])+(" ..." if cnt>12 else ""))
