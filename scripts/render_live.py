#!/usr/bin/env python3
"""라이브 VRAM 덤프(tmp/trace/live)를 BG 레이어별 PNG로 렌더 + BG3 타일맵 그리드 덤프.
크레딧 화면 타일 배치 분석용."""
import struct, zlib, sys

ROOT = 'tmp/trace/live/'
vram = open(ROOT + 'vram.bin', 'rb').read()
cg = open(ROOT + 'cgram.bin', 'rb').read()

def color(idx):
    w = cg[idx*2] | (cg[idx*2+1] << 8)
    return ((w & 31)*255//31, ((w >> 5) & 31)*255//31, ((w >> 10) & 31)*255//31)

def tile_pixels(chr_base, tileno, bpp):
    words = 8 if bpp == 2 else 16 if bpp == 4 else 32
    base = chr_base + tileno * words * 2
    px = [[0]*8 for _ in range(8)]
    for r in range(8):
        for pp in range(0, bpp, 2):
            off = base + (pp//2)*16 + 2*r
            p0 = vram[off] if off < len(vram) else 0
            p1 = vram[off+1] if off+1 < len(vram) else 0
            for c in range(8):
                bit = 7 - c
                px[r][c] |= (((p0 >> bit) & 1) | (((p1 >> bit) & 1) << 1)) << pp
    return px

def render_bg(tilemap_addr, chr_addr, bpp, cols=64, rows=32):
    W, H = cols*8, rows*8
    img = [[(0, 0, 0)]*W for _ in range(H)]
    grid = []
    for ty in range(rows):
        row = []
        for tx in range(cols):
            blk = tx // 32; sub = tx % 32
            ent_addr = tilemap_addr + blk*0x1000 + (ty*32 + sub)*2
            if ent_addr+1 >= len(vram):
                row.append(None); continue
            ent = vram[ent_addr] | (vram[ent_addr+1] << 8)
            tileno = ent & 0x3FF
            pal = (ent >> 10) & 7
            hf = (ent >> 14) & 1; vf = (ent >> 15) & 1
            row.append((tileno, pal, hf, vf))
            px = tile_pixels(chr_addr, tileno, bpp)
            palbase = pal * (4 if bpp == 2 else 16)
            for r in range(8):
                for c in range(8):
                    v = px[7-r if vf else r][7-c if hf else c]
                    if v == 0: continue
                    img[ty*8+r][tx*8+c] = color(palbase + v)
        grid.append(row)
    return img, W, H, grid

def write_png(path, img, W, H):
    raw = bytearray()
    for r in range(H):
        raw.append(0)
        for c in range(W):
            raw += bytes(img[r][c])
    comp = zlib.compress(bytes(raw), 9)
    def chunk(typ, data):
        return struct.pack('>I', len(data)) + typ + data + struct.pack('>I', zlib.crc32(typ+data) & 0xffffffff)
    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', struct.pack('>IIBBBBB', W, H, 8, 2, 0, 0, 0))
    png += chunk(b'IDAT', comp) + chunk(b'IEND', b'')
    open(path, 'wb').write(png)

layers = {}
for ln in open(ROOT + 'ppu.txt'):
    if ln.startswith('BG'):
        p = ln.split()
        n = int(p[0][2])
        layers[n] = (int(p[1].split('=')[1]), int(p[2].split('=')[1]))
bpp_of = {1: 4, 2: 4, 3: 2}
grids = {}
for n, (tm, ch) in layers.items():
    if n == 4 or ch == 0 and tm == 0:
        continue
    img, W, H, grid = render_bg(tm, ch, bpp_of[n])
    write_png(ROOT + f'bg{n}.png', img, W, H)
    grids[n] = grid
    print(f'BG{n}: tilemap={tm}(0x{tm:04X}) chr={ch}(0x{ch:04X}) bpp={bpp_of[n]} -> bg{n}.png ({W}x{H})')

# BG3 그레이스케일(팔레트 무시): 글리프 형태 확인용
if 3 in layers:
    tm, ch = layers[3]
    W, H = 512, 256
    img = [[(0, 0, 0)]*W for _ in range(H)]
    ramp = {0: (0, 0, 0), 1: (255, 255, 255), 2: (160, 160, 160), 3: (80, 80, 80)}
    for ty in range(32):
        for tx in range(64):
            blk = tx // 32; sub = tx % 32
            ea = tm + blk*0x1000 + (ty*32 + sub)*2
            if ea+1 >= len(vram): continue
            ent = vram[ea] | (vram[ea+1] << 8)
            px = tile_pixels(ch, ent & 0x3FF, 2)
            hf = (ent >> 14) & 1; vf = (ent >> 15) & 1
            for r in range(8):
                for c in range(8):
                    v = px[7-r if vf else r][7-c if hf else c]
                    img[ty*8+r][tx*8+c] = ramp[v]
    write_png(ROOT + 'bg3_gray.png', img, W, H)
    print('BG3 grayscale -> bg3_gray.png')

# BG3(텍스트) 타일맵 그리드: 화면 표시영역 32x28만, tileno 16진
if 3 in grids:
    print('\n=== BG3 tilemap (visible 32x28), tileno hex (.. = tile 0/blank) ===')
    g = grids[3]
    for ty in range(28):
        cells = []
        for tx in range(32):
            e = g[ty][tx]
            if e is None: cells.append(' --'); continue
            t = e[0]
            cells.append(' ..' if t == 0 else f'{t:3X}')
        print(f'{ty:2d}|' + ''.join(cells))
