#!/usr/bin/env python3
"""포메이션 선택지와 기기 능력치 타일의 1:1 작업지를 만든다."""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_result_names import (  # noqa: E402
    FONT_BIN,
    FONT_MAP,
    draw_workshop_label,
)


CORPUS = ROOT / "assets/translations/manual_tile_workshops.json"
FORMATION_TEMPLATE = ROOT / "assets/graphics/formation/formation_labels_workshop_256px.png"
FORMATION_GUIDE = ROOT / "assets/graphics/formation/formation_labels_translation.tsv"
FORMATION_CROPS = ROOT / "assets/graphics/formation/crops"
STATS_TEMPLATE = ROOT / "assets/graphics/machine_stats/machine_stats_workshop_256px.png"
STATS_GUIDE = ROOT / "assets/graphics/machine_stats/machine_stats_translation.tsv"
STATS_CROPS = ROOT / "assets/graphics/machine_stats/crops"
GARAGE_TEMPLATE = ROOT / "assets/graphics/garage/garage_categories_workshop_256px.png"
GARAGE_GUIDE = ROOT / "assets/graphics/garage/garage_categories_translation.tsv"
GARAGE_CROPS = ROOT / "assets/graphics/garage/crops"

PALETTE_RGB = (
    (255, 0, 255),
    (255, 255, 255),
    (128, 128, 128),
    (0, 0, 0),
)
SOURCE_BACKGROUND = (33, 41, 140, 255)
SOURCE_TO_INDEX = {
    SOURCE_BACKGROUND: 0,
    (255, 255, 255, 255): 1,
    (0, 0, 0, 255): 3,
}
ROW_HEIGHT = 32
EDIT_X = 4
EDIT_Y = 14


def put_palette(image: Image.Image) -> None:
    palette = []
    for rgb in PALETTE_RGB:
        palette.extend(rgb)
    palette.extend([0] * (768 - len(palette)))
    image.putpalette(palette)


def find_source(normalized_suffix: str) -> Path:
    matches = []
    for path in (ROOT / "out").rglob("*.png"):
        normalized = unicodedata.normalize("NFC", str(path))
        if normalized.endswith(normalized_suffix):
            matches.append(path)
    if len(matches) != 1:
        raise SystemExit(f"소스 캡처 검색 실패: {normalized_suffix!r} -> {matches}")
    return matches[0]


def source_for_group(group_id: str) -> Path:
    if group_id == "formation_labels":
        return find_source("/포메이션_타일/formation.png")
    if group_id == "machine_stats":
        return find_source("/기기능력치.png")
    if group_id == "garage_categories":
        return find_source("/wgp2_kr_001_cat4x.png")
    raise SystemExit(f"알 수 없는 그룹: {group_id}")


def extract_capture_mask(source: Image.Image, entry: dict) -> Image.Image:
    """4배 확대 라벨에서 흰색/검정만 회수하고 배경 텍스처는 투명화한다."""
    width, height = entry["edit_size_px"]
    output = Image.new("P", (width, height), 0)
    put_palette(output)
    capture_box = entry.get("capture_crop_px")
    if capture_box is None:
        return output
    x, y, capture_width, capture_height = capture_box
    if capture_width != width * 4 or capture_height != height * 4:
        raise SystemExit(f"{entry['id']}: 캡처/편집 크기 배율 불일치")
    raw = source.crop((x, y, x + capture_width, y + capture_height)).convert("RGB")
    raw_pixels = raw.load()
    output_pixels = output.load()
    for yy in range(height):
        for xx in range(width):
            block = {
                raw_pixels[xx * 4 + bx, yy * 4 + by]
                for by in range(4) for bx in range(4)
            }
            if (255, 255, 255) in block:
                output_pixels[xx, yy] = 1
            elif (0, 0, 0) in block:
                output_pixels[xx, yy] = 3
    return output


def extract_crop(source: Image.Image, entry: dict, group_id: str) -> Image.Image:
    if group_id == "garage_categories":
        return extract_capture_mask(source, entry)
    x, y, width, height = entry["screen_crop_px"]
    if width % 8 or height % 8:
        raise SystemExit(f"{entry['id']}: 타일 경계가 아닌 크기 {width}x{height}")
    raw = source.crop((x, y, x + width, y + height))
    output = Image.new("P", (width, height), 0)
    put_palette(output)
    raw_pixels = raw.load()
    output_pixels = output.load()
    unexpected = set()
    for yy in range(height):
        for xx in range(width):
            rgba = raw_pixels[xx, yy]
            if rgba not in SOURCE_TO_INDEX:
                unexpected.add(rgba)
            else:
                output_pixels[xx, yy] = SOURCE_TO_INDEX[rgba]
    if unexpected:
        sample = ", ".join("#%02X%02X%02X%02X" % rgba for rgba in sorted(unexpected)[:8])
        raise SystemExit(f"{entry['id']}: 편집 영역에 예상 밖 색상 {sample}")
    return output


def validate_group(group: dict) -> None:
    seen = set()
    for entry in group["labels"]:
        if entry["id"] in seen:
            raise SystemExit(f"{group['id']}: ID 중복 {entry['id']}")
        seen.add(entry["id"])
        full = entry.get("text_kr_full")
        display = entry.get("text_kr_display")
        if not isinstance(full, str) or not isinstance(display, str):
            raise SystemExit(f"{entry['id']}: 완역/표시문 누락")
        if entry.get("abbreviated") != (full != display):
            raise SystemExit(f"{entry['id']}: 축약 플래그 불일치")


def compare_formation_sources(group: dict, reference: Image.Image) -> None:
    """팀러닝/레이스전 화면의 하단 4개 라벨이 같은지 확인한다."""
    suffixes = (
        "/포메이션_타일/팀러닝_포메이션_타일.png",
        "/포메이션_타일/레이스전_포메이션.png",
    )
    for suffix in suffixes:
        candidate = Image.open(find_source(suffix)).convert("RGBA")
        for entry in group["labels"]:
            x, y, width, height = entry["screen_crop_px"]
            box = (x, y, x + width, y + height)
            if candidate.crop(box).tobytes() != reference.crop(box).tobytes():
                raise SystemExit(f"{suffix}의 {entry['id']} 라벨이 formation.png와 다릅니다")


def edit_size(entry: dict) -> tuple[int, int]:
    if "edit_size_px" in entry:
        return tuple(entry["edit_size_px"])
    return tuple(entry["screen_crop_px"][2:])


def workshop_crop(number: int, entry: dict) -> tuple[int, int, int, int]:
    width, height = edit_size(entry)
    return EDIT_X, number * ROW_HEIGHT + EDIT_Y, width, height


def export_group(
    group: dict,
    template_path: Path,
    guide_path: Path,
    crops_dir: Path,
    font: bytes,
    glyph_map: dict[str, int],
) -> None:
    validate_group(group)
    source = Image.open(source_for_group(group["id"])).convert("RGBA")
    if group["id"] == "formation_labels":
        compare_formation_sources(group, source)
    labels = group["labels"]
    workshop = Image.new("P", (256, len(labels) * ROW_HEIGHT), 3)
    put_palette(workshop)
    draw = ImageDraw.Draw(workshop)
    tiny = ImageFont.load_default(size=6)
    guide = [
        "id\tscreen_crop_px\tworkshop_crop_px\ttile_capacity\toriginal_jp"
        "\ttranslation_kr_full\ttranslation_kr_display\tabbreviated"
    ]
    crops_dir.mkdir(parents=True, exist_ok=True)
    for number, entry in enumerate(labels):
        crop = extract_crop(source, entry, group["id"])
        x, y, width, height = workshop_crop(number, entry)
        workshop.paste(crop, (x, y))
        draw_workshop_label(
            workshop,
            font,
            glyph_map,
            EDIT_X,
            number * ROW_HEIGHT + 3,
            entry["text_kr_display"],
        )
        draw.text(
            (112, number * ROW_HEIGHT + 3),
            f"{width // 8}x{height // 8} tiles",
            fill=2,
            font=tiny,
        )
        crop.save(crops_dir / f"{number + 1:02d}_{entry['id']}_{width}x{height}.png")
        source_crop = entry.get("screen_crop_px") or entry.get("capture_crop_px")
        source_crop_text = (
            f"x{source_crop[0]},y{source_crop[1]},w{source_crop[2]},h{source_crop[3]}"
            if source_crop is not None else "(캡처 없음/빈칸)"
        )
        guide.append("\t".join([
            entry["id"], source_crop_text,
            f"x{x},y{y},w{width},h{height}", str(width // 8),
            entry["text_jp"], entry["text_kr_full"], entry["text_kr_display"],
            str(entry["abbreviated"]).lower(),
        ]))
    template_path.parent.mkdir(parents=True, exist_ok=True)
    workshop.save(template_path)
    guide_path.parent.mkdir(parents=True, exist_ok=True)
    guide_path.write_text("\n".join(guide) + "\n", encoding="utf-8")
    print(f"{group['id']} 작업 시트: {template_path} ({workshop.width}x{workshop.height}, 1:1)")
    print(f"개별 편집 PNG {len(labels)}개: {crops_dir}")


def encode_snes_2bpp(image: Image.Image) -> bytes:
    pixels = image.load()
    output = bytearray()
    for tile_y in range(image.height // 8):
        for tile_x in range(image.width // 8):
            for row in range(8):
                plane0 = 0
                plane1 = 0
                for column in range(8):
                    value = pixels[tile_x * 8 + column, tile_y * 8 + row]
                    plane0 |= (value & 1) << (7 - column)
                    plane1 |= ((value >> 1) & 1) << (7 - column)
                output.extend((plane0, plane1))
    return bytes(output)


def import_group(group: dict, workshop_path: Path, output_path: Path, manifest_path: Path) -> None:
    labels = group["labels"]
    image = Image.open(workshop_path).convert("RGB")
    expected_size = (256, len(labels) * ROW_HEIGHT)
    if image.size != expected_size:
        raise SystemExit(f"{group['id']} 작업지 크기 불일치: {image.size} != {expected_size}")
    allowed = {
        PALETTE_RGB[0]: 0,
        PALETTE_RGB[1]: 1,
        PALETTE_RGB[3]: 3,
    }
    source = image.load()
    packed = bytearray()
    records = []
    for number, entry in enumerate(labels):
        x0, y0, width, height = workshop_crop(number, entry)
        crop = Image.new("P", (width, height), 0)
        put_palette(crop)
        target = crop.load()
        unexpected = set()
        for y in range(height):
            for x in range(width):
                rgb = source[x0 + x, y0 + y]
                if rgb in allowed:
                    target[x, y] = allowed[rgb]
                # 사용자가 고른 픽셀 폰트의 잉크가 완전한 #FFFFFF 대신
                # 단일 회색으로 저장될 수 있다. 안티앨리어싱 색을 허용하는
                # 것이 아니라, 중간색 없는 한 가지 밝은 무채색만 게임의
                # 흰 잉크 팔레트로 양자화한다.
                elif rgb[0] == rgb[1] == rgb[2] and rgb[0] >= 128:
                    target[x, y] = 1
                else:
                    unexpected.add(rgb)
        if unexpected:
            sample = ", ".join("#%02X%02X%02X" % rgb for rgb in sorted(unexpected)[:8])
            raise SystemExit(
                f"{entry['id']} 편집 영역에 허용되지 않은 색상: {sample}. "
                "마젠타/밝은 단색 회색(흰 잉크)/검정만 사용하세요"
            )
        encoded = encode_snes_2bpp(crop)
        records.append({
            "id": entry["id"],
            "offset": len(packed),
            "size": len(encoded),
            "screen_crop_px": entry.get("screen_crop_px"),
            "capture_crop_px": entry.get("capture_crop_px"),
            "sjis_addr": entry.get("sjis_addr"),
        })
        packed.extend(encoded)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(packed)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({
        "group": group["id"],
        "format": "SNES 2bpp tile order, label-major",
        "total_bytes": len(packed),
        "entries": records,
        "rom_insertion": group.get(
            "rom_insertion_note", "pending source-address trace from captured tilemaps"
        ),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{group['id']} 2bpp 작업 데이터: {output_path} ({len(packed)}B)")


def load_groups() -> dict[str, dict]:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    return {group["id"]: group for group in corpus["groups"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--import-group",
        choices=("formation_labels", "machine_stats", "garage_categories"),
    )
    parser.add_argument("--workshop", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    groups = load_groups()
    if args.import_group:
        if not args.workshop or not args.out or not args.manifest:
            parser.error("--import-group에는 --workshop/--out/--manifest가 모두 필요합니다")
        import_group(
            groups[args.import_group],
            args.workshop.resolve(),
            args.out.resolve(),
            args.manifest.resolve(),
        )
        return

    font = FONT_BIN.read_bytes()
    glyph_map = json.loads(FONT_MAP.read_text(encoding="utf-8"))
    export_group(
        groups["formation_labels"], FORMATION_TEMPLATE, FORMATION_GUIDE,
        FORMATION_CROPS, font, glyph_map,
    )
    export_group(
        groups["machine_stats"], STATS_TEMPLATE, STATS_GUIDE,
        STATS_CROPS, font, glyph_map,
    )
    export_group(
        groups["garage_categories"], GARAGE_TEMPLATE, GARAGE_GUIDE,
        GARAGE_CROPS, font, glyph_map,
    )


if __name__ == "__main__":
    main()
