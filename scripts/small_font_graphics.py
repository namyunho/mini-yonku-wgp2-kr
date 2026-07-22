#!/usr/bin/env python3
"""공통 8×8 소형 폰트의 고정 그래픽 라벨 조립 도우미."""

from __future__ import annotations

import json
from pathlib import Path


def load_translation(path: Path, entry_id: str) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    matches = [entry for entry in data["entries"] if entry.get("id") == entry_id]
    assert len(matches) == 1, f"추가 메뉴 번역 ID 불일치: {entry_id}"
    entry = matches[0]
    assert entry.get("status") == "implemented", f"미구현 메뉴 번역: {entry_id}"
    for field in ("text_jp", "text_kr_full", "text_kr"):
        assert isinstance(entry.get(field), str), f"{entry_id}: {field} 누락"
    return entry["text_kr"]


def _decode_2bpp(tile: bytes) -> list[list[int]]:
    assert len(tile) == 16
    pixels = [[0] * 8 for _ in range(8)]
    for y in range(8):
        plane0, plane1 = tile[y * 2:y * 2 + 2]
        for x in range(8):
            bit = 7 - x
            pixels[y][x] = ((plane0 >> bit) & 1) | (((plane1 >> bit) & 1) << 1)
    return pixels


def _encode_2bpp(pixels: list[list[int]]) -> bytes:
    assert len(pixels) == 8 and all(len(row) == 8 for row in pixels)
    tile = bytearray(16)
    for y, row in enumerate(pixels):
        for x, value in enumerate(row):
            assert 0 <= value < 4
            bit = 7 - x
            if value & 1:
                tile[y * 2] |= 1 << bit
            if value & 2:
                tile[y * 2 + 1] |= 1 << bit
    return bytes(tile)


def _hangul_tile(font: bytes, glyph_map: dict[str, int], ch: str) -> bytes:
    assert ch in glyph_map, f"8pt 폰트에 없는 음절: {ch!r}"
    glyph = font[glyph_map[ch] * 8:glyph_map[ch] * 8 + 8]
    assert len(glyph) == 8
    tile = bytearray(16)
    for y in range(8):
        source_y = y - 1
        if 0 <= source_y < 8:
            tile[y * 2] = glyph[source_y]
    return bytes(tile)


def pack_tight_2bpp_label(
    raw_font: bytes,
    font: bytes,
    glyph_map: dict[str, int],
    text: str,
    literal_tiles: dict[str, int],
    expected_tiles: int,
) -> bytes:
    """글리프의 빈 좌우 열을 잘라 고정 타일 수의 연속 비트맵으로 조립한다."""
    glyphs: list[list[list[int]]] = []
    for ch in text:
        if "가" <= ch <= "힣":
            tile = _hangul_tile(font, glyph_map, ch)
        else:
            assert ch in literal_tiles, f"고정 그래픽 라벨 문자 미지원: {ch!r}"
            tile_id = literal_tiles[ch]
            tile = raw_font[tile_id * 16:tile_id * 16 + 16]
        pixels = _decode_2bpp(tile)
        assert {value for row in pixels for value in row} <= {0, 1}
        occupied = [x for x in range(8) if any(pixels[y][x] for y in range(8))]
        assert occupied, f"빈 글리프: {ch!r}"
        glyphs.append([row[min(occupied):max(occupied) + 1] for row in pixels])

    width = sum(len(glyph[0]) for glyph in glyphs)
    assert width == expected_tiles * 8, (
        f"고정 그래픽 라벨 폭 불일치: {text!r} {width}px != {expected_tiles * 8}px"
    )
    bitmap = [sum((glyph[y] for glyph in glyphs), []) for y in range(8)]
    out = bytearray()
    for tile_index in range(expected_tiles):
        left = tile_index * 8
        out += _encode_2bpp([row[left:left + 8] for row in bitmap])
    return bytes(out)
