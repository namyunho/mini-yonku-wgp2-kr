#!/usr/bin/env python3
"""SJIS 시작 메뉴 한글화 빌드 (비파괴).

메커니즘(docs/11):
- 렌더러 $C1:965E: VRAM 타일 = 256 + tile_index(표 $C1:D1C3) + base($07=0x2100). body 8비트.
- 메뉴 폰트 = LZSS $D9:0002 → VRAM 타일 256-511(256타일만 DMA), bgMode0 2bpp.
- 자유 VRAM: 메뉴 시점 타일 672-1023 비어있음.

전략(원본 폰트·다른 화면 무손상):
1. 한글 12글리프(2bpp) → 자유 ROM $C1:9880.
2. 메뉴 폰트 로더 $C0:6F43에 JSL 훅 주입 → 한글을 VRAM 타일 672로 별도 DMA.
3. 렌더러 $C1:965E에 훅(마커 상위바이트 0xFE) → 확장 타일(VRAM 512+) 참조.
4. 표 $C1:D1C3: SJIS 0x8240-0x824B → tileval 0xFEA0-0xFEAB.
5. 문자열 $C0:71B9 재작성(처음부터/이어하기/복사/지우기).
"""
import json, sys, os

ROM_IN = "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
ROM_OUT = "out/menu_test.smc"
BIN = "8pt_font/font-007242d37349daf3.bin"
GMAP = "8pt_font/font-007242d37349daf3_glyph_map.json"

# --- 자유 ROM/VRAM 배치 상수 ---
HOOK_RENDER = 0x9843      # $C1:9843 렌더러 훅 루틴
KDATA       = 0x9880      # $C1:9880 한글 글리프 데이터(192B)
HOOK_LOADER = 0x9940      # $C1:9940 로더 DMA 주입 루틴
VRAM_KOR_TILE = 800       # 한글 로드 대상 VRAM 타일(768-1023 자유영역; 256-767은 폰트 2회 로드)
MARKER = 0xFE             # 표 tileval 상위바이트 = 확장 마커
# 렌더러 ext 오프셋: VRAM타일 = low + ADD + 0x100. VRAM 800(0x320) → ADD=0x220 (low=k)
KOR_ADD = 0x0220

# 메뉴 음절(완전형): 처음부터 이어하기 복사 삭제
#   (けす=2타일 슬롯에 맞춰 '지우기'→'삭제'; 원본 옵션 컬럼 정렬로 활성/비활성 색 정확)
SYL = "처음부터이어하기복사삭제"

def foff_c1(addr): return 0x010000 | (addr & 0xFFFF)   # 뱅크 $C1 파일오프셋
def foff_c0(addr): return 0x000000 | (addr & 0xFFFF)   # 뱅크 $C0

def kr_glyph_2bpp(binf, gmap, ch):
    g = binf[gmap[ch]*8: gmap[ch]*8+8]   # 1bpp 8행(MSB=좌)
    t = bytearray(16)
    for r in range(8):
        t[2*r] = g[r]      # plane0 = 잉크(색1)
        t[2*r+1] = 0       # plane1 = 0
    return bytes(t)

def build():
    rom = bytearray(open(ROM_IN, "rb").read())
    binf = open(BIN, "rb").read()
    gmap = json.load(open(GMAP, encoding="utf-8"))

    # distinct 음절 순서
    distinct = []
    for c in SYL:
        if c not in distinct: distinct.append(c)
    assert len(distinct) == 12, f"음절수 {len(distinct)}"
    sjis = {c: 0x8240 + i for i, c in enumerate(distinct)}   # 음절→SJIS
    tile_low = {c: i for i, c in enumerate(distinct)}         # VRAM 800+i → low = i (hook: low+ADD+0x100)

    # 1) 한글 글리프 데이터 (12타일 2bpp = 192B) → $C1:9880
    kdata = bytearray()
    for c in distinct:
        kdata += kr_glyph_2bpp(binf, gmap, c)
    assert len(kdata) == 192
    rom[foff_c1(KDATA):foff_c1(KDATA)+192] = kdata

    # 2) 렌더러 훅 루틴 → $C1:9843
    #    진입: JMP $9843 (렌더러 $9696 대체). $05=tileval, $06=hi, X=타일맵오프셋, $07=base.
    hook = bytes([
        0xA5,0x06,            # LDA $06
        0xC9,MARKER,0x00,     # CMP #$00FE
        0xF0,0x1C,            # BEQ ext ($9866)
        # normal:
        0xA5,0x05,            # LDA $05
        0x29,0xFF,0x00,       # AND #$00FF
        0x18,                 # CLC
        0x65,0x07,            # ADC $07
        0x9F,0x00,0x00,0x7E,  # STA $7E0000,X
        0xA5,0x06,            # LDA $06
        0x29,0xFF,0x00,       # AND #$00FF
        0xF0,0x19,            # BEQ done ($9876)
        0x18,                 # CLC
        0x65,0x07,            # ADC $07
        0x9F,0xC0,0xFF,0x7D,  # STA $7DFFC0,X
        0x80,0x10,            # BRA done ($9876)
        # ext ($9866):
        0xA5,0x05,            # LDA $05
        0x29,0xFF,0x00,       # AND #$00FF
        0x18,                 # CLC
        0x69,KOR_ADD&0xFF,(KOR_ADD>>8)&0xFF,  # ADC #$0220
        0x18,                 # CLC
        0x65,0x07,            # ADC $07
        0x9F,0x00,0x00,0x7E,  # STA $7E0000,X
        # done ($9876):
        0x4C,0xAE,0x96,       # JMP $96AE
    ])
    # 오프셋 검증
    assert HOOK_RENDER == 0x9843
    # ext 라벨 위치 = 0x9843 + 0x23 = 0x9866
    rom[foff_c1(HOOK_RENDER):foff_c1(HOOK_RENDER)+len(hook)] = hook

    # 렌더러 $C1:9696 (AND #$00FF) → JMP $9843
    r9696 = foff_c1(0x9696)
    assert rom[r9696:r9696+3] == bytes([0x29,0xFF,0x00]), rom[r9696:r9696+3].hex()
    rom[r9696:r9696+3] = bytes([0x4C,0x43,0x98])   # JMP $9843

    # 3) 로더 DMA 주입 루틴 → $C1:9940
    src = KDATA
    vram_word = VRAM_KOR_TILE * 8   # 2bpp: 8 words/타일
    inject = bytes([
        0xA9,vram_word&0xFF,(vram_word>>8)&0xFF,   # LDA #vram_word (VRAM 800*8=0x1900)
        0x8F,0x16,0x21,0x00,  # STA $2116
        0xE2,0x20,            # SEP #$20
        0xA9,0x80,            # LDA #$80
        0x8F,0x15,0x21,0x00,  # STA $2115
        0xA9,0xC1,            # LDA #$C1   (src bank $C1)
        0x8F,0x04,0x43,0x00,  # STA $4304
        0xC2,0x20,            # REP #$20
        0xA9,0x01,0x18,       # LDA #$1801 (ctrl/dest $2118)
        0x8F,0x00,0x43,0x00,  # STA $4300
        0xA9,src&0xFF,(src>>8)&0xFF,  # LDA #$9880 (src addr)
        0x8F,0x02,0x43,0x00,  # STA $4302
        0xA9,0xC0,0x00,       # LDA #$00C0 (size 192)
        0x8F,0x05,0x43,0x00,  # STA $4305
        0xE2,0x20,            # SEP #$20
        0xA9,0x01,            # LDA #$01
        0x8F,0x0B,0x42,0x00,  # STA $420B (trigger)
        0xC2,0x20,            # REP #$20
        0xA9,0x7F,0x00,       # LDA #$007F (원래 대체분)
        0x85,0x07,            # STA $07
        0x6B,                 # RTL
    ])
    rom[foff_c1(HOOK_LOADER):foff_c1(HOOK_LOADER)+len(inject)] = inject

    # 로더 $C0:6F93 (A9 7F 00 85 07) → JSL $C19940 + NOP
    L = foff_c0(0x6F93)
    assert rom[L:L+5] == bytes([0xA9,0x7F,0x00,0x85,0x07]), rom[L:L+5].hex()
    rom[L:L+5] = bytes([0x22,0x40,0x99,0xC1, 0xEA])   # JSL $C19940 ; NOP

    # 4) 표 $C1:D1C3: SJIS 0x8240-0x824B → tileval 0xFEA0+i
    TBL = 0x01D1C3
    rb = rom[TBL+(0x82&0x7F)*2] | (rom[TBL+(0x82&0x7F)*2+1] << 8)   # 0x188
    for i, c in enumerate(distinct):
        lo = 0x40 + i
        off = TBL + rb + (lo-0x40)*2
        tileval = (MARKER << 8) | tile_low[c]   # 0xFEA0+i
        assert rom[off] == 0 and rom[off+1] == 0, f"표 슬롯 lo={lo:02X} 비어있지 않음"
        rom[off] = tileval & 0xFF
        rom[off+1] = (tileval >> 8) & 0xFF

    # 5) 문자열 $C0:71B9 재작성
    def s(c): return bytes([0x82, sjis[c] & 0xFF])   # hi 0x82, lo
    SP = bytes([0x81,0x40])
    # 원본 옵션 컬럼 정렬(버퍼 col8 시작): 처음부터=col8-11(흰), 이어하기=col14-17(회),
    #   복사=col20-21(회), 삭제=col26-27(회). 게임의 고정 palette영역과 일치.
    newstr = (s('처')+s('음')+s('부')+s('터') + SP+SP +
              s('이')+s('어')+s('하')+s('기') + SP+SP +
              s('복')+s('사') + SP+SP+SP+SP +
              s('삭')+s('제') + bytes([0x00]))
    STR = 0x0071B9
    # 원본 길이 확인(널까지)
    end = rom.index(0, STR)
    orig_len = end - STR + 1
    assert len(newstr) <= orig_len, f"문자열 초과 {len(newstr)}>{orig_len}"
    rom[STR:STR+len(newstr)] = newstr

    os.makedirs("out", exist_ok=True)
    open(ROM_OUT, "wb").write(rom)
    print(f"완료: {ROM_OUT}")
    print(f"  음절 12: {distinct}")
    print(f"  SJIS 0x8240-0x824B → VRAM 타일 {VRAM_KOR_TILE}-{VRAM_KOR_TILE+11}")
    print(f"  문자열 {len(newstr)}B / 원본슬롯 {orig_len}B")

if __name__ == "__main__":
    build()
