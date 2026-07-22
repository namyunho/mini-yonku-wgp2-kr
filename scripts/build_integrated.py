#!/usr/bin/env python3
"""전체 통합 ROM — Claude(build_all) + Codex(build_menu4_reclean) 병합.

- build_all.py       : System② SJIS·어드벤처·그래픽·타이틀·수동 세팅 X메뉴(build_setbox) → out/wgp2_kr.smc
- build_menu4_reclean: 월드맵 X메뉴·조작방법 튜토리얼·용어집·지도 소형폰트(자원 리다이렉트) → out/menu4_reclean.smc

두 산출물의 원본 대비 차분은 바이트 분리(충돌 0 확인). Codex 차분을 내 ROM에 얹고 SNES 체크섬 재계산.
⚠️ build_menu4_reclean.py는 Codex 작업물(진행중) — 갱신 시 이 스크립트로 통합 재생성.
출력: out/wgp2_kr_full.smc (비커밋).
"""
import subprocess, sys, zlib, hashlib

ORIG  = "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
MINE  = "out/wgp2_kr.smc"
CODEX = "out/menu4_reclean.smc"
OUT   = "out/wgp2_kr_full.smc"
CK    = set(range(0xFFDC, 0xFFE0))     # SNES 체크섬 4바이트(재계산 대상)

def run(cmd):
    print(f"\n$ {' '.join(cmd)}")
    if subprocess.run([sys.executable] + cmd).returncode != 0:
        sys.exit(f"실패: {cmd}")

def snes_checksum(buf):
    b = bytearray(buf)
    b[0xFFDC]=0xFF; b[0xFFDD]=0xFF; b[0xFFDE]=0x00; b[0xFFDF]=0x00
    ck = sum(b) & 0xFFFF
    return ck, ck ^ 0xFFFF

def main():
    run(["scripts/build_all.py"])
    run(["scripts/build_menu4_reclean.py"])
    orig  = open(ORIG, "rb").read()
    mine  = bytearray(open(MINE, "rb").read())
    codex = open(CODEX, "rb").read()
    assert len(orig) == len(mine) == len(codex), "ROM 크기 불일치"

    n = 0; conflicts = []
    for i in range(len(orig)):
        if i in CK: continue
        if codex[i] != orig[i]:
            if mine[i] == orig[i]:        # 내가 안 건드림 → Codex 적용
                mine[i] = codex[i]; n += 1
            elif mine[i] != codex[i]:      # 서로 다른 값으로 변경 → 충돌
                conflicts.append(i)
    if conflicts:
        sys.exit("병합 충돌 %dB: %s" % (len(conflicts),
                 ', '.join('$%02X:%04X' % (0xC0+(c>>16), c&0xFFFF) for c in conflicts[:12])))

    ck, comp = snes_checksum(mine)
    mine[0xFFDC]=comp&0xFF; mine[0xFFDD]=(comp>>8)&0xFF
    mine[0xFFDE]=ck&0xFF;   mine[0xFFDF]=(ck>>8)&0xFF
    open(OUT, "wb").write(mine)
    data = bytes(mine)
    print(f"\nCodex 차분 {n}B 적용 (충돌 0)")
    print(f"SNES 체크섬 {ck:04X} / 보수 {comp:04X}")
    print(f"=== 통합 ROM 완성: {OUT} ===")
    print(f"CRC32 {zlib.crc32(data)&0xffffffff:08X}  MD5 {hashlib.md5(data).hexdigest()}")

if __name__ == "__main__":
    main()
