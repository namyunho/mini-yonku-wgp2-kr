#!/usr/bin/env python3
"""최종 ROM의 챕터 인트로 승인 그래픽 10개와 보존 타일을 검증한다."""

from __future__ import annotations

import argparse
from pathlib import Path

from build_stage_intro_titles import (
    DEFAULT_ROM,
    DEFAULT_WORKSHOP,
    ORIGINAL_ROM,
    POINTER_TABLE_OFFSET,
    RESOURCE_RAW_SIZE,
    ROM_SIZE,
    STAGE_RESOURCE_OFFSETS,
    TOUCHED_TILE_SET,
    expected_resource,
    load_approved_grids,
    pointer_entry,
    snes_address,
)
from lzss import decompress


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--built-rom", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--workshop", type=Path, default=DEFAULT_WORKSHOP)
    args = parser.parse_args()

    original = ORIGINAL_ROM.read_bytes()
    built = args.built_rom.read_bytes()
    if len(original) != ROM_SIZE or len(built) != ROM_SIZE:
        raise SystemExit("원본/최종 ROM이 헤더리스 2MB가 아님")
    grids = load_approved_grids(args.workshop)
    failures = []
    for stage, (offset, grid) in enumerate(zip(STAGE_RESOURCE_OFFSETS, grids), 1):
        pointer_at = POINTER_TABLE_OFFSET + (stage - 1) * 4
        expected_pointer = pointer_entry(offset)
        if original[pointer_at:pointer_at + 4] != expected_pointer:
            failures.append(f"stage {stage}: 원본 포인터 불일치")
        if built[pointer_at:pointer_at + 4] != expected_pointer:
            failures.append(f"stage {stage}: 최종 포인터 변경")
        original_raw, original_used = decompress(original, offset + 2, RESOURCE_RAW_SIZE)
        expected = expected_resource(original_raw, grid)
        actual, built_used = decompress(built, offset + 2, RESOURCE_RAW_SIZE)
        if actual != expected:
            failures.append(f"stage {stage}: 승인 2bpp 결과 불일치")
            continue
        if built_used > original_used:
            failures.append(
                f"stage {stage}: 압축 슬롯 초과 {built_used} > {original_used}"
            )
        changed = set()
        for tile in range(RESOURCE_RAW_SIZE // 16):
            begin = tile * 16
            if actual[begin:begin + 16] != original_raw[begin:begin + 16]:
                changed.add(tile)
        if not changed <= TOUCHED_TILE_SET:
            failures.append(
                f"stage {stage}: 제목 밖 타일 변경 "
                f"{sorted(changed - TOUCHED_TILE_SET)}"
            )
        print(
            f"  stage {stage:2} {snes_address(offset)}: "
            f"LZSS {built_used}/{original_used}B, 실제 변경 {len(changed)}타일"
        )

    if failures:
        print("챕터 인트로 그래픽: FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("챕터 인트로 그래픽: PASS 10/10 (BG3 제목+좌우 여백 한정, STAGE n 보존)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
