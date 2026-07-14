#!/usr/bin/env python3
"""타이틀 화면 한글화: 사용자 번역 이미지 → BG 블롭(4bpp/2bpp) 슬라이스 삽입.

타이틀 = 겹친 BG 레이어. 번역 대상 2개(공통 하늘색 74,107,255 = 투명):
 - logo   : BG1(4bpp), chr=main_0000 블롭, 타일맵 word0x5000(byte0xA000, doubleH 32×64).
            img_tile/credit_logo.png(원본) vs credit_logo.bmp(번역) 셀 diff → 바뀐 타일만 기록.
 - credit : BG3(2bpp), chr=vram_4000 블롭, 타일맵 word0x5C00(byte0xB800, 32×32).
            img_tile/credit.png vs credit.bmp.
BG chr base=DMA dest → blob 타일인덱스 = 타일맵 tileno. 셀 flip(hf/vf)은 언플립해 기록.
변경셀만 해당 타일 재작성(미변경 타일·arch·구름 유지). 타일 재사용 충돌 검출.
→ 이후 build_gfx.py 재압축 in-place(초과 시 재배치 필요 경고).

사용: python scripts/build_title.py logo|credit|all [--dry]
"""
import sys, struct, zlib
from PIL import Image

BLUE = (74, 107, 255)
VRAM = 'tmp/trace/live/vram.bin'
CG = 'tmp/trace/live/cgram.bin'

ASSETS = {
    'logo':   dict(blob='main_0000', bpp=4, tm=0xA000, cols=32, rows=64, doubleH=True,
                   orig='img_tile/credit_logo.png', kr='img_tile/credit_logo.bmp'),
    'credit': dict(blob='vram_4000', bpp=2, tm=0xB800, cols=32, rows=32, doubleH=False,
                   orig='img_tile/credit.png', kr='img_tile/credit.bmp'),
}

def load_pal(cg, bpp):
    def color(i):
        w = cg[i*2] | (cg[i*2+1] << 8)
        return ((w & 31)*255//31, ((w >> 5) & 31)*255//31, ((w >> 10) & 31)*255//31)
    ncol = 16 if bpp == 4 else 4
    return [[color(p*ncol + i) for i in range(ncol)] for p in range(8)]  # pal 0-7

def tile_px(blob, tn, bpp):
    bp = 8*bpp; b = tn*bp; px = [[0]*8 for _ in range(8)]
    for r in range(8):
        for pp in range(0, bpp, 2):
            off = b + (pp//2)*16 + 2*r
            p0 = blob[off] if off < len(blob) else 0; p1 = blob[off+1] if off+1 < len(blob) else 0
            for c in range(8):
                bt = 7-c; px[r][c] |= (((p0 >> bt) & 1) | (((p1 >> bt) & 1) << 1)) << pp
    return px

def set_tile(blob, tn, px, bpp):
    bp = 8*bpp; b = tn*bp
    for r in range(8):
        for pp in range(0, bpp, 2):
            off = b + (pp//2)*16 + 2*r
            p0 = p1 = 0
            for c in range(8):
                v = (px[r][c] >> pp) & 3
                if v & 1: p0 |= (1 << (7-c))
                if v & 2: p1 |= (1 << (7-c))
            blob[off] = p0; blob[off+1] = p1

def nearest(pal, rgb):
    best, bd = 1, 1 << 30
    for i in range(1, len(pal)):
        r, g, b = pal[i]
        d = (r-rgb[0])**2 + (g-rgb[1])**2 + (b-rgb[2])**2
        if d < bd: bd = d; best = i
    return best

def tm_entry(vram, tm, cols, tx, ty):
    blk = ty // 32
    ea = tm + blk*0x800 + ((ty % 32)*32 + tx)*2
    ent = vram[ea] | (vram[ea+1] << 8)
    return ent & 0x3FF, (ent >> 10) & 7, (ent >> 14) & 1, (ent >> 15) & 1

def build(asset, dry):
    s = ASSETS[asset]
    vram = open(VRAM, 'rb').read(); cg = open(CG, 'rb').read()
    pals = load_pal(cg, s['bpp'])
    blob = bytearray(open(f"tmp/gfx/{s['blob']}.bin", 'rb').read())
    orig = Image.open(s['orig']).convert('RGB').load()
    kr = Image.open(s['kr']).convert('RGB').load()

    tile_target = {}    # tileno -> (px, from_cell) 기록
    tile_all_cells = {} # tileno -> [(tx,ty)]
    changed_cells = 0; conflicts = []
    for ty in range(s['rows']):
        for tx in range(s['cols']):
            t, pal, hf, vf = tm_entry(vram, s['tm'], s['cols'], tx, ty)
            tile_all_cells.setdefault(t, []).append((tx, ty))
            if all(orig[tx*8+c, ty*8+r] == kr[tx*8+c, ty*8+r] for r in range(8) for c in range(8)):
                continue
            changed_cells += 1
            # kr 셀 → 팔레트 인덱스, 언플립
            px = [[0]*8 for _ in range(8)]
            for r in range(8):
                for c in range(8):
                    rr = kr[tx*8+c, ty*8+r]
                    idx = 0 if rr == BLUE else nearest(pals[pal], rr)
                    # 언플립: 화면(tx,ty) 픽셀은 타일이 flip된 것 → 타일좌표 = flip 역적용
                    tr = 7-r if vf else r; tc = 7-c if hf else c
                    px[tr][tc] = idx
            if t in tile_target and tile_target[t][0] != px:
                conflicts.append((t, tile_target[t][1], (tx, ty)))
            tile_target[t] = (px, (tx, ty))

    # 변경타일이 미변경셀과도 공유되면 경고(미변경셀 깨질 수 있음)
    shared = [t for t in tile_target if len(tile_all_cells[t]) > sum(
        1 for (tx, ty) in tile_all_cells[t]
        if not all(orig[tx*8+c, ty*8+r] == kr[tx*8+c, ty*8+r] for r in range(8) for c in range(8)))]

    for t, (px, _) in tile_target.items():
        set_tile(blob, t, px, s['bpp'])

    print(f"[{asset}] 변경셀 {changed_cells}, 재작성 타일 {len(tile_target)}, "
          f"충돌 {len(conflicts)}, 미변경셀공유 {len(shared)}")
    if conflicts: print(f"  ⚠️ 충돌 타일(같은 타일 다른내용): {conflicts[:5]}")
    if shared: print(f"  ⚠️ 공유 타일(미변경셀도 사용): {shared[:5]}")
    if not dry:
        import os
        os.makedirs('tmp/gfx_edit', exist_ok=True)
        open(f"tmp/gfx_edit/{s['blob']}.bin", 'wb').write(bytes(blob))
        print(f"  -> tmp/gfx_edit/{s['blob']}.bin")

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in list(ASSETS)+['all']:
        sys.exit("사용: python scripts/build_title.py logo|credit|all [--dry]")
    dry = '--dry' in sys.argv
    targets = list(ASSETS) if sys.argv[1] == 'all' else [sys.argv[1]]
    for a in targets: build(a, dry)

if __name__ == '__main__':
    main()
