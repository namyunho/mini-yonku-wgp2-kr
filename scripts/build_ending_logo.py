#!/usr/bin/env python3
"""VICTORYS 에피소드 인터미션 하단 로고를 승인 256×256 BMP로 교체한다.

타이틀 화면과는 다른 전용 자원이다. Mesen 실측 경로:
  $D9:A5B1 LZSS(raw 3072) -> BG1 4bpp VRAM word $0000
  $D9:B078 LZSS(raw 2048) -> BG1 tilemap VRAM word $7000

승인본은 원래 압축 슬롯을 소폭 초과하므로 확인된 $D9:D239 0xFF 런으로
두 자원을 함께 재배치하고 인터미션 로더의 PEA 소스 두 곳만 갱신한다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zlib
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from lzss import compress_optimal, decompress


ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_ROM = ROOT / "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
DEFAULT_ROM = ROOT / "out/wgp2_kr.smc"
CORPUS = ROOT / "assets/translations/ending_logo.json"
DEFAULT_PREVIEW = ROOT / "out/ending_logo_preview.png"
DEFAULT_MANIFEST = ROOT / "out/ending_logo_manifest.json"
ROM_SIZE = 0x200000
ORIGINAL_CRC32 = 0x4459D4D0
ORIGINAL_MD5 = "acdeb2ee6ef7b460c5dfed6957f8581a"
TILE_CAPACITY = 96
GRID = 32
ALLOWED_PALETTES = (0, 6, 7)


@dataclass(frozen=True)
class BuiltAssets:
    chr_raw: bytes
    tilemap_raw: bytes
    chr_compressed: bytes
    tilemap_compressed: bytes
    preview: Image.Image
    unique_tiles: int
    changed_pixels: int
    nonbackground_pixels: int


def load_corpus() -> dict:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    translation = corpus["translation"]
    if translation["abbreviated"] != (
        translation["text_kr_full"] != translation["text_kr_display"]
    ):
        raise SystemExit("인터미션 로고 완역/표시문 축약 플래그 불일치")
    return corpus


def pc_value(value: str | int) -> int:
    return int(value, 0) if isinstance(value, str) else value


def load_original(corpus: dict) -> tuple[bytes, dict[str, bytes]]:
    rom = ORIGINAL_ROM.read_bytes()
    if len(rom) != ROM_SIZE:
        raise SystemExit(f"원본 ROM이 헤더리스 2MB가 아님: {len(rom)}")
    if zlib.crc32(rom) & 0xFFFFFFFF != ORIGINAL_CRC32:
        raise SystemExit("원본 ROM CRC32 불일치")
    if hashlib.md5(rom).hexdigest() != ORIGINAL_MD5:
        raise SystemExit("원본 ROM MD5 불일치")
    raw_resources: dict[str, bytes] = {}
    for name in ("chr", "tilemap"):
        record = corpus["resources"][name]
        offset = pc_value(record["pc_offset"])
        raw_size = int.from_bytes(rom[offset:offset + 2], "little")
        if raw_size != record["raw_size"]:
            raise SystemExit(f"인터미션 로고 {name} 원본 해제 크기 불일치")
        raw, used = decompress(rom, offset + 2, raw_size)
        if used != record["original_stream_size"]:
            raise SystemExit(f"인터미션 로고 {name} 원본 LZSS 크기 불일치")
        if hashlib.sha256(raw).hexdigest() != record["raw_sha256"]:
            raise SystemExit(f"인터미션 로고 {name} 원본 SHA-256 불일치")
        raw_resources[name] = raw
    return rom, raw_resources


def px_to_bytes(pixels: list[list[int]]) -> bytes:
    output = bytearray(32)
    for y in range(8):
        for plane_pair in (0, 2):
            offset = (plane_pair // 2) * 16 + y * 2
            plane0 = plane1 = 0
            for x in range(8):
                value = (pixels[y][x] >> plane_pair) & 3
                if value & 1:
                    plane0 |= 1 << (7 - x)
                if value & 2:
                    plane1 |= 1 << (7 - x)
            output[offset] = plane0
            output[offset + 1] = plane1
    return bytes(output)


def bytes_to_px(tile: bytes) -> list[list[int]]:
    pixels = [[0] * 8 for _ in range(8)]
    for y in range(8):
        for plane_pair in (0, 2):
            offset = (plane_pair // 2) * 16 + y * 2
            plane0, plane1 = tile[offset:offset + 2]
            for x in range(8):
                bit = 7 - x
                pixels[y][x] |= (
                    ((plane0 >> bit) & 1) | (((plane1 >> bit) & 1) << 1)
                ) << plane_pair
    return pixels


def flip_px(pixels: list[list[int]], horizontal: int, vertical: int) -> list[list[int]]:
    return [
        [pixels[7 - y if vertical else y][7 - x if horizontal else x] for x in range(8)]
        for y in range(8)
    ]


def nearest(palette: list[list[int]], rgb: tuple[int, int, int]) -> tuple[int, int]:
    best_index = 1
    best_error = 1 << 60
    for index in range(1, 16):
        error = sum((palette[index][channel] - rgb[channel]) ** 2 for channel in range(3))
        if error < best_error:
            best_index, best_error = index, error
    return best_index, best_error


def quantize_cell(
    image, cell_x: int, cell_y: int, palette: list[list[int]], background: tuple[int, int, int]
) -> tuple[list[list[int]], int]:
    pixels = [[0] * 8 for _ in range(8)]
    error = 0
    for y in range(8):
        for x in range(8):
            rgb = image[cell_x * 8 + x, cell_y * 8 + y]
            if rgb == background:
                continue
            pixels[y][x], delta = nearest(palette, rgb)
            error += delta
    return pixels, error


def build_assets(corpus: dict) -> BuiltAssets:
    image_path = ROOT / corpus["approved_image"]["path"]
    image_bytes = image_path.read_bytes()
    if hashlib.sha256(image_bytes).hexdigest() != corpus["approved_image"]["sha256"]:
        raise SystemExit("인터미션 로고 승인 BMP SHA-256 불일치")
    approved_image = Image.open(image_path).convert("RGB")
    if approved_image.size != (256, 256):
        raise SystemExit(f"인터미션 로고 승인 BMP 크기 불일치: {approved_image.size}")
    source = approved_image.load()
    background = tuple(corpus["approved_image"]["background_rgb"])
    palettes = {
        int(index): colors for index, colors in corpus["palettes"].items()
    }

    tiles = [bytes(32)]
    lookup: dict[bytes, tuple[int, int, int]] = {bytes(32): (0, 0, 0)}

    def register(index: int, pixels: list[list[int]]) -> None:
        for horizontal in (0, 1):
            for vertical in (0, 1):
                key = px_to_bytes(flip_px(pixels, horizontal, vertical))
                lookup.setdefault(key, (index, horizontal, vertical))

    def get_tile(pixels: list[list[int]]) -> tuple[int, int, int]:
        key = px_to_bytes(pixels)
        if key in lookup:
            return lookup[key]
        index = len(tiles)
        tiles.append(key)
        register(index, pixels)
        return index, 0, 0

    tilemap = bytearray(2048)
    for cell_y in range(GRID):
        for cell_x in range(GRID):
            best = None
            for palette_index in ALLOWED_PALETTES:
                pixels, error = quantize_cell(
                    source, cell_x, cell_y, palettes[palette_index], background
                )
                candidate = (error, palette_index, pixels)
                if best is None or candidate[0] < best[0]:
                    best = candidate
            _, palette_index, pixels = best
            tile_index, horizontal, vertical = get_tile(pixels)
            entry = (
                tile_index | (palette_index << 10) | (horizontal << 14) | (vertical << 15)
            )
            offset = (cell_y * GRID + cell_x) * 2
            tilemap[offset:offset + 2] = entry.to_bytes(2, "little")

    if len(tiles) > TILE_CAPACITY:
        raise SystemExit(f"인터미션 로고 고유 타일 초과: {len(tiles)}/{TILE_CAPACITY}")
    chr_raw = bytearray(TILE_CAPACITY * 32)
    for index, tile in enumerate(tiles):
        chr_raw[index * 32:(index + 1) * 32] = tile

    preview = Image.new("RGB", (256, 256), background)
    target = preview.load()
    for cell_y in range(GRID):
        for cell_x in range(GRID):
            offset = (cell_y * GRID + cell_x) * 2
            entry = int.from_bytes(tilemap[offset:offset + 2], "little")
            tile_index = entry & 0x3FF
            palette_index = (entry >> 10) & 7
            horizontal = (entry >> 14) & 1
            vertical = (entry >> 15) & 1
            tile = bytes_to_px(chr_raw[tile_index * 32:(tile_index + 1) * 32])
            for y in range(8):
                for x in range(8):
                    value = tile[7 - y if vertical else y][7 - x if horizontal else x]
                    if value:
                        target[cell_x * 8 + x, cell_y * 8 + y] = tuple(
                            palettes[palette_index][value]
                        )

    changed_pixels = 0
    nonbackground_pixels = 0
    for y in range(256):
        for x in range(256):
            rgb = source[x, y]
            if rgb == background:
                continue
            nonbackground_pixels += 1
            if sum(abs(target[x, y][channel] - rgb[channel]) for channel in range(3)) > 60:
                changed_pixels += 1

    return BuiltAssets(
        chr_raw=bytes(chr_raw),
        tilemap_raw=bytes(tilemap),
        chr_compressed=compress_optimal(bytes(chr_raw)),
        tilemap_compressed=compress_optimal(bytes(tilemap)),
        preview=preview,
        unique_tiles=len(tiles),
        changed_pixels=changed_pixels,
        nonbackground_pixels=nonbackground_pixels,
    )


def loader_sequence(bank: int, address: int) -> bytes:
    return bytes((0xF4, bank, 0x00, 0xF4, address & 0xFF, address >> 8))


def build(rom_path: Path, out_path: Path) -> None:
    corpus = load_corpus()
    original_rom, original_resources = load_original(corpus)
    assets = build_assets(corpus)
    rom = bytearray(rom_path.read_bytes())
    if len(rom) != ROM_SIZE:
        raise SystemExit(f"통합 ROM이 헤더리스 2MB가 아님: {len(rom)}")

    relocation = corpus["relocation"]
    destination = pc_value(relocation["pc_offset"])
    chr_blob = len(assets.chr_raw).to_bytes(2, "little") + assets.chr_compressed
    tilemap_offset = destination + len(chr_blob)
    tilemap_blob = len(assets.tilemap_raw).to_bytes(2, "little") + assets.tilemap_compressed
    total_size = len(chr_blob) + len(tilemap_blob)
    if total_size > relocation["capacity"]:
        raise SystemExit(f"인터미션 로고 재배치 영역 초과: {total_size}/{relocation['capacity']}B")
    if any(value != 0xFF for value in original_rom[destination:destination + total_size]):
        raise SystemExit("인터미션 로고 재배치 영역이 원본 ROM의 0xFF 런이 아님")

    chr_ref = pc_value(relocation["loader_chr_sequence_pc"])
    tilemap_ref = pc_value(relocation["loader_tilemap_sequence_pc"])
    old_chr_sequence = loader_sequence(0xD9, 0xA5B1)
    old_tilemap_sequence = loader_sequence(0xD9, 0xB078)
    new_chr_sequence = loader_sequence(0xD9, destination & 0xFFFF)
    new_tilemap_sequence = loader_sequence(0xD9, tilemap_offset & 0xFFFF)
    for label, offset, old, new in (
        ("CHR", chr_ref, old_chr_sequence, new_chr_sequence),
        ("타일맵", tilemap_ref, old_tilemap_sequence, new_tilemap_sequence),
    ):
        if bytes(rom[offset:offset + 6]) not in (old, new):
            raise SystemExit(f"인터미션 로고 {label} 로더 원본/승인 시퀀스 불일치")

    current_destination = bytes(rom[destination:destination + total_size])
    wanted_destination = chr_blob + tilemap_blob
    if current_destination != wanted_destination and any(
        value != 0xFF for value in current_destination
    ):
        raise SystemExit("인터미션 로고 재배치 목적지가 비어 있지 않고 승인본도 아님")

    before = bytes(rom)
    rom[destination:destination + total_size] = wanted_destination
    rom[chr_ref:chr_ref + 6] = new_chr_sequence
    rom[tilemap_ref:tilemap_ref + 6] = new_tilemap_sequence

    allowed = set(range(destination, destination + total_size))
    allowed.update(range(chr_ref, chr_ref + 6))
    allowed.update(range(tilemap_ref, tilemap_ref + 6))
    changed = {index for index, (old, new) in enumerate(zip(before, rom)) if old != new}
    if not changed <= allowed:
        raise SystemExit(f"인터미션 로고 허용 범위 밖 변경 {len(changed - allowed)}B")

    rebuilt_chr, used_chr = decompress(rom, destination + 2, len(assets.chr_raw))
    rebuilt_tilemap, used_tilemap = decompress(
        rom, tilemap_offset + 2, len(assets.tilemap_raw)
    )
    if rebuilt_chr != assets.chr_raw or rebuilt_tilemap != assets.tilemap_raw:
        raise SystemExit("인터미션 로고 재배치 LZSS 왕복 실패")
    for name, raw in original_resources.items():
        record = corpus["resources"][name]
        offset = pc_value(record["pc_offset"])
        current_raw, _ = decompress(rom, offset + 2, record["raw_size"])
        if current_raw != raw:
            raise SystemExit(f"인터미션 로고 원본 {name} 자원이 선행 변경됨")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(rom)
    assets.preview.save(DEFAULT_PREVIEW)
    DEFAULT_MANIFEST.write_text(json.dumps({
        "approved_image_sha256": corpus["approved_image"]["sha256"],
        "unique_tiles": assets.unique_tiles,
        "tile_capacity": TILE_CAPACITY,
        "chr_pc_offset": f"0x{destination:06X}",
        "tilemap_pc_offset": f"0x{tilemap_offset:06X}",
        "chr_lzss_size": used_chr,
        "tilemap_lzss_size": used_tilemap,
        "total_relocation_size": total_size,
        "chr_raw_sha256": hashlib.sha256(assets.chr_raw).hexdigest(),
        "tilemap_raw_sha256": hashlib.sha256(assets.tilemap_raw).hexdigest(),
        "render_changed_pixels": assets.changed_pixels,
        "nonbackground_pixels": assets.nonbackground_pixels,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"VICTORYS 인터미션 로고 승인 BMP 주입 완료 → {out_path}")
    print(
        f"  CHR $D9:{destination & 0xFFFF:04X} {used_chr}B, "
        f"타일맵 $D9:{tilemap_offset & 0xFFFF:04X} {used_tilemap}B, "
        f"고유타일 {assets.unique_tiles}/{TILE_CAPACITY}, ROM 2MB 유지"
    )
    print(
        f"  타이틀 자원 무변경 / 인터미션 로더 2곳만 갱신 / "
        f"프리뷰 {DEFAULT_PREVIEW}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rom", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--out", type=Path, default=DEFAULT_ROM)
    args = parser.parse_args()
    build(args.rom.resolve(), args.out.resolve())


if __name__ == "__main__":
    main()
