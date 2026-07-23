#!/usr/bin/env python3
"""경기 HUD의 `ダメージ / 爆走` 2bpp 라벨 작업지를 만든다.

Mesen 실측 경로:
  $D5:4EC3 LZSS(raw 0x2000) -> VRAM word $2000-$2FFF
  BG3 chr base word $2000, tilemap word $3800

작업지는 실제 ROM 타일을 1:1로 내보낸다. 마젠타는 투명 인덱스 0,
흰색은 인덱스 1, 청회색은 인덱스 2, 검정은 인덱스 3이다. 이미지 크기나
각 마젠타 편집 영역의 위치·크기를 바꾸면 나중에 재삽입할 수 없다.
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

from build_result_names import draw_workshop_label  # noqa: E402
from lzss import decompress  # noqa: E402


ORIGINAL_ROM = ROOT / "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
CORPUS = ROOT / "assets/translations/race_hud_labels.json"
FONT_BIN = ROOT / "8pt_font/font-007242d37349daf3.bin"
FONT_MAP = ROOT / "8pt_font/font-007242d37349daf3_glyph_map.json"
DEFAULT_TEMPLATE = ROOT / "assets/race_hud/race_hud_labels_workshop_256px.png"
DEFAULT_GUIDE = ROOT / "assets/race_hud/race_hud_labels_translation.tsv"
DEFAULT_CROPS = ROOT / "assets/race_hud/crops"
DEFAULT_ART = ROOT / "out/race_hud_labels_2bpp.bin"
DEFAULT_MANIFEST = ROOT / "out/race_hud_labels_manifest.json"

ROM_SIZE = 0x200000
RESOURCE_OFFSET = 0x154EC3  # $D5:4EC3
RAW_SIZE = 0x2000
ORIGINAL_STREAM_SIZE = 2811
ORIGINAL_RAW_SHA256 = "898431ab854830f7cf9d9719e4411168251d175a2ab33c53758c2b2d6b7f60ad"

PALETTE_RGB = (
    (255, 0, 255),      # 0: transparent
    (255, 255, 255),    # 1: white
    (90, 90, 115),      # 2: blue-gray shadow
    (0, 0, 0),          # 3: black outline / workshop background
)
ROW_HEIGHT = 32
EDIT_X = 4
EDIT_Y = 14
WORKSHOP_SIZE = (256, 64)


def put_palette(image: Image.Image) -> None:
    palette = []
    for rgb in PALETTE_RGB:
        palette.extend(rgb)
    palette.extend([0] * (768 - len(palette)))
    image.putpalette(palette)


def load_corpus() -> dict:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    entries = corpus.get("entries")
    if not isinstance(entries, list) or [entry.get("id") for entry in entries] != [
        "damage", "berserk"
    ]:
        raise SystemExit("race_hud_labels.json 엔트리는 damage/berserk 순서여야 합니다")
    for entry in entries:
        full = entry.get("text_kr_full")
        display = entry.get("text_kr_display")
        if not isinstance(full, str) or not isinstance(display, str):
            raise SystemExit(f"{entry.get('id')}: 완역/표시문 누락")
        if entry.get("abbreviated") != (full != display):
            raise SystemExit(f"{entry['id']}: 축약 플래그 불일치")
        if len(entry["tile_ids"]) * 8 != entry["screen_crop_px"][2]:
            raise SystemExit(f"{entry['id']}: 타일 수와 편집 폭 불일치")
    return corpus


def load_original_resource(corpus: dict) -> bytes:
    rom = ORIGINAL_ROM.read_bytes()
    if len(rom) != ROM_SIZE:
        raise SystemExit(f"원본 ROM이 헤더리스 2MB가 아님: {len(rom)}")
    raw_size = int.from_bytes(rom[RESOURCE_OFFSET:RESOURCE_OFFSET + 2], "little")
    if raw_size != RAW_SIZE:
        raise SystemExit(f"$D5:4EC3 raw 크기 불일치: {raw_size:04X}")
    raw, used = decompress(rom, RESOURCE_OFFSET + 2, raw_size)
    if used != ORIGINAL_STREAM_SIZE:
        raise SystemExit(f"$D5:4EC3 압축 stream 크기 불일치: {used}")
    digest = hashlib.sha256(raw).hexdigest()
    if digest != ORIGINAL_RAW_SHA256 or digest != corpus["resource"]["raw_sha256"]:
        raise SystemExit("$D5:4EC3 원본 해제 자원 SHA-256 불일치")
    return raw


def decode_tile(tile: bytes) -> list[list[int]]:
    if len(tile) != 16:
        raise ValueError("2bpp 타일은 16바이트여야 함")
    pixels = [[0] * 8 for _ in range(8)]
    for y in range(8):
        plane0, plane1 = tile[y * 2:y * 2 + 2]
        for x in range(8):
            bit = 7 - x
            pixels[y][x] = ((plane0 >> bit) & 1) | (((plane1 >> bit) & 1) << 1)
    return pixels


def encode_tile(pixels: list[list[int]]) -> bytes:
    output = bytearray()
    for row in pixels:
        plane0 = 0
        plane1 = 0
        for x, value in enumerate(row):
            plane0 |= (value & 1) << (7 - x)
            plane1 |= ((value >> 1) & 1) << (7 - x)
        output.extend((plane0, plane1))
    return bytes(output)


def label_image(raw: bytes, tile_ids: list[int]) -> Image.Image:
    image = Image.new("P", (len(tile_ids) * 8, 8), 0)
    put_palette(image)
    target = image.load()
    for cell, tile_id in enumerate(tile_ids):
        pixels = decode_tile(raw[tile_id * 16:(tile_id + 1) * 16])
        for y, row in enumerate(pixels):
            for x, value in enumerate(row):
                target[cell * 8 + x, y] = value
    return image


def workshop_crop(number: int, entry: dict) -> tuple[int, int, int, int]:
    return EDIT_X, number * ROW_HEIGHT + EDIT_Y, entry["screen_crop_px"][2], 8


def export_workshop(template: Path, guide: Path, crops_dir: Path) -> None:
    corpus = load_corpus()
    raw = load_original_resource(corpus)
    font = FONT_BIN.read_bytes()
    glyph_map = json.loads(FONT_MAP.read_text(encoding="utf-8"))
    workshop = Image.new("P", WORKSHOP_SIZE, 3)
    put_palette(workshop)
    draw = ImageDraw.Draw(workshop)
    tiny = ImageFont.load_default(size=6)
    guide_lines = [
        "id\tsource\tbg3_tile_ids\tscreen_crop_px\tworkshop_crop_px\ttile_capacity"
        "\toriginal_jp\ttranslation_kr_full\ttranslation_kr_display\tabbreviated"
    ]
    crops_dir.mkdir(parents=True, exist_ok=True)
    for number, entry in enumerate(corpus["entries"]):
        tile_ids = entry["tile_ids"]
        source = label_image(raw, tile_ids)
        packed = b"".join(raw[tile * 16:(tile + 1) * 16] for tile in tile_ids)
        if hashlib.sha256(packed).hexdigest() != entry["target_sha256"]:
            raise SystemExit(f"{entry['id']}: 원본 대상 타일 SHA-256 불일치")
        x, y, width, height = workshop_crop(number, entry)
        workshop.paste(source, (x, y))
        draw_workshop_label(
            workshop, font, glyph_map, EDIT_X, number * ROW_HEIGHT + 3,
            entry["text_kr_full"],
        )
        first, last = tile_ids[0], tile_ids[-1]
        draw.text(
            (112, number * ROW_HEIGHT + 3),
            f"{len(tile_ids)}x1 tiles ${first:03X}-${last:03X}",
            fill=2,
            font=tiny,
        )
        if x + width < 254:
            draw.line((x + width, y, x + width, y + height - 1), fill=2)
        crop_path = crops_dir / f"{number + 1:02d}_{entry['id']}_{width}x8.png"
        source.save(crop_path)
        sx, sy, sw, sh = entry["screen_crop_px"]
        guide_lines.append("\t".join([
            entry["id"], "$D5:4EC3",
            ",".join(f"${tile:03X}" for tile in tile_ids),
            f"x{sx},y{sy},w{sw},h{sh}", f"x{x},y{y},w{width},h{height}",
            str(len(tile_ids)), entry["text_jp"], entry["text_kr_full"],
            entry["text_kr_display"], str(entry["abbreviated"]).lower(),
        ]))
    template.parent.mkdir(parents=True, exist_ok=True)
    workshop.save(template)
    guide.parent.mkdir(parents=True, exist_ok=True)
    guide.write_text("\n".join(guide_lines) + "\n", encoding="utf-8")
    print(f"경기 HUD 라벨 작업지: {template} ({WORKSHOP_SIZE[0]}x{WORKSHOP_SIZE[1]}, 1:1)")
    print(f"개별 편집 PNG 2개: {crops_dir}")
    print(f"주소·번역 기록표: {guide}")


def import_workshop(workshop_path: Path, art_path: Path, manifest_path: Path) -> None:
    corpus = load_corpus()
    image = Image.open(workshop_path).convert("RGB")
    if image.size != WORKSHOP_SIZE:
        raise SystemExit(f"작업지 크기 불일치: {image.size} != {WORKSHOP_SIZE} (리사이즈 금지)")
    color_to_index = {rgb: index for index, rgb in enumerate(PALETTE_RGB)}
    source = image.load()
    packed = bytearray()
    records = []
    for number, entry in enumerate(corpus["entries"]):
        x0, y0, width, height = workshop_crop(number, entry)
        pixels = [[0] * width for _ in range(height)]
        unexpected = set()
        for y in range(height):
            for x in range(width):
                rgb = source[x0 + x, y0 + y]
                if rgb in color_to_index:
                    pixels[y][x] = color_to_index[rgb]
                elif rgb[0] == rgb[1] == rgb[2] and rgb[0] >= 128:
                    pixels[y][x] = 1
                else:
                    unexpected.add(rgb)
        if unexpected:
            sample = ", ".join("#%02X%02X%02X" % rgb for rgb in sorted(unexpected)[:8])
            raise SystemExit(
                f"{entry['id']} 편집 영역의 예상 밖 색상: {sample}. "
                "마젠타/흰색/청회색/검정만 사용하세요"
            )
        offset = len(packed)
        for tile_x in range(width // 8):
            tile_pixels = [row[tile_x * 8:(tile_x + 1) * 8] for row in pixels]
            packed.extend(encode_tile(tile_pixels))
        records.append({
            "id": entry["id"], "offset": offset,
            "size": len(entry["tile_ids"]) * 16,
            "source": "$D5:4EC3", "tile_ids": entry["tile_ids"],
            "screen_crop_px": entry["screen_crop_px"],
        })
    art_path.parent.mkdir(parents=True, exist_ok=True)
    art_path.write_bytes(packed)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({
        "format": "SNES 2bpp tile order, label-major",
        "palette": list(PALETTE_RGB),
        "total_bytes": len(packed),
        "entries": records,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"경기 HUD 편집 데이터: {art_path} ({len(packed)}B)")
    print(f"매니페스트: {manifest_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--guide", type=Path, default=DEFAULT_GUIDE)
    parser.add_argument("--crops", type=Path, default=DEFAULT_CROPS)
    parser.add_argument("--import-workshop", type=Path)
    parser.add_argument("--art", type=Path, default=DEFAULT_ART)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    if args.import_workshop:
        import_workshop(args.import_workshop.resolve(), args.art.resolve(), args.manifest.resolve())
    else:
        export_workshop(args.template.resolve(), args.guide.resolve(), args.crops.resolve())


if __name__ == "__main__":
    main()
