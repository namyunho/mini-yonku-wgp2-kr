#!/usr/bin/env python3
"""타이틀 하단 텍스트(BG3, PUSH START + 크레딧줄) 한글화: credit.bmp → chr($C7:593D) repaint.

BG3 = 2bpp, chr=$C7:593D(1024B=64타일, LZSS+2바이트헤더), 타일맵 word$5C00(byte0xB800).
타일 53개 전부 고유(재사용0)=비트맵 스트립 → **타일맵 불변, chr 타일만 repaint**.
각 타일이 쓰인 셀 위치의 credit.bmp 8×8을 2bpp(pal0)로 변환해 해당 타일에 기록(un-flip).
pal0: 0=파랑(투명)·1=흰·2=(172,156,156)·3=검정. credit.bmp 파랑=투명.
재압축 in-place(≤697B). 타일맵은 라이브 덤프(tmp/trace/title/vram.bin byte0xB800)에서 셀→타일 매핑만 읽음.

사용: python scripts/build_title_credit.py [--dry]
"""
import sys
from PIL import Image
sys.path.insert(0, 'scripts')
from lzss import decompress, compress, foff

ROM = "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
CHR_SRC = (0xC7, 0x593D)   # BG3 chr (1024B=64타일 2bpp, LZSS+헤더)
TM_SRC = (0xC7, 0x63A3)    # BG3 타일맵 소스 (2112B, LZSS+헤더). ty23(PUSH START)만 런타임기록.
VRAM = 'tmp/trace/title/vram.bin'
CG = 'tmp/trace/title/cgram.bin'
TM_OFF = 0xB800            # 라이브 VRAM의 BG3 타일맵(word$5C00) — 셀→타일 매핑 참조
ORIG = 'img_tile/credit.png'
KR = 'img_tile/credit.bmp'
BLUE = (74, 107, 255)
NTILE = 64

def load_pal0(cg):
    def color(i):
        w = cg[i*2] | (cg[i*2+1] << 8)
        return ((w & 31)*255//31, ((w >> 5) & 31)*255//31, ((w >> 10) & 31)*255//31)
    return [color(i) for i in range(4)]

def tile2_to_px(chr, tn):
    b = tn*16; px = [[0]*8 for _ in range(8)]
    for r in range(8):
        p0 = chr[b+2*r]; p1 = chr[b+2*r+1]
        for c in range(8):
            bt = 7-c; px[r][c] = ((p0 >> bt) & 1) | (((p1 >> bt) & 1) << 1)
    return px

def px_to_tile2(chr, tn, px):
    b = tn*16
    for r in range(8):
        p0 = p1 = 0
        for c in range(8):
            v = px[r][c]
            if v & 1: p0 |= (1 << (7-c))
            if v & 2: p1 |= (1 << (7-c))
        chr[b+2*r] = p0; chr[b+2*r+1] = p1

def nearest(pal, rgb):
    best, bd = 0, 1 << 30
    for i in range(4):
        r, g, b = pal[i]
        d = (r-rgb[0])**2 + (g-rgb[1])**2 + (b-rgb[2])**2
        if d < bd: bd = d; best = i
    return best

def main():
    dry = '--dry' in sys.argv
    rom = bytearray(open(ROM, 'rb').read())
    vram = open(VRAM, 'rb').read()
    cg = open(CG, 'rb').read()
    pal = load_pal0(cg)
    cb = foff(*CHR_SRC); chdr = rom[cb] | (rom[cb+1] << 8)
    chr, cclen = decompress(rom, cb+2, chdr)
    chr = bytearray(chr)
    tb = foff(*TM_SRC); tdhr = rom[tb] | (rom[tb+1] << 8)
    tmdata, tclen = decompress(rom, tb+2, tdhr)
    tmdata = bytearray(tmdata)      # 편집할 타일맵(2112B; word$5C00로 앞 2048B DMA)
    orig = Image.open(ORIG).convert('RGB').load()
    kr = Image.open(KR).convert('RGB').load()

    def quant_cell(tx, ty, hf, vf):
        px = [[0]*8 for _ in range(8)]
        for r in range(8):
            for c in range(8):
                rgb = kr[tx*8+c, ty*8+r]
                idx = 0 if rgb == BLUE else nearest(pal, rgb)
                tr = 7-r if vf else r; tc = 7-c if hf else c
                px[tr][tc] = idx
        return px

    # 타일맵 셀 → 타일 매핑(고유). 사용 타일 집합.
    tile_cell = {}; used_tiles = set()
    tiled = set()
    for ty in range(32):
        for tx in range(32):
            e = vram[TM_OFF+(ty*32+tx)*2] | (vram[TM_OFF+(ty*32+tx)*2+1] << 8)
            t = e & 0x3FF; hf = (e >> 14) & 1; vf = (e >> 15) & 1
            if t:
                used_tiles.add(t); tiled.add((tx, ty))
                if t not in tile_cell: tile_cell[t] = (tx, ty, hf, vf)

    # 1) 기존 타일 repaint(변경분)
    changed = 0
    for t, (tx, ty, hf, vf) in tile_cell.items():
        if all(orig[tx*8+c, ty*8+r] == kr[tx*8+c, ty*8+r] for r in range(8) for c in range(8)): continue
        changed += 1
        px_to_tile2(chr, t, quant_cell(tx, ty, hf, vf))

    # 2) 마스킹: 타일 없는 변경셀 → 자유 타일 할당 + 타일맵 엔트리 추가
    free = [i for i in range(1, NTILE) if i not in used_tiles]
    added = 0
    for ty in range(32):
        for tx in range(32):
            if (tx, ty) in tiled: continue
            if not any(orig[tx*8+c, ty*8+r] != kr[tx*8+c, ty*8+r] for r in range(8) for c in range(8)): continue
            if not free:
                print('⚠️ 자유 타일 부족 — 중단'); return
            nt = free.pop(0)
            px_to_tile2(chr, nt, quant_cell(tx, ty, 0, 0))
            # 타일맵 엔트리(pal0, priority 원행과 동일하게: 기존 ty행 엔트리에서 상위비트 복사)
            ref = None
            for rx in range(32):
                e = tmdata[(ty*32+rx)*2] | (tmdata[(ty*32+rx)*2+1] << 8)
                if e & 0x3FF: ref = e & 0xFC00; break
            hi = ref if ref is not None else 0
            ent = (nt & 0x3FF) | hi
            tmdata[(ty*32+tx)*2] = ent & 0xFF; tmdata[(ty*32+tx)*2+1] = ent >> 8
            added += 1

    cre = compress(bytes(chr)); tre = compress(bytes(tmdata))
    print(f'repaint 타일 {changed}, 마스킹 추가타일 {added}, 자유 남음 {len(free)}')
    print(f'chr 재압축 {len(cre)}/{cclen}B ({"OK" if len(cre)<=cclen else "초과"}), '
          f'타일맵 재압축 {len(tre)}/{tclen}B ({"OK" if len(tre)<=tclen else "초과"})')
    nomasktile = 0

    # 검증 렌더 vs credit.bmp (편집된 타일맵 tmdata 사용, ty23 PUSH START 제외는 라이브와 동일)
    diff = nb = 0
    for ty in range(32):
        for tx in range(32):
            e = tmdata[(ty*32+tx)*2] | (tmdata[(ty*32+tx)*2+1] << 8)
            t = e & 0x3FF
            if not t: continue
            hf = (e >> 14) & 1; vf = (e >> 15) & 1
            px = tile2_to_px(chr, t)
            for r in range(8):
                for c in range(8):
                    v = px[7-r if vf else r][7-c if hf else c]
                    rc = BLUE if v == 0 else pal[v]
                    k = kr[tx*8+c, ty*8+r]
                    if k == BLUE: continue
                    nb += 1
                    if abs(rc[0]-k[0])+abs(rc[1]-k[1])+abs(rc[2]-k[2]) > 60: diff += 1
    print(f'재빌드 렌더 vs credit.bmp(비파랑, 편집타일맵): diff {diff}/{nb}')

    # chr는 in-place, 타일맵은 초과 시 재배치($C6:E000, 참조 2곳 패치)
    TM_RELOC = foff(0xC6, 0xE000)      # ROM 0x06E000 (로고 블롭 뒤 자유공간)
    TM_REFS = [0x35BE5, 0x35E8C]       # JSL $C353C7 뒤 인라인($C7:63A3)
    if not dry and len(cre) <= cclen:
        import os
        base = 'out/wgp2_kr.smc' if os.path.exists('out/wgp2_kr.smc') else ROM
        out = bytearray(open(base, 'rb').read())
        out[cb+2:cb+2+len(cre)] = cre          # chr in-place
        if len(tre) <= tclen:
            out[tb+2:tb+2+len(tre)] = tre       # 타일맵 in-place
            tmloc = '$C7:63A3(in-place)'
        else:
            blob = bytes([tdhr & 0xFF, tdhr >> 8]) + tre   # 헤더+스트림
            assert all(b == 0xFF for b in out[TM_RELOC:TM_RELOC+len(blob)]), '재배치 자유공간 아님'
            out[TM_RELOC:TM_RELOC+len(blob)] = blob
            ptr = bytes([TM_RELOC & 0xFF, (TM_RELOC >> 8) & 0xFF, 0xC0 + (TM_RELOC >> 16)])
            for r in TM_REFS: out[r:r+3] = ptr
            tmloc = f'$C6:{TM_RELOC&0xFFFF:04X}(재배치, 참조{len(TM_REFS)}패치)'
            tb2 = TM_RELOC
        b1, _ = decompress(out, cb+2, chdr)
        b2loc = (tb+2) if len(tre) <= tclen else (TM_RELOC+2)
        b2, _ = decompress(out, b2loc, tdhr)
        assert b1 == bytes(chr) and b2 == bytes(tmdata), '역검증 실패'
        open('out/wgp2_kr.smc', 'wb').write(out)
        print(f'-> out/wgp2_kr.smc: chr $C7:593D in-place + 타일맵 {tmloc}, 역검증 OK')
    elif not dry:
        print('⚠️ chr 재압축 초과 — 미기록.')

if __name__ == '__main__':
    main()
