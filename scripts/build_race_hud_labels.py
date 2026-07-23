#!/usr/bin/env python3
"""승인된 경기 HUD `DAMAGE / BOOST` 2bpp 라벨을 통합 ROM에 삽입한다.

원본 `$D5:4EC3` LZSS 자원에서 BG3 라벨 타일 `$1D1-$1D4`,
`$121-$123`을 교체한다. `DAMAGE` 윗행에 남은 일본어 글자 조각 네 타일은
같은 행의 정상 상단 테두리 `$131`로 복원한다. 해제 크기·ROM 크기·소스
포인터는 유지하고, 원래 압축 슬롯 2811바이트 안에 들어갈 때만 기록한다.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from export_race_hud_workshop import (
    DEFAULT_ART,
    DEFAULT_MANIFEST,
    ORIGINAL_ROM,
    ORIGINAL_STREAM_SIZE,
    RAW_SIZE,
    RESOURCE_OFFSET,
    import_workshop,
    load_corpus,
    load_original_resource,
)
from lzss import compress_optimal, decompress


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROM = ROOT / "out/wgp2_kr.smc"
DEFAULT_APPROVED = ROOT / "assets/race_hud/race_hud_labels_workshop_approved.png"
ROM_SIZE = 0x200000


def expected_resource(
    original_raw: bytes,
    art: bytes,
    corpus: dict,
    *,
    remove_upper_remnants: bool = True,
) -> tuple[bytes, set[int]]:
    edited = bytearray(original_raw)
    cursor = 0
    target_tiles: set[int] = set()
    for entry in corpus["entries"]:
        tile_ids = entry["tile_ids"]
        size = len(tile_ids) * 16
        block = art[cursor:cursor + size]
        if len(block) != size:
            raise SystemExit(f"{entry['id']}: 승인 2bpp 데이터 길이 부족")
        for number, tile_id in enumerate(tile_ids):
            if tile_id in target_tiles:
                raise SystemExit(f"중복 경기 HUD 타일: ${tile_id:03X}")
            target_tiles.add(tile_id)
            edited[tile_id * 16:(tile_id + 1) * 16] = block[number * 16:(number + 1) * 16]
        cursor += size
    if cursor != len(art):
        raise SystemExit(f"승인 2bpp 데이터 잉여: {len(art) - cursor}B")

    if remove_upper_remnants:
        cleanup = corpus["cleanup"]
        cleanup_tiles = cleanup["tile_ids"]
        packed = b"".join(
            original_raw[tile_id * 16:(tile_id + 1) * 16]
            for tile_id in cleanup_tiles
        )
        if hashlib.sha256(packed).hexdigest() != cleanup["source_sha256"]:
            raise SystemExit("DAMAGE 윗행 일본어 잔재 원본 SHA-256 불일치")
        replacement_id = cleanup["replacement_tile_id"]
        replacement = original_raw[replacement_id * 16:(replacement_id + 1) * 16]
        if hashlib.sha256(replacement).hexdigest() != cleanup["replacement_tile_sha256"]:
            raise SystemExit("DAMAGE 정상 상단 테두리 `$131` SHA-256 불일치")
        if any(
            original_raw[tile_id * 16:tile_id * 16 + 6] != replacement[:6]
            for tile_id in cleanup_tiles
        ):
            raise SystemExit("DAMAGE 윗행과 정상 타일의 상단 테두리 3행이 다름")
        for tile_id in cleanup_tiles:
            if tile_id in target_tiles:
                raise SystemExit(f"중복 경기 HUD 정리 타일: ${tile_id:03X}")
            target_tiles.add(tile_id)
            edited[tile_id * 16:(tile_id + 1) * 16] = replacement
        restored = replacement * len(cleanup_tiles)
        if hashlib.sha256(restored).hexdigest() != cleanup["restored_sha256"]:
            raise SystemExit("DAMAGE 윗행 복원 결과 SHA-256 불일치")
    return bytes(edited), target_tiles


def build(rom_path: Path, out_path: Path, approved: Path) -> None:
    corpus = load_corpus()
    original_rom = ORIGINAL_ROM.read_bytes()
    original_raw = load_original_resource(corpus)
    rom = bytearray(rom_path.read_bytes())
    if len(original_rom) != ROM_SIZE or len(rom) != ROM_SIZE:
        raise SystemExit("원본/통합 ROM이 헤더리스 2MB가 아님")
    if rom[RESOURCE_OFFSET:RESOURCE_OFFSET + 2] != RAW_SIZE.to_bytes(2, "little"):
        raise SystemExit("통합 ROM의 $D5:4EC3 해제 길이 헤더 변경")

    import_workshop(approved, DEFAULT_ART, DEFAULT_MANIFEST)
    art = DEFAULT_ART.read_bytes()
    labels_only, _ = expected_resource(
        original_raw, art, corpus, remove_upper_remnants=False
    )
    wanted, target_tiles = expected_resource(original_raw, art, corpus)
    current, _ = decompress(rom, RESOURCE_OFFSET + 2, RAW_SIZE)
    if current not in (original_raw, labels_only, wanted):
        raise SystemExit("$D5:4EC3 자원이 원본·이전 라벨본·승인본 중 어느 것도 아님")

    for tile in range(RAW_SIZE // 16):
        if tile in target_tiles:
            continue
        begin = tile * 16
        if wanted[begin:begin + 16] != original_raw[begin:begin + 16]:
            raise SystemExit(f"경기 HUD 대상 밖 타일 변경: ${tile:03X}")

    compressed = compress_optimal(wanted)
    if len(compressed) > ORIGINAL_STREAM_SIZE:
        raise SystemExit(
            f"경기 HUD LZSS 원본 슬롯 초과: {len(compressed)} > {ORIGINAL_STREAM_SIZE}B"
        )
    rom[RESOURCE_OFFSET + 2:RESOURCE_OFFSET + 2 + ORIGINAL_STREAM_SIZE] = \
        b"\xFF" * ORIGINAL_STREAM_SIZE
    rom[RESOURCE_OFFSET + 2:RESOURCE_OFFSET + 2 + len(compressed)] = compressed
    rebuilt, used = decompress(rom, RESOURCE_OFFSET + 2, RAW_SIZE)
    if rebuilt != wanted:
        raise SystemExit("경기 HUD 승인 그래픽 LZSS 왕복 실패")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(rom)
    print(f"경기 HUD DAMAGE / BOOST + 일본어 윗행 잔재 제거 완료 → {out_path}")
    print(
        f"  $D5:4EC3 raw 0x{RAW_SIZE:04X}, LZSS {used}/{ORIGINAL_STREAM_SIZE}B, "
        f"대상 {len(target_tiles)}타일(라벨 7 + 윗행 복원 4), ROM 2MB 유지"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rom", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--out", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--approved", type=Path, default=DEFAULT_APPROVED)
    args = parser.parse_args()
    build(args.rom.resolve(), args.out.resolve(), args.approved.resolve())


if __name__ == "__main__":
    main()
