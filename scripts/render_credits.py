#!/usr/bin/env python3
"""크레딧 화면 VRAM 덤프를 각 BG 레이어별로 PNG 렌더 (그래픽 자원 확인용).
입력: tmp/trace/credits/{vram.bin,cgram.bin,ppu.txt}. 출력: tmp/trace/credits/bgN.png"""
import struct, zlib, os

ROOT = 'tmp/trace/credits/'
vram = open(ROOT + 'vram.bin', 'rb').read()
cg = open(ROOT + 'cgram.bin', 'rb').read()

def color(idx):
    w = cg[idx*2] | (cg[idx*2+1] << 8)
    r = (w & 31) * 255 // 31
    g = ((w >> 5) & 31) * 255 // 31
    b = ((w >> 10) & 31) * 255 // 31
    return (r, g, b)

def tile_pixels(chr_base, tileno, bpp):
    """8x8 픽셀의 팔레트 인덱스(0..2^bpp-1) 반환."""
    words = 8 if bpp == 2 else 16 if bpp == 4 else 32
    base = chr_base + tileno * words * 2
    px = [[0]*8 for _ in range(8)]
    planes = bpp
    for r in range(8):
        # plane pairs: (0,1) at base+2r ; (2,3) at base+16+2r ; ...
        for pp in range(0, planes, 2):
            off = base + (pp//2)*16 + 2*r
            p0 = vram[off] if off < len(vram) else 0
            p1 = vram[off+1] if off+1 < len(vram) else 0
            for c in range(8):
                bit = 7 - c
                v = ((p0 >> bit) & 1) | (((p1 >> bit) & 1) << 1)
                px[r][c] |= v << pp
    return px

def render_bg(tilemap_addr, chr_addr, bpp, cols=64, rows=32):
    W, H = cols*8, rows*8
    img = [[(0, 0, 0)]*W for _ in range(H)]
    for ty in range(rows):
        for tx in range(cols):
            # 64폭 타일맵: 두 32x32 블록 (block1 = +0x800 word=+0x1000 byte)
            blk = tx // 32; sub = tx % 32
            ent_addr = tilemap_addr + blk*0x1000 + (ty*32 + sub)*2
            if ent_addr+1 >= len(vram): continue
            ent = vram[ent_addr] | (vram[ent_addr+1] << 8)
            tileno = ent & 0x3FF
            pal = (ent >> 10) & 7
            hf = (ent >> 14) & 1; vf = (ent >> 15) & 1
            px = tile_pixels(chr_addr, tileno, bpp)
            palbase = pal * (4 if bpp == 2 else 16)
            for r in range(8):
                for c in range(8):
                    v = px[7-r if vf else r][7-c if hf else c]
                    if v == 0: continue          # 색0=투명
                    img[ty*8+r][tx*8+c] = color(palbase + v)
    return img, W, H

def write_png(path, img, W, H):
    raw = bytearray()
    for r in range(H):
        raw.append(0)
        for c in range(W):
            raw += bytes(img[r][c])
    comp = zlib.compress(bytes(raw), 9)
    def chunk(typ, data):
        return struct.pack('>I', len(data)) + typ + data + struct.pack('>I', zlib.crc32(typ + data) & 0xffffffff)
    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', struct.pack('>IIBBBBB', W, H, 8, 2, 0, 0, 0))
    png += chunk(b'IDAT', comp)
    png += chunk(b'IEND', b'')
    open(path, 'wb').write(png)

# ppu.txt 파싱
layers = {}
for ln in open(ROOT + 'ppu.txt'):
    if ln.startswith('BG'):
        p = ln.split()
        n = int(p[0][2])
        tm = int(p[1].split('=')[1]); ch = int(p[2].split('=')[1])
        layers[n] = (tm, ch)
bpp_of = {1: 4, 2: 4, 3: 2}    # mode1
for n, (tm, ch) in layers.items():
    if n == 4: continue
    img, W, H = render_bg(tm, ch, bpp_of[n])
    write_png(ROOT + f'bg{n}.png', img, W, H)
    print(f'BG{n}: tilemap={tm} chr={ch} bpp={bpp_of[n]} -> bg{n}.png ({W}x{H})')
