#!/usr/bin/env python3
"""챕터 1~10 시작 화면 제목의 1:1 타일 작업지를 내보내고 검사한다.

정본 캡처는 out/스테이지_타이틀 아래의 256x256 타일맵 이미지다.
승인 제목은 화면 x32..223, y80..143의 192x64px(24x8 타일)에 넣는다.
원문 제목의 실제 타일맵은 좌우로 2타일씩 더 넓으므로 빌드 시 그 여백을
투명화한다. y193..199의 ``STAGE n``은 별도 표시라 편집 대상에서 제외한다.

각 88px 행:
  y+01: 현재 통합 ROM의 한글 문자열 렌더(번역 참고용)
  y+17: STAGE/원문·번역 폭/캡처 유무(참고용)
  y+24: 192x64px 제목 편집 영역

편집 영역의 팔레트:
  #FF00FF = 투명 배경, #FFFFFF = 흰 잉크, #AD9C9C = 그림자
안티앨리어싱과 이미지 리사이즈는 금지한다.
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
import unicodedata
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_patch import WIDTH_BASE, decode_game_glyph  # noqa: E402
from decode_script import decode, render  # noqa: E402


ORIGINAL_ROM = ROOT / "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
BUILT_ROM = ROOT / "out/wgp2_kr.smc"
GLYPH_MAP = ROOT / "out/glyph_map.json"
TRANSLATIONS = ROOT / "assets/translations/stage_titles.json"
DEFAULT_TEMPLATE = ROOT / "assets/stage_titles/stage_titles_workshop_256px.png"
DEFAULT_GUIDE = ROOT / "assets/stage_titles/stage_titles_translation.tsv"
DEFAULT_CROPS = ROOT / "assets/stage_titles/crops"
DEFAULT_ART_BIN = ROOT / "out/stage_titles_art_2bpp.bin"
DEFAULT_MANIFEST = ROOT / "out/stage_titles_art_manifest.json"

PALETTE_RGB = (
    (255, 0, 255),      # 0: transparent
    (255, 255, 255),    # 1: white ink
    (173, 156, 156),    # 2: captured shadow
    (0, 0, 0),          # 3: workshop-only background
)
CAPTURE_COLORS = {
    (74, 107, 255, 255): 0,
    (255, 255, 255, 255): 1,
    (173, 156, 156, 255): 2,
}

STAGE_COUNT = 10
SCREEN_X = 32
SCREEN_Y = 80
EDIT_WIDTH = 192
EDIT_HEIGHT = 64
EDIT_X = 4
EDIT_Y = 24
ROW_HEIGHT = EDIT_Y + EDIT_HEIGHT
WORKSHOP_SIZE = (256, STAGE_COUNT * ROW_HEIGHT)


def put_palette(image: Image.Image) -> None:
    palette = []
    for rgb in PALETTE_RGB:
        palette.extend(rgb)
    palette.extend([0] * (768 - len(palette)))
    image.putpalette(palette)


def read_terminated_stream(rom: bytes, offset: int) -> bytes:
    end = offset
    while end < len(rom):
        lead = rom[end]
        end += 2 if 1 <= lead <= 4 or lead == 7 else 1
        if lead == 0:
            return rom[offset:end]
    raise SystemExit(f"종료자가 없는 제목 스트림: 0x{offset:06X}")


def render_tokens(rom: bytes, tokens: list[tuple], width: int = 208) -> tuple[Image.Image, int]:
    image = Image.new("P", (width, 16), 0)
    put_palette(image)
    target = image.load()
    pen_x = 0
    for token in tokens:
        if token[0] != "glyph":
            continue
        glyph_index = token[1]
        glyph = decode_game_glyph(rom, glyph_index)
        for y in range(16):
            for x in range(16):
                if glyph[y][x] and pen_x + x < width:
                    target[pen_x + x, y] = 1
        pen_x += rom[WIDTH_BASE + glyph_index]
    if pen_x > width:
        raise SystemExit(f"제목 참고 렌더 폭 초과: {pen_x}px > {width}px")
    return image, pen_x


def find_capture_paths() -> dict[int, Path]:
    captures = {}
    for path in (ROOT / "out").rglob("*.png"):
        normalized = unicodedata.normalize("NFC", str(path))
        if "스테이지_타이틀" not in normalized:
            continue
        match = re.search(r"스테이지(\d+)", normalized)
        if not match:
            continue
        stage = int(match.group(1))
        if 1 <= stage <= STAGE_COUNT:
            if stage in captures:
                raise SystemExit(f"stage {stage} 캡처 중복: {captures[stage]} / {path}")
            captures[stage] = path
    return captures


def captured_title_crop(path: Path, stage: int) -> Image.Image:
    source = Image.open(path).convert("RGBA")
    if source.size != (256, 256):
        raise SystemExit(f"stage {stage} 캡처 크기 불일치: {source.size} != (256, 256)")
    crop = source.crop((SCREEN_X, SCREEN_Y, SCREEN_X + EDIT_WIDTH, SCREEN_Y + EDIT_HEIGHT))
    result = Image.new("P", (EDIT_WIDTH, EDIT_HEIGHT), 0)
    put_palette(result)
    source_pixels = crop.load()
    target_pixels = result.load()
    unexpected = set()
    for y in range(EDIT_HEIGHT):
        for x in range(EDIT_WIDTH):
            rgba = source_pixels[x, y]
            if rgba not in CAPTURE_COLORS:
                unexpected.add(rgba)
            else:
                target_pixels[x, y] = CAPTURE_COLORS[rgba]
    if unexpected:
        sample = ", ".join("#%02X%02X%02X%02X" % rgba for rgba in sorted(unexpected)[:8])
        raise SystemExit(f"stage {stage} 제목 영역에 예상 밖 색상: {sample}")
    return result


def load_entries(original: bytes, built: bytes) -> list[dict]:
    corpus = json.loads(TRANSLATIONS.read_text(encoding="utf-8"))
    entries = corpus.get("entries")
    if not isinstance(entries, list) or [e.get("stage") for e in entries] != list(range(1, 11)):
        raise SystemExit("stage_titles.json은 stage 1~10의 10개 엔트리여야 합니다")

    pointer_offset = int(corpus["pointer_table"]["file_offset"], 16)
    glyph_map = json.loads(GLYPH_MAP.read_text(encoding="utf-8"))["char2idx"]
    index_to_char = {index: char for char, index in glyph_map.items()}
    captures = find_capture_paths()
    loaded = []
    for number, entry in enumerate(entries):
        raw_jp = bytes.fromhex(entry["raw_hex"])
        original_offset = int(entry["file_offset"], 16)
        if original[original_offset:original_offset + len(raw_jp)] != raw_jp:
            raise SystemExit(f"stage {number + 1}: raw_hex != 원본 ROM")
        _, jp_width = render_tokens(original, decode(raw_jp))

        built_addr = struct.unpack_from("<H", built, pointer_offset + number * 2)[0]
        raw_kr = read_terminated_stream(built, built_addr)
        kr_tokens = decode(raw_kr)
        expected = entry["text_kr"]
        if not expected.endswith("{end}"):
            expected += "{end}"
        actual = render(kr_tokens, index_to_char)
        if actual != expected:
            raise SystemExit(
                f"stage {number + 1}: 통합 ROM 제목 불일치: {actual!r} != {expected!r}"
            )
        kr_image, kr_width = render_tokens(built, kr_tokens)
        capture_path = captures.get(number + 1)
        edit_image = (
            captured_title_crop(capture_path, number + 1)
            if capture_path else Image.new("P", (EDIT_WIDTH, EDIT_HEIGHT), 0)
        )
        put_palette(edit_image)
        loaded.append({
            "entry": entry,
            "jp_width": jp_width,
            "kr_image": kr_image,
            "kr_width": kr_width,
            "capture_path": capture_path,
            "edit_image": edit_image,
        })
    return loaded


def workshop_crop(stage: int) -> tuple[int, int, int, int]:
    return EDIT_X, (stage - 1) * ROW_HEIGHT + EDIT_Y, EDIT_WIDTH, EDIT_HEIGHT


def paste_white_ink(target: Image.Image, source: Image.Image, x0: int, y0: int) -> None:
    target_pixels = target.load()
    source_pixels = source.load()
    for y in range(source.height):
        for x in range(source.width):
            if source_pixels[x, y] == 1:
                target_pixels[x0 + x, y0 + y] = 1


def export_template(template_path: Path, guide_path: Path, crops_dir: Path) -> None:
    original = ORIGINAL_ROM.read_bytes()
    built = BUILT_ROM.read_bytes()
    if len(original) != 0x200000 or len(built) != len(original):
        raise SystemExit("원본/통합 ROM은 헤더리스 2MB여야 합니다")
    loaded = load_entries(original, built)

    workshop = Image.new("P", WORKSHOP_SIZE, 3)
    put_palette(workshop)
    draw = ImageDraw.Draw(workshop)
    tiny = ImageFont.load_default(size=6)
    guide = [
        "stage\tscreen_crop_px\tworkshop_crop_px\tcanvas_px\tcapture"
        "\tjp_render_width_px\tkr_render_width_px\toriginal_jp\ttranslation_kr"
    ]
    crops_dir.mkdir(parents=True, exist_ok=True)
    for item in loaded:
        entry = item["entry"]
        stage = entry["stage"]
        row_y = (stage - 1) * ROW_HEIGHT
        paste_white_ink(workshop, item["kr_image"], EDIT_X, row_y + 1)
        capture_label = "CAPTURE" if item["capture_path"] else "BLANK"
        draw.text(
            (EDIT_X, row_y + 17),
            f"S{stage:02d} KR{item['kr_width']:03d} JP{item['jp_width']:03d} {capture_label}",
            fill=2,
            font=tiny,
        )
        x, y, width, height = workshop_crop(stage)
        workshop.paste(item["edit_image"], (x, y))
        crop_path = crops_dir / f"stage{stage:02d}_title_192x64.png"
        item["edit_image"].save(crop_path)
        guide.append("\t".join([
            str(stage),
            f"x{SCREEN_X},y{SCREEN_Y},w{EDIT_WIDTH},h{EDIT_HEIGHT}",
            f"x{x},y{y},w{width},h{height}",
            f"{width}x{height}",
            unicodedata.normalize("NFC", str(item["capture_path"])) if item["capture_path"] else "(캡처 없음/빈칸)",
            str(item["jp_width"]), str(item["kr_width"]),
            entry["text_jp"].removesuffix("{end}"),
            entry["text_kr"].removesuffix("{end}"),
        ]))

    template_path.parent.mkdir(parents=True, exist_ok=True)
    workshop.save(template_path)
    guide_path.parent.mkdir(parents=True, exist_ok=True)
    guide_path.write_text("\n".join(guide) + "\n", encoding="utf-8")
    print(
        f"챕터 제목 작업 시트: {template_path} "
        f"({WORKSHOP_SIZE[0]}x{WORKSHOP_SIZE[1]}, 1:1, {STAGE_COUNT}개)"
    )
    print(f"개별 편집 PNG 10개: {crops_dir}")
    print(f"좌표/번역표: {guide_path}")


def encode_snes_2bpp(image: Image.Image) -> bytes:
    """192x64 인덱스 이미지를 24x8 SNES 2bpp 타일 순서로 인코딩한다."""
    pixels = image.load()
    output = bytearray()
    for tile_y in range(EDIT_HEIGHT // 8):
        for tile_x in range(EDIT_WIDTH // 8):
            for row in range(8):
                plane0 = 0
                plane1 = 0
                for column in range(8):
                    value = pixels[tile_x * 8 + column, tile_y * 8 + row]
                    plane0 |= (value & 1) << (7 - column)
                    plane1 |= ((value >> 1) & 1) << (7 - column)
                output.extend((plane0, plane1))
    return bytes(output)


def import_workshop(image_path: Path, art_path: Path, manifest_path: Path) -> None:
    image = Image.open(image_path).convert("RGB")
    if image.size != WORKSHOP_SIZE:
        raise SystemExit(f"작업 PNG 크기 불일치: {image.size} != {WORKSHOP_SIZE} (리사이즈 금지)")

    allowed = {rgb: index for index, rgb in enumerate(PALETTE_RGB[:3])}
    source = image.load()
    packed = bytearray()
    entries = []
    for stage in range(1, STAGE_COUNT + 1):
        x0, y0, width, height = workshop_crop(stage)
        crop = Image.new("P", (width, height), 0)
        put_palette(crop)
        crop_pixels = crop.load()
        unexpected = set()
        for y in range(height):
            for x in range(width):
                rgb = source[x0 + x, y0 + y]
                if rgb not in allowed:
                    unexpected.add(rgb)
                else:
                    crop_pixels[x, y] = allowed[rgb]
        if unexpected:
            sample = ", ".join("#%02X%02X%02X" % rgb for rgb in sorted(unexpected)[:8])
            raise SystemExit(
                f"stage {stage} 편집 영역에 허용되지 않은 색상: {sample}. "
                "마젠타/흰색/#AD9C9C 그림자만 사용하세요"
            )
        stage_bytes = encode_snes_2bpp(crop)
        entries.append({
            "stage": stage,
            "offset": len(packed),
            "size": len(stage_bytes),
            "screen_origin": [SCREEN_X, SCREEN_Y],
            "tile_grid": [EDIT_WIDTH // 8, EDIT_HEIGHT // 8],
        })
        packed.extend(stage_bytes)

    art_path.parent.mkdir(parents=True, exist_ok=True)
    art_path.write_bytes(packed)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({
        "format": "SNES 2bpp tile order, stage-major",
        "stage_count": STAGE_COUNT,
        "canvas": f"{EDIT_WIDTH}x{EDIT_HEIGHT}",
        "screen_crop": [SCREEN_X, SCREEN_Y, EDIT_WIDTH, EDIT_HEIGHT],
        "bytes_per_stage": EDIT_WIDTH // 8 * EDIT_HEIGHT // 8 * 16,
        "total_bytes": len(packed),
        "palette": list(PALETTE_RGB[:3]),
        "entries": entries,
        "rom_insertion": (
            "build_stage_intro_titles.py maps the 24x8 screen cells into each original "
            "$D9/$DA LZSS resource, clears the two outer columns on each side, and "
            "preserves STAGE n"
        ),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"챕터 제목 2bpp 작업 데이터: {art_path} ({len(packed)}B)")
    print(f"매니페스트: {manifest_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--guide", type=Path, default=DEFAULT_GUIDE)
    parser.add_argument("--crops", type=Path, default=DEFAULT_CROPS)
    parser.add_argument("--import-workshop", type=Path)
    parser.add_argument("--art-bin", type=Path, default=DEFAULT_ART_BIN)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    if args.import_workshop:
        import_workshop(
            args.import_workshop.resolve(),
            args.art_bin.resolve(),
            args.manifest.resolve(),
        )
    else:
        export_template(args.template.resolve(), args.guide.resolve(), args.crops.resolve())


if __name__ == "__main__":
    main()
