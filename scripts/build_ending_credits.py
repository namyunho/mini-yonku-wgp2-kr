#!/usr/bin/env python3
"""실제 엔딩 스크롤 크레딧·베스트타임의 전용 8×8 한글화 빌더.

에피소드 사이의 VICTORYS 로고가 아니라 $C7:A2A5의 최종 엔딩 행
명령열을 패치한다. 원본 154개 물리 레코드와 77개 논리행의 순서를
유지하고, 현지화 메시지를 위해 C7 말단의 검증된 자유 영역으로 명령열을
재배치한다. $D9:0000 공용 글꼴은 건드리지 않고 $D9:E000에 엔딩 전용
사본을 둔다.
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
STREAM_POINTER_INSTRUCTION = 0x038275  # $C3:8275 LDA #$A2A5
STREAM_POINTER_OPERAND = STREAM_POINTER_INSTRUCTION + 1
ORIGINAL_STREAM_POINTER = b"\xA5\xA2"
RELOCATED_STREAM_START = 0x07EE7B  # $C7:EE7B
RELOCATED_STREAM_END = 0x080000
RELOCATED_STREAM_CAPACITY = RELOCATED_STREAM_END - RELOCATED_STREAM_START
RELOCATED_STREAM_POINTER = (
    RELOCATED_STREAM_START & 0xFFFF
).to_bytes(2, "little")
LOGICAL_ROWS = 77
PHYSICAL_RECORDS = 154
INSERT_BEFORE_SOURCE_PAIR = 63
ADDED_LOGICAL_ROWS = 0
ACTIVE_LOGICAL_ROWS = LOGICAL_ROWS + ADDED_LOGICAL_ROWS
ACTIVE_PHYSICAL_RECORDS = PHYSICAL_RECORDS + ADDED_LOGICAL_ROWS * 2
BEST_TIME_PAIRS = (65, 66, 67, 68)

ORIGINAL_FONT = 0x190000  # $D9:0000
ORIGINAL_FONT_RAW_SIZE = 0x1760
ORIGINAL_FONT_RAW_SHA256 = "78dfbb47aff74d3d6ccfa055ab0cb5975cdf779fcc617edb9db2ebf266bb43dd"
ENDING_FONT = 0x19E000  # $D9:E000
ENDING_FONT_CAPACITY = 0x2000
# 실제 최종 엔딩 첫 진입은 $C3:6B31의 로더를 거쳐 $C3:6B35를 읽는다.
# 같은 크레딧 오브젝트의 대체 초기화 경로 $C3:6CFF도 $C3:6D03을 읽으므로
# 두 경로를 모두 엔딩 전용 글꼴로 통일한다.
ENDING_FONT_POINTERS = (
    0x036B35,  # $C3:6B35, 실제 첫 진입
    0x036D03,  # $C3:6D03, 대체 초기화/재진입
)
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
PUNCTUATION_1BPP = {
    ",": bytes((0x00, 0x00, 0x00, 0x00, 0x00, 0x18, 0x18, 0x10)),
    ".": bytes((0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x18, 0x18)),
    "·": bytes((0x00, 0x00, 0x00, 0x18, 0x18, 0x00, 0x00, 0x00)),
}


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


def parse_stream(
    stream: bytes,
    expected_records: int = PHYSICAL_RECORDS,
) -> list[Record]:
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
    assert len(records) == expected_records
    return records


def encoded_stream_size(
    data: bytes,
    physical_records: int = ACTIVE_PHYSICAL_RECORDS,
) -> int:
    pos = 0
    for _ in range(physical_records):
        assert pos + 2 <= len(data), "엔딩 스트림 헤더 범위 초과"
        pos += 2 + data[pos] * 2
        assert pos <= len(data), "엔딩 스트림 레코드 범위 초과"
    assert data[pos:pos + 2] == b"\xFF\xFF", "엔딩 스트림 종료어 없음"
    return pos + 2


def collect_custom_chars(
    entries: list[dict[str, object]],
    message_lines: list[dict[str, object]],
) -> list[str]:
    texts: list[str] = []
    for entry in entries:
        fields = (
            ("text_kr",)
            if entry["kind"] == "credit"
            else ("label_kr", "course_kr", "unit_kr")
        )
        texts.extend(str(entry[field]) for field in fields)
    texts.extend(str(line["text"]) for line in message_lines)

    custom_chars: list[str] = []
    for text in texts:
        for ch in text:
            if (
                ("가" <= ch <= "힣" or ch in PUNCTUATION_1BPP)
                and ch not in custom_chars
            ):
                custom_chars.append(ch)
    return custom_chars


def collect_syllables(entries: list[dict[str, object]]) -> list[str]:
    """기존 분석·도구 호환용: 정규 크레딧의 한글 음절만 모은다."""
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


def custom_glyph_2bpp(
    font: bytes,
    glyph_map: dict[str, int],
    ch: str,
) -> bytes:
    if ch in PUNCTUATION_1BPP:
        out = bytearray(16)
        for row, value in enumerate(PUNCTUATION_1BPP[ch]):
            out[row * 2] = value
        return bytes(out)
    return glyph_2bpp(font, glyph_map, ch)


def encode_text(text: str, char_to_tile: dict[str, int]) -> list[int]:
    encoded: list[int] = []
    for ch in text:
        if ch == " ":
            encoded.append(0x00)
        elif "가" <= ch <= "힣" or ch in PUNCTUATION_1BPP:
            encoded.append(char_to_tile[ch])
        elif ch in LATIN_UPPER:
            encoded.append(LATIN_UPPER[ch])
        else:
            raise AssertionError(f"엔딩 직접 타일로 인코딩할 수 없는 문자: {ch!r}")
    return encoded


def patch_message_pair(
    top: Record,
    bottom: Record,
    text: str,
    char_to_tile: dict[str, int],
    start_column: int | None = None,
) -> tuple[int, int]:
    assert top.count == bottom.count == 0
    assert top.control == bottom.control == 0x20
    encoded = encode_text(text, char_to_tile)
    assert encoded, "빈 현지화 메시지 행"
    assert len(encoded) <= 31, f"현지화 메시지 행 폭 초과: {text} {len(encoded)}>31"

    start = (
        (32 - len(encoded)) // 2
        if start_column is None
        else start_column
    )
    assert 0 <= start and start + len(encoded) <= 31, (
        f"현지화 메시지 행 배치 초과: {text} start={start}"
    )
    top.words = []
    bottom.words = [0x2000] * start + [
        0x2000 | tile for tile in encoded
    ]
    top.count = 0
    bottom.count = len(bottom.words)
    assert bottom.count <= 31
    return len(encoded), start


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
        custom[tile * 16:tile * 16 + 16] = custom_glyph_2bpp(
            font, glyph_map, ch,
        )
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

    logical_rows = len(records) // 2
    assert len(records) % 2 == 0
    width = 256
    height = logical_rows * 16
    image = Image.new("RGB", (width, height), (12, 12, 16))
    pixels = image.load()
    palette = ((12, 12, 16), (232, 232, 232), (112, 112, 120), (255, 255, 255))
    for pair in range(logical_rows):
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
    assert original[
        STREAM_POINTER_INSTRUCTION:STREAM_POINTER_OPERAND + 2
    ] == b"\xA9" + ORIGINAL_STREAM_POINTER

    ledger = json.loads(TRANSLATIONS.read_text(encoding="utf-8"))
    assert ledger["source"]["stream_sha256"] == STREAM_SHA256
    assert ledger["source"]["stream_size"] == STREAM_SIZE
    assert ledger["policy"]["preserve_source_record_order"] is True
    assert (
        ledger["policy"]["insert_localization_logical_rows"]
        == ADDED_LOGICAL_ROWS
    )
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

    message = ledger["localization_message"]
    assert message["source_type"] == "user_authored"
    assert message["text_jp"] is None
    assert message["abbreviated"] is False
    message_lines = message["lines"]
    assert isinstance(message_lines, list) and message_lines
    message_by_pair = {
        int(line["pair"]): str(line["text"]) for line in message_lines
    }
    message_start_by_pair = {
        int(line["pair"]): (
            int(line["start_column"])
            if "start_column" in line
            else None
        )
        for line in message_lines
    }
    assert len(message_by_pair) == len(message_lines), "현지화 메시지 pair 중복"
    first_message_pair = min(message_by_pair)
    last_message_pair = max(message_by_pair)
    rendered_message = "\n".join(
        message_by_pair.get(pair, "")
        for pair in range(first_message_pair, last_message_pair + 1)
    )
    assert rendered_message == message["text_kr"]
    assert " ".join(rendered_message.split()) == " ".join(
        str(message["text_kr_full"]).split()
    ), "현지화 메시지 완문/실제 삽입문 내용 불일치"

    custom_chars = collect_custom_chars(entries, message_lines)
    syllables = [ch for ch in custom_chars if "가" <= ch <= "힣"]
    punctuation = [ch for ch in custom_chars if ch in PUNCTUATION_1BPP]
    assert len(custom_chars) <= len(KOREAN_TILE_CANDIDATES)
    char_to_tile = dict(
        zip(
            custom_chars,
            KOREAN_TILE_CANDIDATES[:len(custom_chars)],
            strict=True,
        )
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
    source_message_pairs = {
        pair for pair in message_by_pair if pair < INSERT_BEFORE_SOURCE_PAIR
    }
    inserted_message_pairs = set(message_by_pair) - source_message_pairs
    assert source_message_pairs <= set(blank_zero_pairs)
    assert inserted_message_pairs == set(range(
        INSERT_BEFORE_SOURCE_PAIR,
        INSERT_BEFORE_SOURCE_PAIR + ADDED_LOGICAL_ROWS,
    ))
    assert min(message_by_pair) > 48 and max(message_by_pair) < (
        INSERT_BEFORE_SOURCE_PAIR + ADDED_LOGICAL_ROWS
    ), (
        "현지화 메시지는 총괄 프로듀서 이름과 베스트타임 사이여야 함"
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
                "label_jp": entry["label_jp"],
                "label_kr": entry["label_kr"],
                "course_jp": entry["course_jp"],
                "course_kr": entry["course_kr"],
                "unit_jp": entry["unit_jp"],
                "unit_kr": entry["unit_kr"],
            })

    base_patched_stream = (
        b"".join(record.encode() for record in records) + b"\xFF\xFF"
    )
    assert len(base_patched_stream) == STREAM_SIZE
    assert len(parse_stream(base_patched_stream)) == PHYSICAL_RECORDS

    insert_at = INSERT_BEFORE_SOURCE_PAIR * 2
    records[insert_at:insert_at] = [
        Record(offset=0, count=0, control=0x20, words=[])
        for _ in range(ADDED_LOGICAL_ROWS * 2)
    ]
    assert len(records) == ACTIVE_PHYSICAL_RECORDS

    message_ledger: list[dict[str, object]] = []
    for pair, text in sorted(message_by_pair.items()):
        top, bottom = records[pair * 2:pair * 2 + 2]
        width, start = patch_message_pair(
            top,
            bottom,
            text,
            char_to_tile,
            message_start_by_pair[pair],
        )
        message_ledger.append({
            "pair": pair,
            "kind": "localization_message",
            "width": width,
            "start_column": start,
            "text_kr": text,
        })

    relocated_stream = (
        b"".join(record.encode() for record in records) + b"\xFF\xFF"
    )
    assert len(relocated_stream) <= RELOCATED_STREAM_CAPACITY
    active_records = parse_stream(
        relocated_stream, ACTIVE_PHYSICAL_RECORDS,
    )
    assert len(active_records) == ACTIVE_PHYSICAL_RECORDS
    for row in row_ledger:
        source_pair = int(row["pair"])
        active_pair = (
            source_pair + ADDED_LOGICAL_ROWS
            if source_pair >= INSERT_BEFORE_SOURCE_PAIR
            else source_pair
        )
        row["active_pair"] = active_pair
        top, bottom = active_records[
            active_pair * 2:active_pair * 2 + 2
        ]
        row["top_address"] = (
            f"$C7:{(RELOCATED_STREAM_START + top.offset) & 0xFFFF:04X}"
        )
        row["bottom_address"] = (
            f"$C7:{(RELOCATED_STREAM_START + bottom.offset) & 0xFFFF:04X}"
        )
    for row in message_ledger:
        pair = int(row["pair"])
        top, bottom = active_records[pair * 2:pair * 2 + 2]
        row["top_address"] = (
            f"$C7:{(RELOCATED_STREAM_START + top.offset) & 0xFFFF:04X}"
        )
        row["bottom_address"] = (
            f"$C7:{(RELOCATED_STREAM_START + bottom.offset) & 0xFFFF:04X}"
        )

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
    assert current_stream in (original_stream, base_patched_stream), (
        "현재 ROM의 엔딩 스트림이 원본/승인 번역 어느 쪽과도 일치하지 않음"
    )
    current_font = bytes(rom[ENDING_FONT:ENDING_FONT + ENDING_FONT_CAPACITY])
    assert (
        all(value == 0xFF for value in current_font)
        or current_font[:len(resource)] == resource
    ), "$D9:E000 엔딩 폰트 예약 영역 충돌"
    for pointer in ENDING_FONT_POINTERS:
        assert bytes(rom[pointer:pointer + 3]) in (
            ORIGINAL_FONT_POINTER,
            ENDING_FONT_POINTER_BYTES,
        ), f"${0xC00000 | pointer:06X} 엔딩 글꼴 포인터 원형 불일치"

    current_stream_pointer = bytes(
        rom[STREAM_POINTER_OPERAND:STREAM_POINTER_OPERAND + 2]
    )
    assert rom[STREAM_POINTER_INSTRUCTION] == 0xA9
    assert current_stream_pointer in (
        ORIGINAL_STREAM_POINTER,
        RELOCATED_STREAM_POINTER,
    ), "$C3:8275 엔딩 스트림 포인터 원형 불일치"
    relocation_area = bytes(
        rom[RELOCATED_STREAM_START:RELOCATED_STREAM_END]
    )
    assert (
        all(value == 0xFF for value in relocation_area)
        or (
            encoded_stream_size(relocation_area) == len(relocated_stream)
            and relocation_area[:len(relocated_stream)] == relocated_stream
            and all(
                value == 0xFF for value in relocation_area[len(relocated_stream):]
            )
        )
    ), "$C7:EE7B 엔딩 스트림 재배치 영역 충돌"

    relocation_spare = RELOCATED_STREAM_CAPACITY - len(relocated_stream)
    full_width_row_bytes = 2 + (2 + 31 * 2)
    additional_full_width_rows = relocation_spare // full_width_row_bytes

    rom[STREAM_START:STREAM_END] = base_patched_stream
    rom[
        RELOCATED_STREAM_START:
        RELOCATED_STREAM_START + len(relocated_stream)
    ] = relocated_stream
    rom[
        STREAM_POINTER_OPERAND:
        STREAM_POINTER_OPERAND + 2
    ] = RELOCATED_STREAM_POINTER
    rom[ENDING_FONT:ENDING_FONT + len(resource)] = resource
    for pointer in ENDING_FONT_POINTERS:
        rom[pointer:pointer + 3] = ENDING_FONT_POINTER_BYTES
    checksum, complement = update_snes_checksum(rom)
    rom_path.write_bytes(rom)

    # 출력 ROM에서 자원·스트림을 다시 해제/파싱해 쓰기 결과를 검증한다.
    rebuilt_size = int.from_bytes(rom[ENDING_FONT:ENDING_FONT + 2], "little")
    rebuilt_font, rebuilt_used = decompress(rom, ENDING_FONT + 2, rebuilt_size)
    assert rebuilt_size == ORIGINAL_FONT_RAW_SIZE
    assert rebuilt_font == custom_font
    assert rebuilt_used == len(resource) - 2
    assert bytes(rom[STREAM_START:STREAM_END]) == base_patched_stream
    assert bytes(
        rom[
            RELOCATED_STREAM_START:
            RELOCATED_STREAM_START + len(relocated_stream)
        ]
    ) == relocated_stream
    assert bytes(
        rom[STREAM_POINTER_OPERAND:STREAM_POINTER_OPERAND + 2]
    ) == RELOCATED_STREAM_POINTER
    for pointer in ENDING_FONT_POINTERS:
        assert bytes(rom[pointer:pointer + 3]) == ENDING_FONT_POINTER_BYTES

    render_preview(preview_path, active_records, custom_font)
    map_path.parent.mkdir(parents=True, exist_ok=True)
    map_path.write_text(json.dumps({
        "schema": "wgp2-ending-credits-build-v1",
        "rom": str(rom_path),
        "stream": {
            "address": "$C7:EE7B",
            "pointer_operand_address": "$C3:8276",
            "size": len(relocated_stream),
            "record_count": ACTIVE_PHYSICAL_RECORDS,
            "logical_row_count": ACTIVE_LOGICAL_ROWS,
            "source_record_count": PHYSICAL_RECORDS,
            "source_logical_row_count": LOGICAL_ROWS,
            "inserted_logical_rows": ADDED_LOGICAL_ROWS,
            "sha256": hashlib.sha256(relocated_stream).hexdigest(),
            "record_count_preserved": True,
            "relocated": True,
            "original_shadow_address": "$C7:A2A5",
            "original_shadow_size": len(base_patched_stream),
            "original_shadow_sha256": hashlib.sha256(
                base_patched_stream
            ).hexdigest(),
        },
        "font": {
            "address": "$D9:E000",
            "loader_pointer_addresses": [
                f"${0xC00000 | pointer:06X}"
                for pointer in ENDING_FONT_POINTERS
            ],
            "resource_size": len(resource),
            "raw_size": len(custom_font),
            "original_resource_size": original_font_resource_size,
            "required_syllable_count": len(syllables),
            "required_punctuation": punctuation,
            "required_custom_glyph_count": len(custom_chars),
            "candidate_tile_count": len(KOREAN_TILE_CANDIDATES),
            "remaining_candidate_tiles": (
                len(KOREAN_TILE_CANDIDATES) - len(custom_chars)
            ),
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
        "localization_message": {
            "text_kr_full": message["text_kr_full"],
            "text_kr": message["text_kr"],
            "abbreviated": message["abbreviated"],
            "rows": message_ledger,
        },
        "additional_capacity": {
            "existing_blank_logical_rows": len(blank_zero_pairs),
            "existing_blank_pair_indices": blank_zero_pairs,
            "used_message_pair_indices": sorted(message_by_pair),
            "remaining_blank_logical_rows": (
                len(blank_zero_pairs) - len(source_message_pairs)
            ),
            "c7_relocation_pool_start": "$C7:EE7B",
            "c7_relocation_pool_bytes": RELOCATED_STREAM_CAPACITY,
            "stream_bytes_after_translation": len(relocated_stream),
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
          f"사용자 글리프 {len(custom_chars)}/{len(KOREAN_TILE_CANDIDATES)}타일")
    record_note = "원본 154레코드 순서 보존"
    if ADDED_LOGICAL_ROWS:
        record_note += f" + 메시지 {ADDED_LOGICAL_ROWS * 2}레코드"
    print(f"엔딩 스트림: $C7:EE7B {len(relocated_stream)}B, "
          f"{record_note}")
    print(f"현지화 메시지: {len(message_by_pair)}행, 축약 0")
    print(f"남은 빈 논리행: "
          f"{len(blank_zero_pairs) - len(source_message_pairs)}행")
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
