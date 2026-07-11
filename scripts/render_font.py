#!/usr/bin/env python3
"""본문 폰트 시트($CA:1137) 렌더러 — 확정된 8×16 글리프 + base03 배열 + 2bpp 인터리브.

폰트 글리프는 8×16(8폭×16높이), 2bpp, 32바이트/글리프. 렌더 코드($C0:686D/6875)가
각 행마다 워드 2개를 읽어 위 타일/아래 타일에 그린다:
  top    off(n)      = 0x0A1137 + 16*((n & ~7)*2 + (n & 7))   → 위 8행
  bottom off(n)+0x80                                           → 아래 8행
각 행 = 16비트 워드(lo=bp0, hi=bp1) 표준 SNES 인터리브 2bpp.
기존 render-tiles(선형·8×8)는 이 배열/높이를 못 맞추므로 폰트엔 이 스크립트를 쓴다.

사용: python scripts/render_font.py <rom> <out.png> [--base 0x0A1137] [--glyphs 1056] [--start 0] [--cols 32] [--scale 4]
"""
import argparse, struct, zlib, sys

def base03(n):
    return 16 * (((n & 0xFFF8) * 2) + (n & 7))

# 1bpp 픽셀값 → 그레이 (0=셀 배경, 격자와 구분되게 순검정 대신 약간 밝게)
LUT = {0: 16, 1: 255}
GRID = 80   # 격자선 색
GW, GH = 16, 16   # 글리프 폭/높이 (16×16 1bpp)
MARGIN = 2        # 셀 사방 격자 여백(px)

def decode_glyph(rom, base):
    """16×16 1bpp 글리프를 [GH][GW] 픽셀값(0/1)로 디코드.
    상단 8행 = base 블록, 하단 8행 = base+0x80 블록. 각 행 = 좌바이트+우바이트(16px)."""
    px = [[0] * GW for _ in range(GH)]
    for R in range(GH):
        block = base if R < 8 else base + 0x80
        r = R & 7
        # 각 행 = 16비트 리틀엔디언 워드, bit15=좌측 픽셀:
        #   좌 8px = 둘째 바이트(block+2r+1), 우 8px = 첫째 바이트(block+2r)
        bl = rom[block + 2 * r + 1] if block + 2 * r + 1 < len(rom) else 0
        br = rom[block + 2 * r]
        for c in range(8):
            px[R][c] = (bl >> (7 - c)) & 1
            px[R][8 + c] = (br >> (7 - c)) & 1
    return px

def render(rom, base, ng, cols, start=0):
    cw = GW + MARGIN      # 셀 폭 (글리프 + 우측 여백; 좌/상 여백은 앞 셀이 제공, +MARGIN 초기)
    ch = GH + MARGIN      # 셀 높이
    rows = (ng + cols - 1) // cols
    W = cols * cw + MARGIN
    H = rows * ch + MARGIN
    img = bytearray([GRID]) * (W * H)  # 전체 격자색 → 셀 사이 여백이 격자 박스
    for i in range(ng):
        n = start + i
        base_n = base + base03(n)
        if base_n + 0x80 + 16 > len(rom):
            break
        px = decode_glyph(rom, base_n)
        gx = (i % cols) * cw + MARGIN
        gy = (i // cols) * ch + MARGIN
        for r in range(GH):
            for c in range(GW):
                img[(gy + r) * W + (gx + c)] = LUT[px[r][c]]
    return bytes(img), W, H

def write_png(path, img, W, H, scale):
    ow, oh = W * scale, H * scale
    raw = bytearray()
    for y in range(oh):
        raw.append(0)
        srow = y // scale
        for x in range(ow):
            raw.append(img[srow * W + (x // scale)])
    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", ow, oh, 8, 0, 0, 0, 0)
    with open(path, "wb") as f:
        f.write(sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("out")
    ap.add_argument("--base", type=lambda s: int(s, 0), default=0x0A1137)
    ap.add_argument("--glyphs", type=int, default=1024)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--cols", type=int, default=32)
    ap.add_argument("--scale", type=int, default=4)
    a = ap.parse_args()
    rom = open(a.rom, "rb").read()
    img, W, H = render(rom, a.base, a.glyphs, a.cols, a.start)
    write_png(a.out, img, W, H, a.scale)
    print(f"wrote {a.out} ({W*a.scale}x{H*a.scale}px, glyphs {a.start}..{a.start+a.glyphs-1} @ base 0x{a.base:06X})")

if __name__ == "__main__":
    main()
