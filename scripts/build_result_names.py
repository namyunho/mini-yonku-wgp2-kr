#!/usr/bin/env python3
"""Result 화면의 동적 선수명 2bpp 아틀라스를 한글로 재삽입한다.

경로(실측/정적 교차검증):
  $D9:1DDC LZSS -> $7F:0000 (0x2780 bytes)
  $C1:CBAF racer ID별 (시작, 끝) 타일 좌표표 110개
  $C1:678A -> $C1:6801 DMA: $7F:10xx/$11xx -> Result 이름 슬롯

공용 SJIS 폰트나 VRAM 로더를 바꾸지 않고 Result 전용 압축 자산만 수정한다.
원문/완역/실제 표시문은 assets/translations/result_names.json에 분리 보관한다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import lzss  # noqa: E402


ORIGINAL_ROM = ROOT / "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
DEFAULT_ROM = ROOT / "out/wgp2_kr.smc"
TRANSLATIONS = ROOT / "assets/translations/result_names.json"
FONT_BIN = ROOT / "assets/fonts/small/font-007242d37349daf3.bin"
FONT_MAP = ROOT / "assets/fonts/small/font-007242d37349daf3_glyph_map.json"
DEFAULT_PREVIEW = ROOT / "out/result_names_preview.png"
DEFAULT_MANIFEST = ROOT / "out/result_names_manifest.json"
DEFAULT_TEMPLATE = ROOT / "assets/graphics/result/names/result_names_workshop_256px.png"
DEFAULT_GUIDE = ROOT / "assets/graphics/result/names/result_names_translation.tsv"
DEFAULT_ALIGNMENT_TEMPLATE = ROOT / "out/result_names_alignment_workshop_256px.png"
DEFAULT_ALIGNMENT_GUIDE = ROOT / "out/result_names_alignment_guide.tsv"
DEFAULT_ALIGNMENT_MANIFEST = ROOT / "out/result_names_alignment_manifest.json"

ASSET_OFFSET = 0x191DDC       # $D9:1DDC, 2-byte decompressed-length header
NEXT_ASSET_OFFSET = 0x1930B1  # $D9:30B1, verified next loader source
DECOMPRESSED_SIZE = 0x2780
RACER_TABLE_OFFSET = 0x01CBAF  # $C1:CBAF
RACER_COUNT = 110
TILE_BYTES = 16
FONT_Y = 4
ATLAS_COLS = 16
ATLAS_ROWS = (DECOMPRESSED_SIZE // TILE_BYTES + ATLAS_COLS - 1) // ATLAS_COLS
ATLAS_SIZE = (ATLAS_COLS * 8, ATLAS_ROWS * 8)
PALETTE_RGB = (
    (255, 0, 255),
    (255, 255, 255),
    (128, 128, 128),
    (0, 0, 0),
)
# 일부 PNG 편집기가 불투명 검정에 1단계 색 편차를 남긴다. 수동 작업지의
# 편집 칸에서만 이 한 색을 검정으로 정규화한다(그 밖의 임의 색은 계속 거부).
WORKSHOP_COLOR_ALIASES = {
    (1, 0, 1): 3,
}


ASCII_5X7 = {
    "D": (
        "11110",
        "10001",
        "10001",
        "10001",
        "10001",
        "10001",
        "11110",
    ),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01110", "10001", "10000", "10111", "10001", "10001", "01110"),
    "J": ("00111", "00010", "00010", "00010", "00010", "10010", "01100"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
}


def parse_span(text: str) -> tuple[int, int]:
    start, end = text.split("-", 1)
    return int(start, 16), int(end, 16)


def tile_indices(start: int, end: int) -> list[int]:
    """$C1:678A와 같은 방식으로 16타일 행 경계를 건너뛴다.

    이름의 위쪽 타일이 행 끝에서 감기면 바로 다음 행(아래쪽 타일)을
    건너뛰고 그 다음 위쪽 행에서 이어진다.
    """
    if end < start:
        raise ValueError(f"역방향 타일 범위: {start:04X}-{end:04X}")
    if end - start < 0x10:
        return list(range(start, end + 1))
    first = list(range(start, (start | 0x0F) + 1))
    second = list(range(end & 0xFFF0, end + 1))
    return first + second


def decode_asset(rom: bytes) -> tuple[bytes, int]:
    size = int.from_bytes(rom[ASSET_OFFSET:ASSET_OFFSET + 2], "little")
    if size != DECOMPRESSED_SIZE:
        raise SystemExit(f"$D9:1DDC 해제 길이 불일치: 0x{size:04X}")
    data, used = lzss.decompress(rom, ASSET_OFFSET + 2, size)
    return data, used


def read_racer_spans(rom: bytes) -> dict[int, tuple[int, int]]:
    result = {}
    for racer_id in range(RACER_COUNT):
        pos = RACER_TABLE_OFFSET + racer_id * 4
        result[racer_id] = (
            int.from_bytes(rom[pos:pos + 2], "little"),
            int.from_bytes(rom[pos + 2:pos + 4], "little"),
        )
    return result


def validate_corpus(corpus: dict, racer_spans: dict[int, tuple[int, int]]) -> list[dict]:
    labels = corpus.get("labels")
    if not isinstance(labels, list):
        raise SystemExit("result_names.json: labels 배열 없음")

    seen_ids: set[int] = set()
    for entry in labels:
        ids = entry.get("racer_ids")
        if not isinstance(ids, list) or not ids:
            raise SystemExit(f"racer_ids 누락: {entry}")
        span = parse_span(entry["tile_span"])
        source_span = parse_span(entry.get("original_tile_span", entry["tile_span"]))
        indices = tile_indices(*span)
        for racer_id in ids:
            if racer_id in seen_ids:
                raise SystemExit(f"racer ID 중복: {racer_id}")
            if racer_id not in racer_spans:
                raise SystemExit(f"racer ID 범위 초과: {racer_id}")
            if racer_spans[racer_id] not in (source_span, span):
                raise SystemExit(
                    f"ID {racer_id} 타일표 불일치: "
                    f"원본 JSON {source_span[0]:04X}-{source_span[1]:04X}, "
                    f"표시 JSON {span[0]:04X}-{span[1]:04X}, "
                    f"ROM {racer_spans[racer_id][0]:04X}-{racer_spans[racer_id][1]:04X}"
                )
            seen_ids.add(racer_id)

        full = entry.get("text_kr_full")
        display = entry.get("text_kr_display")
        abbreviated = entry.get("abbreviated")
        if entry.get("render_mode", "replace") == "replace":
            if not isinstance(full, str) or not isinstance(display, str):
                raise SystemExit(f"번역 누락: ID {ids}")
            if abbreviated != (full != display):
                raise SystemExit(
                    f"축약 플래그 불일치 ID {ids}: full={full!r}, display={display!r}, "
                    f"abbreviated={abbreviated!r}"
                )
            if len(display) > len(indices):
                raise SystemExit(
                    f"타일 용량 초과 ID {ids}: {display!r} {len(display)}자 > {len(indices)}타일"
                )

    expected = set(range(RACER_COUNT))
    if seen_ids != expected:
        missing = sorted(expected - seen_ids)
        extra = sorted(seen_ids - expected)
        raise SystemExit(
            f"{RACER_COUNT} ID 커버리지 실패: missing={missing}, extra={extra}"
        )
    return labels


def patch_racer_spans(
    original: bytes,
    current: bytearray,
    labels: list[dict],
) -> list[dict]:
    """승인된 타일 공유 해소용 범위 변경만 선수 표에 반영한다."""
    records = []
    occupied_ids: set[int] = set()
    for entry in labels:
        if "original_tile_span" not in entry:
            continue
        source_span = parse_span(entry["original_tile_span"])
        target_span = parse_span(entry["tile_span"])
        if source_span == target_span:
            raise SystemExit(f"불필요한 original_tile_span: ID {entry['racer_ids']}")
        for racer_id in entry["racer_ids"]:
            if racer_id in occupied_ids:
                raise SystemExit(f"Result 범위 재정의 ID 중복: {racer_id}")
            occupied_ids.add(racer_id)
            pos = RACER_TABLE_OFFSET + racer_id * 4
            source = (
                source_span[0].to_bytes(2, "little")
                + source_span[1].to_bytes(2, "little")
            )
            target = (
                target_span[0].to_bytes(2, "little")
                + target_span[1].to_bytes(2, "little")
            )
            if original[pos:pos + 4] != source:
                raise SystemExit(f"Result ID {racer_id} 원본 타일 범위 불일치")
            if current[pos:pos + 4] not in (source, target):
                raise SystemExit(f"Result ID {racer_id} 타일 범위 선행 변경")
            current[pos:pos + 4] = target
            records.append({
                "racer_id": racer_id,
                "table_offset": f"0x{pos:06X}",
                "original_span": f"{source_span[0]:04X}-{source_span[1]:04X}",
                "patched_span": f"{target_span[0]:04X}-{target_span[1]:04X}",
            })
    return records


def glyph_mask(font: bytes, glyph_map: dict[str, int], ch: str) -> list[list[int]]:
    mask = [[0] * 8 for _ in range(8)]
    if ch == " ":
        return mask
    if "가" <= ch <= "힣":
        if ch not in glyph_map:
            raise SystemExit(f"8pt 글꼴에 음절 없음: {ch!r}")
        raw = font[glyph_map[ch] * 8:glyph_map[ch] * 8 + 8]
        for y, value in enumerate(raw):
            for x in range(8):
                mask[y][x] = (value >> (7 - x)) & 1
        return mask
    if ch == "・":
        mask[4][3] = 1
        mask[4][4] = 1
        return mask
    if ch in ASCII_5X7:
        for y, row in enumerate(ASCII_5X7[ch]):
            for x, value in enumerate(row):
                if value == "1":
                    mask[y][x + 1] = 1
        return mask
    raise SystemExit(f"Result 전용 글꼴에서 지원하지 않는 문자: {ch!r}")


def compose_label(font: bytes, glyph_map: dict[str, int], text: str, capacity: int) -> list[list[int]]:
    width = capacity * 8
    ink = [[0] * width for _ in range(16)]
    for cell, ch in enumerate(text):
        glyph = glyph_mask(font, glyph_map, ch)
        for gy in range(8):
            for gx in range(8):
                if glyph[gy][gx]:
                    ink[FONT_Y + gy][cell * 8 + gx] = 1

    # 원본 Result 이름과 같은 2색 구성: 흰색(인덱스1) + 검은 1px 외곽선(인덱스3).
    pixels = [[0] * width for _ in range(16)]
    for y in range(16):
        for x in range(width):
            if not ink[y][x]:
                continue
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    xx, yy = x + dx, y + dy
                    if 0 <= xx < width and 0 <= yy < 16:
                        pixels[yy][xx] = 3
    for y in range(16):
        for x in range(width):
            if ink[y][x]:
                pixels[y][x] = 1
    return pixels


def encode_tile(pixels: list[list[int]], x0: int, y0: int) -> bytes:
    out = bytearray(TILE_BYTES)
    for row in range(8):
        plane0 = 0
        plane1 = 0
        for col in range(8):
            value = pixels[y0 + row][x0 + col]
            plane0 |= (value & 1) << (7 - col)
            plane1 |= ((value >> 1) & 1) << (7 - col)
        out[row * 2] = plane0
        out[row * 2 + 1] = plane1
    return bytes(out)


def decode_tile(raw: bytes) -> list[list[int]]:
    if len(raw) != TILE_BYTES:
        raise ValueError(f"2bpp 타일 길이 불일치: {len(raw)}")
    pixels = [[0] * 8 for _ in range(8)]
    for row in range(8):
        plane0, plane1 = raw[row * 2:row * 2 + 2]
        for col in range(8):
            bit = 7 - col
            pixels[row][col] = ((plane0 >> bit) & 1) | (((plane1 >> bit) & 1) << 1)
    return pixels


def atlas_image(data: bytes) -> Image.Image:
    image = Image.new("P", ATLAS_SIZE, 0)
    palette = []
    for rgb in PALETTE_RGB:
        palette.extend(rgb)
    palette.extend([0] * (768 - len(palette)))
    image.putpalette(palette)
    px = image.load()
    for tile_index in range(len(data) // TILE_BYTES):
        tile = decode_tile(data[tile_index * TILE_BYTES:(tile_index + 1) * TILE_BYTES])
        x0 = (tile_index % ATLAS_COLS) * 8
        y0 = (tile_index // ATLAS_COLS) * 8
        for y in range(8):
            for x in range(8):
                px[x0 + x, y0 + y] = tile[y][x]
    return image


def pixels_to_asset(image_path: Path) -> bytes:
    image = Image.open(image_path).convert("RGB")
    if image.size != ATLAS_SIZE:
        raise SystemExit(
            f"편집 PNG 크기 불일치: {image.size[0]}x{image.size[1]} != "
            f"{ATLAS_SIZE[0]}x{ATLAS_SIZE[1]} (리사이즈 금지)"
        )
    color_to_index = {rgb: index for index, rgb in enumerate(PALETTE_RGB)}
    unexpected = sorted(set(image.getdata()) - set(color_to_index))
    if unexpected:
        sample = ", ".join("#%02X%02X%02X" % rgb for rgb in unexpected[:8])
        raise SystemExit(
            f"편집 PNG에 2bpp 팔레트 밖 색상 {len(unexpected)}개: {sample}. "
            "안티앨리어싱을 끄고 마젠타/흰색/회색/검정만 사용하세요."
        )

    source = image.load()
    out = bytearray(DECOMPRESSED_SIZE)
    tile_count = DECOMPRESSED_SIZE // TILE_BYTES
    for tile_index in range(tile_count):
        x0 = (tile_index % ATLAS_COLS) * 8
        y0 = (tile_index // ATLAS_COLS) * 8
        pixels = [[color_to_index[source[x0 + x, y0 + y]] for x in range(8)] for y in range(8)]
        out[tile_index * TILE_BYTES:(tile_index + 1) * TILE_BYTES] = encode_tile(pixels, 0, 0)
    return bytes(out)


def edit_segments(indices: list[int]) -> list[tuple[int, int, int, int]]:
    """논리 이름 타일을 PNG의 연속 사각형들(x,y,w,h)로 묶는다."""
    if not indices:
        return []
    runs: list[list[int]] = [[indices[0]]]
    for tile_index in indices[1:]:
        previous = runs[-1][-1]
        if tile_index == previous + 1 and tile_index // ATLAS_COLS == previous // ATLAS_COLS:
            runs[-1].append(tile_index)
        else:
            runs.append([tile_index])
    return [
        (
            (run[0] % ATLAS_COLS) * 8,
            (run[0] // ATLAS_COLS) * 8,
            len(run) * 8,
            16,
        )
        for run in runs
    ]


def label_pixels_from_asset(data: bytes, indices: list[int]) -> list[list[int]]:
    pixels = [[0] * (len(indices) * 8) for _ in range(16)]
    for cell, top_index in enumerate(indices):
        top_pos = top_index * TILE_BYTES
        bottom_pos = (top_index + 0x10) * TILE_BYTES
        top = decode_tile(data[top_pos:top_pos + TILE_BYTES])
        bottom = decode_tile(data[bottom_pos:bottom_pos + TILE_BYTES])
        for y in range(8):
            for x in range(8):
                pixels[y][cell * 8 + x] = top[y][x]
                pixels[y + 8][cell * 8 + x] = bottom[y][x]
    return pixels


def indexed_image_from_pixels(pixels: list[list[int]]) -> Image.Image:
    height = len(pixels)
    width = len(pixels[0]) if height else 0
    image = Image.new("P", (width, height), 0)
    palette = []
    for rgb in PALETTE_RGB:
        palette.extend(rgb)
    palette.extend([0] * (768 - len(palette)))
    image.putpalette(palette)
    target = image.load()
    for y in range(height):
        for x in range(width):
            target[x, y] = pixels[y][x]
    return image


def workshop_entries(labels: list[dict]) -> list[dict]:
    return [entry for entry in labels if entry.get("text_jp") is not None]


def workshop_crop(number: int, capacity: int) -> tuple[int, int, int, int]:
    col, row = number % 2, number // 2
    return col * 128 + 4, row * 32 + 12, capacity * 8, 16


def draw_workshop_label(
    image: Image.Image,
    font: bytes,
    glyph_map: dict[str, int],
    x0: int,
    y0: int,
    text: str,
) -> None:
    target = image.load()
    for cell, ch in enumerate(text):
        mask = glyph_mask(font, glyph_map, ch)
        for y in range(8):
            for x in range(8):
                if mask[y][x]:
                    target[x0 + cell * 8 + x, y0 + y] = 1


def make_workshop_image(data: bytes, labels: list[dict], font: bytes, glyph_map: dict[str, int]) -> Image.Image:
    entries = workshop_entries(labels)
    rows = (len(entries) + 1) // 2
    image = Image.new("P", (256, rows * 32), 3)
    palette = []
    for rgb in PALETTE_RGB:
        palette.extend(rgb)
    palette.extend([0] * (768 - len(palette)))
    image.putpalette(palette)
    draw = ImageDraw.Draw(image)
    tiny = ImageFont.load_default(size=6)
    for number, entry in enumerate(entries):
        indices = tile_indices(*parse_span(entry["tile_span"]))
        x, y, width, height = workshop_crop(number, len(indices))
        original = indexed_image_from_pixels(label_pixels_from_asset(data, indices))
        image.paste(original, (x, y))
        col_base = number % 2 * 128
        row_base = number // 2 * 32
        draw_workshop_label(
            image,
            font,
            glyph_map,
            col_base + 4,
            row_base + 2,
            entry["text_kr_display"],
        )
        draw.text((col_base + 56, row_base + 2), entry["tile_span"], fill=1, font=tiny)
        # 편집 영역 밖의 기준선이며 ROM에 재삽입할 때는 잘라내지 않는다.
        if x + width < col_base + 126:
            draw.line((x + width, y, x + width, y + height - 1), fill=2)
    return image


def horizontal_padding(pixels: list[list[int]]) -> tuple[int, int]:
    width = len(pixels[0]) if pixels else 0
    occupied = [
        x
        for x in range(width)
        if any(pixels[y][x] != 0 for y in range(len(pixels)))
    ]
    if not occupied:
        return width, width
    return min(occupied), width - 1 - max(occupied)


def make_alignment_workshop_image(
    data: bytes,
    labels: list[dict],
    font: bytes,
    glyph_map: dict[str, int],
) -> tuple[Image.Image, list[dict]]:
    """현재 ROM 이름을 같은 시작선·셀 눈금과 함께 1:1 작업지로 만든다."""
    image = make_workshop_image(data, labels, font, glyph_map)
    draw = ImageDraw.Draw(image)
    tiny = ImageFont.load_default(size=6)
    records = []
    for number, entry in enumerate(workshop_entries(labels)):
        indices = tile_indices(*parse_span(entry["tile_span"]))
        pixels = label_pixels_from_asset(data, indices)
        leading, trailing = horizontal_padding(pixels)
        x, y, width, height = workshop_crop(number, len(indices))
        col_base = number % 2 * 128
        row_base = number // 2 * 32

        # 편집 영역 바깥에만 시작선·8px 셀 눈금을 그린다. 편집 픽셀은
        # current ROM에서 추출한 값 그대로이므로 기존 importer를 재사용한다.
        draw.line((x - 1, y, x - 1, y + height - 1), fill=2)
        draw.line((x + width, y, x + width, y + height - 1), fill=2)
        for cell in range(len(indices) + 1):
            tick_x = x + cell * 8
            draw.point((tick_x, y - 1), fill=2)
            if y + height < image.height:
                draw.point((tick_x, y + height), fill=2)

        # 헤더는 양쪽 칸이 같은 규칙으로 보이도록 번호·ID·범위·leading만 쓴다.
        draw.rectangle((col_base, row_base, col_base + 127, row_base + 10), fill=3)
        ids = ",".join(str(racer_id) for racer_id in entry["racer_ids"])
        draw.text(
            (col_base + 4, row_base + 2),
            f"#{number + 1:02d} ID{ids} {entry['tile_span']} L{leading}px",
            fill=1,
            font=tiny,
        )
        records.append({
            "number": number + 1,
            "racer_ids": entry["racer_ids"],
            "tile_span": entry["tile_span"],
            "workshop_crop_px": {"x": x, "y": y, "w": width, "h": height},
            "tile_capacity": len(indices),
            "leading_transparent_px": leading,
            "leading_empty_cells": leading // 8,
            "leading_px_in_next_cell": leading % 8,
            "trailing_transparent_px": trailing,
            "text_jp": entry["text_jp"],
            "text_kr_display": entry["text_kr_display"],
            "render_mode": entry.get("render_mode", "replace"),
        })
    return image, records


def workshop_to_asset(image_path: Path, original_data: bytes, labels: list[dict]) -> bytes:
    image = Image.open(image_path).convert("RGB")
    expected_size = (256, ((len(workshop_entries(labels)) + 1) // 2) * 32)
    if image.size != expected_size:
        raise SystemExit(
            f"수동 편집 시트 크기 불일치: {image.size[0]}x{image.size[1]} != "
            f"{expected_size[0]}x{expected_size[1]} (리사이즈 금지)"
        )
    color_to_index = {rgb: index for index, rgb in enumerate(PALETTE_RGB)}
    color_to_index.update(WORKSHOP_COLOR_ALIASES)
    data = bytearray(original_data)
    source = image.load()
    for number, entry in enumerate(workshop_entries(labels)):
        indices = tile_indices(*parse_span(entry["tile_span"]))
        x0, y0, width, height = workshop_crop(number, len(indices))
        unexpected = set()
        pixels = [[0] * width for _ in range(height)]
        for y in range(height):
            for x in range(width):
                rgb = source[x0 + x, y0 + y]
                if rgb not in color_to_index:
                    unexpected.add(rgb)
                else:
                    pixels[y][x] = color_to_index[rgb]
        if unexpected:
            sample = ", ".join("#%02X%02X%02X" % rgb for rgb in sorted(unexpected)[:8])
            raise SystemExit(
                f"{entry['tile_span']} 편집 영역에 팔레트 밖 색상 {len(unexpected)}개: {sample}. "
                "안티앨리어싱을 끄고 마젠타/흰색/회색/검정만 사용하세요."
            )
        patch_label(data, indices, pixels)
    return bytes(data)


def export_manual_assets(template_path: Path, guide_path: Path) -> None:
    original = ORIGINAL_ROM.read_bytes()
    data, used = decode_asset(original)
    capacity = NEXT_ASSET_OFFSET - (ASSET_OFFSET + 2)
    if used != capacity:
        raise SystemExit(f"원본 압축 경계 불일치: used={used}, capacity={capacity}")
    spans = read_racer_spans(original)
    corpus = json.loads(TRANSLATIONS.read_text(encoding="utf-8"))
    labels = validate_corpus(corpus, spans)
    font = FONT_BIN.read_bytes()
    glyph_map = json.loads(FONT_MAP.read_text(encoding="utf-8"))

    template_path.parent.mkdir(parents=True, exist_ok=True)
    workshop = make_workshop_image(data, labels, font, glyph_map)
    workshop.save(template_path)
    lines = [
        "racer_ids\ttile_span\tworkshop_crop_px\tatlas_segments_px\ttile_capacity\toriginal_jp\ttranslation_kr\tmode",
    ]
    for number, entry in enumerate(workshop_entries(labels)):
        indices = tile_indices(*parse_span(entry["tile_span"]))
        segments = ";".join(f"x{x},y{y},w{w},h{h}" for x, y, w, h in edit_segments(indices))
        wx, wy, ww, wh = workshop_crop(number, len(indices))
        lines.append("\t".join([
            ",".join(str(i) for i in entry["racer_ids"]),
            entry["tile_span"],
            f"x{wx},y{wy},w{ww},h{wh}",
            segments,
            str(len(indices)),
            entry.get("text_jp") or "(미사용)",
            entry.get("text_kr_display") or "(원본 보존)",
            entry.get("render_mode", "replace"),
    ]))
    guide_path.parent.mkdir(parents=True, exist_ok=True)
    guide_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        f"수동 편집 시트: {template_path} "
        f"({workshop.width}x{workshop.height}, 1:1 pixels, "
        f"{len(workshop_entries(labels))} unique names)"
    )
    print(f"번역/좌표표: {guide_path} (workshop crop -> ROM atlas segments)")


def export_current_alignment_assets(
    rom_path: Path,
    template_path: Path,
    guide_path: Path,
    manifest_path: Path,
) -> None:
    rom = rom_path.read_bytes()
    if len(rom) != 0x200000:
        raise SystemExit(f"현재 Result 작업지 ROM 크기 불일치: {len(rom)}")
    data, used = decode_asset(rom)
    corpus = json.loads(TRANSLATIONS.read_text(encoding="utf-8"))
    labels = validate_corpus(corpus, read_racer_spans(rom))
    current_spans = read_racer_spans(rom)
    for entry in labels:
        target = parse_span(entry["tile_span"])
        for racer_id in entry["racer_ids"]:
            if current_spans[racer_id] != target:
                raise SystemExit(
                    f"현재 ROM ID {racer_id} 범위가 승인값과 다름: "
                    f"{current_spans[racer_id]} != {target}"
                )
    font = FONT_BIN.read_bytes()
    glyph_map = json.loads(FONT_MAP.read_text(encoding="utf-8"))
    image, records = make_alignment_workshop_image(data, labels, font, glyph_map)
    template_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(template_path)

    lines = [
        "number\tracer_ids\ttile_span\tworkshop_crop_px\ttile_capacity"
        "\tleading_transparent_px\tleading_empty_cells\tleading_px_in_next_cell"
        "\ttrailing_transparent_px\toriginal_jp\ttranslation_kr\tmode"
    ]
    for item in records:
        crop = item["workshop_crop_px"]
        lines.append("\t".join([
            str(item["number"]),
            ",".join(str(racer_id) for racer_id in item["racer_ids"]),
            item["tile_span"],
            f"x{crop['x']},y{crop['y']},w{crop['w']},h{crop['h']}",
            str(item["tile_capacity"]),
            str(item["leading_transparent_px"]),
            str(item["leading_empty_cells"]),
            str(item["leading_px_in_next_cell"]),
            str(item["trailing_transparent_px"]),
            item["text_jp"],
            item["text_kr_display"],
            item["render_mode"],
        ]))
    guide_path.parent.mkdir(parents=True, exist_ok=True)
    guide_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    empty_cell_summary: dict[str, int] = {}
    pixel_summary: dict[str, int] = {}
    column_summary = {"left": {}, "right": {}}
    for item in records:
        cell_key = str(item["leading_empty_cells"])
        pixel_key = str(item["leading_transparent_px"])
        empty_cell_summary[cell_key] = empty_cell_summary.get(cell_key, 0) + 1
        pixel_summary[pixel_key] = pixel_summary.get(pixel_key, 0) + 1
        column = "left" if (item["number"] - 1) % 2 == 0 else "right"
        column_counts = column_summary[column]
        column_counts[pixel_key] = column_counts.get(pixel_key, 0) + 1
    manifest = {
        "source_rom": str(rom_path),
        "source_rom_sha256": hashlib.sha256(rom).hexdigest(),
        "source_asset": "$D9:1DDC",
        "source_table": "$C1:CBAF",
        "compressed_size": used,
        "image": str(template_path),
        "image_size_px": [image.width, image.height],
        "entry_count": len(records),
        "leading_empty_cell_distribution": empty_cell_summary,
        "leading_transparent_px_distribution": pixel_summary,
        "leading_transparent_px_by_sheet_column": column_summary,
        "guide": str(guide_path),
        "records": records,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"현재 Result 전체 정렬 작업지: {template_path} "
        f"({image.width}x{image.height}, 1:1, {len(records)}종)"
    )
    print(f"첫 픽셀·빈 셀 기록표: {guide_path}")
    print(f"작업지 매니페스트: {manifest_path}")


def patch_label(data: bytearray, indices: list[int], pixels: list[list[int]]) -> None:
    for cell, top_index in enumerate(indices):
        top = encode_tile(pixels, cell * 8, 0)
        bottom = encode_tile(pixels, cell * 8, 8)
        top_pos = top_index * TILE_BYTES
        bottom_pos = (top_index + 0x10) * TILE_BYTES
        if bottom_pos + TILE_BYTES > len(data):
            raise SystemExit(f"아틀라스 범위 초과: tile {top_index:04X}/bottom {top_index + 0x10:04X}")
        data[top_pos:top_pos + TILE_BYTES] = top
        data[bottom_pos:bottom_pos + TILE_BYTES] = bottom


def preview_image(rendered: list[tuple[dict, list[int], list[list[int]]]]) -> Image.Image:
    scale = 3
    slot_w = 280
    slot_h = 66
    cols = 3
    rows = (len(rendered) + cols - 1) // cols
    image = Image.new("RGB", (slot_w * cols, slot_h * rows), "#dddddd")
    draw = ImageDraw.Draw(image)
    palette = [(255, 0, 255), (255, 255, 255), (128, 128, 128), (0, 0, 0)]
    for number, (entry, indices, pixels) in enumerate(rendered):
        col, row = number % cols, number // cols
        x0, y0 = col * slot_w, row * slot_h
        ids = ",".join(str(i) for i in entry["racer_ids"])
        label = entry.get("text_kr_display") or "(원본 보존)"
        draw.text((x0 + 3, y0 + 2), f"ID {ids} {entry['tile_span']} {label}", fill="black")
        cell = Image.new("RGB", (len(indices) * 8, 16), "magenta")
        px = cell.load()
        for y in range(16):
            for x in range(len(indices) * 8):
                px[x, y] = palette[pixels[y][x]]
        cell = cell.resize((cell.width * scale, cell.height * scale))
        image.paste(cell, (x0 + 3, y0 + 17))
    return image


def build(
    rom_path: Path,
    out_path: Path,
    preview_path: Path,
    manifest_path: Path,
    edited_png: Path | None = None,
    workshop_png: Path | None = None,
) -> None:
    original = ORIGINAL_ROM.read_bytes()
    current = bytearray(rom_path.read_bytes())
    if len(original) != 0x200000 or len(current) != len(original):
        raise SystemExit("헤더리스 2MB ROM 크기 불일치")

    original_data, original_used = decode_asset(original)
    capacity = NEXT_ASSET_OFFSET - (ASSET_OFFSET + 2)
    if original_used != capacity:
        raise SystemExit(f"원본 압축 경계 불일치: used={original_used}, capacity={capacity}")

    racer_spans = read_racer_spans(original)
    corpus = json.loads(TRANSLATIONS.read_text(encoding="utf-8"))
    labels = validate_corpus(corpus, racer_spans)
    font = FONT_BIN.read_bytes()
    glyph_map = json.loads(FONT_MAP.read_text(encoding="utf-8"))

    data = bytearray(original_data)
    rendered = []
    translated_ids = 0
    if edited_png is not None and workshop_png is not None:
        raise SystemExit("--edited-png와 --workshop-png는 동시에 사용할 수 없습니다")
    if workshop_png is not None:
        data[:] = workshop_to_asset(workshop_png, original_data, labels)
        translated_ids = sum(
            len(entry["racer_ids"])
            for entry in labels
            if entry.get("text_jp") is not None
        )
    elif edited_png is not None:
        data[:] = pixels_to_asset(edited_png)
        translated_ids = sum(
            len(entry["racer_ids"])
            for entry in labels
            if entry.get("render_mode", "replace") == "replace"
        )
    else:
        for entry in labels:
            start, end = parse_span(entry["tile_span"])
            indices = tile_indices(start, end)
            if entry.get("render_mode", "replace") == "replace":
                pixels = compose_label(font, glyph_map, entry["text_kr_display"], len(indices))
                patch_label(data, indices, pixels)
                translated_ids += len(entry["racer_ids"])
            else:
                # 미리보기에서는 보존 엔트리를 빈 칸으로 표시하고 실제 아틀라스 바이트는 건드리지 않는다.
                pixels = [[0] * (len(indices) * 8) for _ in range(16)]
            rendered.append((entry, indices, pixels))

    compressed = lzss.compress(bytes(data))
    if len(compressed) > capacity:
        raise SystemExit(f"Result 이름 압축 스트림 초과: {len(compressed)} > {capacity}B")
    roundtrip, used = lzss.decompress(compressed + b"\x00\x00", 0, DECOMPRESSED_SIZE)
    if roundtrip != bytes(data) or used != len(compressed):
        raise SystemExit("Result 이름 LZSS 라운드트립 실패")

    # 재실행 시에도 같은 바이트가 되도록 소유 구간을 원본으로 복구한 뒤 새 스트림을 쓴다.
    current[ASSET_OFFSET:NEXT_ASSET_OFFSET] = original[ASSET_OFFSET:NEXT_ASSET_OFFSET]
    span_patches = patch_racer_spans(original, current, labels)
    current[ASSET_OFFSET:ASSET_OFFSET + 2] = DECOMPRESSED_SIZE.to_bytes(2, "little")
    current[ASSET_OFFSET + 2:ASSET_OFFSET + 2 + len(compressed)] = compressed
    verify, _ = decode_asset(bytes(current))
    if verify != bytes(data):
        raise SystemExit("ROM 재삽입 후 Result 이름 역검증 실패")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(current)
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    if edited_png is not None or workshop_png is not None:
        atlas_image(bytes(data)).resize((ATLAS_SIZE[0] * 4, ATLAS_SIZE[1] * 4)).save(preview_path)
    else:
        preview_image(rendered).save(preview_path)
    manifest = {
        "asset": "$D9:1DDC",
        "table": "$C1:CBAF",
        "racer_id_count": RACER_COUNT,
        "translated_id_count": translated_ids,
        "preserved_id_count": RACER_COUNT - translated_ids,
        "decompressed_size": DECOMPRESSED_SIZE,
        "original_compressed_size": original_used,
        "translated_compressed_size": len(compressed),
        "capacity": capacity,
        "free_bytes": capacity - len(compressed),
        "rom_size": len(current),
        "input_mode": (
            "workshop_png" if workshop_png is not None
            else "edited_png" if edited_png is not None
            else "automatic_fallback"
        ),
        "edited_png": str(edited_png) if edited_png is not None else None,
        "workshop_png": str(workshop_png) if workshop_png is not None else None,
        "preview": str(preview_path),
        "racer_span_patches": span_patches,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Result 선수명: {translated_ids}/{RACER_COUNT} ID 교체, "
        f"{RACER_COUNT - translated_ids} ID 원본 보존"
    )
    print(
        f"LZSS {original_used}B -> {len(compressed)}B "
        f"(여유 {capacity - len(compressed)}B), round-trip PASS"
    )
    if span_patches:
        print(
            "선수 타일 범위 재정의: "
            + ", ".join(
                f"ID {item['racer_id']} "
                f"{item['original_span']}→{item['patched_span']}"
                for item in span_patches
            )
        )
    print(f"ROM {out_path} ({len(current)}B), preview {preview_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rom", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--out", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--preview", type=Path, default=DEFAULT_PREVIEW)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--edited-png", type=Path, help="128x320 수동 편집본을 그대로 2bpp로 재삽입")
    parser.add_argument(
        "--workshop-png",
        type=Path,
        help="256px 폭 수동 편집 시트의 모든 이름 칸을 주소별 재삽입",
    )
    parser.add_argument("--export-template", action="store_true", help="원본 2bpp 아틀라스와 번역/좌표 TSV 생성 후 종료")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--guide", type=Path, default=DEFAULT_GUIDE)
    parser.add_argument(
        "--export-current-alignment",
        action="store_true",
        help="현재 통합 ROM의 전 선수명을 동일 시작선·셀 눈금 작업지로 내보냄",
    )
    parser.add_argument(
        "--alignment-template",
        type=Path,
        default=DEFAULT_ALIGNMENT_TEMPLATE,
    )
    parser.add_argument("--alignment-guide", type=Path, default=DEFAULT_ALIGNMENT_GUIDE)
    parser.add_argument(
        "--alignment-manifest",
        type=Path,
        default=DEFAULT_ALIGNMENT_MANIFEST,
    )
    args = parser.parse_args()
    if args.export_current_alignment:
        export_current_alignment_assets(
            args.rom.resolve(),
            args.alignment_template.resolve(),
            args.alignment_guide.resolve(),
            args.alignment_manifest.resolve(),
        )
        return
    if args.export_template:
        export_manual_assets(args.template.resolve(), args.guide.resolve())
        return
    build(
        args.rom.resolve(),
        args.out.resolve(),
        args.preview.resolve(),
        args.manifest.resolve(),
        args.edited_png.resolve() if args.edited_png else None,
        args.workshop_png.resolve() if args.workshop_png else None,
    )


if __name__ == "__main__":
    main()
