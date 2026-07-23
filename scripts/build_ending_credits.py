#!/usr/bin/env python3
"""실제 엔딩 스크롤 크레딧·베스트타임의 전용 8×8 한글화 빌더.

에피소드 사이의 VICTORYS 로고가 아니라 $C7:A2A5의 최종 엔딩 행
명령열을 패치한다. 원본 154개 물리 레코드와 77개 논리행의 길이·순서를
그대로 유지하고, $D9:0000 공용 글꼴은 건드리지 않은 채 $D9:E000에
엔딩 전용 사본을 둔다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from lzss import compress, decompress  # noqa: E402


ORIGINAL_ROM = ROOT / "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
DEFAULT_ROM = ROOT / "out/wgp2_kr.smc"
TRANSLATIONS = ROOT / "assets/translations/ending_credits.json"
FONT_BIN = ROOT / "8pt_font/font-007242d37349daf3.bin"
FONT_MAP = ROOT / "8pt_font/font-007242d37349daf3_glyph_map.json"
DEFAULT_MAP = ROOT / "out/ending_credits_glyph_map.json"
DEFAULT_PREVIEW = ROOT / "out/ending_credits_preview.png"

ORIGINAL_SIZE = 0x200000
ORIGINAL_CRC32 = 0x4459D4D0
ORIGINAL_MD5 = "acdeb2ee6ef7b460c5dfed6957f8581a"

STREAM_START = 0x07A2A5
STREAM_END = 0x07B183
STREAM_SIZE = STREAM_END - STREAM_START
STREAM_SHA256 = "82c7fe140fb878cbc0a3b61fa61aac485a98d0b336decfa02d42917dd7ae03b9"
LOGICAL_ROWS = 77
PHYSICAL_RECORDS = 154
BEST_TIME_PAIRS = (65, 66, 67, 68)

ORIGINAL_FONT = 0x190000  # $D9:0000
ORIGINAL_FONT_RAW_SIZE = 0x1760
ORIGINAL_FONT_RAW_SHA256 = "78dfbb47aff74d3d6ccfa055ab0cb5975cdf779fcc617edb9db2ebf266bb43dd"
ENDING_FONT = 0x19E000  # $D9:E000
ENDING_FONT_CAPACITY = 0x2000
ENDING_FONT_POINTER = 0x036D03  # $C3:6D03, 24-bit inline pointer
ORIGINAL_FONT_POINTER = bytes.fromhex("00 00 D9")
ENDING_FONT_POINTER_BYTES = bytes.fromhex("00 E0 D9")

# 첫 글자가 0~5이면 행 처리기로 분기한다. $70~A9는 라틴 대문자,
# 원본 숫자 자리, 탁점, 런타임 숫자 $A0~A9가 모여 있어 보수적으로
# 전부 보존한다. 나머지 192타일을 엔딩 전용 한글 후보로 쓴다.
RESERVED_TILE_CODES = frozenset(range(0x00, 0x06)) | frozenset(range(0x70, 0xAA))
KOREAN_TILE_CANDIDATES = tuple(
    tile for tile in range(0x100) if tile not in RESERVED_TILE_CODES
)
LATIN_UPPER = {chr(ord("A") + index): 0x70 + index for index in range(26)}


@dataclass
class Record:
    offset: int
    count: int
    control: int
    words: list[int]

    def encode(self) -> bytes:
        out = bytearray((self.count, self.control))
        for word in self.words:
            out += word.to_bytes(2, "little")
        return bytes(out)


def parse_stream(stream: bytes) -> list[Record]:
    records: list[Record] = []
    pos = 0
    while stream[pos:pos + 2] != b"\xFF\xFF":
        assert pos + 2 <= len(stream), "엔딩 스트림 헤더 범위 초과"
        count = stream[pos]
        control = stream[pos + 1]
        end = pos + 2 + count * 2
        assert end <= len(stream), "엔딩 스트림 레코드 범위 초과"
        words = [
            int.from_bytes(stream[at:at + 2], "little")
            for at in range(pos + 2, end, 2)
        ]
        records.append(Record(pos, count, control, words))
        pos = end
    assert stream[pos:pos + 2] == b"\xFF\xFF"
    assert pos + 2 == len(stream), "엔딩 스트림 종료어 뒤 예상 밖 데이터"
    assert len(records) == PHYSICAL_RECORDS
    return records


def collect_syllables(entries: list[dict[str, object]]) -> list[str]:
    syllables: list[str] = []
    for entry in entries:
        fields = (
            ("text_kr",)
            if entry["kind"] == "credit"
            else ("label_kr", "course_kr", "unit_kr")
        )
        for field in fields:
            text = str(entry[field])
            for ch in text:
                if "가" <= ch <= "힣" and ch not in syllables:
                    syllables.append(ch)
    return syllables


def glyph_2bpp(font: bytes, glyph_map: dict[str, int], ch: str) -> bytes:
    """프로젝트 8×8 1bpp 완성형을 엔딩의 16바이트 SNES 2bpp로 변환."""
    assert ch in glyph_map, f"8pt 글꼴에 없는 음절: {ch}"
    glyph_index = glyph_map[ch]
    source = font[glyph_index * 8:glyph_index * 8 + 8]
    assert len(source) == 8
    out = bytearray(16)
    for row in range(8):
        source_row = row - 1
        if 0 <= source_row < 8:
            out[row * 2] = source[source_row]
    return bytes(out)


def encode_text(text: str, char_to_tile: dict[str, int]) -> list[int]:
    encoded: list[int] = []
    for ch in text:
        if ch == " ":
            encoded.append(0x00)
        elif "가" <= ch <= "힣":
            encoded.append(char_to_tile[ch])
        elif ch in LATIN_UPPER:
            encoded.append(LATIN_UPPER[ch])
        else:
            raise AssertionError(f"엔딩 직접 타일로 인코딩할 수 없는 문자: {ch!r}")
    return encoded


def replace_low(word: int, tile: int) -> int:
    return (word & 0xFF00) | tile


def clear_record(record: Record) -> None:
    record.words = [replace_low(word, 0) for word in record.words]


def patch_general_pair(
    top: Record,
    bottom: Record,
    text: str,
    char_to_tile: dict[str, int],
) -> tuple[int, int]:
    original_codes = [word & 0xFF for word in bottom.words]
    used = [index for index, tile in enumerate(original_codes) if tile != 0]
    assert used, f"본문 슬롯을 찾을 수 없음: 논리행 {top.offset:#x}"
    first, last = min(used), max(used)
    capacity = last - first + 1
    encoded = encode_text(text, char_to_tile)
    assert len(encoded) <= capacity, f"엔딩 행 폭 초과: {text} {len(encoded)}>{capacity}"

    clear_record(top)
    clear_record(bottom)
    start = first + (capacity - len(encoded)) // 2
    for index, tile in enumerate(encoded, start):
        bottom.words[index] = replace_low(bottom.words[index], tile)
    return capacity, start


def patch_best_time_pair(
    pair_index: int,
    top: Record,
    bottom: Record,
    course: str,
    unit: str,
    char_to_tile: dict[str, int],
) -> None:
    assert top.count == bottom.count == 25
    original = [word & 0xFF for word in bottom.words]
    handler = BEST_TIME_PAIRS.index(pair_index) + 1
    assert original[0] == handler
    assert original[1:6] == [0] * 5

    course_codes = encode_text(course, char_to_tile)
    unit_codes = encode_text(unit, char_to_tile)
    assert len(course_codes) <= 12, f"베스트타임 코스명 폭 초과: {course}"
    assert len(unit_codes) <= 3, f"베스트타임 단위 폭 초과: {unit}"

    clear_record(top)
    for index in range(6, 18):
        bottom.words[index] = replace_low(bottom.words[index], 0)
    for index in range(20, 23):
        bottom.words[index] = replace_low(bottom.words[index], 0)
    for index, tile in enumerate(course_codes, 6):
        bottom.words[index] = replace_low(bottom.words[index], tile)
    for index, tile in enumerate(unit_codes, 20):
        bottom.words[index] = replace_low(bottom.words[index], tile)

    patched = [word & 0xFF for word in bottom.words]
    assert patched[0] == handler
    assert patched[18:20] == original[18:20], "런타임 초 자리 원형 훼손"
    assert patched[23:25] == original[23:25], "런타임 백분의 초 자리 원형 훼손"


def build_font_resource(
    original: bytes,
    char_to_tile: dict[str, int],
    best_time_labels: dict[int, str],
) -> tuple[bytes, bytes, int]:
    raw_size = int.from_bytes(original[ORIGINAL_FONT:ORIGINAL_FONT + 2], "little")
    assert raw_size == ORIGINAL_FONT_RAW_SIZE
    raw_font, original_used = decompress(original, ORIGINAL_FONT + 2, raw_size)
    assert hashlib.sha256(raw_font).hexdigest() == ORIGINAL_FONT_RAW_SHA256

    font = FONT_BIN.read_bytes()
    glyph_map = json.loads(FONT_MAP.read_text(encoding="utf-8"))
    custom = bytearray(raw_font)
    for ch, tile in char_to_tile.items():
        custom[tile * 16:tile * 16 + 16] = glyph_2bpp(font, glyph_map, ch)
    # 처리기 번호 1~4는 첫 글리프로도 그려져 원본에서는
    # `あ/い/う/え`가 보인다. 분기 코드값은 유지하고 전용 폰트만
    # `가/나/다/라`로 바꿔 일본어를 남기지 않는다.
    assert set(best_time_labels) == {1, 2, 3, 4}
    for tile, ch in best_time_labels.items():
        custom[tile * 16:tile * 16 + 16] = glyph_2bpp(font, glyph_map, ch)

    compressed = compress(bytes(custom))
    resource = raw_size.to_bytes(2, "little") + compressed
    rebuilt, used = decompress(resource, 2, raw_size)
    assert rebuilt == bytes(custom)
    assert used == len(compressed)
    assert len(resource) <= ENDING_FONT_CAPACITY
    return resource, bytes(custom), original_used + 2


def render_preview(
    path: Path,
    records: list[Record],
    raw_font: bytes,
) -> None:
    try:
        from PIL import Image
    except ImportError:
        print("Pillow 없음: 엔딩 프리뷰 생성을 건너뜀")
        return

    width = 256
    height = LOGICAL_ROWS * 16
    image = Image.new("RGB", (width, height), (12, 12, 16))
    pixels = image.load()
    palette = ((12, 12, 16), (232, 232, 232), (112, 112, 120), (255, 255, 255))
    for pair in range(LOGICAL_ROWS):
        for row_in_pair, record in enumerate(records[pair * 2:pair * 2 + 2]):
            for x_tile, word in enumerate(record.words):
                tile = word & 0xFF
                glyph = raw_font[tile * 16:tile * 16 + 16]
                assert len(glyph) == 16
                for py in range(8):
                    plane0 = glyph[py * 2]
                    plane1 = glyph[py * 2 + 1]
                    for px in range(8):
                        bit = 7 - px
                        color = ((plane1 >> bit) & 1) * 2 + ((plane0 >> bit) & 1)
                        x = x_tile * 8 + px
                        y = pair * 16 + row_in_pair * 8 + py
                        if x < width:
                            pixels[x, y] = palette[color]
    path.parent.mkdir(parents=True, exist_ok=True)
    image.resize((width * 2, height * 2), Image.Resampling.NEAREST).save(path)


def update_snes_checksum(rom: bytearray) -> tuple[int, int]:
    rom[0xFFDC:0xFFE0] = b"\x00\x00\x00\x00"
    checksum = (sum(rom) + 0x1FE) & 0xFFFF
    complement = checksum ^ 0xFFFF
    rom[0xFFDC:0xFFDE] = complement.to_bytes(2, "little")
    rom[0xFFDE:0xFFE0] = checksum.to_bytes(2, "little")
    assert (sum(rom) & 0xFFFF) == checksum
    return checksum, complement


def build(rom_path: Path, map_path: Path, preview_path: Path) -> None:
    original = ORIGINAL_ROM.read_bytes()
    assert len(original) == ORIGINAL_SIZE
    assert zlib.crc32(original) & 0xFFFFFFFF == ORIGINAL_CRC32
    assert hashlib.md5(original).hexdigest() == ORIGINAL_MD5
    original_stream = original[STREAM_START:STREAM_END]
    assert len(original_stream) == STREAM_SIZE
    assert hashlib.sha256(original_stream).hexdigest() == STREAM_SHA256

    ledger = json.loads(TRANSLATIONS.read_text(encoding="utf-8"))
    assert ledger["source"]["stream_sha256"] == STREAM_SHA256
    assert ledger["source"]["stream_size"] == STREAM_SIZE
    entries = ledger["entries"]
    assert isinstance(entries, list) and len(entries) == 45
    by_pair = {int(entry["pair"]): entry for entry in entries}
    assert len(by_pair) == len(entries), "엔딩 번역 pair 중복"
    assert tuple(pair for pair in BEST_TIME_PAIRS if by_pair[pair]["kind"] != "best_time") == ()
    for entry in entries:
        for field in ("abbreviated",):
            assert entry[field] is False, f"엔딩 완역이 아닌 항목: pair {entry['pair']}"
        if entry["kind"] == "credit":
            assert entry["text_kr_full"] == entry["text_kr"]
        else:
            assert entry["label_kr_full"] == entry["label_kr"]
            assert entry["course_kr_full"] == entry["course_kr"]
            assert entry["unit_kr_full"] == entry["unit_kr"]

    syllables = collect_syllables(entries)
    assert len(syllables) <= len(KOREAN_TILE_CANDIDATES)
    char_to_tile = dict(
        zip(syllables, KOREAN_TILE_CANDIDATES[:len(syllables)], strict=True)
    )

    records = parse_stream(original_stream)
    nonblank_pairs: set[int] = set()
    blank_zero_pairs: list[int] = []
    row_ledger: list[dict[str, object]] = []
    for pair in range(LOGICAL_ROWS):
        top, bottom = records[pair * 2:pair * 2 + 2]
        original_lows = [word & 0xFF for word in top.words + bottom.words]
        if any(original_lows):
            nonblank_pairs.add(pair)
        elif top.count == bottom.count == 0:
            blank_zero_pairs.append(pair)

    assert len(blank_zero_pairs) == ledger["policy"]["blank_logical_rows"] == 31
    assert set(by_pair) == nonblank_pairs, (
        f"번역 원장/원문 비공백 행 불일치: "
        f"누락={sorted(nonblank_pairs - set(by_pair))}, "
        f"초과={sorted(set(by_pair) - nonblank_pairs)}"
    )

    for pair, entry in sorted(by_pair.items()):
        top, bottom = records[pair * 2:pair * 2 + 2]
        if entry["kind"] == "credit":
            capacity, start = patch_general_pair(
                top, bottom, str(entry["text_kr"]), char_to_tile,
            )
            row_ledger.append({
                "pair": pair,
                "kind": "credit",
                "top_address": f"$C7:{(STREAM_START + top.offset) & 0xFFFF:04X}",
                "bottom_address": f"$C7:{(STREAM_START + bottom.offset) & 0xFFFF:04X}",
                "capacity": capacity,
                "start_column": start,
                "text_jp": entry["text_jp"],
                "text_kr": entry["text_kr"],
            })
        else:
            patch_best_time_pair(
                pair,
                top,
                bottom,
                str(entry["course_kr"]),
                str(entry["unit_kr"]),
                char_to_tile,
            )
            row_ledger.append({
                "pair": pair,
                "kind": "best_time",
                "top_address": f"$C7:{(STREAM_START + top.offset) & 0xFFFF:04X}",
                "bottom_address": f"$C7:{(STREAM_START + bottom.offset) & 0xFFFF:04X}",
                "label_jp": entry["label_jp"],
                "label_kr": entry["label_kr"],
                "course_jp": entry["course_jp"],
                "course_kr": entry["course_kr"],
                "unit_jp": entry["unit_jp"],
                "unit_kr": entry["unit_kr"],
            })

    patched_stream = b"".join(record.encode() for record in records) + b"\xFF\xFF"
    assert len(patched_stream) == STREAM_SIZE, "위치보존 엔딩 스트림 길이 변경"
    assert len(parse_stream(patched_stream)) == PHYSICAL_RECORDS

    best_time_labels = {
        BEST_TIME_PAIRS.index(pair) + 1: str(by_pair[pair]["label_kr"])
        for pair in BEST_TIME_PAIRS
    }
    resource, custom_font, original_font_resource_size = build_font_resource(
        original, char_to_tile, best_time_labels,
    )

    rom = bytearray(rom_path.read_bytes())
    assert len(rom) == ORIGINAL_SIZE, f"헤더리스 2MB가 아님: {len(rom)}"
    current_stream = bytes(rom[STREAM_START:STREAM_END])
    assert current_stream in (original_stream, patched_stream), (
        "현재 ROM의 엔딩 스트림이 원본/승인 번역 어느 쪽과도 일치하지 않음"
    )
    current_font = bytes(rom[ENDING_FONT:ENDING_FONT + ENDING_FONT_CAPACITY])
    assert (
        all(value == 0xFF for value in current_font)
        or current_font[:len(resource)] == resource
    ), "$D9:E000 엔딩 폰트 예약 영역 충돌"
    assert bytes(rom[ENDING_FONT_POINTER:ENDING_FONT_POINTER + 3]) in (
        ORIGINAL_FONT_POINTER,
        ENDING_FONT_POINTER_BYTES,
    ), "$C3:6D03 엔딩 글꼴 포인터 원형 불일치"

    # 번역 후에도 C7 말단의 재배치 후보 풀은 건드리지 않는다. 이 값이
    # 사용자가 나중에 별도 현지화 메시지를 넣을 수 있는 실제 행 예산이다.
    c7_suffix_start = 0x080000
    while c7_suffix_start > 0x070000 and rom[c7_suffix_start - 1] == 0xFF:
        c7_suffix_start -= 1
    c7_suffix_capacity = 0x080000 - c7_suffix_start
    assert c7_suffix_capacity >= STREAM_SIZE
    relocation_spare = c7_suffix_capacity - STREAM_SIZE
    full_width_row_bytes = 2 + (2 + 31 * 2)
    additional_full_width_rows = relocation_spare // full_width_row_bytes

    rom[STREAM_START:STREAM_END] = patched_stream
    rom[ENDING_FONT:ENDING_FONT + len(resource)] = resource
    rom[ENDING_FONT_POINTER:ENDING_FONT_POINTER + 3] = ENDING_FONT_POINTER_BYTES
    checksum, complement = update_snes_checksum(rom)
    rom_path.write_bytes(rom)

    # 출력 ROM에서 자원·스트림을 다시 해제/파싱해 쓰기 결과를 검증한다.
    rebuilt_size = int.from_bytes(rom[ENDING_FONT:ENDING_FONT + 2], "little")
    rebuilt_font, rebuilt_used = decompress(rom, ENDING_FONT + 2, rebuilt_size)
    assert rebuilt_size == ORIGINAL_FONT_RAW_SIZE
    assert rebuilt_font == custom_font
    assert rebuilt_used == len(resource) - 2
    assert bytes(rom[STREAM_START:STREAM_END]) == patched_stream
    assert bytes(rom[ENDING_FONT_POINTER:ENDING_FONT_POINTER + 3]) == ENDING_FONT_POINTER_BYTES

    render_preview(preview_path, records, custom_font)
    map_path.parent.mkdir(parents=True, exist_ok=True)
    map_path.write_text(json.dumps({
        "schema": "wgp2-ending-credits-build-v1",
        "rom": str(rom_path),
        "stream": {
            "address": "$C7:A2A5",
            "size": STREAM_SIZE,
            "record_count": PHYSICAL_RECORDS,
            "logical_row_count": LOGICAL_ROWS,
            "sha256": hashlib.sha256(patched_stream).hexdigest(),
            "length_preserved": True,
        },
        "font": {
            "address": "$D9:E000",
            "resource_size": len(resource),
            "raw_size": len(custom_font),
            "original_resource_size": original_font_resource_size,
            "required_syllable_count": len(syllables),
            "candidate_tile_count": len(KOREAN_TILE_CANDIDATES),
            "remaining_candidate_tiles": len(KOREAN_TILE_CANDIDATES) - len(syllables),
            "syllables": "".join(syllables),
            "char_to_tile": {
                ch: f"{tile:02X}" for ch, tile in char_to_tile.items()
            },
        },
        "translated": {
            "credit_rows": sum(entry["kind"] == "credit" for entry in entries),
            "best_time_rows": sum(entry["kind"] == "best_time" for entry in entries),
            "abbreviated_rows": sum(bool(entry["abbreviated"]) for entry in entries),
            "rows": row_ledger,
        },
        "additional_capacity": {
            "existing_blank_logical_rows": len(blank_zero_pairs),
            "existing_blank_pair_indices": blank_zero_pairs,
            "c7_relocation_pool_start": f"$C7:{c7_suffix_start & 0xFFFF:04X}",
            "c7_relocation_pool_bytes": c7_suffix_capacity,
            "stream_bytes_after_translation": STREAM_SIZE,
            "spare_bytes_after_relocation": relocation_spare,
            "full_width_logical_row_bytes": full_width_row_bytes,
            "additional_full_width_logical_rows": additional_full_width_rows,
            "definition": "빈 상단 레코드 + 최대 31타일 본문 레코드",
        },
        "checksum": f"{checksum:04X}",
        "complement": f"{complement:04X}",
        "crc32": f"{zlib.crc32(rom) & 0xFFFFFFFF:08X}",
        "md5": hashlib.md5(rom).hexdigest(),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"엔딩 번역: 크레딧 {len(entries) - len(BEST_TIME_PAIRS)}행 + "
          f"베스트타임 {len(BEST_TIME_PAIRS)}행, 축약 0")
    print(f"엔딩 글꼴: $D9:E000 {len(resource)}B, "
          f"한글 {len(syllables)}/{len(KOREAN_TILE_CANDIDATES)}타일")
    print(f"엔딩 스트림: $C7:A2A5 {STREAM_SIZE}B 위치·길이 보존")
    print(f"빈 논리행: {len(blank_zero_pairs)}행")
    print(f"추가 독립행: 최대 폭(31타일) 기준 {additional_full_width_rows}행 "
          f"({relocation_spare}B 여유)")
    print(f"프리뷰: {preview_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rom", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--preview", type=Path, default=DEFAULT_PREVIEW)
    args = parser.parse_args()
    build(args.rom, args.map, args.preview)


if __name__ == "__main__":
    main()
