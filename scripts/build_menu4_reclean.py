#!/usr/bin/env python3
"""월드맵 소형 메뉴와 조작방법 튜토리얼의 독립 한글화 빌더.

기존 System④ 훅을 사용하지 않는다. 원본이 월드맵과 튜토리얼에서 공통으로
읽는 $D9:0000 소형 폰트 자원을 해제해 문맥 전용 한글 폰트로 다시 압축하고,
두 자원 포인터와 원본 고정 길이 타일 문자열만 패치한다.

실행 코드 훅, NMI, WRAM 플래그, 화면 전환 중 추가 DMA는 전혀 삽입하지 않는다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from lzss import compress, decompress  # noqa: E402


ORIGINAL_ROM = ROOT / "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
DEFAULT_OUT = ROOT / "out/menu4_reclean.smc"
DEFAULT_MAP = ROOT / "out/menu4_reclean_glyph_map.json"
FONT_BIN = ROOT / "8pt_font/font-007242d37349daf3.bin"
FONT_MAP = ROOT / "8pt_font/font-007242d37349daf3_glyph_map.json"

ORIGINAL_SIZE = 0x200000
ORIGINAL_CRC32 = 0x4459D4D0
ORIGINAL_MD5 = "acdeb2ee6ef7b460c5dfed6957f8581a"

# 원본 공통 소형 폰트 자원. 2바이트 해제 길이 헤더 뒤에 LZSS가 이어진다.
ORIGINAL_FONT = (0xD9, 0x0000)
ORIGINAL_FONT_RAW_SIZE = 0x1760
ORIGINAL_FONT_RAW_SHA256 = "78dfbb47aff74d3d6ccfa055ab0cb5975cdf779fcc617edb9db2ebf266bb43dd"
ORIGINAL_TILE_PAGE_SHA256 = "9f84cb8c101db514d4c4f6218099d1a90b95daea24d4d1c1fc2ce340986bd155"

# 원본 $C7:B49B 이후의 0xFF 자유 영역 안쪽. 최대 8KB를 넘지 않는다.
NEW_FONT = (0xC7, 0xE000)
NEW_FONT_CAPACITY = 0x2000

# 72개 음절은 대상 일본어 라벨이 쓰던 가나 타일과 원본 빈 타일 FC~FE만
# 재사용한다. 라틴/숫자/공백/행 제어 타일은 보존한다.
KOREAN_TILE_CODES = bytes.fromhex(
    "02 03 04 05 06 07 08 09 0A 0B 0C 0E 0F 10 12 13 14 16 "
    "19 1A 1C 1D 23 28 2E 2F 36 37 38 39 3A 3B 3E 3F 41 43 "
    "44 45 47 48 49 4A 4B 4C 4D 51 52 53 55 56 58 59 5A 5E "
    "5F 60 61 63 65 67 69 6A 6B 6C 6D 6E 6F 94 95 FC FD FE"
)


def pc(bank: int, addr: int) -> int:
    """프로젝트의 유일한 HiROM 변환식."""
    return ((bank & 0x3F) << 16) | (addr & 0xFFFF)


def hex_bytes(text: str) -> bytes:
    return bytes.fromhex(text)


@dataclass(frozen=True)
class TutorialRecord:
    top: int
    bottom: int
    original_bottom: bytes
    korean: str
    prefix: bytes = b""


@dataclass(frozen=True)
class DirectLabel:
    addr: int
    original: bytes
    korean: str


def tr(
    top: int,
    bottom: int,
    original: str,
    korean: str,
    prefix: str = "",
) -> TutorialRecord:
    return TutorialRecord(top, bottom, hex_bytes(original), korean, hex_bytes(prefix))


# 각 주소는 원본 ROM 읽기와 Mesen 실행 추적으로 독립 확인한 길이 레코드다.
# 같은 문구가 여러 페이지에 있으면 모든 실제 발생 위치를 명시한다.
TUTORIAL_RECORDS = [
    # 목차와 페이지 제목
    tr(0xB183, 0xB187, "23 08 0C", "목차"),
    tr(0xB1DF, 0xB1E7, "56 6E 53 00 5A 6F 4B", "맵 모드"),
    tr(0xB23F, 0xB24A, "45 6E 4A 67 65 3F 00 5A 6F 4B", "세팅 모드"),
    tr(0xB2A7, 0xB2B1, "51 5E 59 6F 47 16 12 02 13", "성능 설명"),
    tr(0xB361, 0xB36E, "3F 5F 6E 4B 1D 2E 0A 03 00 5A 6F 4B", "그리드변경 모드"),
    tr(0xB3BB, 0xB3C3, "61 6F 44 00 5A 6F 4B", "레이스 모드"),
    tr(0xB42D, 0xB43A, "86 76 7F 3B 65 4B 5F 6F 00 5A 6F 4B", "WGP 참가 모드"),

    # 맵 모드
    tr(0xB1EF, 0xB1F5, "38 3F 43 6D 65", "동작"),
    tr(0xB1FB, 0xB1FF, "02 14 03", "이동"),
    tr(0xB203, 0xB209, "56 4D 6C 38 60", "수동"),
    tr(0xB20F, 0xB215, "3A 67 65 4B 3A", "창"),
    tr(0xB21B, 0xB221, "38 3F 43 6D 65", "동작"),
    tr(0xB227, 0xB22C, "47 6E 43 6C", "대시"),
    tr(0xB231, 0xB238, "45 6E 4A 67 65 3F", "세팅"),

    # 세팅 모드
    tr(0xB255, 0xB25D, "56 43 65 07 28 06 04", "머신전환"),
    tr(0xB265, 0xB26D, "56 43 65 07 28 06 04", "머신전환"),
    tr(0xB275, 0xB27D, "51 6F 49 0E 2E 10 08", "파츠선택"),
    tr(0xB285, 0xB28A, "09 2F 13 02", "결정"),
    tr(0xB28F, 0xB295, "3E 6B 65 45 60", "취소"),
    tr(0xB29B, 0xB2A1, "3A 67 65 4B 3A", "창"),

    # 성능 설명: 영문 약어와 뒤 공백 세 타일은 그대로 둔다.
    tr(0xB2BB, 0xB2C7, "82 7F 00 44 52 6F 4B 0E 02 19 03", "속도성능", "82 7F 00"),
    tr(0xB2D3, 0xB2E1, "72 7D 00 41 6F 4C 5F 65 3F 0E 02 19 03", "코너링성능", "72 7D 00"),
    tr(0xB2EF, 0xB2FA, "7F 86 00 51 63 6F 0E 02 19 03", "파워성능", "7F 86 00"),
    tr(0xB305, 0xB314, "73 75 00 47 3A 65 53 6A 6F 44 0E 02 19 03", "다운포스성능", "73 75 00"),
    tr(0xB323, 0xB32A, "86 83 00 05 23 0B", "무게", "86 83 00"),
    tr(0xB331, 0xB33D, "73 7F 00 10 02 07 36 03 28 37 08", "내구력", "73 7F 00"),
    tr(0xB349, 0xB355, "71 7F 00 1A 08 0F 03 55 39 65 4B", "폭주포인트", "71 7F 00"),

    # 그리드변경 모드
    tr(0xB37B, 0xB383, "56 43 65 0E 2E 10 08", "머신선택"),
    tr(0xB38B, 0xB390, "09 2F 13 02", "결정"),
    tr(0xB395, 0xB39B, "3E 6B 65 45 60", "취소"),
    tr(0xB3A1, 0xB3A8, "0C 36 03 28 37 03", "종료"),
    tr(0xB3AF, 0xB3B5, "56 4D 6C 38 60", "수동조작"),

    # 레이스 모드
    tr(0xB3CB, 0xB3D2, "44 4A 38 5F 65 3F", "조향"),
    tr(0xB3D9, 0xB3E0, "71 7F 06 02 1C 08", "회복", "71 7F 00"),
    tr(0xB3E7, 0xB3EC, "1A 08 0F 03", "폭주"),
    tr(0xB3F1, 0xB3F9, "4B 6E 53 48 69 65 43", "선두전환"),
    tr(0xB401, 0xB409, "61 6F 44 38 39 4A 58", "레이스아이템"),
    tr(0xB411, 0xB416, "48 69 65 43", "전환"),
    tr(0xB41B, 0xB420, "48 69 65 43", "전환"),
    tr(0xB425, 0xB429, "55 6F 44", "정지"),

    # WGP 참가 모드
    tr(0xB447, 0xB44C, "0E 2E 10 08", "선택"),
    tr(0xB451, 0xB456, "09 2F 13 02", "결정"),
    tr(0xB45B, 0xB461, "3E 6B 65 45 60", "취소"),
]


DIRECT_LABELS = [
    # 월드맵 X 메뉴
    DirectLabel(0x0395BE, hex_bytes("45 6E 4A 67 65 00 94 3F"), "세팅"),
    DirectLabel(0x0395CA, hex_bytes("00 94 3F 5F 6E 00 94 4B 1D 2E 0A 03"), "그리드변경"),
    DirectLabel(0x0395DA, hex_bytes("38 39 4A 58"), "아이템"),
    # 아이템 서브메뉴
    DirectLabel(0x039201, hex_bytes("56 6E 00 95 53"), "지도"),
    DirectLabel(0x039208, hex_bytes("0F 03 0B 56 4D 6C 38 60"), "조작방법"),
    DirectLabel(0x039212, hex_bytes("26 03 00 94 0A 0C 36 03"), "용어집"),
    # 세팅 서브메뉴
    DirectLabel(0x0399C0, hex_bytes("39 6F 00 94 43 6F"), "쉬운조작"),
    DirectLabel(0x0399CA, hex_bytes("56 4D 6C 38 60"), "수동조작"),
]


def collect_syllables() -> list[str]:
    syllables: list[str] = []
    for text in [r.korean for r in TUTORIAL_RECORDS] + [r.korean for r in DIRECT_LABELS]:
        for ch in text:
            if "가" <= ch <= "힣" and ch not in syllables:
                syllables.append(ch)
    return syllables


def glyph_2bpp(font: bytes, glyph_map: dict[str, int], ch: str) -> bytes:
    """8×8 1bpp 한글을 게임의 16바이트 SNES 2bpp 타일로 바꾼다."""
    if ch not in glyph_map:
        raise AssertionError(f"8pt 폰트에 없는 음절: {ch!r}")
    src = font[glyph_map[ch] * 8:glyph_map[ch] * 8 + 8]
    assert len(src) == 8
    out = bytearray(16)
    for row in range(8):
        source_row = row - 1  # 원본 $D9 글꼴의 바닥선에 맞춰 1px 아래로 이동
        if 0 <= source_row < 8:
            out[row * 2] = src[source_row]
    return bytes(out)


def encode_text(text: str, char_to_tile: dict[str, int]) -> bytes:
    out = bytearray()
    latin = {
        "W": 0x86, "G": 0x76, "P": 0x7F,
    }
    for ch in text:
        if ch == " ":
            out.append(0x00)
        elif "가" <= ch <= "힣":
            out.append(char_to_tile[ch])
        elif ch in latin:
            out.append(latin[ch])
        else:
            raise AssertionError(f"지원하지 않는 직접 타일 문자: {ch!r}")
    return bytes(out)


def patch_tutorial(rom: bytearray, char_to_tile: dict[str, int]) -> None:
    for spec in TUTORIAL_RECORDS:
        top = pc(0xC7, spec.top)
        bottom = pc(0xC7, spec.bottom)
        top_len = rom[top]
        bottom_len = rom[bottom]
        assert top_len == bottom_len == len(spec.original_bottom), (
            f"레코드 길이 불일치 $C7:{spec.top:04X}/$C7:{spec.bottom:04X}"
        )
        assert rom[bottom + 1:bottom + 1 + bottom_len] == spec.original_bottom, (
            f"원본 본문 불일치 $C7:{spec.bottom:04X}"
        )
        old_top = rom[top + 1:top + 1 + top_len]
        assert set(old_top) <= {0x00, 0x94, 0x95}, f"예상 밖 상단 타일 $C7:{spec.top:04X}"

        encoded = spec.prefix + encode_text(spec.korean, char_to_tile)
        assert len(encoded) <= bottom_len, (
            f"튜토리얼 슬롯 초과 $C7:{spec.bottom:04X}: {spec.korean} "
            f"{len(encoded)}>{bottom_len}"
        )
        rom[top + 1:top + 1 + top_len] = bytes(top_len)
        rom[bottom + 1:bottom + 1 + bottom_len] = encoded + bytes(bottom_len - len(encoded))


def patch_direct(rom: bytearray, char_to_tile: dict[str, int]) -> None:
    for spec in DIRECT_LABELS:
        end = spec.addr + len(spec.original)
        assert rom[spec.addr:end] == spec.original, f"직접 라벨 원본 불일치 PC ${spec.addr:06X}"
        encoded = encode_text(spec.korean, char_to_tile)
        assert len(encoded) <= len(spec.original), (
            f"직접 라벨 슬롯 초과 PC ${spec.addr:06X}: {spec.korean}"
        )
        # $C0:1B4B 원본 렌더러의 0xFF 빈 타일 처리를 그대로 쓴다.
        rom[spec.addr:end] = encoded + bytes((0xFF,)) * (len(spec.original) - len(encoded))


def update_snes_checksum(rom: bytearray) -> tuple[int, int]:
    """2MB HiROM 헤더의 체크섬/보수를 다시 계산한다."""
    rom[0xFFDC:0xFFE0] = b"\x00\x00\x00\x00"
    checksum = (sum(rom) + 0x1FE) & 0xFFFF
    complement = checksum ^ 0xFFFF
    rom[0xFFDC:0xFFDE] = complement.to_bytes(2, "little")
    rom[0xFFDE:0xFFE0] = checksum.to_bytes(2, "little")
    assert (sum(rom) & 0xFFFF) == checksum
    return checksum, complement


def verify_patched_records(rom: bytes, char_to_tile: dict[str, int]) -> None:
    for spec in TUTORIAL_RECORDS:
        top = pc(0xC7, spec.top)
        bottom = pc(0xC7, spec.bottom)
        size = rom[bottom]
        encoded = spec.prefix + encode_text(spec.korean, char_to_tile)
        assert rom[top + 1:top + 1 + size] == bytes(size)
        assert rom[bottom + 1:bottom + 1 + len(encoded)] == encoded
        assert rom[bottom + 1 + len(encoded):bottom + 1 + size] == bytes(size - len(encoded))
    for spec in DIRECT_LABELS:
        encoded = encode_text(spec.korean, char_to_tile)
        span = rom[spec.addr:spec.addr + len(spec.original)]
        assert span == encoded + bytes((0xFF,)) * (len(spec.original) - len(encoded))


def build(input_path: Path, output_path: Path, map_path: Path) -> None:
    original = input_path.read_bytes()
    assert len(original) == ORIGINAL_SIZE, f"헤더리스 2MB가 아님: {len(original)}"
    crc = zlib.crc32(original) & 0xFFFFFFFF
    md5 = hashlib.md5(original).hexdigest()
    assert crc == ORIGINAL_CRC32, f"원본 CRC32 불일치: {crc:08X}"
    assert md5 == ORIGINAL_MD5, f"원본 MD5 불일치: {md5}"

    syllables = collect_syllables()
    assert len(KOREAN_TILE_CODES) == len(set(KOREAN_TILE_CODES)) == 72
    assert len(syllables) == len(KOREAN_TILE_CODES), (
        f"한글 음절 수가 설계와 달라짐: {len(syllables)} != {len(KOREAN_TILE_CODES)}"
    )
    char_to_tile = dict(zip(syllables, KOREAN_TILE_CODES, strict=True))

    font = FONT_BIN.read_bytes()
    glyph_map = json.loads(FONT_MAP.read_text(encoding="utf-8"))

    source = pc(*ORIGINAL_FONT)
    raw_size = int.from_bytes(original[source:source + 2], "little")
    assert raw_size == ORIGINAL_FONT_RAW_SIZE
    raw_font, original_used = decompress(original, source + 2, raw_size)
    assert hashlib.sha256(raw_font).hexdigest() == ORIGINAL_FONT_RAW_SHA256
    assert hashlib.sha256(raw_font[:0x1000]).hexdigest() == ORIGINAL_TILE_PAGE_SHA256

    custom_font = bytearray(raw_font)
    for ch, tile in char_to_tile.items():
        custom_font[tile * 16:tile * 16 + 16] = glyph_2bpp(font, glyph_map, ch)

    compressed = compress(bytes(custom_font))
    resource = raw_size.to_bytes(2, "little") + compressed
    assert len(resource) <= NEW_FONT_CAPACITY, (
        f"새 폰트 자원 {len(resource)}B > 자유 슬롯 {NEW_FONT_CAPACITY}B"
    )
    roundtrip, used = decompress(resource, 2, raw_size)
    assert roundtrip == bytes(custom_font)
    assert used == len(compressed)

    rom = bytearray(original)
    target = pc(*NEW_FONT)
    assert all(b == 0xFF for b in rom[target:target + NEW_FONT_CAPACITY]), (
        "$C7:E000~FFFF 자유 영역이 0xFF가 아님"
    )
    rom[target:target + len(resource)] = resource

    # 월드맵: PEA #$D9, PEA #$0000 -> PEA #$C7, PEA #$E000
    world_pointer = pc(0xC0, 0x94D4)
    assert rom[world_pointer:world_pointer + 6] == hex_bytes("F4 D9 00 F4 00 00")
    rom[world_pointer:world_pointer + 6] = hex_bytes("F4 C7 00 F4 00 E0")

    # 튜토리얼 자원 스크립트: $D9:0000 -> $C7:E000
    tutorial_pointer = pc(0xC3, 0x67A8)
    assert rom[tutorial_pointer:tutorial_pointer + 3] == hex_bytes("00 00 D9")
    rom[tutorial_pointer:tutorial_pointer + 3] = hex_bytes("00 E0 C7")

    patch_tutorial(rom, char_to_tile)
    patch_direct(rom, char_to_tile)
    checksum, complement = update_snes_checksum(rom)

    # 출력 ROM 자체에서 새 자원과 모든 문자열을 다시 읽어 검증한다.
    out_size = int.from_bytes(rom[target:target + 2], "little")
    rebuilt_font, rebuilt_used = decompress(rom, target + 2, out_size)
    assert out_size == raw_size
    assert rebuilt_used == len(compressed)
    assert rebuilt_font == bytes(custom_font)
    verify_patched_records(rom, char_to_tile)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(rom)
    map_path.parent.mkdir(parents=True, exist_ok=True)
    map_path.write_text(json.dumps({
        "source": str(input_path),
        "output": str(output_path),
        "font_resource": "$C7:E000",
        "font_resource_size": len(resource),
        "original_compressed_size": original_used + 2,
        "syllable_count": len(syllables),
        "syllables": "".join(syllables),
        "char_to_tile": {ch: f"{tile:02X}" for ch, tile in char_to_tile.items()},
        "tutorial_record_count": len(TUTORIAL_RECORDS),
        "direct_label_count": len(DIRECT_LABELS),
        "checksum": f"{checksum:04X}",
        "complement": f"{complement:04X}",
        "crc32": f"{zlib.crc32(rom) & 0xFFFFFFFF:08X}",
        "md5": hashlib.md5(rom).hexdigest(),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"원본 검증: CRC32 {crc:08X} / MD5 {md5}")
    print(f"공통 폰트: $D9:0000 {raw_size}B 해제, 원본 압축 {original_used + 2}B")
    print(f"새 폰트:   $C7:E000 {len(resource)}B, LZSS 왕복 PASS")
    print(f"한글 매핑: {len(syllables)}음절 / 튜토리얼 {len(TUTORIAL_RECORDS)}레코드 / 메뉴 {len(DIRECT_LABELS)}라벨")
    print("코드 훅/NMI/WRAM 플래그/추가 DMA: 없음")
    print(f"SNES 체크섬: {checksum:04X} / 보수 {complement:04X}")
    print(f"출력: {output_path}")
    print(f"CRC32 {zlib.crc32(rom) & 0xFFFFFFFF:08X} / MD5 {hashlib.md5(rom).hexdigest()}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rom", type=Path, default=ORIGINAL_ROM)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--map-out", type=Path, default=DEFAULT_MAP)
    args = parser.parse_args()
    build(args.rom, args.out, args.map_out)


if __name__ == "__main__":
    main()
