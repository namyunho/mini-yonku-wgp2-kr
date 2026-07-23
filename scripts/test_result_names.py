#!/usr/bin/env python3
"""최종 ROM의 Result 선수명 승인 시트·타일 범위·공유 해소를 검증한다."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_result_names import (
    ASSET_OFFSET,
    DEFAULT_ROM,
    DEFAULT_TEMPLATE,
    NEXT_ASSET_OFFSET,
    ORIGINAL_ROM,
    RACER_COUNT,
    RACER_TABLE_OFFSET,
    TRANSLATIONS,
    decode_asset,
    parse_span,
    read_racer_spans,
    tile_indices,
    validate_corpus,
    workshop_to_asset,
)


DEFAULT_APPROVED = (
    Path(__file__).resolve().parents[1]
    / "assets/graphics/result/names/result_names_workshop_approved.png"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--built-rom", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--approved", type=Path, default=DEFAULT_APPROVED)
    args = parser.parse_args()

    original = ORIGINAL_ROM.read_bytes()
    built = args.built_rom.read_bytes()
    if len(original) != 0x200000 or len(built) != len(original):
        raise SystemExit("Result 검증 원본/통합 ROM 크기 불일치")

    original_data, original_used = decode_asset(original)
    actual_data, actual_used = decode_asset(built)
    capacity = NEXT_ASSET_OFFSET - (ASSET_OFFSET + 2)
    if original_used != capacity or actual_used > capacity:
        raise SystemExit(
            f"Result 이름 압축 범위 실패: original={original_used}, "
            f"built={actual_used}, capacity={capacity}"
        )

    corpus = json.loads(TRANSLATIONS.read_text(encoding="utf-8"))
    labels = validate_corpus(corpus, read_racer_spans(original))
    expected_data = workshop_to_asset(args.approved, original_data, labels)
    failures = []
    if actual_data != expected_data:
        failures.append("최종 ROM 선수명 아틀라스가 승인 시트와 다름")

    # 110개 범위표 전체를 원본에서 재구성해 승인된 override 외 변경을 막는다.
    expected_table = bytearray(
        original[
            RACER_TABLE_OFFSET:
            RACER_TABLE_OFFSET + RACER_COUNT * 4
        ]
    )
    for entry in labels:
        target_span = parse_span(entry["tile_span"])
        for racer_id in entry["racer_ids"]:
            pos = racer_id * 4
            expected_table[pos:pos + 4] = (
                target_span[0].to_bytes(2, "little")
                + target_span[1].to_bytes(2, "little")
            )
    actual_table = built[
        RACER_TABLE_OFFSET:
        RACER_TABLE_OFFSET + RACER_COUNT * 4
    ]
    if actual_table != expected_table:
        failures.append("선수 ID 110개 타일 범위표가 승인 정의와 다름")

    # 실제 표시되는 고유 이름끼리 위/아래 물리 타일을 공유하지 않아야 한다.
    owners: dict[int, list[tuple[int, str]]] = {}
    displayed = [entry for entry in labels if entry.get("text_jp") is not None]
    for number, entry in enumerate(displayed):
        for top in tile_indices(*parse_span(entry["tile_span"])):
            owners.setdefault(top, []).append((number, "top"))
            owners.setdefault(top + 0x10, []).append((number, "bottom"))
    overlaps = {
        tile: uses
        for tile, uses in owners.items()
        if len({number for number, _role in uses}) > 1
    }
    if overlaps:
        failures.append(
            "표시 선수명 물리 타일 공유 잔존: "
            + ", ".join(f"${tile:04X}" for tile in sorted(overlaps))
        )

    spans = read_racer_spans(built)
    if spans[16] != (0x0080, 0x0084):
        failures.append(f"아돌프 범위 불일치: {spans[16]}")
    if spans[19] != (0x008F, 0x00A4):
        failures.append(f"FOX1 범위 불일치: {spans[19]}")

    if failures:
        print("Result 선수명: FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(
        "Result 선수명: PASS "
        f"승인 아틀라스 일치, 범위표 {RACER_COUNT}/{RACER_COUNT}, "
        f"표시 이름 {len(displayed)}종 타일 공유 0, "
        f"아돌프 $0080-$0084 / FOX1 $008F-$00A4, "
        f"LZSS {actual_used}/{capacity}B"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
