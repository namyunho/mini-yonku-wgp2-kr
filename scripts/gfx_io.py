#!/usr/bin/env python3
"""범용 타일 그래픽 export/import — 사용자 픽셀아트 편집 왕복 파이프라인.

개념: 게임 그래픽 = 고정크기 타일(8×8, bpp별 색상수) 집합을 화면에 조각조각 배치.
이 도구는 편집 대상 타일을 (편집용 PNG + 팔레트 + 매니페스트)로 뽑아주고,
편집본 PNG를 받아 타일로 역변환해 해제 블롭(tmp/gfx/<blob>.bin)에 다시 써넣는다.
→ 이후 `python scripts/build_gfx.py`로 LZSS 재압축 in-place.

교환 포맷(work/<asset>/):
  edit.png      RGBA. 게임 정확 색상, 투명 픽셀=알파0(팔레트 인덱스0). 포토샵/ImageStudio 편집.
  palette.act   Adobe Color Table(256 RGB) — 색상감소(4bpp=16색)용.
  palette.pal   JASC-PAL 텍스트 팔레트(동일 내용).
  palette.png   팔레트 미리보기(16색 스와치).
  manifest.json 각 편집셀(x,y,w,h) → 블롭 타일 인덱스 매핑. import가 이걸로 역삽입.

레이아웃 두 가지:
  screen : 화면 실제 좌표에 셀 배치(WYSIWYG 풀이미지 편집 = 모드B).
  grid   : 편집할 타일만 촘촘한 격자로 팩(타깃 타일만 편집 = 모드A).

사용:
  python scripts/gfx_io.py export credit [--mode screen|grid]
  # (사용자가 work/credit/edit.png 편집 후)
  python scripts/gfx_io.py import credit
  python scripts/build_gfx.py --rom out/wgp2_kr.smc --out out/wgp2_kr.smc
"""
import argparse, json, os, sys
from PIL import Image

sys.path.insert(0, 'scripts')
from lzss import SOURCES

GFX_DIR = 'tmp/gfx'
EDIT_DIR = 'tmp/gfx_edit'
WORK = 'work'

# ── 팔레트 (OBJ, CGRAM 실측) ─────────────────────────────────────────────
PAL2 = [[0,0,115],[255,255,255],[123,123,123],[57,57,57],[65,90,213],[32,57,115],
        [8,32,49],[205,205,222],[74,74,82],[24,24,32],[0,0,8],[205,180,82],
        [230,148,8],[197,49,32],[0,106,0],[0,0,0]]

# ── 에셋 레지스트리 ───────────────────────────────────────────────────────
# cells_from='oam' : OAM 덤프에서 스프라이트 셀 유도. tile_base = blob_tile = oam_tileno - base.
ASSETS = {
    'credit': {
        'blob': 'vram_7000', 'bpp': 4, 'palette': PAL2,
        'canvas': (256, 224),
        'cells_from': 'oam', 'oam': 'tmp/trace/credit2/oam.bin',
        'tile_base': 0x100, 'sprite': 16,
        'keep_tiles': [95, 96, 111, 112],   # © 스프라이트(타일번호 0x15F) 4타일: 원본 유지
        'black_transparent': True,   # 알파없는 RGB 편집본: 근사검정=투명 처리
    },
}

# ── 타일 <-> 픽셀 ────────────────────────────────────────────────────────
def tile_to_px(blob, tileno, bpp):
    """블롭 tileno(bpp) → 8×8 팔레트인덱스."""
    bytes_per = 8 * bpp
    b = tileno * bytes_per
    px = [[0]*8 for _ in range(8)]
    for r in range(8):
        for pp in range(0, bpp, 2):
            off = b + (pp//2)*16 + 2*r
            p0 = blob[off] if off < len(blob) else 0
            p1 = blob[off+1] if off+1 < len(blob) else 0
            for c in range(8):
                bt = 7-c
                px[r][c] |= (((p0 >> bt) & 1) | (((p1 >> bt) & 1) << 1)) << pp
    return px

def px_to_tile(blob, tileno, px, bpp):
    """8×8 팔레트인덱스 → 블롭 tileno(bpp) 기록."""
    bytes_per = 8 * bpp
    b = tileno * bytes_per
    for r in range(8):
        for pp in range(0, bpp, 2):
            off = b + (pp//2)*16 + 2*r
            p0 = p1 = 0
            for c in range(8):
                v = (px[r][c] >> pp) & 3
                if v & 1: p0 |= (1 << (7-c))
                if v & 2: p1 |= (1 << (7-c))
            blob[off] = p0; blob[off+1] = p1

# ── 셀 유도 ──────────────────────────────────────────────────────────────
def cells_from_oam(spec):
    """OAM 덤프 → 스프라이트 셀 목록. 각 셀 = {x,y,w,h,tiles:[[...]]}."""
    oam = open(spec['oam'], 'rb').read()
    base = spec['tile_base']; dim = spec['sprite']; tpr = dim // 8
    seen = set(); cells = []
    for i in range(128):
        x = oam[i*4]; y = oam[i*4+1]; t = oam[i*4+2]; a = oam[i*4+3]
        hi = oam[512 + i//4]; bits = (hi >> ((i % 4) * 2)) & 3
        xh = bits & 1
        X = x | (xh << 8); X = X - 512 if X >= 256 else X
        if y >= 0xE0: continue
        tileno = t | ((a & 1) << 8)
        b = tileno - base
        tiles = [[b + sx + sy*16 for sx in range(tpr)] for sy in range(tpr)]
        key = (X, y, b)
        if key in seen: continue
        seen.add(key)
        cells.append({'x': X, 'y': y, 'w': dim, 'h': dim, 'tiles': tiles})
    return cells

def build_cells(spec):
    if spec['cells_from'] == 'oam':
        return cells_from_oam(spec)
    raise SystemExit(f"unknown cells_from: {spec['cells_from']}")

def pack_grid(cells, per_row=8):
    """screen 좌표 대신 촘촘한 격자로 셀 재배치(타깃 편집용). 셀 크기 동일 가정."""
    if not cells: return cells, (0, 0)
    w = cells[0]['w']; h = cells[0]['h']
    out = []
    for i, c in enumerate(cells):
        gx = (i % per_row) * w; gy = (i // per_row) * h
        out.append({**c, 'x': gx, 'y': gy})
    W = per_row * w; H = ((len(cells) + per_row - 1) // per_row) * h
    return out, (W, H)

# ── 팔레트 파일 ──────────────────────────────────────────────────────────
def write_palette(pal, outdir):
    pal16 = (pal + [[0,0,0]]*16)[:16]
    act = bytearray()
    for r, g, b in (pal16 + [[0,0,0]]*(256-16)):
        act += bytes([r, g, b])
    open(os.path.join(outdir, 'palette.act'), 'wb').write(bytes(act))
    with open(os.path.join(outdir, 'palette.pal'), 'w') as f:
        f.write('JASC-PAL\n0100\n16\n')
        for r, g, b in pal16: f.write(f'{r} {g} {b}\n')
    sw = Image.new('RGB', (16*16, 16))
    for i, (r, g, b) in enumerate(pal16):
        for yy in range(16):
            for xx in range(16): sw.putpixel((i*16+xx, yy), (r, g, b))
    sw.save(os.path.join(outdir, 'palette.png'))

# ── nearest 팔레트 인덱스 ────────────────────────────────────────────────
def nearest(pal, rgb):
    best = 1; bd = 1 << 30
    for i, (r, g, b) in enumerate(pal):
        if i == 0: continue          # 인덱스0=투명, 색매칭 제외
        d = (r-rgb[0])**2 + (g-rgb[1])**2 + (b-rgb[2])**2
        if d < bd: bd = d; best = i
    return best

# ── export ───────────────────────────────────────────────────────────────
def do_export(asset, mode):
    spec = ASSETS[asset]
    blob = open(os.path.join(GFX_DIR, spec['blob'] + '.bin'), 'rb').read()
    bpp = spec['bpp']; pal = spec['palette']
    cells = build_cells(spec)
    if mode == 'grid':
        cells, (W, H) = pack_grid(cells)
    else:
        W, H = spec['canvas']
    img = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    for c in cells:
        for sy, row in enumerate(c['tiles']):
            for sx, tn in enumerate(row):
                px = tile_to_px(blob, tn, bpp)
                for r in range(8):
                    for cc in range(8):
                        v = px[r][cc]
                        if v == 0: continue           # 투명
                        rr, gg, bb = pal[v] if v < len(pal) else (255, 0, 255)
                        img.putpixel((c['x']+sx*8+cc, c['y']+sy*8+r), (rr, gg, bb, 255))
    outdir = os.path.join(WORK, asset)
    os.makedirs(outdir, exist_ok=True)
    img.save(os.path.join(outdir, 'edit.png'))
    write_palette(pal, outdir)
    manifest = {'asset': asset, 'blob': spec['blob'], 'bpp': bpp, 'mode': mode,
                'canvas': [W, H], 'palette': pal, 'keep_tiles': spec.get('keep_tiles', []),
                'cells': cells}
    json.dump(manifest, open(os.path.join(outdir, 'manifest.json'), 'w'), ensure_ascii=False, indent=1)
    print(f'export {asset} [{mode}] -> {outdir}/edit.png  ({W}x{H}, {len(cells)} cells, bpp={bpp})')
    print(f'  팔레트: palette.act(.pal/.png)  매핑: manifest.json')
    print(f'  편집 후: python scripts/gfx_io.py import {asset}')

# ── import ───────────────────────────────────────────────────────────────
def do_import(asset, png=None):
    outdir = os.path.join(WORK, asset)
    manifest = json.load(open(os.path.join(outdir, 'manifest.json')))
    spec = ASSETS[asset]
    bpp = manifest['bpp']; pal = manifest['palette']
    keep = set(manifest.get('keep_tiles', []))
    black_tp = spec.get('black_transparent', False)
    blob = bytearray(open(os.path.join(GFX_DIR, spec['blob'] + '.bin'), 'rb').read())
    img = Image.open(png or os.path.join(outdir, 'edit.png')).convert('RGBA')
    W, H = img.size
    changed = set()
    for c in manifest['cells']:
        for sy, row in enumerate(c['tiles']):
            for sx, tn in enumerate(row):
                if tn in keep: continue                # © 등 유지 타일
                px = [[0]*8 for _ in range(8)]
                for r in range(8):
                    for cc in range(8):
                        X = c['x']+sx*8+cc; Y = c['y']+sy*8+r
                        if not (0 <= X < W and 0 <= Y < H): continue
                        pr, pg, pb, pa = img.getpixel((X, Y))
                        transp = pa < 128 or (black_tp and pr < 24 and pg < 24 and pb < 24)
                        px[r][cc] = 0 if transp else nearest(pal, (pr, pg, pb))
                px_to_tile(blob, tn, px, bpp)
                changed.add(tn)
    os.makedirs(EDIT_DIR, exist_ok=True)
    open(os.path.join(EDIT_DIR, spec['blob'] + '.bin'), 'wb').write(bytes(blob))
    print(f'import {asset} -> {EDIT_DIR}/{spec["blob"]}.bin  ({len(changed)} tiles updated)')
    print(f'  다음: python scripts/build_gfx.py --rom out/wgp2_kr.smc --out out/wgp2_kr.smc')

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    e = sub.add_parser('export'); e.add_argument('asset'); e.add_argument('--mode', default='screen', choices=['screen', 'grid'])
    i = sub.add_parser('import'); i.add_argument('asset'); i.add_argument('--png', default=None)
    a = ap.parse_args()
    if a.asset not in ASSETS: sys.exit(f'unknown asset: {a.asset} (등록: {list(ASSETS)})')
    if a.cmd == 'export': do_export(a.asset, a.mode)
    else: do_import(a.asset, a.png)

if __name__ == '__main__':
    main()
