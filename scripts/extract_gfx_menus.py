#!/usr/bin/env python3
"""게임 내 LZSS 그래픽 블롭 전수 추출 → 편집용 PNG(투명=마젠타).

로더 래퍼 JSL $C3:53C7(인라인 소스포인터 + 2바이트 길이헤더)를 정적 전수 파싱해
모든 압축 그래픽 소스를 확보, lzss로 해제 후 타일시트 렌더.
- 투명(팔레트 인덱스0) = 마젠타(255,0,255)로 표기(사용자 요청, bg1_offline 방식).
- 8×8 타일을 16타일폭 팩드 그리드로 렌더(재주입도 이 순서 그대로).
- bpp 미상이라 2bpp·4bpp 둘 다 렌더 → 글자 판독되는 쪽이 정답.
- OptPix로 색감소하므로 팔레트는 인덱스 구분용 디버그색.
산출: assets/graphics/title_credits/extract/<bank><addr>_<bpp>.png
"""
import os, sys, re
sys.path.insert(0, os.path.dirname(__file__))
import lzss
from PIL import Image

ROM = "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
OUTDIR = "assets/graphics/title_credits/extract"
MAGENTA = (255, 0, 255)
PAL2 = [MAGENTA, (255,255,255), (150,150,150), (30,30,30)]
PAL4 = [MAGENTA] + [(v,v,v) for v in (255,220,190,160,130,100,70,40,20)] + \
       [(255,120,120),(120,255,120),(120,120,255),(255,255,120),(120,255,255),(255,120,255)]

def foff(bank, addr): return ((bank & 0x3F) << 16) | (addr & 0xFFFF)

def tile2bpp(data, t):
    o = t*16; px = [[0]*8 for _ in range(8)]
    for row in range(8):
        b0, b1 = data[o+row*2], data[o+row*2+1]
        for col in range(8):
            bit = 7-col
            px[row][col] = ((b0>>bit)&1) | (((b1>>bit)&1)<<1)
    return px

def tile4bpp(data, t):
    o = t*32; px = [[0]*8 for _ in range(8)]
    for row in range(8):
        b0,b1 = data[o+row*2], data[o+row*2+1]
        b2,b3 = data[o+16+row*2], data[o+16+row*2+1]
        for col in range(8):
            bit=7-col
            px[row][col] = ((b0>>bit)&1)|(((b1>>bit)&1)<<1)|(((b2>>bit)&1)<<2)|(((b3>>bit)&1)<<3)
    return px

def render(data, bpp, width_tiles=16):
    tsize = 16 if bpp==2 else 32
    ntiles = len(data)//tsize
    if ntiles==0: return None
    pal = PAL2 if bpp==2 else PAL4
    w = width_tiles*8
    h = ((ntiles + width_tiles-1)//width_tiles)*8
    img = Image.new("RGB",(w,h),MAGENTA)
    px = img.load()
    dec = tile2bpp if bpp==2 else tile4bpp
    for t in range(ntiles):
        tx=(t%width_tiles)*8; ty=(t//width_tiles)*8
        cell=dec(data,t)
        for r in range(8):
            for c in range(8):
                px[tx+c,ty+r]=pal[cell[r][c]]
    return img, ntiles

def main():
    rom = open(ROM,"rb").read()
    os.makedirs(OUTDIR, exist_ok=True)
    calls = [m.start() for m in re.finditer(b'\x22\xC7\x53\xC3', rom)]
    srcs = {}
    for h in calls:
        lo,hi,bk = rom[h+4],rom[h+5],rom[h+6]
        addr = lo|(hi<<8)
        if bk<0xC0: continue
        fo = foff(bk,addr)
        hdr = rom[fo]|(rom[fo+1]<<8)
        srcs[(bk,addr)] = hdr
    print(f"고유 LZSS 소스 {len(srcs)}개")
    for (bk,addr),hdr in sorted(srcs.items()):
        try:
            data,_ = lzss.decompress(rom, foff(bk,addr)+2, hdr)
        except Exception as e:
            print(f"  ${bk:02X}:{addr:04X} 해제실패 {e}"); continue
        tag=f"{bk:02X}{addr:04X}"
        info=""
        for bpp in (2,4):
            res=render(data,bpp)
            if res:
                img,nt=res
                img.save(f"{OUTDIR}/{tag}_{bpp}bpp.png")
                info += f" {bpp}bpp={nt}t({img.size[0]}x{img.size[1]})"
        print(f"  ${bk:02X}:{addr:04X} hdr={hdr:5d} 해제={len(data):5d}B →{info}")
    print(f"\n산출 {OUTDIR}/  (투명=마젠타, 8×8 팩드 16타일폭). bpp는 글자 판독되는 쪽이 정답.")

if __name__=="__main__":
    main()
