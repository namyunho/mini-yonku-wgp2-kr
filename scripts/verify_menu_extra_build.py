#!/usr/bin/env python3
"""추가 소형 메뉴 3종의 최종 통합 ROM 무결성 게이트.

확인 대화문은 직접 타일 프로그램 전체 바이트를, `다음LV까지`는 월드맵과
이지·수동 세팅의 $D9 파생 자원·로더를, 일시정지 메뉴는 $D4:6630 해제본을
각각 원본에서 다시 조립해 최종 ROM과 대조한다.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import zlib


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_menu4_reclean as menu4  # noqa: E402
import build_pause_menu as pause  # noqa: E402
import build_setbox as setbox  # noqa: E402
import lzss  # noqa: E402
from small_font_graphics import load_translation, pack_tight_2bpp_label  # noqa: E402


ORIGINAL = ROOT / "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
BUILT = ROOT / "out/wgp2_kr.smc"
TRANSLATIONS = ROOT / "assets/translations/menu_extra_labels.json"
FONT_BIN = ROOT / "assets/fonts/small/font-007242d37349daf3.bin"
FONT_MAP = ROOT / "assets/fonts/small/font-007242d37349daf3_glyph_map.json"
MANUAL_SETBOX_RELOC = (0xC1, 0xD900)
MANUAL_ALLOWED_TILES = set(range(0xC0, 0xD8)) | set(range(0x140, 0x160))


def pc(bank: int, address: int) -> int:
    return ((bank & 0x3F) << 16) | address


def resource(rom: bytes, bank: int, address: int) -> tuple[bytes, int]:
    start = pc(bank, address)
    raw_size = int.from_bytes(rom[start:start + 2], "little")
    raw, used = lzss.decompress(rom, start + 2, raw_size)
    assert len(raw) == raw_size
    return raw, used


def expected_next_level(original_font: bytes) -> bytes:
    font = FONT_BIN.read_bytes()
    glyph_map = json.loads(FONT_MAP.read_text(encoding="utf-8"))
    text = load_translation(TRANSLATIONS, "next_level")
    return pack_tight_2bpp_label(
        original_font, font, glyph_map, text, {"L": 0x7B, "V": 0x85}, 5
    )


def expected_pause(original_raw: bytes) -> bytes:
    font = FONT_BIN.read_bytes()
    glyph_map = json.loads(FONT_MAP.read_text(encoding="utf-8"))
    canvas = pause.page_canvas(original_raw)
    continue_text, continue_cells = pause.load_label("pause_continue")
    retire_text, retire_cells = pause.load_label("pause_retire")
    pause.draw_label(canvas, font, glyph_map, continue_text, 0, continue_cells)
    pause.draw_label(canvas, font, glyph_map, retire_text, 48, retire_cells)
    expected = bytearray(original_raw)
    pause.write_page(expected, canvas)
    return bytes(expected)


def expected_setbox(original_font: bytes) -> bytes:
    font = FONT_BIN.read_bytes()
    glyph_map = json.loads(FONT_MAP.read_text(encoding="utf-8"))
    expected = bytearray(original_font)
    for ch, tile in zip(setbox.SYL, setbox.OFFS, strict=True):
        begin = tile * 16
        expected[begin:begin + 16] = setbox.kr_glyph_2bpp(font, glyph_map, ch)
    begin, end = (value * 16 for value in setbox.NEXT_LEVEL_TILE_SPAN)
    expected[begin:end] = expected_next_level(original_font)
    return bytes(expected)


def main() -> None:
    original = ORIGINAL.read_bytes()
    built = BUILT.read_bytes()
    assert len(original) == len(built) == 0x200000, "ROM은 헤더리스 2MB여야 함"
    assert zlib.crc32(original) & 0xFFFFFFFF == 0x4459D4D0
    assert hashlib.md5(original).hexdigest() == "acdeb2ee6ef7b460c5dfed6957f8581a"
    assert built[0xFFD7] == original[0xFFD7] == 0x0B, "ROM 크기 헤더가 변함"

    ledger = json.loads(TRANSLATIONS.read_text(encoding="utf-8"))
    for entry in ledger["entries"]:
        assert entry.get("status") == "implemented", f"미구현 항목: {entry['id']}"
        assert all(isinstance(entry.get(key), str)
                   for key in ("text_jp", "text_kr_full", "text_kr"))
    shortened = [entry["id"] for entry in ledger["entries"]
                 if entry["text_kr_full"] != entry["text_kr"]]
    assert shortened == ["next_level"], f"추가 메뉴 축약 원장 불일치: {shortened}"

    confirm = next(program for program in menu4.DIRECT_PROGRAMS
                   if program.addr == 0x007841)
    expected_confirm = menu4.encode_program(confirm, menu4.SAVE_CONFIRM_CHAR_TO_TILE)
    assert built[confirm.addr:confirm.addr + len(expected_confirm)] == expected_confirm

    original_font, original_font_used = resource(original, 0xD9, 0x0000)
    assert original_font_used == 3766
    font = FONT_BIN.read_bytes()
    glyph_map = json.loads(FONT_MAP.read_text(encoding="utf-8"))
    expected_save_resource, expected_save_font = menu4.make_font_resource(
        original_font,
        len(original_font),
        font,
        glyph_map,
        menu4.SAVE_CONFIRM_CHAR_TO_TILE,
    )
    built_save_font, built_save_used = resource(built, *menu4.SAVE_CONFIRM_FONT)
    assert built_save_font == expected_save_font
    assert built_save_used == len(expected_save_resource) - 2
    save_loader = pc(*menu4.SAVE_CONFIRM_LOADER)
    assert built[save_loader:save_loader + 14] == bytes.fromhex(
        "A9 C7 00 85 03 A9 00 C0 85 01 22 52 0D C0"
    )

    next_tiles = expected_next_level(original_font)
    start, end = 0xF4 * 16, 0xF9 * 16
    world_font, _ = resource(built, 0xC7, 0xE000)
    assert world_font[start:end] == next_tiles, "월드맵 다음 LV 타일 불일치"

    expected_setbox_raw = expected_setbox(original_font)
    intermediate_setbox, _ = resource(built, *setbox.RELOC)
    assert intermediate_setbox == expected_setbox_raw, \
        "수동 세팅 중간 자원의 허용 밖 타일 변경"

    manual_source = bytes([
        0xF4, MANUAL_SETBOX_RELOC[0], 0x00,
        0xF4, MANUAL_SETBOX_RELOC[1] & 0xFF, MANUAL_SETBOX_RELOC[1] >> 8,
    ])
    first_loader_pc = pc(*next(iter(setbox.FONT_SOURCE_LOADERS.values()))[0])
    manual_mode = built[first_loader_pc:first_loader_pc + 6] == manual_source
    if manual_mode:
        built_setbox, _ = resource(built, *MANUAL_SETBOX_RELOC)
        assert len(built_setbox) == len(expected_setbox_raw)
        changed_tiles = {
            tile for tile in range(len(built_setbox) // 16)
            if built_setbox[tile * 16:(tile + 1) * 16]
            != expected_setbox_raw[tile * 16:(tile + 1) * 16]
        }
        assert changed_tiles <= MANUAL_ALLOWED_TILES, \
            f"승인 능력치/개러지 외 세팅 타일 변경: {sorted(changed_tiles - MANUAL_ALLOWED_TILES)}"
    else:
        built_setbox = intermediate_setbox
    assert built_setbox[start:end] == next_tiles, "이지·수동 세팅 다음 LV 타일 불일치"
    assert set(setbox.OFFS) <= setbox.RECLAIMED_LABEL_TILES
    assert set(setbox.OFFS).isdisjoint(setbox.PROTECTED_ALPHANUMERIC_TILES)
    for tile in setbox.PROTECTED_ALPHANUMERIC_TILES:
        begin = tile * 16
        assert built_setbox[begin:begin + 16] == original_font[begin:begin + 16], \
            f"수동 세팅 영문·숫자 타일 훼손: ${tile:02X}"

    original_source = bytes([0xF4, 0xD9, 0x00, 0xF4, 0x00, 0x00])
    relocated_source = bytes([
        0xF4, setbox.RELOC[0], 0x00,
        0xF4, setbox.RELOC[1] & 0xFF, setbox.RELOC[1] >> 8,
    ])
    active_source = manual_source if manual_mode else relocated_source
    for label, (loader, dma_size) in setbox.FONT_SOURCE_LOADERS.items():
        loader_pc = pc(*loader)
        assert original[loader_pc:loader_pc + 6] == original_source, \
            f"{label} 원본 폰트 포인터 불일치"
        assert built[loader_pc:loader_pc + 6] == active_source, \
            f"{label} 폰트 리다이렉트 누락"
        assert built[loader_pc + 0x35:loader_pc + 0x38] == bytes([
            0xA9, dma_size & 0xFF, dma_size >> 8
        ]), f"{label} DMA 길이 변경"
        assert dma_size >= end, f"{label} DMA가 `$F4-$F8`을 포함하지 않음"

    original_pause, original_pause_used = resource(original, 0xD4, 0x6630)
    built_pause, built_pause_used = resource(built, 0xD4, 0x6630)
    assert original_pause_used == pause.ORIGINAL_STREAM_SIZE
    assert built_pause_used <= pause.ORIGINAL_STREAM_SIZE
    assert built_pause == expected_pause(original_pause), "일시정지 대상 밖 타일 변경"

    print("추가 메뉴 최종 무결성 PASS")
    print(
        "  확인문: 괜찮습니까？ / 예 / 아니오 "
        f"(저장 화면 전용 폰트 {built_save_used}B·직접 프로그램 일치)"
    )
    active_label = "$C1:D900 승인 파생" if manual_mode else "$C7:D000 세팅 파생"
    print(f"  다음 LV: 월드맵 + 이지·수동 세팅 $F4-$F8 자원·로더 일치 ({active_label})")
    print("  세팅: 교체 원문 가나 14타일만 재사용, 영문·숫자 $70-$9F 원본 일치")
    print(
        "  일시정지: 이어하기 / 리타이어, "
        f"대상 24타일 한정, LZSS {built_pause_used}/{pause.ORIGINAL_STREAM_SIZE}B"
    )
    print("  ROM: 헤더리스 2MB / 헤더 0x0B 유지, 축약 1건 원장 보존")


if __name__ == "__main__":
    main()
