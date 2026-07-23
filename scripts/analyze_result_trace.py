#!/usr/bin/env python3
"""Result 선수명 Mesen 추적 덤프의 연속 VRAM 차이를 요약한다.

사용법:
  python3 scripts/analyze_result_trace.py
  python3 scripts/analyze_result_trace.py --trace-dir tmp/result_trace/run_YYYYMMDD_HHMMSS

기본값은 tmp/result_trace/LATEST.txt가 가리키는 가장 최근 실행이다.
파일을 수정하지 않고 stdout에만 분석 결과를 출력한다.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRACE_ROOT = ROOT / "tmp" / "result_trace"


@dataclass(frozen=True)
class ChangedRange:
    start: int
    end: int

    @property
    def size(self) -> int:
        return self.end - self.start


def resolve_trace_dir(value: str | None) -> Path:
    if value:
        path = Path(value)
        return path if path.is_absolute() else ROOT / path
    latest = DEFAULT_TRACE_ROOT / "LATEST.txt"
    if not latest.exists():
        raise SystemExit(f"최근 추적 포인터가 없습니다: {latest}")
    return Path(latest.read_text(encoding="utf-8").strip())


def changed_ranges(before: bytes, after: bytes) -> list[ChangedRange]:
    if len(before) != len(after):
        raise ValueError(f"크기 불일치: {len(before)} != {len(after)}")
    changed = [index for index, pair in enumerate(zip(before, after)) if pair[0] != pair[1]]
    if not changed:
        return []
    ranges: list[ChangedRange] = []
    start = previous = changed[0]
    for index in changed[1:]:
        if index != previous + 1:
            ranges.append(ChangedRange(start, previous + 1))
            start = index
        previous = index
    ranges.append(ChangedRange(start, previous + 1))
    return ranges


def merge_nearby(ranges: list[ChangedRange], gap: int = 15) -> list[ChangedRange]:
    if not ranges:
        return []
    merged = [ranges[0]]
    for current in ranges[1:]:
        previous = merged[-1]
        if current.start - previous.end <= gap:
            merged[-1] = ChangedRange(previous.start, current.end)
        else:
            merged.append(current)
    return merged


def tile_span(item: ChangedRange, tile_bytes: int) -> str:
    first = item.start // tile_bytes
    last = (item.end - 1) // tile_bytes
    return f"{first}-{last}" if first != last else str(first)


def read_dma_rows(trace_dir: Path) -> list[dict[str, str]]:
    path = trace_dir / "vram_dma.tsv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-dir")
    args = parser.parse_args()
    trace_dir = resolve_trace_dir(args.trace_dir).resolve()
    if not trace_dir.is_dir():
        raise SystemExit(f"추적 디렉터리가 없습니다: {trace_dir}")

    snapshots = sorted(trace_dir.glob("*_vram.bin"))
    print(f"trace: {trace_dir}")
    print(f"VRAM snapshots: {len(snapshots)}")
    if len(snapshots) < 2:
        print("연속 비교에 필요한 VRAM 덤프가 아직 2개 미만입니다.")
    for before_path, after_path in zip(snapshots, snapshots[1:]):
        before = before_path.read_bytes()
        after = after_path.read_bytes()
        ranges = changed_ranges(before, after)
        merged = merge_nearby(ranges)
        total = sum(1 for left, right in zip(before, after) if left != right)
        print(f"\n{before_path.stem} -> {after_path.stem}: changed={total}B ranges={len(ranges)}")
        for item in merged[:24]:
            print(
                f"  VRAM byte ${item.start:04X}-${item.end - 1:04X} "
                f"({item.size}B), 2bpp tiles {tile_span(item, 16)}, "
                f"4bpp tiles {tile_span(item, 32)}"
            )
        if len(merged) > 24:
            print(f"  ... {len(merged) - 24}개 병합 구간 생략")

    dma_rows = read_dma_rows(trace_dir)
    print(f"\nVRAM DMA rows: {len(dma_rows)}")
    wram_rows = [row for row in dma_rows if row.get("source", "").startswith(("7E:", "7F:"))]
    print(f"WRAM -> VRAM rows: {len(wram_rows)}")
    for row in wram_rows[-40:]:
        print(
            "  seq={seq} f={frame} pc=${pc} src=${source} size={size} "
            "vmadd=${vmadd} tile2={tile2bpp} tile4={tile4bpp}".format(**row)
        )


if __name__ == "__main__":
    main()
