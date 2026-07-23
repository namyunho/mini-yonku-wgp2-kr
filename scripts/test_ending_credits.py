#!/usr/bin/env python3
"""최종 ROM의 실제 엔딩 크레딧·베스트타임 한글화 회귀 검사."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_ending_credits as ending  # noqa: E402
from lzss import decompress  # noqa: E402


def lows(record: ending.Record) -> list[int]:
    return [word & 0xFF for word in record.words]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rom", type=Path, default=ending.DEFAULT_ROM)
    parser.add_argument("--map", type=Path, default=ending.DEFAULT_MAP)
    args = parser.parse_args()

    original = ending.ORIGINAL_ROM.read_bytes()
    rom = args.rom.read_bytes()
    assert len(original) == len(rom) == ending.ORIGINAL_SIZE
    assert rom[
        ending.ENDING_FONT_POINTER:ending.ENDING_FONT_POINTER + 3
    ] == ending.ENDING_FONT_POINTER_BYTES

    ledger = json.loads(ending.TRANSLATIONS.read_text(encoding="utf-8"))
    build_map = json.loads(args.map.read_text(encoding="utf-8"))
    entries = ledger["entries"]
    by_pair = {int(entry["pair"]): entry for entry in entries}
    char_to_tile = {
        ch: int(tile, 16)
        for ch, tile in build_map["font"]["char_to_tile"].items()
    }

    original_stream = original[ending.STREAM_START:ending.STREAM_END]
    patched_stream = rom[ending.STREAM_START:ending.STREAM_END]
    original_records = ending.parse_stream(original_stream)
    patched_records = ending.parse_stream(patched_stream)
    assert len(original_records) == len(patched_records) == ending.PHYSICAL_RECORDS
    assert len(original_stream) == len(patched_stream) == ending.STREAM_SIZE

    for before, after in zip(original_records, patched_records, strict=True):
        assert (after.offset, after.count, after.control) == (
            before.offset, before.count, before.control,
        ), f"레코드 위치/길이/제어 변경: {before.offset:#x}"
        assert [word & 0xFF00 for word in after.words] == [
            word & 0xFF00 for word in before.words
        ], f"타일 속성 변경: {before.offset:#x}"

    for pair, entry in sorted(by_pair.items()):
        before_top, before_bottom = original_records[pair * 2:pair * 2 + 2]
        top, bottom = patched_records[pair * 2:pair * 2 + 2]
        assert lows(top) == [0] * top.count, f"상단 일본어 오버레이 잔존: pair {pair}"

        if entry["kind"] == "credit":
            original_codes = lows(before_bottom)
            used = [index for index, tile in enumerate(original_codes) if tile]
            first, last = min(used), max(used)
            capacity = last - first + 1
            encoded = ending.encode_text(str(entry["text_kr"]), char_to_tile)
            start = first + (capacity - len(encoded)) // 2
            expected = [0] * bottom.count
            expected[start:start + len(encoded)] = encoded
            assert lows(bottom) == expected, f"크레딧 본문 불일치: pair {pair}"
        else:
            original_codes = lows(before_bottom)
            patched_codes = lows(bottom)
            handler = ending.BEST_TIME_PAIRS.index(pair) + 1
            assert patched_codes[0] == original_codes[0] == handler
            assert patched_codes[18:20] == original_codes[18:20]
            assert patched_codes[23:25] == original_codes[23:25]
            expected_course = ending.encode_text(str(entry["course_kr"]), char_to_tile)
            expected_unit = ending.encode_text(str(entry["unit_kr"]), char_to_tile)
            assert patched_codes[6:18] == expected_course + [0] * (12 - len(expected_course))
            assert patched_codes[20:23] == expected_unit + [0] * (3 - len(expected_unit))

    # 원래 완전 공백이던 31행과 종료 직전 폭 5의 공백 행은 그대로다.
    blank_zero_pairs = []
    for pair in range(ending.LOGICAL_ROWS):
        before_top, before_bottom = original_records[pair * 2:pair * 2 + 2]
        top, bottom = patched_records[pair * 2:pair * 2 + 2]
        if before_top.count == before_bottom.count == 0:
            blank_zero_pairs.append(pair)
            assert top.encode() == before_top.encode()
            assert bottom.encode() == before_bottom.encode()
    assert len(blank_zero_pairs) == ledger["policy"]["blank_logical_rows"] == 31

    # 전용 폰트의 한글, 베스트타임 가/나/다/라, 런타임 숫자를 검증한다.
    raw_size = int.from_bytes(
        rom[ending.ENDING_FONT:ending.ENDING_FONT + 2], "little",
    )
    final_font, used = decompress(rom, ending.ENDING_FONT + 2, raw_size)
    assert used == build_map["font"]["resource_size"] - 2
    font = ending.FONT_BIN.read_bytes()
    glyph_map = json.loads(ending.FONT_MAP.read_text(encoding="utf-8"))
    for ch, tile in char_to_tile.items():
        expected = ending.glyph_2bpp(font, glyph_map, ch)
        assert final_font[tile * 16:tile * 16 + 16] == expected
    for handler, pair in enumerate(ending.BEST_TIME_PAIRS, 1):
        ch = str(by_pair[pair]["label_kr"])
        expected = ending.glyph_2bpp(font, glyph_map, ch)
        assert final_font[handler * 16:handler * 16 + 16] == expected

    original_raw_size = int.from_bytes(
        original[ending.ORIGINAL_FONT:ending.ORIGINAL_FONT + 2], "little",
    )
    original_font, _ = decompress(
        original, ending.ORIGINAL_FONT + 2, original_raw_size,
    )
    for tile in (0x00, 0x05, *range(0x70, 0xAA)):
        assert final_font[tile * 16:tile * 16 + 16] == (
            original_font[tile * 16:tile * 16 + 16]
        ), f"보존 글리프 변경: {tile:02X}"

    capacity = build_map["additional_capacity"]
    assert capacity["existing_blank_logical_rows"] == 31
    assert capacity["c7_relocation_pool_start"] == "$C7:EE7B"
    assert capacity["c7_relocation_pool_bytes"] == 4485
    assert capacity["spare_bytes_after_relocation"] == 679
    assert capacity["additional_full_width_logical_rows"] == 10
    assert build_map["translated"]["abbreviated_rows"] == 0
    print(
        "엔딩 크레딧 PASS: 45행 완역, 154레코드 위치보존, "
        "베스트타임 처리기·숫자 보존, 추가 최대폭 10행"
    )


if __name__ == "__main__":
    main()
