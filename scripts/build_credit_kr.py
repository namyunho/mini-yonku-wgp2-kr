#!/usr/bin/env python3
"""크레딧 화면 한글화: screen.bmp(목표) → vram_7000 블롭(4bpp 스프라이트 아틀라스) 편집.

크레딧 텍스트는 BG가 아니라 **16×16 스프라이트 스트립**으로 렌더됨.
 - OBJ chr base word 0x6000(byte 0xC000), 글리프 = vram_7000 블롭(DMA vmadd word $7000=byte 0xE000).
 - 매핑: OAM 타일번호 T → 블롭 타일 인덱스 = T - 0x100. 16×16 = 블롭 타일 {b, b+1, b+16, b+17}.
 - 팔레트: pal0/pal2 공통 인덱스 1=흰(255), 3=진회(57), 0=투명(검정). screen.bmp가 이 색 사용.
편집 대상 줄: Y=55(こした→한글)·71(タミヤ→한글)·183(하단 상표줄→한글). Y=39(영어)·© 타일(0x15F)은 유지.
산출: tmp/gfx_edit/vram_7000.bin (해제길이 불변) → build_gfx.py로 재압축 in-place.
--dry: ROM 미기록, 프리뷰 PNG만.
"""
import sys, struct, zlib
from PIL import Image

DRY = '--dry' in sys.argv
BLOB = 'tmp/gfx/vram_7000.bin'
OUT  = 'tmp/gfx_edit/vram_7000.bin'
SCREEN = 'img_tile/screen.bmp'
OAM = 'tmp/trace/credit2/oam.bin'
CG  = 'tmp/trace/credit2/cgram.bin'
EDIT_LINES = {39, 55, 71, 183}   # 전 줄 screen.bmp 베이킹(1줄 영어 포함 — 잉여 점 제거, 전체 정합)
SKIP_TILE_BLOB = {0x15F - 0x100}  # © 공유 타일(블롭 95) 유지

blob = bytearray(open(BLOB, 'rb').read())
oam = open(OAM, 'rb').read()
cg = open(CG, 'rb').read()
im = Image.open(SCREEN).convert('RGB')
sw, sh = im.size
spx = im.load()

def rgb2idx(r, g, b):
    if r < 40 and g < 40 and b < 40: return 0          # 검정=투명
    if r > 180 and g > 180 and b > 180: return 1       # 흰
    return 3                                            # 진회(57)

def set_tile4(blob, tileno, px):
    """px = 8x8 팔레트인덱스(0-15) → 블롭 tileno(4bpp 32B) 기록."""
    b = tileno * 32
    for r in range(8):
        for pp in range(0, 4, 2):
            off = b + (pp // 2) * 16 + 2 * r
            p0 = p1 = 0
            for c in range(8):
                v = (px[r][c] >> pp) & 3
                if v & 1: p0 |= (1 << (7 - c))
                if v & 2: p1 |= (1 << (7 - c))
            blob[off] = p0; blob[off + 1] = p1

# OAM 파싱
sprites = []
for i in range(128):
    x = oam[i*4]; y = oam[i*4+1]; t = oam[i*4+2]; a = oam[i*4+3]
    hi = oam[512 + i//4]; bits = (hi >> ((i % 4) * 2)) & 3
    xh = bits & 1; size = (bits >> 1) & 1
    X = x | (xh << 8); X = X - 512 if X >= 256 else X
    tileno = t | ((a & 1) << 8)
    if y >= 0xE0: continue
    sprites.append((X, y, tileno, (a >> 1) & 7, (a >> 6) & 1, (a >> 7) & 1, size))

edited = 0
for (X, Y, tileno, pal, hf, vf, size) in sprites:
    if Y not in EDIT_LINES: continue
    bbase = tileno - 0x100
    if bbase in SKIP_TILE_BLOB: continue
    # screen.bmp 16×16 추출(hf/vf 없다고 가정 — 크레딧 스프라이트는 flip 0)
    for sy in range(2):
        for sx in range(2):
            tn = bbase + sx + sy * 16
            px = [[0]*8 for _ in range(8)]
            for r in range(8):
                for c in range(8):
                    px_y = Y + sy*8 + r; px_x = X + sx*8 + c
                    if 0 <= px_x < sw and 0 <= px_y < sh:
                        px[r][c] = rgb2idx(*spx[px_x, px_y])
            set_tile4(blob, tn, px)
    edited += 1
print(f'edited sprites: {edited}, blob size {len(blob)} (원본 {len(open(BLOB,"rb").read())})')

# 프리뷰: 편집된 블롭으로 스프라이트 재렌더
def color(idx):
    w = cg[idx*2] | (cg[idx*2+1] << 8)
    return ((w & 31)*255//31, ((w >> 5) & 31)*255//31, ((w >> 10) & 31)*255//31)
def tile4(data, tileno):
    b = tileno*32; px = [[0]*8 for _ in range(8)]
    for r in range(8):
        for pp in range(0, 4, 2):
            off = b + (pp//2)*16 + 2*r
            p0 = data[off] if off < len(data) else 0; p1 = data[off+1] if off+1 < len(data) else 0
            for c in range(8):
                bt = 7-c; px[r][c] |= (((p0 >> bt) & 1) | (((p1 >> bt) & 1) << 1)) << pp
    return px
W, H = 256, 224; img = [[(0,0,0)]*W for _ in range(H)]
for (X, Y, tileno, pal, hf, vf, size) in sprites:
    bbase = tileno - 0x100
    for sy in range(2):
        for sx in range(2):
            tn = bbase + sx + sy*16
            px = tile4(blob, tn)
            for r in range(8):
                for c in range(8):
                    v = px[r][c]
                    if v == 0: continue
                    py = Y + sy*8 + r; pxx = X + sx*8 + c
                    if 0 <= py < H and 0 <= pxx < W: img[py][pxx] = color(128 + pal*16 + v)
def wpng(path, img, W, H):
    raw = bytearray()
    for r in range(H):
        raw.append(0)
        for c in range(W): raw += bytes(img[r][c])
    comp = zlib.compress(bytes(raw), 9)
    def ch(t, d): return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t+d) & 0xffffffff)
    open(path, 'wb').write(b'\x89PNG\r\n\x1a\n' + ch(b'IHDR', struct.pack('>IIBBBBB', W, H, 8, 2, 0, 0, 0)) + ch(b'IDAT', comp) + ch(b'IEND', b''))
wpng('tmp/gfx_edit/credit_preview.png', img, W, H)
print('-> tmp/gfx_edit/credit_preview.png')

if not DRY:
    import os
    os.makedirs('tmp/gfx_edit', exist_ok=True)
    open(OUT, 'wb').write(bytes(blob))
    print(f'-> {OUT} (write)')
