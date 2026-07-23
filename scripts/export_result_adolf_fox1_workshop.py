#!/usr/bin/env python3
"""아돌프/FOX1 Result 이름의 과거 겹침을 분석·이관하는 도구다.

두 이름은 물리 타일 $008F를 공유한다.

* 아돌프: 아래쪽 첫 셀
* FOX1:   위쪽 첫 셀

기본 내보내기는 분리 전 구조를 진단하기 위한 기록이다. 현재 빌드는 아돌프를
$0080-$0084로 옮겨 FOX1과 분리했으며, ``--import-workshop``은 사용자가 편집한
구 작업지를 새 독립 범위 승인본으로 이관할 때만 사용한다.
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

from build_result_names import (  # noqa: E402
    PALETTE_RGB,
    decode_asset,
    indexed_image_from_pixels,
    label_pixels_from_asset,
)


DEFAULT_ROM = ROOT / "out/wgp2_kr.smc"
DEFAULT_IMAGE = ROOT / "out/result_adolf_fox1_overlap_workshop_256px.png"
DEFAULT_MANIFEST = ROOT / "out/result_adolf_fox1_overlap_workshop.json"
DEFAULT_APPROVED = ROOT / "assets/result_names/result_names_workshop_approved.png"
TRANSLATIONS = ROOT / "assets/translations/result_names.json"

ADOLF_TOP = [0x007F, 0x0080, 0x0081, 0x0082, 0x0083, 0x0084]
FOX1_TOP = [0x008F, 0x00A0, 0x00A1, 0x00A2, 0x00A3, 0x00A4]
SHARED_TILE = 0x008F

ADOLF_CROP = (4, 12, 48, 16)
FOX1_CROP = (4, 44, 48, 16)
ADOLF_SHARED_CROP = (4, 20, 8, 8)
FOX1_SHARED_CROP = (4, 44, 8, 8)


def set_palette(image: Image.Image) -> None:
    palette: list[int] = []
    for rgb in PALETTE_RGB:
        palette.extend(rgb)
    palette.extend([0] * (768 - len(palette)))
    image.putpalette(palette)


def paste_label(image: Image.Image, data: bytes, top_tiles: list[int], crop: tuple[int, int, int, int]) -> None:
    x, y, width, height = crop
    logical = indexed_image_from_pixels(label_pixels_from_asset(data, top_tiles))
    assert logical.size == (width, height)
    image.paste(logical, (x, y))


def tile_bytes(data: bytes, tile_index: int) -> str:
    start = tile_index * 16
    return data[start:start + 16].hex(" ").upper()


def checked_crop(
    image: Image.Image,
    box: tuple[int, int, int, int],
    label: str,
) -> Image.Image:
    crop = image.crop(box).convert("RGB")
    allowed = set(PALETTE_RGB)
    unexpected = sorted(set(crop.getdata()) - allowed)
    if unexpected:
        sample = ", ".join("#%02X%02X%02X" % rgb for rgb in unexpected[:8])
        raise SystemExit(f"{label} 편집 영역에 2bpp 팔레트 밖 색상: {sample}")
    return crop


def import_legacy_overlap_workshop(
    image_path: Path,
    approved_path: Path,
    manifest_path: Path,
) -> None:
    """사용자가 편집한 구 겹침 작업지를 새 독립 범위 승인본으로 옮긴다.

    아돌프는 새 범위 $0080-$0084의 5셀에 구 작업지 앞 40px를 그대로
    저장한다. 따라서 구 공유 타일 영역은 새 물리 타일 $0090이 되고 FOX1의
    $008F와 더 이상 충돌하지 않는다.
    """
    source_bytes = image_path.read_bytes()
    source = Image.open(image_path).convert("RGB")
    if source.size != (256, 128):
        raise SystemExit(f"아돌프/FOX1 작업지 크기 불일치: {source.size}")

    corpus = json.loads(TRANSLATIONS.read_text(encoding="utf-8"))
    entries = [entry for entry in corpus["labels"] if entry.get("text_jp") is not None]
    adolf_number = next(
        number for number, entry in enumerate(entries)
        if entry["racer_ids"] == [16]
    )
    fox1_number = next(
        number for number, entry in enumerate(entries)
        if entry["racer_ids"] == [19, 24, 29]
    )
    adolf_entry = entries[adolf_number]
    fox1_entry = entries[fox1_number]
    if adolf_entry.get("original_tile_span") != "007F-0084" or adolf_entry["tile_span"] != "0080-0084":
        raise SystemExit("아돌프 독립 범위 정의 불일치")
    if fox1_entry["tile_span"] != "008F-00A4":
        raise SystemExit("FOX1 범위 정의 불일치")

    approved_bytes_before = approved_path.read_bytes()
    approved = Image.open(approved_path).convert("RGB")
    expected_size = (256, ((len(entries) + 1) // 2) * 32)
    if approved.size != expected_size:
        raise SystemExit(f"Result 승인 작업지 크기 불일치: {approved.size} != {expected_size}")

    adolf = checked_crop(source, (4, 12, 44, 28), "아돌프")
    fox1 = checked_crop(source, (4, 44, 52, 60), "FOX1")
    adolf_dest = (adolf_number % 2 * 128 + 4, adolf_number // 2 * 32 + 12)
    fox1_dest = (fox1_number % 2 * 128 + 4, fox1_number // 2 * 32 + 12)
    approved.paste(adolf, adolf_dest)
    approved.paste(fox1, fox1_dest)

    # 구 6셀 아돌프의 마지막 칸은 새 5셀 편집 범위 밖이다. 사람이 다음
    # 작업 때 이전 데이터로 오인하지 않도록 작업지에서만 검정으로 비운다.
    approved.paste(Image.new("RGB", (8, 16), PALETTE_RGB[3]), (adolf_dest[0] + 40, adolf_dest[1]))
    approved.save(approved_path)
    approved_bytes_after = approved_path.read_bytes()

    record = {
        "input_workshop": str(image_path),
        "input_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "approved_workshop": str(approved_path),
        "approved_sha256_before": hashlib.sha256(approved_bytes_before).hexdigest(),
        "approved_sha256_after": hashlib.sha256(approved_bytes_after).hexdigest(),
        "adolf": {
            "source_crop_px": {"x": 4, "y": 12, "w": 40, "h": 16},
            "destination_crop_px": {
                "x": adolf_dest[0], "y": adolf_dest[1], "w": 40, "h": 16,
            },
            "original_span": "007F-0084",
            "patched_span": "0080-0084",
        },
        "fox1": {
            "source_crop_px": {"x": 4, "y": 44, "w": 48, "h": 16},
            "destination_crop_px": {
                "x": fox1_dest[0], "y": fox1_dest[1], "w": 48, "h": 16,
            },
            "span": "008F-00A4",
        },
        "shared_tile_resolution": {
            "old_shared_tile": "008F",
            "adolf_new_bottom_tile": "0090",
            "fox1_top_tile": "008F",
            "result": "independent",
        },
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"아돌프/FOX1 승인 작업본 반영 → {approved_path}")
    print("  아돌프 5셀 $0080-$0084 / FOX1 $008F,$00A0-$00A4, 공유 해소")
    print(f"  가져오기 기록 → {manifest_path}")


def build(rom_path: Path, image_path: Path, manifest_path: Path) -> None:
    rom = rom_path.read_bytes()
    data, compressed_size = decode_asset(rom)

    image = Image.new("P", (256, 128), 3)
    set_palette(image)
    paste_label(image, data, ADOLF_TOP, ADOLF_CROP)
    paste_label(image, data, FOX1_TOP, FOX1_CROP)

    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=6)
    draw.text((4, 2), "ADOLF  ID16  007F-0084", fill=1, font=font)
    draw.text((4, 34), "FOX1  ID19/24/29  008F-00A4", fill=1, font=font)

    # 편집 픽셀을 건드리지 않는 바깥쪽 괄호. 회색 괄호가 가리키는 두 8x8
    # 영역은 동일한 물리 타일 $008F다.
    draw.line((3, 20, 3, 27), fill=2)
    draw.line((3, 20, 3, 20), fill=2)
    draw.line((3, 27, 3, 27), fill=2)
    draw.text((58, 20), "SHARED 008F: ADOLF LOWER CELL 0", fill=2, font=font)
    draw.line((3, 44, 3, 51), fill=2)
    draw.line((3, 44, 3, 44), fill=2)
    draw.line((3, 51, 3, 51), fill=2)
    draw.text((58, 44), "SHARED 008F: FOX1 UPPER CELL 0", fill=2, font=font)

    # 물리 행을 별도로 재표시한다. 왼쪽은 아돌프, 오른쪽은 FOX1이며,
    # 공유 타일은 두 블록의 첫 열에서 정확히 같은 픽셀로 보인다.
    draw.text((4, 67), "PHYSICAL ROWS / CURRENT ROM", fill=1, font=font)
    paste_label(image, data, ADOLF_TOP, (4, 78, 48, 16))
    paste_label(image, data, FOX1_TOP, (132, 78, 48, 16))
    draw.text((4, 97), "A TOP 007F-0084", fill=1, font=font)
    draw.text((4, 106), "A BOT 008F-0094", fill=1, font=font)
    draw.text((132, 97), "F TOP 008F,A0-A4", fill=1, font=font)
    draw.text((132, 106), "F BOT 009F,B0-B4", fill=1, font=font)
    draw.text((4, 117), "RULE: ADOLF (4,20,8,8) == FOX1 (4,44,8,8)", fill=2, font=font)

    image_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(image_path)

    manifest = {
        "source_rom": str(rom_path),
        "source_rom_sha256": hashlib.sha256(rom).hexdigest(),
        "source_asset": "$D9:1DDC",
        "racer_span_table": "$C1:CBAF",
        "compressed_size": compressed_size,
        "image": str(image_path),
        "image_size_px": [256, 128],
        "palette_rgb": [list(rgb) for rgb in PALETTE_RGB],
        "editable_crops": {
            "adolf": {
                "racer_ids": [16],
                "logical_span": "007F-0084",
                "crop_px": {"x": 4, "y": 12, "w": 48, "h": 16},
                "top_tiles": [f"{tile:04X}" for tile in ADOLF_TOP],
                "bottom_tiles": [f"{tile + 0x10:04X}" for tile in ADOLF_TOP],
            },
            "fox1": {
                "racer_ids": [19, 24, 29],
                "logical_span": "008F-00A4",
                "crop_px": {"x": 4, "y": 44, "w": 48, "h": 16},
                "top_tiles": [f"{tile:04X}" for tile in FOX1_TOP],
                "bottom_tiles": [f"{tile + 0x10:04X}" for tile in FOX1_TOP],
            },
        },
        "shared_tile": {
            "tile": "008F",
            "adolf_role": "bottom tile of logical cell 0",
            "fox1_role": "top tile of logical cell 0",
            "adolf_crop_px": {"x": 4, "y": 20, "w": 8, "h": 8},
            "fox1_crop_px": {"x": 4, "y": 44, "w": 8, "h": 8},
            "current_2bpp_hex": tile_bytes(data, SHARED_TILE),
            "import_invariant": "the two 8x8 crops must be pixel-identical",
        },
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"아돌프/FOX1 겹침 작업지: {image_path} (256x128, 1:1)")
    print(f"주소·공유 타일 기록: {manifest_path}")
    print(f"$008F 2bpp: {manifest['shared_tile']['current_2bpp_hex']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rom", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--import-workshop",
        type=Path,
        help="사용자가 편집한 구 겹침 작업지를 승인 전체 시트에 반영",
    )
    parser.add_argument("--approved", type=Path, default=DEFAULT_APPROVED)
    args = parser.parse_args()
    if args.import_workshop:
        import_legacy_overlap_workshop(
            args.import_workshop.resolve(),
            args.approved.resolve(),
            args.manifest.resolve(),
        )
        return
    build(args.rom.resolve(), args.image.resolve(), args.manifest.resolve())


if __name__ == "__main__":
    main()
