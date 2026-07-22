#!/usr/bin/env python3
"""전체 한글패치 통합 빌드 — 모든 작업을 반영한 단일 ROM 생성.

순서:
 1. build_patch.py       정적 대사 681 + 스테이지 제목 10개 한글
                         + **어드벤처·월드맵 음절도 같은 글리프 할당에 포함**
                         (--adv-json/--worldmap-json → $CA 전역 공유, out/glyph_map.json 산출)
 2. build_credit_kr.py   크레딧 화면 스프라이트 편집본(tmp/gfx_edit/vram_7000.bin)
 3. build_gfx.py         크레딧 화면 그래픽 LZSS 재삽입(out in-place)
 4. build_title_logo.py  타이틀 로고(BG1 chr+타일맵 재빌드·재배치)
 5. build_title_credit.py 타이틀 하단 크레딧줄(BG3 chr repaint+타일맵 마스킹·재배치)
 6. build_adv.py         어드벤처 씬 한글 재삽입(자유공간 재배치+씬표 패치). 그래픽 뒤에
                         둬서 어드벤처가 마지막에 기록됨(그래픽 영역과 비겹침이나 안전 우선).
 7. build_adv_parts.py   파츠 획득 동적 이름 27조각을 원래 $C0 영역에 재패킹
 8. build_field.py       필드/NPC 1,411런 위치보존 재삽입(원본 2MB 내부 재패킹)
 9. build_worldmap.py    월드맵 퀴즈 70문항(350문자열) $C6 in-bank 재배치+포인터 패치
10. build_sjis.py        SJIS UI(→out/menu_test.smc) → 원본 대비 차분 통합
11. build_menu4_reclean.py 월드맵 X메뉴·튜토리얼·용어집·지도 → 원본 대비 차분 통합
12. build_setbox.py      수동 세팅 X메뉴를 현재 통합 ROM 위에 적용
13. verify_field_build.py 최종 병합 뒤 필드 원본·목적지·포인터 무결성 재검증
14. 헤더 체크섬 갱신 + BPS 배포 패치 생성(flips)

산출: out/wgp2_kr.smc (통합 ROM), out/wgp2_kr.bps (배포용 차분)
※ ROM은 비커밋. 이 스크립트+에셋으로 원본에서 재생성.
"""
import subprocess, sys, os, zlib, hashlib, shutil
from pathlib import Path

ORIG = "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
OUT = "out/wgp2_kr.smc"
MENU = "out/menu_test.smc"
MENU4 = "out/menu4_reclean.smc"
BPS = "out/wgp2_kr.bps"
ADV_JSON = "assets/translations/adventure_kr.json"
WORLDMAP_JSON = "assets/translations/worldmap_text.json"
FIELD_JSON = "assets/translations/field_kr.json"
ADV_PARTS_JSON = "assets/translations/adv_parts_fragments.json"
# flips: PATH에 설치돼 있으면 자동 인식, 없으면 로컬 경로 폴백(맥/윈도우 공용).
# BPS 생성(마지막 단계)에만 쓰이며 os.path.exists 가드로 없으면 건너뜀.
FLIPS = shutil.which("flips") or os.path.expanduser("~/tools/flips/flips")
SNAPSHOT_DIR = os.environ.get("WGP2_SNAPSHOT_DIR")

def run(cmd):
    print(f"\n$ {' '.join(cmd)}")
    r = subprocess.run([sys.executable] + cmd if cmd[0].endswith('.py') else cmd)
    if r.returncode != 0:
        sys.exit(f"실패: {cmd}")

def snapshot(name, data=None):
    if not SNAPSHOT_DIR:
        return
    target = Path(SNAPSHOT_DIR)
    target.mkdir(parents=True, exist_ok=True)
    target_file = target / f"{name}.smc"
    if data is None:
        shutil.copyfile(OUT, target_file)
    else:
        target_file.write_bytes(data)

def main():
    run(["scripts/build_patch.py", "--adv-json", ADV_JSON,
         "--worldmap-json", WORLDMAP_JSON, "--field-json", FIELD_JSON,
         "--adv-parts-json", ADV_PARTS_JSON])                           # 1 (공유 $CA 글리프 할당)
    snapshot("01-static")
    run(["scripts/build_credit_kr.py"])                                # 2
    run(["scripts/build_gfx.py", "--rom", OUT, "--out", OUT])          # 3
    run(["scripts/build_title_logo.py", "--write"])                    # 4
    run(["scripts/build_title_credit.py"])                             # 5
    snapshot("05-graphics")
    run(["scripts/build_adv.py"])                                      # 6 어드벤처 재삽입(out+base→out)
    snapshot("06-adventure")
    run(["scripts/build_adv_parts.py"])                                # 7 파츠 획득 동적 이름 → OUT
    snapshot("07-adventure-parts")
    run(["scripts/build_field.py"])                                    # 8 필드/NPC → out(2MB 내부 재패킹)
    snapshot("08-field")
    run(["scripts/build_worldmap.py"])                                 # 9 월드맵 퀴즈 → out
    snapshot("09-worldmap")
    run(["scripts/build_sjis.py"])                                     # 10 SJIS UI 한글화 → menu_test.smc
    run(["scripts/build_menu4_reclean.py"])                            # 11 소형 타일 메뉴 → menu4_reclean.smc

    # 독립 빌더 두 개의 원본 대비 변경 바이트를 통합 ROM에 적용한다.
    # 체크섬은 마지막에 다시 계산하므로 각 독립 ROM의 체크섬 4B는 병합하지 않는다.
    orig = open(ORIG, 'rb').read()
    menu = open(MENU, 'rb').read()
    menu4 = open(MENU4, 'rb').read()
    rom = bytearray(open(OUT, 'rb').read())
    checksum_bytes = set(range(0xFFDC, 0xFFE0))

    def merge_diff(label, patch):
        n = 0; conflicts = []
        if len(patch) != len(orig):
            sys.exit(f"{label} ROM 크기 불일치: {len(patch)}")
        for i in range(len(orig)):
            if i in checksum_bytes or orig[i] == patch[i]:
                continue
            if rom[i] != orig[i] and rom[i] != patch[i]:
                conflicts.append(i)
                continue
            rom[i] = patch[i]; n += 1
        if conflicts:
            sys.exit(f"{label} 영역 충돌 {len(conflicts)}B: "
                     f"{', '.join(f'0x{c:06X}' for c in conflicts[:8])}")
        print(f"{label} 패치 {n}B 통합 (충돌 0)")

    merge_diff("SJIS", menu)
    snapshot("10-sjis", rom)
    merge_diff("소형 타일 메뉴", menu4)
    open(OUT, 'wb').write(rom)
    snapshot("11-menu4")

    run(["scripts/build_setbox.py"])                                   # 12 수동 세팅 X메뉴 → OUT
    snapshot("12-setbox")
    run(["scripts/verify_field_build.py"])                             # 13 후속 덮어쓰기·원본 변경 방지
    rom = bytearray(open(OUT, 'rb').read())

    # 원본 2MB HiROM 크기·헤더는 유지하고 체크섬만 갱신한다.
    if len(rom) != len(orig) or rom[0xFFD7] != orig[0xFFD7]:
        sys.exit("원본 ROM 크기/크기 헤더 보존 실패")
    rom[0xFFDC:0xFFE0] = b'\x00\x00\x00\x00'
    checksum = (sum(rom) + 0x1FE) & 0xFFFF
    complement = checksum ^ 0xFFFF
    rom[0xFFDC:0xFFDE] = complement.to_bytes(2, 'little')
    rom[0xFFDE:0xFFE0] = checksum.to_bytes(2, 'little')
    if (sum(rom) & 0xFFFF) != checksum:
        sys.exit("SNES 체크섬 자기검증 실패")
    open(OUT, 'wb').write(rom)
    snapshot("14-final")

    # 14: BPS
    if os.path.exists(FLIPS):
        subprocess.run([FLIPS, "--create", ORIG, OUT, BPS])
    data = bytes(rom)
    print(f"\n=== 통합 ROM 완성: {OUT} ===")
    print(f"크기 {len(data)}B  CRC32 {zlib.crc32(data) & 0xffffffff:08X}  MD5 {hashlib.md5(data).hexdigest()}")

if __name__ == '__main__':
    main()
