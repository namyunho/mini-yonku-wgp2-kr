#!/usr/bin/env python3
"""이지·수동 세팅(개러지) 소형폰트 한글화 (docs/18).

수동 세팅에서 X로 여는 4항목(쉬운 세팅/파츠 해제/세팅 저장/세팅 불러오기)은 직접타일 박스
$C1:C6D4~C75F 이며, 소형 글꼴 $D9:0000(타일256 페이지)을 파츠/옵션/팀/인물명과 공유한다.

방식(다중 화면 리스크 0):
 1) $D9:0000 디컴프 → 한글로 교체하는 원문 4행에서만 회수한 가나 타일 14개를
    한글 글리프로 덮어씀. 영문·숫자 대역 $70~$9F는 절대 재사용하지 않음.
 2) 수정 자원을 재압축해 자유 ROM $C7:D000 에 배치.
 3) 수동 세팅 `$C1:1EBB`와 이지 세팅 `$C1:303F` 로더를 새 자원으로
    리다이렉트(PEA #$00D9;#$0000 → #$00C7;#$D000). 두 화면은 같은 타일
    `$F4~$F8`을 쓰지만 서로 다른 로더가 원본 폰트를 다시 올린다.
 4) 박스 4항목 오버레이 행 비우고 본문 행을 한글 타일 오프셋으로 재조립(테두리 E3/E4·행종단 00 보존).

⚠️ 실기 전수검증 필수(docs/18): X메뉴 4행 + 배경 파츠/옵션/팀/인물명 무손 + 화면전환 노이즈 부재.
"""
import hashlib, json, sys, os
from pathlib import Path
sys.path.insert(0, os.path.dirname(__file__))
import lzss
from small_font_graphics import load_translation, pack_tight_2bpp_label

ROM = "out/wgp2_kr.smc"   # build_all 산출물에 layering (없으면 원본에서)
ROM_IN = "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
BIN  = "assets/fonts/small/font-007242d37349daf3.bin"
GMAP = "assets/fonts/small/font-007242d37349daf3_glyph_map.json"
EXTRA_TRANSLATIONS = "assets/translations/menu_extra_labels.json"

def fo(bank, a): return ((bank & 0x3F) << 16) | (a & 0xFFFF)

D9_SRC   = (0xD9, 0x0000)       # 공유 소형폰트 원본
RELOC    = (0xC7, 0xD000)       # 수정 자원 재배치(자유 ROM). build_adv 성장(~B625)·Codex E000 사이 안전구간.
FONT_SOURCE_LOADERS = {
    "수동 세팅": ((0xC1, 0x1EBB), 0x1400),
    "이지 세팅": ((0xC1, 0x303F), 0x1600),
}

# 원문 4행에서 회수한 가나 슬롯(타일256 페이지 오프셋).
# 이전 구현은 현재 프레임에서 보이지 않던 $80~$95를 '미사용'으로 오판해
# S=$82, V=$85, Z=$89 및 숫자/기호를 훼손했다. 이제 교체되는 라벨의
# 가나만 재사용하고 영문·숫자 대역 전체를 보호한다.
OFFS = [0x0D, 0x1A, 0x2D, 0x39, 0x43, 0x49, 0x4A,
        0x4B, 0x51, 0x53, 0x62, 0x65, 0x67, 0x6E]
SYL  = "쉬운세팅파츠해제저장불러오기"   # 고유 음절(순서 = OFFS 대응)
PROTECTED_ALPHANUMERIC_TILES = range(0x70, 0xA0)
NEXT_LEVEL_TILE_SPAN = (0xF4, 0xF9)
NEXT_LEVEL_ORIGINAL_SHA256 = "bb42ce52659d6e4545a0bbf7f6d8b4948b8481e267cf177363fcee8d70ebdc2b"

ORIGINAL_LABEL_ROWS = {
    0xC6F0: "E3FF396F436F456E4A67653FE400",
    0xC70C: "E3FF516F492D1A0D0DFFFFFFE400",
    0xC728: "E3FF456E4A67653F456F53FFE400",
    0xC744: "E3FF456E4A67653F626F4BFFE400",
}
RECLAIMED_LABEL_TILES = {
    value
    for raw_hex in ORIGINAL_LABEL_ROWS.values()
    for value in bytes.fromhex(raw_hex)[2:12]
    if value != 0xFF
}

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
    assert set(OFFS) <= RECLAIMED_LABEL_TILES, "원문 라벨 밖 타일 재사용 금지"
    assert set(OFFS).isdisjoint(PROTECTED_ALPHANUMERIC_TILES), \
        "영문·숫자 타일 $70~$9F 재사용 금지"

    # 1) $D9:0000 디컴프 → 14 타일 한글로 덮어씀
    d = fo(*D9_SRC); hdr = rom[d] | (rom[d+1] << 8)
    dec, consumed = lzss.decompress(rom, d+2, hdr)
    dec = bytearray(dec)
    original_dec = bytes(dec)
    for ch, off in kmap.items():
        dec[off*16: off*16+16] = kr_glyph_2bpp(binf, gmap, ch)

    # 세팅 화면의 `次のLVまで`는 일반 문자열이 아니라 $F4~$F8의 40px
    # 연속 비트맵이다. 원본 5타일을 검증한 뒤 8pt 글리프를 빈 열 없이
    # 패킹해 같은 위치·같은 타일 수로 교체한다.
    next_start = NEXT_LEVEL_TILE_SPAN[0] * 16
    next_end = NEXT_LEVEL_TILE_SPAN[1] * 16
    assert hashlib.sha256(dec[next_start:next_end]).hexdigest() == (
        NEXT_LEVEL_ORIGINAL_SHA256
    )
    next_level_text = load_translation(
        Path(EXTRA_TRANSLATIONS), "next_level"
    )
    dec[next_start:next_end] = pack_tight_2bpp_label(
        original_dec, binf, gmap, next_level_text, {"L": 0x7B, "V": 0x85}, 5
    )

    # 타일 단위 변경 표면을 고정한다. 회수 가나 14개와 `다음 LV`
    # 5개 외에는 원본 바이트가 하나도 바뀌면 안 된다.
    allowed_changes = set(OFFS) | set(range(*NEXT_LEVEL_TILE_SPAN))
    for tile in range(len(dec) // 16):
        if tile not in allowed_changes:
            begin = tile * 16
            assert dec[begin:begin + 16] == original_dec[begin:begin + 16], \
                f"허용 밖 타일 변경: ${tile:02X}"
    for tile in PROTECTED_ALPHANUMERIC_TILES:
        begin = tile * 16
        assert dec[begin:begin + 16] == original_dec[begin:begin + 16], \
            f"영문·숫자 타일 훼손: ${tile:02X}"

    # 2) 재압축 → 자유 ROM $C7:D000 (2B 헤더 + 스트림)
    comp = lzss.compress(bytes(dec))
    comp = comp[0] if isinstance(comp, tuple) else comp
    newres = bytes([hdr & 0xFF, (hdr >> 8) & 0xFF]) + comp
    ro = fo(*RELOC)
    assert ro + len(newres) <= fo(0xC7, 0xE000), "수동 세팅 자원이 $C7:E000을 침범"
    assert all(b == 0xFF for b in rom[ro: ro+len(newres)]), f"재배치 영역 비어있지 않음 $C7:{RELOC[1]:04X}"
    rt, _ = lzss.decompress(newres, 2, hdr)            # LZSS 왕복 검증
    assert bytes(rt) == bytes(dec), "재압축 왕복 실패"
    rom[ro: ro+len(newres)] = newres

    # 3) 이지·수동 세팅은 같은 $D9:0000 을 서로 다른 루틴에서
    # 해제한다. 두 소스 포인터를 모두 $C7:D000으로 돌리되, 각
    # 루틴의 기존 DMA 길이(0x1400/0x1600)는 유지한다.
    original_source = bytes([0xF4, 0xD9, 0x00, 0xF4, 0x00, 0x00])
    relocated_source = bytes([
        0xF4, RELOC[0], 0x00,
        0xF4, RELOC[1] & 0xFF, (RELOC[1] >> 8) & 0xFF,
    ])
    for label, (loader, dma_size) in FONT_SOURCE_LOADERS.items():
        lo = fo(*loader)
        got = bytes(rom[lo:lo + len(original_source)])
        assert got == original_source, \
            f"{label} ${loader[0]:02X}:{loader[1]:04X} 원본 불일치 {got.hex()}"
        assert rom[lo + 6:lo + 10] == bytes([0x22, 0x52, 0x0D, 0xC0]), \
            f"{label} LZSS 호출 시그니처 불일치"
        assert rom[lo + 0x35:lo + 0x38] == bytes([
            0xA9, dma_size & 0xFF, dma_size >> 8
        ]), f"{label} DMA 길이 불일치"
        assert dma_size >= next_end, f"{label} DMA가 `$F4-$F8`을 포함하지 않음"
        rom[lo:lo + len(relocated_source)] = relocated_source

    # 4) 박스 4항목 재조립. 오버레이 비움 + 본문 한글. 원본 대조 후 패치.
    def m(*chars):
        cells = [0xFF]                              # 좌 마진
        for c in chars:
            cells.append(0xFF if c == ' ' else kmap[c])
        cells += [0xFF] * (11 - len(cells))
        return body(cells)
    rows = {
        0xC6E2: EMPTY_OVL, 0xC6F0: m('쉬','운',' ','세','팅'),
        0xC6FE: EMPTY_OVL, 0xC70C: m('파','츠',' ','해','제'),
        0xC71A: EMPTY_OVL, 0xC728: m('세','팅',' ','저','장'),
        0xC736: EMPTY_OVL, 0xC744: m('세','팅',' ','불','러','오','기'),
    }
    for addr, patch in rows.items():
        o = fo(0xC1, addr)
        if addr in ORIGINAL_LABEL_ROWS:
            got = rom[o:o+14].hex().upper()
            expected = ORIGINAL_LABEL_ROWS[addr]
            assert got == expected, f"$C1:{addr:04X} 원본 불일치 {got} != {expected}"
        assert len(patch) == 14
        rom[o:o+14] = patch

    open(ROM, "wb").write(rom)
    import zlib
    print(f"이지·수동 세팅 소형폰트 한글화 완료 → {ROM}")
    loaders = ", ".join(
        f"${bank:02X}:{addr:04X}" for (bank, addr), _ in FONT_SOURCE_LOADERS.values()
    )
    print(f"  $D9 수정자원 → $C7:{RELOC[1]:04X} ({len(newres)}B), 로더 {loaders} 리다이렉트")
    print(f"  박스 4항목 재조립(테두리 보존). 회수 가나 슬롯 {[hex(x) for x in OFFS]}")
    print(f"  CRC32 {zlib.crc32(bytes(rom))&0xffffffff:08X}  MD5 {hashlib.md5(bytes(rom)).hexdigest()}")

if __name__ == "__main__":
    build()
