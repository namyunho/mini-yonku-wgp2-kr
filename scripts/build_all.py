#!/usr/bin/env python3
"""전체 한글패치 통합 빌드 — 모든 작업을 반영한 단일 ROM 생성.

순서:
 1. build_patch.py       정적 대사 681 + 스테이지 제목 10개 한글
                         + **어드벤처 음절도 같은 글리프 할당에 포함**
                         (--adv-json → 폰트 시트 $CA 전역 공유, out/glyph_map.json 산출)
 2. build_credit_kr.py   크레딧 화면 스프라이트 편집본(tmp/gfx_edit/vram_7000.bin)
 3. build_gfx.py         크레딧 화면 그래픽 LZSS 재삽입(out in-place)
 4. build_title_logo.py  타이틀 로고(BG1 chr+타일맵 재빌드·재배치)
 5. build_title_credit.py 타이틀 하단 크레딧줄(BG3 chr repaint+타일맵 마스킹·재배치)
 6. build_adv.py         어드벤처 씬 한글 재삽입(자유공간 재배치+씬표 패치). 그래픽 뒤에
                         둬서 어드벤처가 마지막에 기록됨(그래픽 영역과 비겹침이나 안전 우선).
 7. build_menu.py        SJIS 시작메뉴(→out/menu_test.smc) → diff를 out/wgp2_kr.smc에 통합
 8. BPS 배포 패치 생성(flips)

산출: out/wgp2_kr.smc (통합 ROM), out/wgp2_kr.bps (배포용 차분)
※ ROM은 비커밋. 이 스크립트+에셋으로 원본에서 재생성.
"""
import subprocess, sys, os, zlib, hashlib, shutil

ORIG = "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
OUT = "out/wgp2_kr.smc"
MENU = "out/menu_test.smc"
BPS = "out/wgp2_kr.bps"
ADV_JSON = "assets/translations/adventure_kr.json"
# flips: PATH에 설치돼 있으면 자동 인식, 없으면 로컬 경로 폴백(맥/윈도우 공용).
# BPS 생성(마지막 단계)에만 쓰이며 os.path.exists 가드로 없으면 건너뜀.
FLIPS = shutil.which("flips") or os.path.expanduser("~/tools/flips/flips")

def run(cmd):
    print(f"\n$ {' '.join(cmd)}")
    r = subprocess.run([sys.executable] + cmd if cmd[0].endswith('.py') else cmd)
    if r.returncode != 0:
        sys.exit(f"실패: {cmd}")

def main():
    run(["scripts/build_patch.py", "--adv-json", ADV_JSON])            # 1 (+어드벤처 음절 할당)
    run(["scripts/build_credit_kr.py"])                                # 2
    run(["scripts/build_gfx.py", "--rom", OUT, "--out", OUT])          # 3
    run(["scripts/build_title_logo.py", "--write"])                    # 4
    run(["scripts/build_title_credit.py"])                             # 5
    run(["scripts/build_adv.py"])                                      # 6 어드벤처 재삽입(out+base→out)
    run(["scripts/build_sjis.py"])                                     # 7a SJIS UI 한글화 → menu_test.smc

    # 6b: SJIS 패치(원본 대비 변경 바이트)를 통합 ROM에 적용.
    #     충돌 가드: build_sjis가 바꾼 바이트를 이전 단계(어드벤처·그래픽)가 이미 건드렸으면 중단.
    orig = open(ORIG, 'rb').read()
    menu = open(MENU, 'rb').read()
    rom = bytearray(open(OUT, 'rb').read())
    n = 0; conflicts = []
    for i in range(len(orig)):
        if orig[i] != menu[i]:
            if rom[i] != orig[i]:
                conflicts.append(i)
            rom[i] = menu[i]; n += 1
    if conflicts:
        sys.exit(f"SJIS 영역 충돌 {len(conflicts)}B (이전 단계와 겹침): "
                 f"{', '.join(f'0x{c:06X}' for c in conflicts[:8])}")
    open(OUT, 'wb').write(rom)
    print(f"\nSJIS 패치 {n}B 통합 (충돌 0)")

    # 7: BPS
    if os.path.exists(FLIPS):
        subprocess.run([FLIPS, "--create", ORIG, OUT, BPS])
    data = bytes(rom)
    print(f"\n=== 통합 ROM 완성: {OUT} ===")
    print(f"크기 {len(data)}B  CRC32 {zlib.crc32(data) & 0xffffffff:08X}  MD5 {hashlib.md5(data).hexdigest()}")

if __name__ == '__main__':
    main()
