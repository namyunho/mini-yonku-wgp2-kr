#!/usr/bin/env python3
"""수동 세팅 X메뉴(개러지) 한글화 — 공유 소형폰트 보존 방식 (docs/20).

수동 세팅에서 X로 여는 4항목(쉬운 세팅/파츠 해제/세팅 저장/세팅 불러오기)은 직접타일 박스
$C1:C6D4~C75F 이며, 소형 글꼴 $D9:0000(타일256 페이지)을 파츠/옵션/팀/인물명과 공유한다.

방식(다중 화면 리스크 0):
 1) $D9:0000 디컴프 → 수동 세팅 화면에서 실측된 **미사용 타일 14개**(0x80~0x95 계열)만 한글 글리프로
    덮어씀. 파츠/옵션이 쓰는 가나 타일은 그대로 → 보존.
 2) 수정 자원을 재압축해 자유 ROM $C7:B49B 에 배치.
 3) **수동 세팅 로더 $C1:1EBB 만** 새 자원으로 리다이렉트(PEA #$00D9;#$0000 → #$00C7;#$B49B).
    다른 개러지 화면은 원본 $D9:0000 을 그대로 읽으므로 무영향.
 4) 박스 4항목 오버레이 행 비우고 본문 행을 한글 타일 오프셋으로 재조립(테두리 E3/E4·행종단 00 보존).

실측 근거: scripts/lua/dump_setbox_vram.lua → tmp/trace/setbox_vram.bin.
⚠️ 실기 전수검증 필수(docs/20 §검증): X메뉴 4행 + 배경 파츠/옵션/팀/인물명 무손 + 화면전환 노이즈 부재.
"""
import json, sys, os
sys.path.insert(0, os.path.dirname(__file__))
import lzss

ROM = "out/wgp2_kr.smc"   # build_all 산출물에 layering (없으면 원본에서)
ROM_IN = "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
BIN  = "8pt_font/font-007242d37349daf3.bin"
GMAP = "8pt_font/font-007242d37349daf3_glyph_map.json"

def fo(bank, a): return ((bank & 0x3F) << 16) | (a & 0xFFFF)

D9_SRC   = (0xD9, 0x0000)       # 공유 소형폰트 원본
RELOC    = (0xC7, 0xD000)       # 수정 자원 재배치(자유 ROM). build_adv 성장(~B625)·Codex E000 사이 안전구간.
LOADER   = (0xC1, 0x1EBB)       # 수동 세팅 폰트 로더 (PEA #$00D9;PEA #$0000)

# 미사용 예약 슬롯(타일256 페이지 오프셋) — dump_setbox_vram 실측 free 집합에서 선택.
OFFS = [0x80,0x82,0x85,0x88,0x89,0x8B,0x8D,0x8E,0x90,0x91,0x92,0x93,0x94,0x95]
SYL  = "쉬운세팅파츠해제저장불러오기"   # 고유 음절(순서 = OFFS 대응)

def body(interior):
    assert len(interior) == 11, len(interior)
    return bytes([0xE3]) + bytes(interior) + bytes([0xE4, 0x00])
EMPTY_OVL = body([0xFF]*11)

def kr_glyph_2bpp(binf, gmap, ch):
    g = binf[gmap[ch]*8: gmap[ch]*8+8]
    t = bytearray(16)
    for r in range(8):
        s = r - 1                     # $D9 바닥정렬 1px down (build_sjis와 동일)
        if 0 <= s < 8: t[2*r] = g[s]
    return bytes(t)

def build():
    src = ROM if os.path.exists(ROM) else ROM_IN
    rom = bytearray(open(src, "rb").read())
    binf = open(BIN, "rb").read()
    gmap = json.load(open(GMAP, encoding="utf-8"))

    kmap = {ch: OFFS[i] for i, ch in enumerate(SYL)}
    assert len(kmap) == 14, f"고유 음절 {len(kmap)} != 14"
    assert len(set(OFFS)) == 14

    # 1) $D9:0000 디컴프 → 14 타일 한글로 덮어씀
    d = fo(*D9_SRC); hdr = rom[d] | (rom[d+1] << 8)
    dec, consumed = lzss.decompress(rom, d+2, hdr)
    dec = bytearray(dec)
    for ch, off in kmap.items():
        dec[off*16: off*16+16] = kr_glyph_2bpp(binf, gmap, ch)

    # 2) 재압축 → 자유 ROM $C7:B49B (2B 헤더 + 스트림)
    comp = lzss.compress(bytes(dec))
    comp = comp[0] if isinstance(comp, tuple) else comp
    newres = bytes([hdr & 0xFF, (hdr >> 8) & 0xFF]) + comp
    ro = fo(*RELOC)
    assert all(b == 0xFF for b in rom[ro: ro+len(newres)]), f"재배치 영역 비어있지 않음 $C7:{RELOC[1]:04X}"
    rt, _ = lzss.decompress(newres, 2, hdr)            # LZSS 왕복 검증
    assert bytes(rt) == bytes(dec), "재압축 왕복 실패"
    rom[ro: ro+len(newres)] = newres

    # 3) 로더 $C1:1EBB 리다이렉트: PEA #$00D9;PEA #$0000 → PEA #$00C7;PEA #$B49B
    lo = fo(*LOADER)
    assert rom[lo:lo+6] == bytes([0xF4,0xD9,0x00,0xF4,0x00,0x00]), \
        f"$C1:1EBB 원본 불일치 {rom[lo:lo+6].hex()}"
    rom[lo:lo+6] = bytes([0xF4, RELOC[0], 0x00, 0xF4, RELOC[1]&0xFF, (RELOC[1]>>8)&0xFF])

    # 4) 박스 4항목 재조립. 오버레이 비움 + 본문 한글. 원본 대조 후 패치.
    def m(*chars):
        cells = [0xFF]                              # 좌 마진
        for c in chars:
            cells.append(0xFF if c == ' ' else kmap[c])
        cells += [0xFF] * (11 - len(cells))
        return body(cells)
    ORIG = {
        0xC6F0: "E3FF396F436F456E4A67653FE400",
        0xC70C: "E3FF516F492D1A0D0DFFFFFFE400",
        0xC728: "E3FF456E4A67653F456F53FFE400",
        0xC744: "E3FF456E4A67653F626F4BFFE400",
    }
    rows = {
        0xC6E2: EMPTY_OVL, 0xC6F0: m('쉬','운',' ','세','팅'),
        0xC6FE: EMPTY_OVL, 0xC70C: m('파','츠',' ','해','제'),
        0xC71A: EMPTY_OVL, 0xC728: m('세','팅',' ','저','장'),
        0xC736: EMPTY_OVL, 0xC744: m('세','팅',' ','불','러','오','기'),
    }
    for addr, patch in rows.items():
        o = fo(0xC1, addr)
        if addr in ORIG:
            got = rom[o:o+14].hex().upper()
            assert got == ORIG[addr], f"$C1:{addr:04X} 원본 불일치 {got} != {ORIG[addr]}"
        assert len(patch) == 14
        rom[o:o+14] = patch

    open(ROM, "wb").write(rom)
    import zlib, hashlib
    print(f"수동 세팅 X메뉴 한글화 완료 → {ROM}")
    print(f"  $D9 수정자원 → $C7:{RELOC[1]:04X} ({len(newres)}B), 로더 $C1:1EBB 리다이렉트")
    print(f"  박스 4항목 재조립(테두리 보존). 예약슬롯 {[hex(x) for x in OFFS]}")
    print(f"  CRC32 {zlib.crc32(bytes(rom))&0xffffffff:08X}  MD5 {hashlib.md5(bytes(rom)).hexdigest()}")

if __name__ == "__main__":
    build()
