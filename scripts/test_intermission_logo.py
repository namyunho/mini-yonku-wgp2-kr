#!/usr/bin/env python3
"""최종 통합 ROM의 VICTORYS 인터미션 로고 자원·로더를 역검증한다."""

from __future__ import annotations

import argparse
from pathlib import Path

from build_intermission_logo import (
    DEFAULT_ROM,
    ROM_SIZE,
    TILE_CAPACITY,
    build_assets,
    load_corpus,
    loader_sequence,
    pc_value,
)
from lzss import decompress


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--built-rom", type=Path, default=DEFAULT_ROM)
    args = parser.parse_args()

    corpus = load_corpus()
    assets = build_assets(corpus)
    rom = args.built_rom.read_bytes()
    if len(rom) != ROM_SIZE:
        raise SystemExit(f"최종 ROM이 헤더리스 2MB가 아님: {len(rom)}")

    relocation = corpus["relocation"]
    chr_offset = pc_value(relocation["pc_offset"])
    chr_raw_size = int.from_bytes(rom[chr_offset:chr_offset + 2], "little")
    chr_raw, chr_used = decompress(rom, chr_offset + 2, chr_raw_size)
    tilemap_offset = chr_offset + 2 + chr_used
    tilemap_raw_size = int.from_bytes(rom[tilemap_offset:tilemap_offset + 2], "little")
    tilemap_raw, tilemap_used = decompress(
        rom, tilemap_offset + 2, tilemap_raw_size
    )

    failures = []
    if chr_raw != assets.chr_raw:
        failures.append("승인 CHR 해제 결과 불일치")
    if tilemap_raw != assets.tilemap_raw:
        failures.append("승인 타일맵 해제 결과 불일치")
    expected_chr_loader = loader_sequence(0xD9, chr_offset & 0xFFFF)
    expected_tilemap_loader = loader_sequence(0xD9, tilemap_offset & 0xFFFF)
    chr_ref = pc_value(relocation["loader_chr_sequence_pc"])
    tilemap_ref = pc_value(relocation["loader_tilemap_sequence_pc"])
    if rom[chr_ref:chr_ref + 6] != expected_chr_loader:
        failures.append("인터미션 CHR 로더 포인터 불일치")
    if rom[tilemap_ref:tilemap_ref + 6] != expected_tilemap_loader:
        failures.append("인터미션 타일맵 로더 포인터 불일치")
    if failures:
        print("VICTORYS 인터미션 로고: FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(
        "VICTORYS 인터미션 로고: PASS "
        f"CHR {chr_used}B + 타일맵 {tilemap_used}B, "
        f"고유타일 {assets.unique_tiles}/{TILE_CAPACITY}, "
        "인터미션 로더 2곳 일치"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
