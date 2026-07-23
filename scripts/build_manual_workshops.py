#!/usr/bin/env python3
"""사용자 승인 1:1 타일 작업본 3종을 통합 ROM에 주입한다.

대상:
  * 포메이션 하단 4라벨: $DA:9E1F BG + $DA:AD53 선택 OBJ 타일
  * 이지 세팅 능력치 7라벨: $D9:0000 파생 2bpp 자원의 $140~$15F
  * 개러지 분류 7라벨: 같은 파생 자원의 전용 타일 $C0~$D7

Result 경기장명은 별도 ``build_result_courses.py --workshop-png``가 담당한다.
모든 재배치는 헤더리스 2MB HiROM 내부의 확인된 0xFF 런만 사용한다.
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

from export_manual_tile_workshops import (  # noqa: E402
    PALETTE_RGB,
    extract_crop,
    load_groups,
    source_for_group,
    workshop_crop,
)
from lzss import compress, decompress  # noqa: E402


ORIGINAL_ROM = ROOT / "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
DEFAULT_ROM = ROOT / "out/wgp2_kr.smc"
FORMATION_WORKSHOP = ROOT / "assets/graphics/formation/formation_labels_workshop_approved.png"
STATS_WORKSHOP = ROOT / "assets/graphics/machine_stats/machine_stats_workshop_approved.png"
GARAGE_WORKSHOP = ROOT / "assets/graphics/garage/garage_categories_workshop_approved.png"
DEFAULT_MANIFEST = ROOT / "out/manual_workshops_manifest.json"

ROM_SIZE = 0x200000
ORIGINAL_SHA256 = "3a4d8c178b85f75e26193a3c31e88b2a545cc9223ca93cb463e9abb69fd24f2b"


def pc(bank: int, addr: int) -> int:
    return ((bank & 0x3F) << 16) | (addr & 0xFFFF)


def require_ff(rom: bytes | bytearray, start: int, end: int, label: str) -> None:
    if not all(value == 0xFF for value in rom[start:end]):
        raise SystemExit(f"{label} 재배치 영역이 0xFF가 아님: 0x{start:06X}~0x{end - 1:06X}")


def approved_crop(image: Image.Image, number: int, entry: dict) -> Image.Image:
    x0, y0, width, height = workshop_crop(number, entry)
    crop = Image.new("P", (width, height), 0)
    palette = []
    for rgb in PALETTE_RGB:
        palette.extend(rgb)
    palette.extend([0] * (768 - len(palette)))
    crop.putpalette(palette)
    source = image.load()
    target = crop.load()
    unexpected = set()
    for y in range(height):
        for x in range(width):
            rgb = source[x0 + x, y0 + y]
            if rgb == PALETTE_RGB[0]:
                target[x, y] = 0
            elif rgb == PALETTE_RGB[3]:
                target[x, y] = 3
            elif rgb == PALETTE_RGB[1] or (
                rgb[0] == rgb[1] == rgb[2] and rgb[0] >= 128
            ):
                target[x, y] = 1
            else:
                unexpected.add(rgb)
    if unexpected:
        sample = ", ".join("#%02X%02X%02X" % rgb for rgb in sorted(unexpected)[:8])
        raise SystemExit(f"{entry['id']}: 승인 영역의 예상 밖 색상 {sample}")
    return crop


def encode_2bpp(image: Image.Image) -> bytes:
    pixels = image.load()
    output = bytearray()
    for tile_y in range(image.height // 8):
        for tile_x in range(image.width // 8):
            for row in range(8):
                plane0 = plane1 = 0
                for column in range(8):
                    value = pixels[tile_x * 8 + column, tile_y * 8 + row]
                    plane0 |= (value & 1) << (7 - column)
                    plane1 |= ((value >> 1) & 1) << (7 - column)
                output.extend((plane0, plane1))
    return bytes(output)


def encode_formation_4bpp(image: Image.Image) -> bytes:
    """작업 팔레트 0/1/3을 실제 포메이션 팔레트 0/1/15로 바꾼다."""
    pixels = image.load()
    output = bytearray()
    for tile_y in range(image.height // 8):
        for tile_x in range(image.width // 8):
            low = bytearray(16)
            high = bytearray(16)
            for row in range(8):
                planes = [0, 0, 0, 0]
                for column in range(8):
                    source_value = pixels[tile_x * 8 + column, tile_y * 8 + row]
                    value = 15 if source_value == 3 else source_value
                    for plane in range(4):
                        planes[plane] |= ((value >> plane) & 1) << (7 - column)
                low[row * 2:row * 2 + 2] = bytes(planes[:2])
                high[row * 2:row * 2 + 2] = bytes(planes[2:])
            output.extend(low + high)
    return bytes(output)


def decode_4bpp_strip(data: bytes | bytearray) -> list[list[int]]:
    """연속 8x8 4bpp 타일을 한 줄짜리 인덱스 픽셀 표면으로 푼다."""
    if len(data) % 32:
        raise ValueError("4bpp 스트립 길이가 32바이트 배수가 아님")
    tile_count = len(data) // 32
    pixels = [[0] * (tile_count * 8) for _ in range(8)]
    for tile in range(tile_count):
        offset = tile * 32
        for row in range(8):
            planes = (
                data[offset + row * 2],
                data[offset + row * 2 + 1],
                data[offset + 16 + row * 2],
                data[offset + 16 + row * 2 + 1],
            )
            for column in range(8):
                bit = 7 - column
                pixels[row][tile * 8 + column] = sum(
                    ((plane >> bit) & 1) << index
                    for index, plane in enumerate(planes)
                )
    return pixels


def encode_4bpp_strip(pixels: list[list[int]]) -> bytes:
    """``decode_4bpp_strip``의 역변환."""
    if len(pixels) != 8 or not pixels or len(pixels[0]) % 8:
        raise ValueError("4bpp 스트립 표면 규격 불일치")
    width = len(pixels[0])
    if any(len(row) != width for row in pixels):
        raise ValueError("4bpp 스트립 행 길이 불일치")
    output = bytearray()
    for tile in range(width // 8):
        low = bytearray(16)
        high = bytearray(16)
        for row in range(8):
            planes = [0, 0, 0, 0]
            for column in range(8):
                value = pixels[row][tile * 8 + column]
                if not 0 <= value <= 15:
                    raise ValueError(f"4bpp 팔레트 인덱스 범위 초과: {value}")
                for plane in range(4):
                    planes[plane] |= ((value >> plane) & 1) << (7 - column)
            low[row * 2:row * 2 + 2] = bytes(planes[:2])
            high[row * 2:row * 2 + 2] = bytes(planes[2:])
        output.extend(low + high)
    return bytes(output)


def patch_pea_source(
    rom: bytearray,
    at: int,
    old_bank: int,
    old_addr: int,
    new_bank: int,
    new_addr: int,
) -> None:
    old = bytes((0xF4, old_bank, 0x00, 0xF4, old_addr & 0xFF, old_addr >> 8))
    new = bytes((0xF4, new_bank, 0x00, 0xF4, new_addr & 0xFF, new_addr >> 8))
    if rom[at:at + 6] != old:
        raise SystemExit(f"로더 소스 시그니처 불일치 0x{at:06X}: {rom[at:at + 6].hex()}")
    rom[at:at + 6] = new


def build_formation(rom: bytearray, original: bytes, groups: dict[str, dict]) -> dict:
    source = pc(0xDA, 0x9E1F)
    raw_size = int.from_bytes(original[source:source + 2], "little")
    raw, used = decompress(original, source + 2, raw_size)
    if raw_size != 0x1E00 or used != 0x0F32:
        raise SystemExit(f"포메이션 자원 규격 불일치: {raw_size:04X}/{used:04X}")
    edited = bytearray(raw)
    group = groups["formation_labels"]
    approved = Image.open(FORMATION_WORKSHOP).convert("RGB")
    if approved.size != (256, 128):
        raise SystemExit(f"포메이션 승인본 크기 불일치: {approved.size}")
    capture = Image.open(source_for_group("formation_labels")).convert("RGBA")
    raw_offsets = (0x1200, 0x12C0, 0x13E0, 0x14C0)
    records = []
    for number, (entry, raw_offset) in enumerate(zip(group["labels"], raw_offsets, strict=True)):
        original_crop = extract_crop(capture, entry, group["id"])
        original_tiles = encode_formation_4bpp(original_crop)
        if raw[raw_offset:raw_offset + len(original_tiles)] != original_tiles:
            raise SystemExit(f"{entry['id']}: $DA:9E1F 원본 타일 대조 실패")
        new_crop = approved_crop(approved, number, entry)
        new_tiles = encode_formation_4bpp(new_crop)
        edited[raw_offset:raw_offset + len(new_tiles)] = new_tiles
        records.append({"id": entry["id"], "raw_offset": raw_offset, "bytes": len(new_tiles)})

    packed = raw_size.to_bytes(2, "little") + compress(bytes(edited))
    target_bank, target_addr = 0xC6, 0xCD10
    capacity = 0xE000 - target_addr
    if len(packed) > capacity:
        raise SystemExit(f"포메이션 재압축 자원 초과: {len(packed)} > {capacity}")
    target = pc(target_bank, target_addr)
    require_ff(rom, target, target + capacity, "포메이션")
    rom[target:target + len(packed)] = packed
    for loader in (pc(0xC1, 0x69B7), pc(0xC1, 0x74BF)):
        patch_pea_source(rom, loader, 0xDA, 0x9E1F, target_bank, target_addr)
    # 레이스 전 포메이션 화면은 위 두 PEA 호출 외에도 C3 장면 로더의 인라인
    # 24비트 포인터로 같은 BG 자원을 읽으므로 세 호출을 함께 전환한다.
    inline_source = pc(0xC3, 0x6760)
    old_inline = bytes((0x1F, 0x9E, 0xDA))
    new_inline = bytes((target_addr & 0xFF, target_addr >> 8, target_bank))
    if rom[inline_source:inline_source + 3] != old_inline:
        raise SystemExit("포메이션 C3 인라인 소스 포인터 시그니처 불일치")
    rom[inline_source:inline_source + 3] = new_inline
    rebuilt, rebuilt_used = decompress(rom, target + 2, raw_size)
    if rebuilt != bytes(edited) or rebuilt_used != len(packed) - 2:
        raise SystemExit("포메이션 재압축 왕복 실패")

    # 선택 중에는 BG 라벨 위로 $DA:AD53의 별도 OBJ 라벨이 2프레임마다
    # 나타났다 사라진다. 네 라벨은 VRAM $E080부터 논리 OBJ $104~$11E에
    # 놓이며, $11F는 손가락 그래픽이므로 절대 덮지 않는다.
    selected_source = pc(0xDA, 0xAD53)
    selected_next = pc(0xDA, 0xB5C5)
    selected_size = int.from_bytes(original[selected_source:selected_source + 2], "little")
    selected_raw, selected_used = decompress(
        original, selected_source + 2, selected_size
    )
    if selected_size != 0x12C0 or selected_used + 2 != selected_next - selected_source:
        raise SystemExit(
            f"포메이션 선택 OBJ 규격 불일치: {selected_size:04X}/{selected_used:04X}"
        )
    if rom[selected_source:selected_next] != original[selected_source:selected_next]:
        raise SystemExit("$DA:AD53 선택 OBJ 원본 슬롯이 선행 빌드에서 변경됨")
    selected_edited = bytearray(selected_raw)
    # raw 오프셋, 실제 OBJ 타일 수, BG 승인본 대비 내부 x 정렬.
    # TEST RUN 승인 캔버스의 7번째 타일은 빈 여백이라 OBJ에는 6타일만 존재한다.
    selected_spans = (
        (0x0880, 6, 0),
        (0x0940, 9, -2),
        (0x0A60, 6, -2),
        (0x0B20, 6, 1),
    )
    selected_records = []
    for number, (entry, (raw_offset, tile_count, shift_x)) in enumerate(
        zip(group["labels"], selected_spans, strict=True)
    ):
        byte_count = tile_count * 32
        pixels = decode_4bpp_strip(
            selected_edited[raw_offset:raw_offset + byte_count]
        )
        original_ink = sum(value == 14 for row in pixels for value in row)
        if original_ink == 0:
            raise SystemExit(f"{entry['id']}: 선택 OBJ의 원문 잉크가 없음")
        # 일본어 흰 잉크(14)만 검정 바탕(15)으로 지운다. 투명 외곽과
        # 다른 팔레트로 공유되는 손가락/장식 타일은 그대로 보존한다.
        for row in range(8):
            for column in range(tile_count * 8):
                if pixels[row][column] == 14:
                    pixels[row][column] = 15
        crop = approved_crop(approved, number, entry)
        new_ink = 0
        for row in range(8):
            for column in range(crop.width):
                if crop.getpixel((column, row)) != 1:
                    continue
                target_x = column + shift_x
                if not 0 <= target_x < tile_count * 8:
                    raise SystemExit(f"{entry['id']}: 선택 OBJ 승인 잉크가 범위를 벗어남")
                if pixels[row][target_x] == 0:
                    raise SystemExit(f"{entry['id']}: 선택 OBJ 승인 잉크 아래가 투명함")
                pixels[row][target_x] = 14
                new_ink += 1
        selected_edited[raw_offset:raw_offset + byte_count] = encode_4bpp_strip(pixels)
        selected_records.append({
            "id": entry["id"],
            "raw_offset": raw_offset,
            "tile_count": tile_count,
            "shift_x": shift_x,
            "old_ink_pixels": original_ink,
            "new_ink_pixels": new_ink,
        })

    selected_packed = selected_size.to_bytes(2, "little") + compress(
        bytes(selected_edited)
    )
    selected_capacity = selected_next - selected_source
    if len(selected_packed) > selected_capacity:
        raise SystemExit(
            f"포메이션 선택 OBJ 재압축 초과: {len(selected_packed)} > {selected_capacity}"
        )
    rom[selected_source:selected_source + len(selected_packed)] = selected_packed
    selected_rebuilt, selected_rebuilt_used = decompress(
        rom, selected_source + 2, selected_size
    )
    if (
        selected_rebuilt != bytes(selected_edited)
        or selected_rebuilt_used != len(selected_packed) - 2
    ):
        raise SystemExit("포메이션 선택 OBJ 재압축 왕복 실패")
    return {
        "resource": "$C6:CD10",
        "raw_bytes": raw_size,
        "compressed_bytes": len(packed),
        "loaders": ["$C1:69B7", "$C1:74BF", "$C3:6760 inline"],
        "records": records,
        "selected_obj": {
            "resource": "$DA:AD53",
            "vram": "$D800~EABF",
            "logical_tiles": "$104~$11E ($11F hand preserved)",
            "compressed_bytes": len(selected_packed),
            "capacity": selected_capacity,
            "loaders": ["$C1:6A43", "$C1:7617"],
            "records": selected_records,
        },
    }


def build_stats_and_garage(
    rom: bytearray,
    original: bytes,
    groups: dict[str, dict],
) -> dict:
    # build_setbox.py가 만든 현재 $C7:D000 문맥 자원을 기반으로 한다.
    current_source = pc(0xC7, 0xD000)
    current_size = int.from_bytes(rom[current_source:current_source + 2], "little")
    current_raw, _ = decompress(rom, current_source + 2, current_size)
    if current_size != 0x1760 or len(current_raw) != 0x1760:
        raise SystemExit(f"세팅 파생 폰트 규격 불일치: {current_size:04X}")
    edited = bytearray(current_raw)

    original_source = pc(0xD9, 0x0000)
    original_size = int.from_bytes(original[original_source:original_source + 2], "little")
    original_raw, _ = decompress(original, original_source + 2, original_size)
    if original_size != 0x1760:
        raise SystemExit("원본 $D9:0000 폰트 길이 불일치")

    stats_group = groups["machine_stats"]
    stats_approved = Image.open(STATS_WORKSHOP).convert("RGB")
    if stats_approved.size != (256, 224):
        raise SystemExit(f"능력치 승인본 크기 불일치: {stats_approved.size}")
    stats_capture = Image.open(source_for_group("machine_stats")).convert("RGBA")
    # (대상 raw 타일, 6타일 작업행에서 건너뛸 수, 쓸 타일 수)
    stats_spans = (
        (0x140, 2, 4), (0x144, 0, 6), (0x14A, 2, 4), (0x14E, 0, 6),
        (0x154, 2, 4), (0x158, 2, 4), (0x15C, 2, 4),
    )
    stats_records = []
    for number, (entry, (tile, skip, count)) in enumerate(
        zip(stats_group["labels"], stats_spans, strict=True)
    ):
        original_crop = extract_crop(stats_capture, entry, stats_group["id"])
        original_row = encode_2bpp(original_crop)
        expected = original_row[skip * 16:(skip + count) * 16]
        begin = tile * 16
        if original_raw[begin:begin + len(expected)] != expected:
            raise SystemExit(f"{entry['id']}: $D9 능력치 원본 타일 대조 실패")
        if current_raw[begin:begin + len(expected)] != expected:
            raise SystemExit(f"{entry['id']}: build_setbox가 능력치 전용 타일을 변경함")
        approved_row = encode_2bpp(approved_crop(stats_approved, number, entry))
        patch = approved_row[skip * 16:(skip + count) * 16]
        edited[begin:begin + len(patch)] = patch
        stats_records.append({"id": entry["id"], "tile_start": tile, "tile_count": count})

    garage_group = groups["garage_categories"]
    garage_approved = Image.open(GARAGE_WORKSHOP).convert("RGB")
    if garage_approved.size != (256, 224):
        raise SystemExit(f"개러지 승인본 크기 불일치: {garage_approved.size}")
    # 추적 확정: 왼쪽 분류명은 SJIS $C0:EBE8~EC1A가 아니라
    # $D9:0000의 전용 2bpp 스트립 $C0~$D7을 타일맵이 직접 참조한다.
    # 해당 SJIS 문자열은 오른쪽 부품 설명에 사용되므로 건드리지 않는다.
    # 원본 BUMPER의 마지막 칸은 GEAR의 마지막 $C9를 공유한다.
    garage_tile_maps = (
        (0xC0, 0xC1, 0xC2),
        (0xC3, 0xC4, 0xC5, 0xC6),
        (0xC7, 0xC8, 0xC9),
        (0xCA, 0xCB, 0xCC),
        (0xCD, 0xCE, 0xCF, 0xD0),
        (0xD1, 0xD2, 0xD3, 0xC9),
        (0xD4, 0xD5, 0xD6, 0xD7),
    )
    garage_original = original_raw[0xC0 * 16:0xD8 * 16]
    if hashlib.sha256(garage_original).hexdigest() != (
        "610b1ea095f274483296379c1adb774bb2c58371ce12071b28dbe14e096b4d5c"
    ):
        raise SystemExit("개러지 분류 전용 원본 타일 해시 불일치")
    if current_raw[0xC0 * 16:0xD8 * 16] != garage_original:
        raise SystemExit("build_setbox가 개러지 분류 전용 타일을 변경함")

    garage_records = []
    assigned: dict[int, bytes] = {}
    for number, (entry, tile_map) in enumerate(
        zip(garage_group["labels"], garage_tile_maps, strict=True)
    ):
        encoded = encode_2bpp(approved_crop(garage_approved, number, entry))
        chunks = [encoded[index:index + 16] for index in range(0, len(encoded), 16)]
        if len(chunks) != len(tile_map):
            raise SystemExit(f"{entry['id']}: 개러지 타일 맵 길이 불일치")
        for tile, chunk in zip(tile_map, chunks, strict=True):
            previous = assigned.get(tile)
            if previous is not None and previous != chunk:
                raise SystemExit(f"{entry['id']}: 공유 타일 ${tile:02X} 승인 이미지 불일치")
            assigned[tile] = chunk
            begin = tile * 16
            edited[begin:begin + 16] = chunk
        garage_records.append({
            "id": entry["id"],
            "raw_tiles": [f"${tile:02X}" for tile in tile_map],
            "vram_tiles": [f"${0x100 + tile:03X}" for tile in tile_map],
        })
    if set(assigned) != set(range(0xC0, 0xD8)):
        raise SystemExit("개러지 분류 전용 $C0~$D7 타일 커버리지 불일치")
    if len(edited) != 0x1760:
        raise SystemExit(f"세팅 자원 길이 변경됨: {len(edited):04X}")

    resource = len(edited).to_bytes(2, "little") + compress(bytes(edited))
    target_bank, target_addr = 0xC1, 0xD900
    target_end = 0xE900
    if len(resource) > target_end - target_addr:
        raise SystemExit(
            f"세팅 승인 자원 초과: {len(resource)} > {target_end - target_addr}"
        )
    target = pc(target_bank, target_addr)
    require_ff(rom, target, pc(target_bank, target_end), "세팅 승인 폰트")
    rom[target:target + len(resource)] = resource

    old_source = bytes((0xF4, 0xC7, 0x00, 0xF4, 0x00, 0xD0))
    new_source = bytes((0xF4, target_bank, 0x00, 0xF4, target_addr & 0xFF, target_addr >> 8))
    loaders = ((0x1EBB, 0x1400), (0x303F, 0x1600))
    for addr, old_dma_size in loaders:
        loader = pc(0xC1, addr)
        if rom[loader:loader + 6] != old_source:
            raise SystemExit(f"세팅 로더 $C1:{addr:04X}가 $C7:D000을 가리키지 않음")
        rom[loader:loader + 6] = new_source
        dma = loader + 0x35
        old_dma = bytes((0xA9, old_dma_size & 0xFF, old_dma_size >> 8))
        if rom[dma:dma + 3] != old_dma:
            raise SystemExit(f"세팅 DMA 길이 시그니처 불일치 $C1:{addr + 0x35:04X}")
        # 수동/이지 세팅의 기존 DMA 표면(0x1400/0x1600)을 유지한다.
        # 개러지 타일 $C0~$D7은 두 길이 모두에 포함된다.

    rebuilt, rebuilt_used = decompress(rom, target + 2, len(edited))
    if rebuilt != bytes(edited) or rebuilt_used != len(resource) - 2:
        raise SystemExit("확장 세팅 자원 재압축 왕복 실패")
    return {
        "resource": "$C1:D900",
        "raw_bytes": len(edited),
        "compressed_bytes": len(resource),
        "loaders": ["$C1:1EBB", "$C1:303F"],
        "dma_bytes": {"manual_setting": 0x1400, "easy_setting": 0x1600},
        "stats": stats_records,
        "garage": garage_records,
        "garage_tiles": "$D9-derived raw $C0~$D7 / VRAM $1C0~$1D7",
        "garage_note": "$C0:EBE8~EC1A SJIS는 오른쪽 부품 설명이므로 변경하지 않음",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rom", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--out", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()

    original = ORIGINAL_ROM.read_bytes()
    if len(original) != ROM_SIZE or hashlib.sha256(original).hexdigest() != ORIGINAL_SHA256:
        raise SystemExit("원본 ROM 크기/SHA256 불일치")
    rom = bytearray(args.rom.read_bytes())
    if len(rom) != ROM_SIZE:
        raise SystemExit(f"입력 통합 ROM이 헤더리스 2MB가 아님: {len(rom)}")

    groups = load_groups()
    report = {
        "formation": build_formation(rom, original, groups),
        "stats_and_garage": build_stats_and_garage(rom, original, groups),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(rom)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"승인 작업본 3종 주입 완료 → {args.out}")
    print(
        f"  포메이션: BG {report['formation']['compressed_bytes']}B @ $C6:CD10, "
        f"선택 OBJ {report['formation']['selected_obj']['compressed_bytes']}B @ $DA:AD53"
    )
    print(
        f"  능력치/개러지: {report['stats_and_garage']['compressed_bytes']}B @ $C1:D900, "
        f"raw {report['stats_and_garage']['raw_bytes']}B"
    )
    print(f"  매니페스트: {args.manifest}")


if __name__ == "__main__":
    main()
