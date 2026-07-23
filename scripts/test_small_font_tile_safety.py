#!/usr/bin/env python3
"""월드맵 소형폰트 상태줄 전용 타일의 코드/공유자산 안전성 검사.

`문/제`에 배정한 $1B/$1E가 직접 렌더러의 제어값이 아니며, 지원 원본에서
확정한 모든 $C0:1B4B 호출자 중 월드 폰트 문맥의 다른 레코드가 두 타일을
참조하지 않는지 검사한다. 최종 폰트는 승인된 타일만 바뀌었는지도 대조한다.
"""

from __future__ import annotations

import hashlib
import json
import sys
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_menu4_reclean as menu4  # noqa: E402
from lzss import decompress  # noqa: E402
from menu4_labels import tile_value  # noqa: E402


ORIGINAL = ROOT / "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
BUILT = ROOT / "out/wgp2_kr.smc"
SJIS_UI = ROOT / "assets/translations/sjis_ui.json"

DIRECT_RENDER_JSL = bytes.fromhex("22 4B 1B C0")
DIRECT_RENDER_CALLS = {
    0x00719A, 0x00778C, 0x0079F9, 0x007A0D, 0x007A31,
    0x007C00, 0x008D6F, 0x038B81, 0x0395A4, 0x0399B8,
}
WORLD_FONT_DIRECT_CALLS = {0x008D6F, 0x038B81, 0x0395A4, 0x0399B8}
SAVE_FONT_DIRECT_CALLS = DIRECT_RENDER_CALLS - WORLD_FONT_DIRECT_CALLS

# $C0:1B4B 메인행 루프. 00만 오버레이행 진입, FF만 빈 타일이며
# 그 밖의 8-bit 값은 base를 더해 $7E:0000 타일맵 버퍼에 기록한다.
DIRECT_RENDER_MAIN_LOOP = bytes.fromhex(
    "B7 0F C8 29 FF 00 F0 13 C9 FF 00 D0 03 A9 00 00 "
    "18 65 01 9F 00 00 7E E8 E8 80 E5"
)
DIRECT_RENDER_MAIN_LOOP_PC = 0x001B5C
DIRECT_CONTROL_VALUES = {0x00, 0xFF}

QUIZ_NEW_TILES = {"간": 0x01, "문": 0x1B, "제": 0x1E}
QUIZ_EXCLUSIVE_TILES = {0x1B, 0x1E}


def find_all(data: bytes, needle: bytes) -> set[int]:
    found: set[int] = set()
    cursor = 0
    while True:
        cursor = data.find(needle, cursor)
        if cursor < 0:
            return found
        found.add(cursor)
        cursor += 1


def resource(rom: bytes, bank: int, address: int) -> tuple[bytes, int, int]:
    start = menu4.pc(bank, address)
    raw_size = int.from_bytes(rom[start:start + 2], "little")
    raw, used = decompress(rom, start + 2, raw_size)
    return raw, used, raw_size


def original_world_catalog_tiles() -> set[int]:
    """월드 폰트로 표시되는 직접 타일 레코드 원문의 전수 타일 집합."""
    tiles = {
        value
        for record in menu4.TUTORIAL_RECORDS
        for value in record.original_bottom + record.prefix
    }
    tiles.update(
        value
        for program in menu4.DIRECT_PROGRAMS
        if program.addr != 0x007841  # 저장 확인창은 전용 폰트
        for row in program.rows
        for value in row.original + row.control
    )
    return tiles


def main() -> None:
    original = ORIGINAL.read_bytes()
    built = BUILT.read_bytes()
    assert len(original) == len(built) == 0x200000
    assert zlib.crc32(original) & 0xFFFFFFFF == menu4.ORIGINAL_CRC32
    assert hashlib.md5(original).hexdigest() == menu4.ORIGINAL_MD5

    # 직접 렌더러 진입 분모를 원본 리비전의 명시 사양으로 고정한다.
    calls = find_all(original, DIRECT_RENDER_JSL)
    assert calls == DIRECT_RENDER_CALLS, (
        "직접 렌더러 $C0:1B4B 호출자 분모 변경: "
        f"누락={sorted(DIRECT_RENDER_CALLS - calls)}, "
        f"신규={sorted(calls - DIRECT_RENDER_CALLS)}"
    )
    assert WORLD_FONT_DIRECT_CALLS | SAVE_FONT_DIRECT_CALLS == calls

    # $1B/$1E는 opcode나 제어 토큰이 아니라 메인행의 일반 타일값이다.
    assert original[
        DIRECT_RENDER_MAIN_LOOP_PC:
        DIRECT_RENDER_MAIN_LOOP_PC + len(DIRECT_RENDER_MAIN_LOOP)
    ] == DIRECT_RENDER_MAIN_LOOP
    assert QUIZ_EXCLUSIVE_TILES.isdisjoint(DIRECT_CONTROL_VALUES)
    assert original[0x008D5E:0x008D73] == bytes.fromhex(
        "F4 C0 00 F4 8A 8D A9 84 04 18 6D 4D 05 AA "
        "A9 00 21 22 4B 1B C0"
    ), "퀴즈 상태줄 포인터→직접 렌더러 호출 시그니처 변경"

    # 원본 $D9 폰트 변환표상 실제 가나 글리프 슬롯임을 독립 확인한다.
    assert tile_value(original, "あ") == 0x01
    assert tile_value(original, "ひ") == 0x1B
    assert tile_value(original, "ほ") == 0x1E

    # 월드 폰트 문맥의 다른 직접 레코드와 제어 바이트에서는 쓰지 않는다.
    catalog_tiles = original_world_catalog_tiles()
    assert QUIZ_EXCLUSIVE_TILES.isdisjoint(catalog_tiles), (
        "`문/제` 전용 타일이 다른 월드맵·튜토리얼 직접 레코드와 충돌"
    )
    tutorial_block = original[0x07B180:0x07B461]
    assert not (QUIZ_EXCLUSIVE_TILES & set(tutorial_block)), (
        "`문/제` 전용 타일이 튜토리얼 전체 데이터 블록과 충돌"
    )

    # 구조화된 SJIS UI 원문에도 ひ/ほ가 없다. 유일한 비압축 `ほぞん`
    # ($C0:71E2)은 저장 화면이며 $C0:6F4B의 별도 폰트 로더를 사용한다.
    sjis = json.loads(SJIS_UI.read_text(encoding="utf-8"))
    sjis_jp = [
        str(entry["jp"])
        for entries in sjis.values()
        if isinstance(entries, list)
        for entry in entries
    ]
    assert not any(("ひ" in text or "ほ" in text) for text in sjis_jp)
    assert original[0x0071E2:0x0071E8] == "ほぞん".encode("cp932")
    save_loader = menu4.pc(*menu4.SAVE_CONFIRM_LOADER)
    assert built[save_loader:save_loader + 10] == bytes.fromhex(
        "A9 C7 00 85 03 A9 00 C0 85 01"
    )

    # 로더는 고정 0x1000B(256×16B)를 VRAM에 보내며 새 타일은 그 안의
    # 독립 16B 2bpp 블록이다. 코드·길이·DMA 규칙은 바꾸지 않는다.
    assert original[0x0094D4:0x0094DA] == bytes.fromhex(
        "F4 D9 00 F4 00 00"
    )
    assert built[0x0094D4:0x0094DA] == bytes.fromhex(
        "F4 C7 00 F4 00 E0"
    )
    assert original[0x009509:0x00950C] == built[0x009509:0x00950C] \
        == bytes.fromhex("A9 00 10")

    original_font, original_used, original_size = resource(
        original, *menu4.ORIGINAL_FONT
    )
    world_font, _, world_size = resource(built, *menu4.NEW_FONT)
    assert original_used == 3766
    assert original_size == world_size == menu4.ORIGINAL_FONT_RAW_SIZE

    changed_tiles = {
        tile
        for tile in range(original_size // 16)
        if original_font[tile * 16:(tile + 1) * 16]
        != world_font[tile * 16:(tile + 1) * 16]
    }
    expected_changed = set(menu4.KOREAN_TILE_CODES) | set(
        range(*menu4.NEXT_LEVEL_TILE_SPAN)
    )
    assert changed_tiles == expected_changed, (
        "월드 폰트 승인 밖 타일 변경: "
        f"추가={sorted(changed_tiles - expected_changed)}, "
        f"누락={sorted(expected_changed - changed_tiles)}"
    )
    assert set(QUIZ_NEW_TILES.values()) <= changed_tiles

    glyph_font = menu4.FONT_BIN.read_bytes()
    glyph_map = json.loads(menu4.FONT_MAP.read_text(encoding="utf-8"))
    syllables = menu4.collect_syllables()
    char_to_tile = dict(zip(syllables, menu4.KOREAN_TILE_CODES, strict=True))
    for ch, tile in QUIZ_NEW_TILES.items():
        begin = tile * 16
        expected = menu4.glyph_2bpp(glyph_font, glyph_map, ch)
        assert world_font[begin:begin + 16] == expected, (
            f"퀴즈 상태줄 `{ch}` 글리프 타일 ${tile:02X} 불일치"
        )

    # 직전 `회/시간` 구현(간=$01)과 비교하면 이번 `문제` 변경이 더한
    # 폰트 차이는 $1B/$1E 두 개의 16B 글리프 블록뿐이어야 한다.
    prior_raw_font = bytearray(original_font)
    next_start, next_end = (tile * 16 for tile in menu4.NEXT_LEVEL_TILE_SPAN)
    prior_raw_font[next_start:next_end] = world_font[next_start:next_end]
    prior_mapping = {
        ch: tile for ch, tile in char_to_tile.items() if ch not in {"문", "제"}
    }
    _, prior_world_font = menu4.make_font_resource(
        bytes(prior_raw_font),
        original_size,
        glyph_font,
        glyph_map,
        prior_mapping,
    )
    incremental_tiles = {
        tile
        for tile in range(original_size // 16)
        if prior_world_font[tile * 16:(tile + 1) * 16]
        != world_font[tile * 16:(tile + 1) * 16]
    }
    assert incremental_tiles == QUIZ_EXCLUSIVE_TILES, (
        "`문제` 후속 변경이 $1B/$1E 밖의 폰트 타일을 수정"
    )

    print("월드맵 소형폰트 상태줄 타일 안전성 PASS")
    print("  직접 렌더러 호출자 10/10: 월드 4 + 저장 전용 6")
    print("  메인행 제어값 00/FF, `문=$1B`·`제=$1E`는 일반 타일값")
    print("  원본 대응: あ=$01 / ひ=$1B / ほ=$1E")
    print("  다른 월드맵·튜토리얼 직접 레코드의 $1B/$1E 참조 0")
    print("  월드 폰트 변경 87/87 승인 타일, 승인 밖 변경 0")
    print("  직전 `회/시간` 대비 추가 폰트 변경: $1B/$1E 두 블록만")
    print("  2MB·고정 DMA 0x1000B·코드 훅 없음")


if __name__ == "__main__":
    main()
