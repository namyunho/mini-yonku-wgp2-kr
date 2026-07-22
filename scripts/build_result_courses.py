#!/usr/bin/env python3
"""Result/Best 화면의 경기장명 2bpp 자산을 한글로 재삽입한다.

경로:
  $D9:444A LZSS -> $7F:0000 (0x0C00 bytes)
  $C3:C12E course ID별 (시작, 끝) 타일 좌표표 8개
  $C3:0B47 -> $C1:6801 DMA, 현재 course ID=$09AB, VRAM word $0180

팀명 자산 $D9:30B1은 읽거나 수정하지 않는다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import lzss  # noqa: E402
from build_result_names import (  # noqa: E402
    FONT_BIN,
    FONT_MAP,
    PALETTE_RGB,
    compose_label,
    draw_workshop_label,
    indexed_image_from_pixels,
    label_pixels_from_asset,
    parse_span,
    patch_label,
    tile_indices,
)


ORIGINAL_ROM = ROOT / "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
DEFAULT_ROM = ROOT / "out/wgp2_kr.smc"
TRANSLATIONS = ROOT / "assets/translations/result_courses.json"
DEFAULT_PREVIEW = ROOT / "out/result_courses_preview.png"
DEFAULT_MANIFEST = ROOT / "out/result_courses_manifest.json"
DEFAULT_TEMPLATE = ROOT / "assets/result_courses/result_courses_workshop_256px.png"
DEFAULT_GUIDE = ROOT / "assets/result_courses/result_courses_translation.tsv"

ASSET_OFFSET = 0x19444A       # $D9:444A, 2-byte decompressed-length header
NEXT_ASSET_OFFSET = 0x194867  # $D9:4867, verified next LZSS source
DECOMPRESSED_SIZE = 0x0C00
COURSE_TABLE_OFFSET = 0x03C12E  # $C3:C12E
COURSE_COUNT = 8
WORKSHOP_SIZE = (256, COURSE_COUNT * 32)


def decode_asset(rom: bytes) -> tuple[bytes, int]:
    size = int.from_bytes(rom[ASSET_OFFSET:ASSET_OFFSET + 2], "little")
    if size != DECOMPRESSED_SIZE:
        raise SystemExit(f"$D9:444A 해제 길이 불일치: 0x{size:04X}")
    return lzss.decompress(rom, ASSET_OFFSET + 2, size)


def read_course_spans(rom: bytes) -> dict[int, tuple[int, int]]:
    spans = {}
    for course_id in range(COURSE_COUNT):
        pos = COURSE_TABLE_OFFSET + course_id * 4
        spans[course_id] = (
            int.from_bytes(rom[pos:pos + 2], "little"),
            int.from_bytes(rom[pos + 2:pos + 4], "little"),
        )
    return spans


def validate_corpus(corpus: dict, spans: dict[int, tuple[int, int]]) -> list[dict]:
    labels = corpus.get("labels")
    if not isinstance(labels, list):
        raise SystemExit("result_courses.json: labels 배열 없음")
    seen = set()
    for entry in labels:
        course_id = entry.get("course_id")
        if course_id in seen or course_id not in spans:
            raise SystemExit(f"경기장 ID 오류/중복: {course_id}")
        seen.add(course_id)
        span = parse_span(entry["tile_span"])
        if spans[course_id] != span:
            raise SystemExit(
                f"경기장 ID {course_id} 타일표 불일치: JSON {span}, ROM {spans[course_id]}"
            )
        indices = tile_indices(*span)
        full = entry.get("text_kr_full")
        display = entry.get("text_kr_display")
        if not isinstance(full, str) or not isinstance(display, str):
            raise SystemExit(f"경기장 ID {course_id} 번역 누락")
        if entry.get("abbreviated") != (full != display):
            raise SystemExit(f"경기장 ID {course_id} 축약 플래그 불일치")
        if len(display) > len(indices):
            raise SystemExit(
                f"경기장 ID {course_id} 타일 용량 초과: {len(display)} > {len(indices)}"
            )
    if seen != set(range(COURSE_COUNT)):
        raise SystemExit(f"경기장 ID 커버리지 실패: {sorted(set(range(COURSE_COUNT)) - seen)}")
    return sorted(labels, key=lambda item: item["course_id"])


def put_palette(image: Image.Image) -> None:
    palette = []
    for rgb in PALETTE_RGB:
        palette.extend(rgb)
    palette.extend([0] * (768 - len(palette)))
    image.putpalette(palette)


def workshop_crop(course_id: int, capacity: int) -> tuple[int, int, int, int]:
    return 4, course_id * 32 + 14, capacity * 8, 16


def make_workshop(
    data: bytes,
    labels: list[dict],
    font: bytes,
    glyph_map: dict[str, int],
) -> Image.Image:
    image = Image.new("P", WORKSHOP_SIZE, 3)
    put_palette(image)
    for entry in labels:
        course_id = entry["course_id"]
        indices = tile_indices(*parse_span(entry["tile_span"]))
        original = indexed_image_from_pixels(label_pixels_from_asset(data, indices))
        x, y, _, _ = workshop_crop(course_id, len(indices))
        image.paste(original, (x, y))
        draw_workshop_label(
            image,
            font,
            glyph_map,
            4,
            course_id * 32 + 3,
            entry["text_kr_display"],
        )
    return image


def workshop_to_asset(image_path: Path, original_data: bytes, labels: list[dict]) -> bytes:
    image = Image.open(image_path).convert("RGB")
    if image.size != WORKSHOP_SIZE:
        raise SystemExit(
            f"경기장명 작업 PNG 크기 불일치: {image.size} != {WORKSHOP_SIZE} (리사이즈 금지)"
        )
    color_to_index = {rgb: index for index, rgb in enumerate(PALETTE_RGB)}
    source = image.load()
    data = bytearray(original_data)
    for entry in labels:
        indices = tile_indices(*parse_span(entry["tile_span"]))
        x0, y0, width, height = workshop_crop(entry["course_id"], len(indices))
        pixels = [[0] * width for _ in range(height)]
        unexpected = set()
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
                f"경기장 ID {entry['course_id']} 팔레트 밖 색상: {sample}"
            )
        patch_label(data, indices, pixels)
    return bytes(data)


def export_template(template_path: Path, guide_path: Path) -> None:
    original = ORIGINAL_ROM.read_bytes()
    data, used = decode_asset(original)
    capacity = NEXT_ASSET_OFFSET - (ASSET_OFFSET + 2)
    if used != capacity:
        raise SystemExit(f"원본 압축 경계 불일치: {used} != {capacity}")
    labels = validate_corpus(
        json.loads(TRANSLATIONS.read_text(encoding="utf-8")),
        read_course_spans(original),
    )
    font = FONT_BIN.read_bytes()
    glyph_map = json.loads(FONT_MAP.read_text(encoding="utf-8"))
    template_path.parent.mkdir(parents=True, exist_ok=True)
    make_workshop(data, labels, font, glyph_map).save(template_path)
    lines = [
        "course_id\ttile_span\tworkshop_crop_px\ttile_capacity\toriginal_jp\ttranslation_kr"
    ]
    for entry in labels:
        indices = tile_indices(*parse_span(entry["tile_span"]))
        x, y, w, h = workshop_crop(entry["course_id"], len(indices))
        lines.append("\t".join([
            str(entry["course_id"]), entry["tile_span"],
            f"x{x},y{y},w{w},h{h}", str(len(indices)),
            entry["text_jp"], entry["text_kr_display"],
        ]))
    guide_path.parent.mkdir(parents=True, exist_ok=True)
    guide_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"경기장명 작업 시트: {template_path} ({WORKSHOP_SIZE[0]}x{WORKSHOP_SIZE[1]}, 1:1)")


def build(
    rom_path: Path,
    out_path: Path,
    preview_path: Path,
    manifest_path: Path,
    workshop_png: Path | None,
) -> None:
    original = ORIGINAL_ROM.read_bytes()
    current = bytearray(rom_path.read_bytes())
    if len(original) != len(current):
        raise SystemExit(f"ROM 크기 보존 실패: {len(current)} != {len(original)}")
    original_data, original_used = decode_asset(original)
    capacity = NEXT_ASSET_OFFSET - (ASSET_OFFSET + 2)
    if original_used != capacity:
        raise SystemExit(f"원본 압축 경계 불일치: {original_used} != {capacity}")
    labels = validate_corpus(
        json.loads(TRANSLATIONS.read_text(encoding="utf-8")),
        read_course_spans(original),
    )
    font = FONT_BIN.read_bytes()
    glyph_map = json.loads(FONT_MAP.read_text(encoding="utf-8"))

    if workshop_png:
        data = workshop_to_asset(workshop_png, original_data, labels)
        input_mode = "workshop_png"
    else:
        mutable = bytearray(original_data)
        for entry in labels:
            indices = tile_indices(*parse_span(entry["tile_span"]))
            pixels = compose_label(font, glyph_map, entry["text_kr_display"], len(indices))
            patch_label(mutable, indices, pixels)
        data = bytes(mutable)
        input_mode = "automatic"

    compressed = lzss.compress(data)
    if len(compressed) > capacity:
        raise SystemExit(f"경기장명 LZSS 초과: {len(compressed)} > {capacity}")
    decoded, used = lzss.decompress(compressed + b"\x00\x00", 0, DECOMPRESSED_SIZE)
    if decoded != data or used != len(compressed):
        raise SystemExit("경기장명 LZSS 라운드트립 실패")

    current[ASSET_OFFSET:NEXT_ASSET_OFFSET] = original[ASSET_OFFSET:NEXT_ASSET_OFFSET]
    current[ASSET_OFFSET:ASSET_OFFSET + 2] = DECOMPRESSED_SIZE.to_bytes(2, "little")
    current[ASSET_OFFSET + 2:ASSET_OFFSET + 2 + len(compressed)] = compressed
    verify, _ = decode_asset(bytes(current))
    if verify != data:
        raise SystemExit("경기장명 ROM 재삽입 역검증 실패")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(current)
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    make_workshop(data, labels, font, glyph_map).resize(
        (WORKSHOP_SIZE[0] * 2, WORKSHOP_SIZE[1] * 2),
        Image.Resampling.NEAREST,
    ).save(preview_path)
    manifest = {
        "asset": "$D9:444A",
        "table": "$C3:C12E-$C3:C14D",
        "course_count": COURSE_COUNT,
        "decompressed_size": DECOMPRESSED_SIZE,
        "original_compressed_size": original_used,
        "translated_compressed_size": len(compressed),
        "capacity": capacity,
        "free_bytes": capacity - len(compressed),
        "input_mode": input_mode,
        "rom_size": len(current),
        "team_asset_touched": False,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Result 경기장명 {COURSE_COUNT}/{COURSE_COUNT} 교체, "
        f"LZSS {original_used}B -> {len(compressed)}B (여유 {capacity - len(compressed)}B)"
    )
    print(f"팀명 $D9:30B1 보존, ROM {out_path} ({len(current)}B)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rom", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--out", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--preview", type=Path, default=DEFAULT_PREVIEW)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--workshop-png", type=Path)
    parser.add_argument("--export-template", action="store_true")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--guide", type=Path, default=DEFAULT_GUIDE)
    args = parser.parse_args()
    if args.export_template:
        export_template(args.template.resolve(), args.guide.resolve())
        return
    build(
        args.rom.resolve(),
        args.out.resolve(),
        args.preview.resolve(),
        args.manifest.resolve(),
        args.workshop_png.resolve() if args.workshop_png else None,
    )


if __name__ == "__main__":
    main()
