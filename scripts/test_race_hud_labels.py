#!/usr/bin/env python3
"""최종 ROM의 경기 HUD 승인 라벨과 비대상 타일 보존을 검증한다."""

from __future__ import annotations

import argparse
from pathlib import Path

from build_race_hud_labels import (
    DEFAULT_APPROVED,
    DEFAULT_ROM,
    ORIGINAL_STREAM_SIZE,
    RAW_SIZE,
    RESOURCE_OFFSET,
    damage_tilemap_variants,
    expected_resource,
    tilemap_bytes,
)
from export_race_hud_workshop import (
    DEFAULT_ART,
    DEFAULT_MANIFEST,
    ORIGINAL_ROM,
    import_workshop,
    load_corpus,
    load_original_resource,
)
from lzss import decompress


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--built-rom", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--approved", type=Path, default=DEFAULT_APPROVED)
    args = parser.parse_args()

    corpus = load_corpus()
    original = ORIGINAL_ROM.read_bytes()
    built = args.built_rom.read_bytes()
    if len(original) != len(built) or len(built) != 0x200000:
        raise SystemExit("원본/최종 ROM이 헤더리스 2MB가 아님")
    import_workshop(args.approved, DEFAULT_ART, DEFAULT_MANIFEST)
    original_raw = load_original_resource(corpus)
    expected, target_tiles = expected_resource(original_raw, DEFAULT_ART.read_bytes(), corpus)
    actual, used = decompress(built, RESOURCE_OFFSET + 2, RAW_SIZE)
    failures = []
    if actual != expected:
        failures.append("승인 2bpp 결과 불일치")
    if used > ORIGINAL_STREAM_SIZE:
        failures.append(f"압축 슬롯 초과 {used}>{ORIGINAL_STREAM_SIZE}")
    cleanup = corpus["cleanup"]
    replacement_id = cleanup["replacement_tile_id"]
    replacement = original_raw[replacement_id * 16:(replacement_id + 1) * 16]
    for tile_id in cleanup["tile_ids"]:
        begin = tile_id * 16
        if actual[begin:begin + 16] != replacement:
            failures.append(f"일본어 윗행 잔재 복원 실패: ${tile_id:03X}")
    verified_variants = []
    for variant in damage_tilemap_variants(corpus):
        offset = int(variant["file_offset"], 0)
        original_entries = tilemap_bytes(variant["original_entries"])
        patched_entries = tilemap_bytes(variant["patched_entries"])
        if original[offset:offset + len(original_entries)] != original_entries:
            failures.append(f"{variant['id']}: 원본 타일맵 불일치")
        if built[offset:offset + len(patched_entries)] != patched_entries:
            failures.append(f"{variant['id']}: DAMAGE 타일맵 통일 실패")
        verified_variants.append(variant["id"])
    changed = set()
    for tile in range(RAW_SIZE // 16):
        begin = tile * 16
        if actual[begin:begin + 16] != original_raw[begin:begin + 16]:
            changed.add(tile)
    if not changed <= target_tiles:
        failures.append(f"대상 밖 타일 변경: {sorted(changed - target_tiles)}")
    if failures:
        print("경기 HUD 승인 그래픽: FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(
        "경기 HUD 승인 그래픽: PASS "
        f"DAMAGE/BOOST + 윗행 잔재 제거 + 타일맵 {len(verified_variants)}형 통일, "
        f"LZSS {used}/{ORIGINAL_STREAM_SIZE}B, "
        f"실제 변경 {len(changed)}타일/허용 {len(target_tiles)}타일"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
