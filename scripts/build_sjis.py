#!/usr/bin/env python3
"""System ② 비압축 SJIS UI 한글화 — 통합 빌드 (build_menu.py 후속·상위호환).

docs/12 설계. build_menu.py의 검증 메커니즘을 12타일 → 전체 코퍼스로 확장:
 - 렌더러 $C1:965E(단일 퍼널) 훅 $C1:9696→$C1:9843: 마커 상위바이트 0xFE → 확장타일(VRAM 800+low).
 - 변환표 확장: SJIS 미정의 리드 0x85 전용. 행-오프셋 $C1:D1C3+0x0A → 새 189슬롯 블록 $C1:D5CB.
 - 글로벌 한글 타일뱅크(2bpp) → 자유 ROM $C1:9A00, 폰트로더 훅 $C0:6F93가 VRAM 800에 DMA.
 - 문자열 재작성: 시작/파일 메뉴는 옵션-컬럼 정렬(활성/비활성 팔레트), 나머지는 in-place(sjis_ui.json).

⚠️ 폰트로더 훅은 저장메뉴 로더 1곳만 → 개러지 등 커버리지는 인게임 QA로 확정(docs/12 §4).
"""
import json, sys, os

ROM_IN  = "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
ROM_OUT = "out/menu_test.smc"     # build_all.py가 이 diff를 통합 ROM에 병합
BIN     = "assets/fonts/small/font-007242d37349daf3.bin"
GMAP    = "assets/fonts/small/font-007242d37349daf3_glyph_map.json"
CORPUS  = "assets/translations/sjis_ui.json"

# --- 자유 ROM/VRAM 배치 (docs/12) ---
HOOK_RENDER = 0x9843     # $C1:9843 렌더러 훅
HOOK_LOADER = 0x9940     # $C1:9940 로더 DMA 인젝트
KBANK       = 0x9A00     # $C1:9A00 한글 타일뱅크(2bpp)
TBL         = 0x01D1C3   # 변환표 파일오프셋
TBL_BLOCK   = 0xD679     # $C1:D679 새 189슬롯 블록 (rowbase = D679-D1C3 = 0x04B6).
                         # ⚠️ build_adv가 $C1:D5CB를 씀 → 그 뒤 자유런. build_all 충돌가드가 회귀 감시.
KLEAD       = 0x85       # 한글 전용 SJIS 리드바이트(미정의)
KLEAD2      = 0x86       # 2차 한글 리드바이트 — 0x85 블록(189) 초과분. 게임은 0x86을 리드로
                         #  안 씀(실측: 발견 0x86은 전부 트레일/포인터데이터) → 리다이렉트 안전.
SLOT1       = 189        # 리드 0x85 슬롯 수(SJIS trail 0x40+i, i=0..188)
VRAM_CAP    = 224        # VRAM 한글 타일 여유(800..1023) = 총 음절 하드 상한
TBL_BLOCK2  = 0xD7F3     # $C1:D7F3 2차 변환블록(block1 D679+189*2=D7F3 직후, 자유런). 0x86 → block2.
VRAM_KOR_TILE = 800      # 한글 VRAM 시작타일
MARKER      = 0xFE
KOR_ADD     = 0x0220     # 렌더러 ext: VRAM타일 = low + 0x220 + base(0x2100) = 800+low

def fo_c1(a): return 0x010000 | (a & 0xFFFF)
def fo_c0(a): return 0x000000 | (a & 0xFFFF)
def fo(bank, a): return ((bank & 0x3F) << 16) | (a & 0xFFFF)

# 시작/파일 메뉴 (정렬 필요 → 하드코딩). (bank, addr, 원본SJIS, [옵션 한글…])
MENUS = [
    (0xC0, 0x71B9, "はじめから　つづきから　うつす　　　けす", ["처음부터", "이어하기", "복사", "삭제"]),
    (0xC0, 0x71E2, "ほぞん　　　もどる　　　うつす　　　けす",   ["저장", "뒤로", "복사", "삭제"]),
]

GLYPH_SHIFT_DOWN = 1   # 게임 $D9 폰트는 바닥정렬(행7). 8pt 한글(행0~6)을 1px 내려 바닥정렬.
                       #  (값1=무손실 바닥정렬. 2는 최하단 1px 획이 잘려 사용자 실측상 과함)

def kr_glyph_2bpp(binf, gmap, ch):
    if ch not in gmap:
        raise KeyError(f"폰트에 음절 없음: {ch!r}")
    g = binf[gmap[ch]*8: gmap[ch]*8+8]
    t = bytearray(16)
    for r in range(8):
        src = r - GLYPH_SHIFT_DOWN
        if 0 <= src < 8:
            t[2*r] = g[src]   # plane0 = 잉크 (아래로 shift)
    return bytes(t)

def parse_menu_columns(orig):
    """원본 SJIS 문자열을 (토큰, 시작컬럼) 리스트로. 전각공백 기준 분리, 컬럼=전각셀 인덱스."""
    toks = []; col = 0; cur = ""; start = 0
    for ch in orig:
        if ch == "　":
            if cur:
                toks.append((cur, start)); cur = ""
            col += 1
        else:
            if not cur:
                start = col
            cur += ch; col += 1
    if cur:
        toks.append((cur, start))
    return toks, col

def sjis_bytes(ch, kmap):
    """한글 음절 → (0x85, 0x40+i); 그 외(공백/라틴/부호)는 원본 SJIS 유지.
    ⚠️ 렌더러 $C1:965E는 항상 2바이트 페어로 읽으므로 모든 문자는 반드시 2바이트여야 함
    (반각 ASCII 공백 0x20은 디싱크 유발 → 전각공백 　만 허용)."""
    if '가' <= ch <= '힣':
        i = kmap[ch]
        if i < SLOT1:
            return bytes([KLEAD, 0x40 + i])          # 리드 0x85, 슬롯 0..188
        return bytes([KLEAD2, 0x40 + (i - SLOT1)])   # 리드 0x86, 슬롯 189..
    b = ch.encode('cp932')
    if len(b) != 2:
        raise SystemExit(f"2바이트 아닌 문자 금지(반각?): {ch!r} → {b.hex()}. 전각으로 교체(공백=　, ！？〜).")
    return b

def build_menu_string(orig, kr_tokens, kmap):
    """옵션별 한글을 원본 옵션의 시작컬럼에 정렬. 총 전각셀 수 = 원본과 동일(패딩=전각공백)."""
    toks, total_cols = parse_menu_columns(orig)
    assert len(toks) == len(kr_tokens), f"옵션 수 불일치 {len(toks)}!={len(kr_tokens)}"
    FW_SP = "　".encode('cp932')
    out = bytearray(); cur_col = 0
    for (jp_tok, start), kr in zip(toks, kr_tokens):
        assert start >= cur_col, "컬럼 역행"
        out += FW_SP * (start - cur_col)
        for ch in kr:
            out += sjis_bytes(ch, kmap)
        cur_col = start + len(kr)
    out += FW_SP * (total_cols - cur_col)
    return bytes(out)

def build():
    rom = bytearray(open(ROM_IN, "rb").read())
    binf = open(BIN, "rb").read()
    gmap = json.load(open(GMAP, encoding="utf-8"))
    corpus = json.load(open(CORPUS, encoding="utf-8"))

    # 1) 전체 코퍼스 고유 음절 수집 (안정 순서: 메뉴 → JSON)
    syls = []
    def add_syls(s):
        for ch in s:
            if '가' <= ch <= '힣' and ch not in syls:
                syls.append(ch)
    for _, _, _, kr_tokens in MENUS:
        for t in kr_tokens: add_syls(t)
    strings = []
    for key, items in corpus.items():
        if not isinstance(items, list): continue
        for it in items:
            add_syls(it["kr"])
            strings.append((int(it["bank"],16), int(it["addr"],16), it["jp"], it["kr"], it.get("mode","inplace")))
    # 리드 0x85 블록 189 + 리드 0x86 블록 → 총 상한 = VRAM 여유(224).
    assert len(syls) <= VRAM_CAP, f"음절 {len(syls)} > VRAM 여유 {VRAM_CAP}"
    assert len(syls) - SLOT1 <= (VRAM_CAP - SLOT1), "block2 초과"
    kmap = {ch: i for i, ch in enumerate(syls)}

    # 2) 한글 타일뱅크 → $C1:9A00
    kdata = bytearray()
    for ch in syls:
        kdata += kr_glyph_2bpp(binf, gmap, ch)
    end = fo_c1(KBANK) + len(kdata)
    assert all(b == 0xFF for b in rom[fo_c1(KBANK):end]), f"타일뱅크 영역 비어있지 않음 $C1:{KBANK:04X}"
    rom[fo_c1(KBANK):end] = kdata

    # 3) 렌더러 훅 $C1:9843 (build_menu 검증본과 동일)
    hook = bytes([
        0xA5,0x06, 0xC9,MARKER,0x00, 0xF0,0x1C,
        0xA5,0x05, 0x29,0xFF,0x00, 0x18, 0x65,0x07, 0x9F,0x00,0x00,0x7E,
        0xA5,0x06, 0x29,0xFF,0x00, 0xF0,0x19, 0x18, 0x65,0x07, 0x9F,0xC0,0xFF,0x7D, 0x80,0x10,
        0xA5,0x05, 0x29,0xFF,0x00, 0x18, 0x69,KOR_ADD&0xFF,(KOR_ADD>>8)&0xFF, 0x18, 0x65,0x07, 0x9F,0x00,0x00,0x7E,
        0x4C,0xAE,0x96,
    ])
    rom[fo_c1(HOOK_RENDER):fo_c1(HOOK_RENDER)+len(hook)] = hook
    r9696 = fo_c1(0x9696)
    assert rom[r9696:r9696+3] == bytes([0x29,0xFF,0x00]), rom[r9696:r9696+3].hex()
    rom[r9696:r9696+3] = bytes([0x4C,0x43,0x98])   # JMP $9843

    # 4) 로더 DMA 인젝트 $C1:9940
    vram_word = VRAM_KOR_TILE * 8
    src = KBANK; size = len(kdata)
    inject = bytes([
        0xA9,vram_word&0xFF,(vram_word>>8)&0xFF, 0x8F,0x16,0x21,0x00,
        0xE2,0x20, 0xA9,0x80, 0x8F,0x15,0x21,0x00,
        0xA9,0xC1, 0x8F,0x04,0x43,0x00,
        0xC2,0x20, 0xA9,0x01,0x18, 0x8F,0x00,0x43,0x00,
        0xA9,src&0xFF,(src>>8)&0xFF, 0x8F,0x02,0x43,0x00,
        0xA9,size&0xFF,(size>>8)&0xFF, 0x8F,0x05,0x43,0x00,
        0xE2,0x20, 0xA9,0x01, 0x8F,0x0B,0x42,0x00,
        0xC2,0x20, 0xA9,0x7F,0x00, 0x85,0x07,
        0x6B,
    ])
    rom[fo_c1(HOOK_LOADER):fo_c1(HOOK_LOADER)+len(inject)] = inject
    L = fo_c0(0x6F93)
    assert rom[L:L+5] == bytes([0xA9,0x7F,0x00,0x85,0x07]), rom[L:L+5].hex()
    rom[L:L+5] = bytes([0x22,0x40,0x99,0xC1, 0xEA])   # JSL $C19940 ; NOP

    # 4b) 개러지·선택화면 폰트로더 훅 (트레이스 확정: 폰트를 타일256에 올리는 로더 2곳).
    #  이 로더들은 $C0:6F43가 아니라 자체 코드라 한글이 안 실림 → 화면전환 시 한글 800 파괴 후 미복원.
    #  훅: 폰트 DMA 트리거 `STA $420B`(8F 0B 42 00)를 JSL $C19980로 대체 → 루틴이 폰트DMA를
    #  실행하고 이어서 한글DMA(VRAM 800)까지 발사 후 RTL. tile256 로더만 대상이라 그래픽 화면 무손상.
    KHOOK2 = 0x9980
    khook2 = bytes([
        0x8F,0x0B,0x42,0x00,                      # STA $420B (원래 폰트 DMA 실행, A=01 8bit)
        0x48,                                     # PHA
        0xC2,0x20,                                # REP #$20
        0xA9,vram_word&0xFF,(vram_word>>8)&0xFF, 0x8F,0x16,0x21,0x00,  # LDA #vram; STA $2116
        0xE2,0x20, 0xA9,0x80, 0x8F,0x15,0x21,0x00,
        0xA9,0xC1, 0x8F,0x04,0x43,0x00,
        0xC2,0x20, 0xA9,0x01,0x18, 0x8F,0x00,0x43,0x00,
        0xA9,src&0xFF,(src>>8)&0xFF, 0x8F,0x02,0x43,0x00,
        0xA9,size&0xFF,(size>>8)&0xFF, 0x8F,0x05,0x43,0x00,
        0xE2,0x20, 0xA9,0x01, 0x8F,0x0B,0x42,0x00,  # 한글 DMA 트리거
        0x68,                                     # PLA
        0x6B,                                     # RTL
    ])
    assert KHOOK2 + len(khook2) <= KBANK, "khook2가 타일뱅크 침범"
    rom[fo_c1(KHOOK2):fo_c1(KHOOK2)+len(khook2)] = khook2
    FONT_LOADERS = [0x1EFB, 0x307F]   # STA $420B 폰트트리거(타일256), 트레이스 확정
    jsl = bytes([0x22, KHOOK2&0xFF, (KHOOK2>>8)&0xFF, 0xC1])
    for t in FONT_LOADERS:
        o = fo_c1(t)
        assert rom[o:o+4] == bytes([0x8F,0x0B,0x42,0x00]), f"트리거 ${t:04X} 불일치 {rom[o:o+4].hex()}"
        rom[o:o+4] = jsl

    # 5) 변환표: 행-오프셋[0x85] → 새 블록, 블록[i] = 0xFE00|i
    roff = TBL + (KLEAD & 0x7F) * 2
    rb = (TBL_BLOCK - 0xD1C3) & 0xFFFF
    rom[roff] = rb & 0xFF; rom[roff+1] = (rb >> 8) & 0xFF
    blk = fo_c1(TBL_BLOCK)
    assert all(b == 0xFF for b in rom[blk:blk+189*2]), "표 블록 영역 비어있지 않음"
    for i in range(189):
        v = ((MARKER << 8) | i) if i < len(syls) else 0x0000
        rom[blk+i*2] = v & 0xFF; rom[blk+i*2+1] = (v >> 8) & 0xFF

    # 5b) 리드 0x86 → 2차 블록(슬롯 189..). block2[j] = 0xFE00|(189+j) → 렌더러가 VRAM 800+(189+j).
    n2 = max(0, len(syls) - SLOT1)
    if n2 > 0:
        roff2 = TBL + (KLEAD2 & 0x7F) * 2
        rb2 = (TBL_BLOCK2 - 0xD1C3) & 0xFFFF
        rom[roff2] = rb2 & 0xFF; rom[roff2+1] = (rb2 >> 8) & 0xFF
        blk2 = fo_c1(TBL_BLOCK2)
        assert all(b == 0xFF for b in rom[blk2:blk2 + n2*2]), "표 블록2 영역 비어있지 않음"
        for j in range(n2):
            v = (MARKER << 8) | (SLOT1 + j)
            rom[blk2+j*2] = v & 0xFF; rom[blk2+j*2+1] = (v >> 8) & 0xFF

    # 6) 문자열 재작성 (모든 초과를 모아 한 번에 보고)
    report = []; overflows = []
    def slot_of(bank, addr):
        o = fo(bank, addr); e = rom.index(0, o); return o, e - o + 1
    pend = []  # (o, bytes, tag, mode, slot)
    for bank, addr, orig, kr_tokens in MENUS:
        newstr = build_menu_string(orig, kr_tokens, kmap) + b"\x00"
        o, slot = slot_of(bank, addr); tag = f"${bank:02X}:{addr:04X}"
        pend.append((o, newstr, tag, "menu", slot))
        if len(newstr) > slot: overflows.append((tag, "menu", len(newstr), slot, "".join(kr_tokens)))
    for bank, addr, jp, kr, mode in strings:
        newb = bytearray()
        for ch in kr: newb += sjis_bytes(ch, kmap)
        newb += b"\x00"
        o, slot = slot_of(bank, addr); tag = f"${bank:02X}:{addr:04X}"
        pend.append((o, bytes(newb), tag, mode, slot))
        if len(newb) > slot: overflows.append((tag, mode, len(newb), slot, kr))
    if overflows:
        print("=== 슬롯 초과 (in-place 불가) ===")
        for tag, mode, n, slot, kr in overflows:
            print(f"  {tag} {n}>{slot}B  {kr!r}")
        raise SystemExit(f"{len(overflows)}개 초과 → kr 축약 또는 mode=reloc 필요")
    for o, b, tag, mode, slot in pend:
        rom[o:o+len(b)] = b
        report.append((tag, mode, len(b), slot))

    # 7) 라운드트립 자체검증
    def decode_kr(bank, addr):
        o = fo(bank, addr); out = ""
        while rom[o] != 0:
            if rom[o] == KLEAD:
                out += syls[rom[o+1]-0x40]; o += 2
            elif rom[o] == KLEAD2:
                out += syls[SLOT1 + rom[o+1]-0x40]; o += 2
            else:
                out += rom[o:o+2].decode('cp932'); o += 2
        return out
    for bank, addr, jp, kr, mode in strings:
        got = decode_kr(bank, addr)
        assert got == kr, f"라운드트립 실패 ${bank:02X}:{addr:04X}: {got!r} != {kr!r}"

    os.makedirs("out", exist_ok=True)
    open(ROM_OUT, "wb").write(rom)
    print(f"완료: {ROM_OUT}")
    print(f"  고유 음절 {len(syls)}개 → VRAM 타일 {VRAM_KOR_TILE}..{VRAM_KOR_TILE+len(syls)-1}, 뱅크 {len(kdata)}B @ $C1:{KBANK:04X}")
    n1 = min(len(syls), SLOT1); n2 = max(0, len(syls) - SLOT1)
    print(f"  변환표 리드 0x{KLEAD:02X} → 블록 $C1:{TBL_BLOCK:04X} ({n1}슬롯)"
          + (f" + 리드 0x{KLEAD2:02X} → 블록 $C1:{TBL_BLOCK2:04X} ({n2}슬롯)" if n2 else ""))
    print(f"  문자열 {len(report)}개 재작성, 라운드트립 OK")
    for tag, mode, n, slot in report:
        flag = "  ⚠️초과" if n > slot else ""
        print(f"    {tag} {mode:8s} {n:3d}/{slot:3d}B{flag}")

if __name__ == "__main__":
    build()
