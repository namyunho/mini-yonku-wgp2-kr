#!/usr/bin/env python3
"""타이틀 로고 한글화: credit_logo.bmp → chr($C3:0E2F) + 타일맵($C7:5BF8) 통째 재빌드.

타이틀 로고 = BG1 블록0(상단 32×32). chr·타일맵 둘 다 LZSS+2바이트 길이헤더.
마스킹(번역이 원본 타일배치와 1:1 아님)은 **이미지에서 재빌드**로 자동 해결:
 - 각 8×8 셀 → 셀별 최적 팔레트 양자화(파랑74,107,255=투명 인덱스0)
 - 타일 디듀프(+H/V flip) → 고유 타일셋(≤400) + 타일맵(1024엔트리=2048B)
 - unchanged 셀(credit_logo.png==bmp)은 원본 팔레트로 양자화해 원본 타일과 동일 유지(디듀프 극대화)
 - LZSS 재압축 in-place(헤더 유지, ≤원본압축). 초과 시 경고.
검증: 재빌드 chr+타일맵 렌더 == credit_logo.bmp(비파랑).

사용: python scripts/build_title_logo.py [--dry] [--write]
"""
import sys, struct, zlib
from PIL import Image
sys.path.insert(0, 'scripts')
from lzss import decompress, compress, foff

ROM = "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
CHR_SRC = (0xC3, 0x0E2F)      # 로고 chr (12800B)
TM_SRC  = (0xC7, 0x5BF8)      # 로고 타일맵 (2048B, 32×32)
ORIG = 'img_tile/credit_logo.png'
KR   = 'img_tile/credit_logo.bmp'
CG   = 'tmp/trace/live/cgram.bin'
BLUE = (74, 107, 255)
NTILE = 400                   # chr 12800B / 32
GRID = 32                     # 32×32 셀

def load_bg_pals(cg):
    def color(i):
        w = cg[i*2] | (cg[i*2+1] << 8)
        return ((w & 31)*255//31, ((w >> 5) & 31)*255//31, ((w >> 10) & 31)*255//31)
    return [[color(p*16 + i) for i in range(16)] for p in range(8)]

def tile_to_px(chr, tn):
    b = tn*32; px = [[0]*8 for _ in range(8)]
    for r in range(8):
        for pp in range(0, 4, 2):
            off = b + (pp//2)*16 + 2*r
            p0 = chr[off] if off < len(chr) else 0; p1 = chr[off+1] if off+1 < len(chr) else 0
            for c in range(8):
                bt = 7-c; px[r][c] |= (((p0 >> bt) & 1) | (((p1 >> bt) & 1) << 1)) << pp
    return px

def px_to_bytes(px):
    """8×8 인덱스 → 4bpp 32B."""
    out = bytearray(32)
    for r in range(8):
        for pp in range(0, 4, 2):
            off = (pp//2)*16 + 2*r
            p0 = p1 = 0
            for c in range(8):
                v = (px[r][c] >> pp) & 3
                if v & 1: p0 |= (1 << (7-c))
                if v & 2: p1 |= (1 << (7-c))
            out[off] = p0; out[off+1] = p1
    return bytes(out)

def flip_px(px, hf, vf):
    return [[px[7-r if vf else r][7-c if hf else c] for c in range(8)] for r in range(8)]

def nearest(pal, rgb):
    best, bd = 1, 1 << 30
    for i in range(1, 16):
        r, g, b = pal[i]
        d = (r-rgb[0])**2 + (g-rgb[1])**2 + (b-rgb[2])**2
        if d < bd: bd = d; best = i
    return best, bd

def fill_holes(load, W, H, ylimit=112, maxsize=8):
    """작은 내부 투명(파랑) 구멍을 이웃 지배색으로 메움(그림자 속 배경 비침 방지).
    ylimit 위 영역만, size<=maxsize·비경계 성분만. 원본 파일 불변(메모리 픽셀 수정)."""
    from collections import deque, Counter
    seen = [[False]*W for _ in range(H)]
    filled = 0
    for y in range(ylimit):
        for x in range(W):
            if load[x, y] == BLUE and not seen[y][x]:
                q = deque([(x, y)]); seen[y][x] = True; cc = []; tb = False
                while q:
                    cx, cy = q.popleft(); cc.append((cx, cy))
                    if cx == 0 or cx == W-1 or cy == 0: tb = True
                    for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
                        nx, ny = cx+dx, cy+dy
                        if 0 <= nx < W and 0 <= ny < ylimit and load[nx, ny] == BLUE and not seen[ny][nx]:
                            seen[ny][nx] = True; q.append((nx, ny))
                if not tb and len(cc) <= maxsize:
                    nb = Counter()
                    for x0, y0 in cc:
                        for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
                            p = load[x0+dx, y0+dy]
                            if p != BLUE: nb[p] += 1
                    if nb:
                        col = nb.most_common(1)[0][0]
                        for x0, y0 in cc: load[x0, y0] = col
                        filled += len(cc)
    return filled

NAVY = (16, 24, 74)   # pal7에만 있는 어두운 외곽선색.

def black_index(pal):
    """팔레트에 순수검정(0,0,0)이 있으면 그 인덱스, 없으면 None."""
    for i in range(1, 16):
        if tuple(pal[i]) == (0, 0, 0): return i
    return None

def navy_index(pal):
    for i in range(1, 16):
        if tuple(pal[i]) == NAVY: return i
    return None

def quantize_cell(img, cx, cy, pal):
    """8×8 셀 → (인덱스px, 총오차). 파랑=0. 네이비=팔레트 네이비 or 순수검정(회색 금지)."""
    bi = black_index(pal); ni = navy_index(pal)
    px = [[0]*8 for _ in range(8)]; err = 0
    for r in range(8):
        for c in range(8):
            rgb = img[cx*8+c, cy*8+r]
            if rgb == BLUE:
                px[r][c] = 0
            elif rgb == NAVY:
                if ni is not None: px[r][c] = ni          # 네이비 유지
                elif bi is not None: px[r][c] = bi         # 순수검정으로 병합
                else: px[r][c] = nearest(pal, rgb)[0]      # (거의 없음)
            else:
                idx, d = nearest(pal, rgb); px[r][c] = idx; err += d
    return px, err

def main():
    dry = '--dry' in sys.argv or '--write' not in sys.argv
    rom = bytearray(open(ROM, 'rb').read())
    cg = open(CG, 'rb').read()
    pals = load_bg_pals(cg)
    # 원본 chr·타일맵 해제
    cb = foff(*CHR_SRC); chdr = rom[cb] | (rom[cb+1] << 8); chr0, chr_comp = decompress(rom, cb+2, chdr)
    tb = foff(*TM_SRC); thdr = rom[tb] | (rom[tb+1] << 8); tm0, tm_comp = decompress(rom, tb+2, thdr)
    orig = Image.open(ORIG).convert('RGB').load()
    kr_img = Image.open(KR).convert('RGB'); kr = kr_img.load()
    nfill = fill_holes(kr, kr_img.width, kr_img.height)
    print(f'구멍 메움: {nfill}px (그림자 속 투명 점 → 이웃색)')

    # 원본 타일맵 엔트리(unchanged 셀 팔레트 참조용)
    def orig_ent(cx, cy):
        e = tm0[(cy*32+cx)*2] | (tm0[(cy*32+cx)*2+1] << 8)
        return e & 0x3FF, (e >> 10) & 7, (e >> 14) & 1, (e >> 15) & 1

    # 타일셋: base 타일 바이트 → 인덱스. 4방향 orientation 조회.
    tileset = [bytes(32)]              # tile0 = blank
    lookup = {bytes(32): (0, 0, 0)}    # bytes(px) → (base_idx, hf, vf)
    def register(base_idx, base_px):
        for hf in (0, 1):
            for vf in (0, 1):
                k = px_to_bytes(flip_px(base_px, hf, vf))
                lookup.setdefault(k, (base_idx, hf, vf))
    def get_tile(px):
        k = px_to_bytes(px)
        if k in lookup: return lookup[k]
        idx = len(tileset); tileset.append(k)
        register(idx, px)
        return (idx, 0, 0)

    new_tm = bytearray(2048)
    changed = 0
    used_pal = set()
    for cy in range(GRID):
        for cx in range(GRID):
            ot, opal, ohf, ovf = orig_ent(cx, cy)
            same = all(orig[cx*8+c, cy*8+r] == kr[cx*8+c, cy*8+r] for r in range(8) for c in range(8))
            if same:
                # 원본 팔레트로 양자화 → 원본 타일과 동일(디듀프)
                px, _ = quantize_cell(kr, cx, cy, pals[opal]); pal = opal
            else:
                changed += 1
                # 최소오차 팔레트 선택(글자색 원본충실). 네이비→회색 방지는 quantize가 처리.
                best = None
                for p in [0, 2, 3, 4, 6, 7, 1, 5]:
                    px, err = quantize_cell(kr, cx, cy, pals[p])
                    if best is None or err < best[1]: best = (px, err, p)
                px, _, pal = best
            ti, hf, vf = get_tile(px)
            used_pal.add(pal)
            ent = (ti & 0x3FF) | (pal << 10) | (hf << 14) | (vf << 15)
            new_tm[(cy*32+cx)*2] = ent & 0xFF; new_tm[(cy*32+cx)*2+1] = ent >> 8

    ntiles = len(tileset)
    # chr 빌드(400타일 고정, 미사용=0)
    new_chr = bytearray(NTILE*32)
    for i, t in enumerate(tileset[:NTILE]):
        new_chr[i*32:i*32+32] = t
    # 재압축
    chr_re = compress(bytes(new_chr)); tm_re = compress(bytes(new_tm))
    print(f'변경셀 {changed}, 고유타일 {ntiles}/{NTILE} ({"OK" if ntiles<=NTILE else "초과!"}), 팔레트 {sorted(used_pal)}')
    print(f'chr 재압축 {len(chr_re)}/{chr_comp}B ({"OK" if len(chr_re)<=chr_comp else "초과"}), '
          f'타일맵 재압축 {len(tm_re)}/{tm_comp}B ({"OK" if len(tm_re)<=tm_comp else "초과"})')

    # 검증 렌더
    def render():
        img = [[BLUE]*256 for _ in range(256)]
        for cy in range(32):
            for cx in range(32):
                e = new_tm[(cy*32+cx)*2] | (new_tm[(cy*32+cx)*2+1] << 8)
                t = e & 0x3FF; pal = (e >> 10) & 7; hf = (e >> 14) & 1; vf = (e >> 15) & 1
                px = tile_to_px(new_chr, t)
                for r in range(8):
                    for c in range(8):
                        v = px[7-r if vf else r][7-c if hf else c]
                        rgb = BLUE if v == 0 else pals[pal][v]
                        img[cy*8+r][cx*8+c] = rgb
        return img
    rimg = render()
    diff = nb = 0
    for y in range(256):
        for x in range(256):
            kk = kr[x, y]
            if kk != BLUE:
                nb += 1
                a = rimg[y][x]
                if abs(a[0]-kk[0])+abs(a[1]-kk[1])+abs(a[2]-kk[2]) > 60: diff += 1
    print(f'재빌드 렌더 vs credit_logo.bmp(비파랑): diff {diff}/{nb}')

    if ntiles > NTILE:
        print('타일 초과 — 중단'); return
    # 재배치: 자유공간 $C6:AB11 (대사 재배치와 무관, out에서도 자유)
    RELOC = foff(0xC6, 0xAB11)     # ROM PC 0x06AB11
    chr_hdr = bytes([chdr & 0xFF, chdr >> 8])   # 해제길이 헤더 유지
    tm_hdr = bytes([thdr & 0xFF, thdr >> 8])
    chr_blob = chr_hdr + chr_re
    tm_blob = tm_hdr + tm_re
    chr_at = RELOC
    tm_at = RELOC + len(chr_blob)
    # 새 인라인 포인터(addr_lo, addr_hi, bank)
    def inl(off):
        bank = 0xC0 + (off >> 16); addr = off & 0xFFFF
        return bytes([addr & 0xFF, addr >> 8, bank])
    chr_ptr = inl(chr_at); tm_ptr = inl(tm_at)
    CHR_REFS = [0x0359F9, 0x035D96]   # JSL $C353C7 뒤 인라인 위치(chr)
    TM_REFS  = [0x035BB9, 0x035E26]   # (tilemap)

    if not dry:
        import os
        base = 'out/wgp2_kr.smc' if os.path.exists('out/wgp2_kr.smc') else ROM
        out = bytearray(open(base, 'rb').read())
        # 재배치 영역 자동 클리어(이전 기록분 정리; 자유런 0x54EF 내 12000B만)
        for i in range(RELOC, RELOC + 12000): out[i] = 0xFF
        span = out[chr_at:tm_at+len(tm_blob)]
        assert all(b == 0xFF for b in span), '자유공간 아님(0xFF 아님) — 중단'
        out[chr_at:chr_at+len(chr_blob)] = chr_blob
        out[tm_at:tm_at+len(tm_blob)] = tm_blob
        for r in CHR_REFS: out[r:r+3] = chr_ptr
        for r in TM_REFS: out[r:r+3] = tm_ptr
        # 역검증: 새 위치에서 재해제
        b1, _ = decompress(out, chr_at+2, chdr); b2, _ = decompress(out, tm_at+2, thdr)
        assert b1 == bytes(new_chr) and b2 == bytes(new_tm), '역검증 실패'
        open('out/wgp2_kr.smc', 'wb').write(out)
        print(f'-> out/wgp2_kr.smc: chr@$C6:{chr_at&0xFFFF:04X} tm@$C6:{tm_at&0xFFFF:04X}, '
              f'포인터 {len(CHR_REFS)+len(TM_REFS)}곳 패치, 역검증 OK')
    else:
        print(f'[dry] 재배치 예정: chr@0x{chr_at:06X}({len(chr_blob)}B) tm@0x{tm_at:06X}({len(tm_blob)}B), '
              f'포인터 패치 chr{CHR_REFS} tm{TM_REFS}')

if __name__ == '__main__':
    main()
