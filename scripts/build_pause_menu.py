#!/usr/bin/env python3
"""경기 중 일시정지 `이어하기 / 리타이어` 4bpp 그래픽 재삽입.

원본 경로:
  $D4:6630 LZSS(해제 0x4000B) -> $D0:1993에서 VRAM word $6000 DMA
  raw tile $140-$14B/$150-$15B -> OBJ tile $140-$14A의 16x16 조합
  composite $CF:8C57/$CF:8C73 -> $D0:1AD1에서 선택 커서와 함께 표시

두 상자의 테두리·위치·타일 수는 그대로 유지하고, 내부 일본어 픽셀만
리포의 8pt 글리프로 다시 그린다. 압축 스트림은 원래 슬롯보다 작을 때만
제자리 기록하며 ROM 크기와 헤더는 건드리지 않는다.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import lzss  # noqa: E402


ORIGINAL_ROM = ROOT / "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
ROM = ROOT / "out/wgp2_kr.smc"
FONT_BIN = ROOT / "assets/fonts/small/font-007242d37349daf3.bin"
FONT_MAP = ROOT / "assets/fonts/small/font-007242d37349daf3_glyph_map.json"
TRANSLATIONS = ROOT / "assets/translations/menu_extra_labels.json"

RESOURCE = (0xD4, 0x6630)
RAW_SIZE = 0x4000
ORIGINAL_RAW_SHA256 = "04aacd601ed745df74f78b0e26f3eb47e3f4a066e290d6688a55609b218c2019"
ORIGINAL_STREAM_SIZE = 5333
TARGET_TILES = tuple(range(0x140, 0x14C)) + tuple(range(0x150, 0x15C))
ORIGINAL_TARGET_SHA256 = "f01f7f5a64260d8fe518856a50b1f551816519539fcc688727a353fd3a444991"


def file_offset(bank: int, address: int) -> int:
    return ((bank & 0x3F) << 16) | address


def load_label(entry_id: str) -> tuple[str, int]:
    data = json.loads(TRANSLATIONS.read_text(encoding="utf-8"))
    matches = [entry for entry in data["entries"] if entry.get("id") == entry_id]
    assert len(matches) == 1, f"추가 메뉴 번역 ID 불일치: {entry_id}"
    entry = matches[0]
    assert entry.get("status") == "implemented", f"미구현 메뉴 번역: {entry_id}"
    for field in ("text_jp", "text_kr_full", "text_kr"):
        assert isinstance(entry.get(field), str), f"{entry_id}: {field} 누락"
    cells = entry.get("slot_cells")
    assert isinstance(cells, int)
    return entry["text_kr"], cells


def decode_4bpp(tile: bytes) -> list[list[int]]:
    assert len(tile) == 32
    pixels = [[0] * 8 for _ in range(8)]
    for y in range(8):
        plane0, plane1 = tile[y * 2:y * 2 + 2]
        plane2, plane3 = tile[16 + y * 2:18 + y * 2]
        for x in range(8):
            bit = 7 - x
            pixels[y][x] = (
                ((plane0 >> bit) & 1)
                | (((plane1 >> bit) & 1) << 1)
                | (((plane2 >> bit) & 1) << 2)
                | (((plane3 >> bit) & 1) << 3)
            )
    return pixels


def encode_4bpp(pixels: list[list[int]]) -> bytes:
    assert len(pixels) == 8 and all(len(row) == 8 for row in pixels)
    tile = bytearray(32)
    for y, row in enumerate(pixels):
        for x, value in enumerate(row):
            assert 0 <= value < 16
            bit = 7 - x
            for plane in range(4):
                if value & (1 << plane):
                    tile[(plane // 2) * 16 + y * 2 + (plane & 1)] |= 1 << bit
    return bytes(tile)


def page_canvas(raw: bytes) -> list[list[int]]:
    """raw tile $100-$1FF를 타일뷰어와 같은 128x128 페이지로 펼친다."""
    canvas = [[0] * 128 for _ in range(128)]
    for local_tile in range(0x100):
        tile_id = 0x100 + local_tile
        pixels = decode_4bpp(raw[tile_id * 32:tile_id * 32 + 32])
        left = (local_tile % 16) * 8
        top = (local_tile // 16) * 8
        for y, row in enumerate(pixels):
            canvas[top + y][left:left + 8] = row
    return canvas


def write_page(raw: bytearray, canvas: list[list[int]]) -> None:
    for local_tile in range(0x100):
        tile_id = 0x100 + local_tile
        left = (local_tile % 16) * 8
        top = (local_tile // 16) * 8
        pixels = [row[left:left + 8] for row in canvas[top:top + 8]]
        raw[tile_id * 32:tile_id * 32 + 32] = encode_4bpp(pixels)


def target_bytes(raw: bytes) -> bytes:
    return b"".join(raw[tile * 32:tile * 32 + 32] for tile in TARGET_TILES)


def draw_label(
    canvas: list[list[int]],
    font: bytes,
    glyph_map: dict[str, int],
    text: str,
    left: int,
    cells: int,
) -> None:
    assert len(text) == cells == 4, f"일시정지 라벨은 정확히 4셀이어야 함: {text!r}"

    # 원본 48x16 조각은 바깥 3/1/14 팔레트의 3중 테두리다. 실제 내부
    # x=3..44, y=3..12만 지워야 좌우 inner E선과 하단 E/1/3선이 보존된다.
    before = [row[left:left + 48] for row in canvas[32:48]]
    for y in range(35, 45):
        for x in range(left + 3, left + 45):
            canvas[y][x] = 0x0F if (x + y) & 1 else 0x00

    # 48px 상자의 44px 내부에 32px(4x8) 글자를 가운데 배치한다.
    text_left = left + 7
    text_top = 36
    for index, ch in enumerate(text):
        assert ch in glyph_map, f"8pt 폰트에 없는 일시정지 음절: {ch!r}"
        glyph = font[glyph_map[ch] * 8:glyph_map[ch] * 8 + 8]
        assert len(glyph) == 8
        for y, bits in enumerate(glyph):
            for x in range(8):
                if bits & (1 << (7 - x)):
                    canvas[text_top + y][text_left + index * 8 + x] = 0x0E

    # 글자 내부가 아닌 테두리 픽셀은 원본과 비트 단위로 같아야 한다.
    for y in range(32, 48):
        for x in range(left, left + 48):
            if 35 <= y < 45 and left + 3 <= x < left + 45:
                continue
            assert canvas[y][x] == before[y - 32][x - left], (
                f"일시정지 테두리 변경: half={left // 48} x={x-left} y={y-32}"
            )


def build() -> None:
    original_rom = ORIGINAL_ROM.read_bytes()
    rom = bytearray(ROM.read_bytes())
    assert len(rom) == len(original_rom) == 0x200000
    assert rom[0xFFD7] == original_rom[0xFFD7]

    source = file_offset(*RESOURCE)
    raw_size = int.from_bytes(original_rom[source:source + 2], "little")
    assert raw_size == RAW_SIZE
    original_raw, used = lzss.decompress(original_rom, source + 2, raw_size)
    assert used == ORIGINAL_STREAM_SIZE
    assert hashlib.sha256(original_raw).hexdigest() == ORIGINAL_RAW_SHA256
    assert hashlib.sha256(target_bytes(original_raw)).hexdigest() == ORIGINAL_TARGET_SHA256

    # 앞 단계가 이 자원을 먼저 바꿨다면 조용히 덮어쓰지 않는다.
    current_raw, current_used = lzss.decompress(rom, source + 2, raw_size)
    assert current_used == ORIGINAL_STREAM_SIZE
    assert current_raw == original_raw, "$D4:6630 자원이 앞 단계에서 변경됨"

    font = FONT_BIN.read_bytes()
    glyph_map = json.loads(FONT_MAP.read_text(encoding="utf-8"))
    canvas = page_canvas(original_raw)
    continue_text, continue_cells = load_label("pause_continue")
    retire_text, retire_cells = load_label("pause_retire")
    draw_label(canvas, font, glyph_map, continue_text, 0, continue_cells)
    draw_label(canvas, font, glyph_map, retire_text, 48, retire_cells)

    edited_raw = bytearray(original_raw)
    write_page(edited_raw, canvas)
    target_set = set(TARGET_TILES)
    for tile in range(RAW_SIZE // 32):
        if tile not in target_set:
            start = tile * 32
            assert edited_raw[start:start + 32] == original_raw[start:start + 32], (
                f"일시정지 대상 밖 타일 변경: ${tile:03X}"
            )

    compressed = lzss.compress(bytes(edited_raw))
    assert len(compressed) <= ORIGINAL_STREAM_SIZE, (
        f"일시정지 그래픽 압축 초과: {len(compressed)}>{ORIGINAL_STREAM_SIZE}B"
    )
    rom[source + 2:source + 2 + len(compressed)] = compressed
    back, _ = lzss.decompress(rom, source + 2, raw_size)
    assert back == bytes(edited_raw), "일시정지 그래픽 재압축 왕복 실패"
    ROM.write_bytes(rom)
    print(f"경기 일시정지 메뉴 한글화 완료 -> {ROM}")
    print(
        f"  $D4:6630 raw tiles $140-$14B/$150-$15B: "
        f"{continue_text} / {retire_text}"
    )
    print(f"  LZSS {len(compressed)}/{ORIGINAL_STREAM_SIZE}B, ROM 2MB/헤더 보존")


if __name__ == "__main__":
    build()
