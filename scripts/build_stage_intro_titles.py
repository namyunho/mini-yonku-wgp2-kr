#!/usr/bin/env python3
"""사용자 승인 챕터 인트로 제목 10개를 원본 LZSS 슬롯에 주입한다.

세이브 파일 선택 화면의 $C0 문자열 제목과 챕터 시작 인트로는 서로 다른
경로다. 인트로는 $D9/$DA의 0x1000-byte 해제 2bpp 자원 10개를 사용하며,
BG3 character base의 VRAM byte $2000-$2FFF에 올라간다.

승인 작업지의 192x64 화면 영역은 실제 BG3 타일 그리드보다 y가 1px 아래에서
시작한다. 화면 x32..223, y79..142의 24x8 타일로 정렬한 뒤, 실측 BG3
tilemap(VRAM byte $E000, vertical tile offset +1)이 가리키는 서로 다른
192타일을 교체한다. 원문 제목의 실제 가로 범위는 x16..239의 28타일이므로
승인 영역 좌우 2타일씩(32타일)은 투명화한다. 화면 하단 ``STAGE n``을
포함한 나머지 32타일은 원본 그대로 보존한다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lzss import compress, decompress  # noqa: E402


ORIGINAL_ROM = ROOT / "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
DEFAULT_ROM = ROOT / "out/wgp2_kr.smc"
DEFAULT_WORKSHOP = ROOT / "assets/graphics/stage_titles/stage_titles_workshop_approved.png"
DEFAULT_MANIFEST = ROOT / "out/stage_intro_titles_manifest.json"

ROM_SIZE = 0x200000
ORIGINAL_SHA256 = "3a4d8c178b85f75e26193a3c31e88b2a545cc9223ca93cb463e9abb69fd24f2b"
STAGE_COUNT = 10
ROW_HEIGHT = 88
EDIT_X = 4
EDIT_Y = 24
EDIT_WIDTH = 192
EDIT_HEIGHT = 64
WORKSHOP_SIZE = (256, STAGE_COUNT * ROW_HEIGHT)

# 2-byte 해제 길이 헤더가 시작되는 PC offset. 모두 raw 0x1000B 2bpp다.
STAGE_RESOURCE_OFFSETS = (
    0x19B8EE,  # $D9:B8EE
    0x19BD8D,  # $D9:BD8D
    0x19C14E,  # $D9:C14E
    0x19C5E5,  # $D9:C5E5
    0x19C979,  # $D9:C979
    0x19CD80,  # $D9:CD80
    0x1A0000,  # $DA:0000
    0x1A039E,  # $DA:039E
    0x1A077E,  # $DA:077E
    0x1A0A89,  # $DA:0A89
)
RESOURCE_RAW_SIZE = 0x1000
POINTER_TABLE_OFFSET = 0x03C0C2  # $C3:C0C2, addr16+bank8+00, 10 entries

PALETTE_TO_INDEX = {
    (255, 0, 255): 0,      # 투명
    (255, 255, 255): 1,    # 흰 잉크
    (173, 156, 156): 2,    # 원본과 같은 그림자
}


def snes_address(offset: int) -> str:
    return f"${0xC0 + (offset >> 16):02X}:{offset & 0xFFFF:04X}"


def displayed_title_tile_index(wide_x: int, tile_y: int) -> int:
    """화면 x16..239의 제목 28x8 셀을 원본 자원 타일 번호로 바꾼다.

    타일맵은 위쪽 4행이 14+14타일, 아래쪽 4행이 16+12타일로
    자원 안에서 갈라진다. 아래쪽도 14+14라고 간주하면 분할점 뒤의
    그림이 화면 오른쪽으로 2타일 밀린다.
    """
    if not (0 <= wide_x < 28 and 0 <= tile_y < 8):
        raise ValueError((wide_x, tile_y))
    if tile_y < 4:
        return tile_y * 0x10 + (0x02 + wide_x if wide_x < 14 else 0x40 + wide_x - 14)
    row = tile_y - 4
    return row * 0x10 + (0x80 + wide_x if wide_x < 16 else 0xC0 + wide_x - 16)


def title_tile_index(tile_x: int, tile_y: int) -> int:
    """승인 영역 x32..223의 24x8 셀을 원본 자원 타일 번호로 바꾼다."""
    if not (0 <= tile_x < 24 and 0 <= tile_y < 8):
        raise ValueError((tile_x, tile_y))
    return displayed_title_tile_index(tile_x + 2, tile_y)


TITLE_TILES = tuple(title_tile_index(x, y) for y in range(8) for x in range(24))
TITLE_TILE_SET = frozenset(TITLE_TILES)
if len(TITLE_TILE_SET) != 192:
    raise RuntimeError("인트로 제목 tilemap이 192개 고유 타일이 아님")

DISPLAYED_TITLE_TILES = tuple(
    displayed_title_tile_index(x, y) for y in range(8) for x in range(28)
)
DISPLAYED_TITLE_TILE_SET = frozenset(DISPLAYED_TITLE_TILES)
CLEAR_TILE_SET = DISPLAYED_TITLE_TILE_SET - TITLE_TILE_SET
TOUCHED_TILE_SET = TITLE_TILE_SET | CLEAR_TILE_SET
if len(DISPLAYED_TITLE_TILE_SET) != 224 or len(CLEAR_TILE_SET) != 32:
    raise RuntimeError("인트로 제목 전체 tilemap이 224타일(본문 192+여백 32)이 아님")


def encode_tile(pixels: list[list[int]]) -> bytes:
    if len(pixels) != 8 or any(len(row) != 8 for row in pixels):
        raise ValueError("2bpp 타일은 8x8이어야 함")
    output = bytearray()
    for row in pixels:
        plane0 = 0
        plane1 = 0
        for column, value in enumerate(row):
            plane0 |= (value & 1) << (7 - column)
            plane1 |= ((value >> 1) & 1) << (7 - column)
        output.extend((plane0, plane1))
    return bytes(output)


def load_approved_grids(path: Path) -> list[list[list[int]]]:
    image = Image.open(path).convert("RGB")
    if image.size != WORKSHOP_SIZE:
        raise SystemExit(f"챕터 제목 승인본 크기 불일치: {image.size} != {WORKSHOP_SIZE}")
    source = image.load()
    grids = []
    for stage in range(1, STAGE_COUNT + 1):
        source_y = (stage - 1) * ROW_HEIGHT + EDIT_Y
        grid = [[0] * EDIT_WIDTH for _ in range(EDIT_HEIGHT)]
        unexpected = set()

        # 실제 BG3 셀은 화면 y79부터, 작업지는 y80부터다. 맨 위 1px을
        # 투명으로 두고 작업지 y0..62를 BG3 y1..63에 복사한다.
        for y in range(1, EDIT_HEIGHT):
            for x in range(EDIT_WIDTH):
                rgb = source[EDIT_X + x, source_y + y - 1]
                if rgb not in PALETTE_TO_INDEX:
                    unexpected.add(rgb)
                else:
                    grid[y][x] = PALETTE_TO_INDEX[rgb]

        # 작업지 마지막 행은 타일 그리드 다음 행(y143)이므로 잉크가 있으면
        # 조용히 버리지 않고 오류로 처리한다.
        for x in range(EDIT_WIDTH):
            rgb = source[EDIT_X + x, source_y + EDIT_HEIGHT - 1]
            if rgb not in PALETTE_TO_INDEX:
                unexpected.add(rgb)
            elif PALETTE_TO_INDEX[rgb] != 0:
                raise SystemExit(f"stage {stage}: 작업지 마지막 y=63 행에 잉크가 있음")
        if unexpected:
            sample = ", ".join("#%02X%02X%02X" % rgb for rgb in sorted(unexpected)[:8])
            raise SystemExit(f"stage {stage}: 승인 영역의 예상 밖 색상 {sample}")
        grids.append(grid)
    return grids


def expected_resource(original_raw: bytes, grid: list[list[int]]) -> bytes:
    if len(original_raw) != RESOURCE_RAW_SIZE:
        raise ValueError(f"원본 인트로 자원 길이 {len(original_raw):04X}")
    edited = bytearray(original_raw)
    for tile in CLEAR_TILE_SET:
        edited[tile * 16:(tile + 1) * 16] = bytes(16)
    for tile_y in range(8):
        for tile_x in range(24):
            tile = title_tile_index(tile_x, tile_y)
            pixels = [
                row[tile_x * 8:(tile_x + 1) * 8]
                for row in grid[tile_y * 8:(tile_y + 1) * 8]
            ]
            edited[tile * 16:(tile + 1) * 16] = encode_tile(pixels)
    return bytes(edited)


def pointer_entry(offset: int) -> bytes:
    return bytes((offset & 0xFF, (offset >> 8) & 0xFF, 0xC0 + (offset >> 16), 0x00))


def build(rom: bytearray, original: bytes, workshop: Path) -> list[dict]:
    grids = load_approved_grids(workshop)
    report = []
    for stage, (offset, grid) in enumerate(zip(STAGE_RESOURCE_OFFSETS, grids), 1):
        pointer_at = POINTER_TABLE_OFFSET + (stage - 1) * 4
        expected_pointer = pointer_entry(offset)
        if original[pointer_at:pointer_at + 4] != expected_pointer:
            raise SystemExit(f"stage {stage}: 원본 그래픽 포인터 불일치")
        if rom[pointer_at:pointer_at + 4] != expected_pointer:
            raise SystemExit(f"stage {stage}: 통합 ROM 그래픽 포인터가 변경됨")

        original_out_len = int.from_bytes(original[offset:offset + 2], "little")
        if original_out_len != RESOURCE_RAW_SIZE:
            raise SystemExit(f"stage {stage}: 해제 길이 {original_out_len:04X} != 1000")
        original_raw, original_used = decompress(original, offset + 2, RESOURCE_RAW_SIZE)
        wanted = expected_resource(original_raw, grid)
        current_raw, _ = decompress(rom, offset + 2, RESOURCE_RAW_SIZE)

        if current_raw != wanted:
            original_span = original[offset:offset + 2 + original_used]
            if rom[offset:offset + 2 + original_used] != original_span:
                raise SystemExit(
                    f"stage {stage}: 원본도 승인본도 아닌 인트로 자원이 이미 존재함"
                )
            compressed = compress(wanted)
            if len(compressed) > original_used:
                raise SystemExit(
                    f"stage {stage}: LZSS 슬롯 초과 {len(compressed)} > {original_used}"
                )
            rom[offset:offset + 2 + original_used] = b"\xFF" * (2 + original_used)
            rom[offset:offset + 2] = RESOURCE_RAW_SIZE.to_bytes(2, "little")
            rom[offset + 2:offset + 2 + len(compressed)] = compressed
        else:
            compressed = compress(wanted)

        rebuilt, rebuilt_used = decompress(rom, offset + 2, RESOURCE_RAW_SIZE)
        if rebuilt != wanted:
            raise SystemExit(f"stage {stage}: 최종 LZSS 왕복 실패")
        for tile in range(RESOURCE_RAW_SIZE // 16):
            if tile in TOUCHED_TILE_SET:
                continue
            begin = tile * 16
            if rebuilt[begin:begin + 16] != original_raw[begin:begin + 16]:
                raise SystemExit(f"stage {stage}: 보존 타일 ${tile:02X} 변경")
        report.append({
            "stage": stage,
            "resource": snes_address(offset),
            "pointer": f"$C3:{0xC0C2 + (stage - 1) * 4:04X}",
            "raw_bytes": RESOURCE_RAW_SIZE,
            "original_stream_bytes": original_used,
            "approved_stream_bytes": rebuilt_used,
            "slot_margin_bytes": original_used - rebuilt_used,
            "art_tiles": len(TITLE_TILE_SET),
            "cleared_margin_tiles": len(CLEAR_TILE_SET),
            "preserved_tiles": RESOURCE_RAW_SIZE // 16 - len(TOUCHED_TILE_SET),
        })
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rom", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--out", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--workshop", type=Path, default=DEFAULT_WORKSHOP)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()

    original = ORIGINAL_ROM.read_bytes()
    if len(original) != ROM_SIZE or hashlib.sha256(original).hexdigest() != ORIGINAL_SHA256:
        raise SystemExit("원본 ROM 크기/SHA256 불일치")
    rom = bytearray(args.rom.read_bytes())
    if len(rom) != ROM_SIZE:
        raise SystemExit(f"입력 통합 ROM이 헤더리스 2MB가 아님: {len(rom)}")

    stages = build(rom, original, args.workshop)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(rom)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps({
        "workshop": str(args.workshop.relative_to(ROOT)),
        "format": "SNES 2bpp, LZSS, raw 0x1000 bytes per stage",
        "vram": "BG3 byte $2000-$2FFF",
        "screen_canvas": "x32,y80,w192,h64 (BG3 tile grid y79-$142)",
        "displayed_title_grid": "x16,y79,w224,h64 (28x8 tiles)",
        "title_tiles": [f"${tile:02X}" for tile in TITLE_TILES],
        "cleared_margin_tiles": [f"${tile:02X}" for tile in sorted(CLEAR_TILE_SET)],
        "stages": stages,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"챕터 인트로 승인 제목 10개 주입 완료 → {args.out}")
    for item in stages:
        print(
            f"  stage {item['stage']:2}: {item['resource']} "
            f"LZSS {item['approved_stream_bytes']}/{item['original_stream_bytes']}B "
            f"(여유 {item['slot_margin_bytes']}B, 제목 192타일/여백 제거 32타일/"
            f"보존 32타일)"
        )
    print(f"  매니페스트: {args.manifest}")


if __name__ == "__main__":
    main()
