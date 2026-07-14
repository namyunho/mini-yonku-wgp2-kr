#!/usr/bin/env python3
"""그래픽(LZSS 압축) 편집본 재삽입.
편집한 타일(.bin, 해제 상태)을 LZSS 재압축해 원래 $C7 슬롯에 in-place 기록.
- 디컴프 길이($05)는 타일 수 불변이라 그대로 → 포인터/길이 패치 불필요.
- 재압축 크기 ≤ 원본 압축 크기면 in-place 안전(다음 블롭 침범 없음).
  초과하면 에러(재배치+레지스터 패치 필요 — 드묾).
편집본은 tmp/gfx_edit/<name>.bin 에 두면 반영, 없으면 원본 유지.

사용: python scripts/build_gfx.py [--rom in.smc] [--out out.smc]
"""
import argparse, os, sys
sys.path.insert(0, 'scripts')
from lzss import decompress, compress, foff, SOURCES

ORIG_ROM = "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rom', default='out/wgp2_kr.smc', help='입력 ROM(기본: 대사 삽입본)')
    ap.add_argument('--out', default='out/wgp2_kr.smc')
    ap.add_argument('--edits', default='tmp/gfx_edit', help='편집 .bin 디렉토리')
    a = ap.parse_args()

    base = a.rom if os.path.exists(a.rom) else ORIG_ROM
    rom = bytearray(open(base, 'rb').read())
    orig = open(ORIG_ROM, 'rb').read()

    print(f"입력 ROM: {base}")
    n_edit = 0
    for name, bank, addr, olen, vram in SOURCES:
        off = foff(bank, addr)
        _, orig_comp = decompress(orig, off, olen)      # 원본 압축 크기
        edit_path = os.path.join(a.edits, f'{name}.bin')
        if os.path.exists(edit_path):
            tiles = open(edit_path, 'rb').read()
            if len(tiles) != olen:
                sys.exit(f"{name}: 편집본 크기 {len(tiles)} != 해제 크기 {olen} (타일 수 유지 필요)")
            comp = compress(tiles)
            tag = 'EDIT'
            n_edit += 1
        else:
            tiles, _ = decompress(orig, off, olen)        # 원본 그대로
            comp = compress(tiles)
            tag = 'orig'
        if len(comp) > orig_comp:
            sys.exit(f"{name}: 재압축 {len(comp)}B > 원본 {orig_comp}B → in-place 불가(재배치 필요)")
        rom[off:off + len(comp)] = comp                   # in-place 기록 (나머지는 원본 잔여, 미사용)
        # 역검증: ROM에서 재해제 == 편집 타일
        back, _ = decompress(rom, off, olen)
        ok = 'OK' if back == tiles else 'FAIL'
        print(f"  {name:10s} [{tag}] 압축 {len(comp)}/{orig_comp}B  역검증 {ok}")
        if ok == 'FAIL':
            sys.exit(f"{name}: 역검증 실패")

    os.makedirs('out', exist_ok=True)
    open(a.out, 'wb').write(rom)
    print(f"\n편집 {n_edit}개 반영 -> {a.out}")

if __name__ == '__main__':
    main()
