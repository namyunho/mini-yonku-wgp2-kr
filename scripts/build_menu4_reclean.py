#!/usr/bin/env python3
"""소형 타일 메뉴·튜토리얼·용어집·지도의 독립 한글화 빌더.

기존 System④ 훅을 사용하지 않는다. 원본 $D9:0000 소형 폰트 자원을 해제해
월드맵·용어집·지도 문맥별 한글 폰트로 다시 압축하고, 원본 로더의 자원
포인터와 고정 타일 문자열만 패치한다.

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

# 용어집·지도는 각각 별도로 $D9:0000을 불러오므로, 문맥 전용
# 폰트 두 개를 $C2:D448~FFFF의 원본 0xFF 자유 영역에 순차 배치한다.
CONTEXT_FONT_POOL = (0xC2, 0xD448)
CONTEXT_FONT_POOL_CAPACITY = 0x2BB8

# 72개 음절은 대상 일본어 라벨이 쓰던 가나 타일과 원본 빈 타일 FC~FE를
# 재사용한다.
# 라틴/숫자/공백/행 제어 타일은 보존한다.
KOREAN_TILE_CODES = bytes.fromhex(
    "02 03 04 05 06 07 08 09 0A 0B 0C 0E 0F 10 12 13 14 16 "
    "19 1A 1C 1D 23 28 2E 2F 36 37 38 39 3A 3B 3E 3F 41 43 "
    "44 45 47 48 49 4A 4B 4C 4D 51 52 53 55 56 58 59 5A 5E "
    "5F 60 61 63 65 67 69 6A 6B 6C 6D 6E 6F 94 95 FC FD FE"
)

SMALL_LITERAL_TILES = {
    "A": 0x70, "C": 0x72, "F": 0x75, "G": 0x76, "I": 0x78,
    "J": 0x79, "M": 0x7C, "N": 0x7D, "O": 0x7E, "P": 0x7F,
    "R": 0x81, "T": 0x83, "W": 0x86, "X": 0x87, "4": 0x8E,
}

GLOSSARY_POINTER_BLOCK = (0x03A142, 0x03A1C5)
GLOSSARY_POINTER_BLOCK_SHA256 = "f2dfb7e4b2de9d17caf7c80f5c25cad7f44f9e1d1c8628a31322dcf8effcb2d6"
GLOSSARY_STRING_BLOCK = (0x03A1C5, 0x03A39B)
GLOSSARY_STRING_BLOCK_SHA256 = "eb75f1b53e2de605d18f8ab2b827e58b7c0e4a4c5ec4f31a70fead87ca506bba"

MAP_POINTER_BLOCK = (0x03AB75, 0x03AB97)
MAP_POINTER_BLOCK_SHA256 = "d39a6a0254ff737105f770010bb3fe109faf7189da03352aa6765fec296f796b"
MAP_STRING_BLOCK = (0x03AB97, 0x03ABF9)
MAP_STRING_BLOCK_SHA256 = "bbf530825ab7d0a8302c9fde1d300cb83ba1d95f91cc1d1cce2901a78e038070"


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
class DirectRow:
    original: bytes
    korean: str
    control: bytes


@dataclass(frozen=True)
class DirectProgram:
    addr: int
    rows: tuple[DirectRow, ...]


@dataclass(frozen=True)
class PackedLabel:
    original_addr: int
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


DIRECT_PROGRAMS = [
    # 월드맵 X 메뉴는 세 행을 한 번의 $C0:1B4B 호출로 그린다.
    DirectProgram(0x0395BE, (
        DirectRow(hex_bytes("45 6E 4A 67 65 00 94 3F"), "세팅", hex_bytes("00 02 00 02")),
        DirectRow(hex_bytes("00 94 3F 5F 6E 00 94 4B 1D 2E 0A 03"), "그리드변경", hex_bytes("00 02 00 02")),
        DirectRow(hex_bytes("38 39 4A 58"), "아이템", hex_bytes("00 00")),
    )),
    # 아이템 서브메뉴는 각 행이 독립 호출이다.
    DirectProgram(0x039201, (
        DirectRow(hex_bytes("56 6E 00 95 53"), "지도", hex_bytes("00 00")),
    )),
    DirectProgram(0x039208, (
        DirectRow(hex_bytes("0F 03 0B 56 4D 6C 38 60"), "조작방법", hex_bytes("00 00")),
    )),
    DirectProgram(0x039212, (
        DirectRow(hex_bytes("26 03 00 94 0A 0C 36 03"), "용어집", hex_bytes("00 00")),
    )),
    # 세팅 서브메뉴는 두 행을 한 번의 호출로 그린다.
    DirectProgram(0x0399C0, (
        DirectRow(hex_bytes("39 6F 00 94 43 6F"), "쉬운조작", hex_bytes("00 02 00 02")),
        DirectRow(hex_bytes("56 4D 6C 38 60"), "수동조작", hex_bytes("00 00")),
    )),
]


# 용어집은 대분류 4개 + 용어 38개다. 사용자가 지정한 인물 10개
# 뒤에 실제 ROM 포인터 테이블의 추가 4개도 같이 번역해 문맥 폰트
# 재매핑으로 인한 원문 깨짐을 막는다.
GLOSSARY_LABELS = (
    PackedLabel(0x03A1C5, "용어"),
    PackedLabel(0x03A1CC, "규칙"),
    PackedLabel(0x03A1D1, "팀"),
    PackedLabel(0x03A1D6, "인물"),

    PackedLabel(0x03A1E0, "FIMA"),
    PackedLabel(0x03A1E6, "WGP"),
    PackedLabel(0x03A1EB, "GP칩"),
    PackedLabel(0x03A1F4, "GP머신"),
    PackedLabel(0x03A1FB, "GP레이서"),
    PackedLabel(0x03A208, "고속 코스"),
    PackedLabel(0x03A211, "테크니컬 코스"),
    PackedLabel(0x03A21B, "오프로드 코스"),

    PackedLabel(0x03A227, "포인트 레이스"),
    PackedLabel(0x03A232, "릴레이 레이스"),
    PackedLabel(0x03A23A, "4톱 레이스"),
    PackedLabel(0x03A245, "배틀 레이스"),
    PackedLabel(0x03A24F, "섹션 레이스"),
    PackedLabel(0x03A259, "포메이션"),

    PackedLabel(0x03A263, "TRF 빅토리즈"),
    PackedLabel(0x03A272, "아이젠 볼프"),
    PackedLabel(0x03A280, "NA 아스트로 레인저스"),
    PackedLabel(0x03A292, "롯소 스트라다"),
    PackedLabel(0x03A29E, "CCP 실버 폭스"),
    PackedLabel(0x03A2AE, "사반나 솔져스"),
    PackedLabel(0x03A2C0, "소사구 주행단 공키"),
    PackedLabel(0x03A2D6, "XTO 리볼버즈"),
    PackedLabel(0x03A2E7, "레 방쿠르"),
    PackedLabel(0x03A2F3, "엔션트 포스"),

    PackedLabel(0x03A2FF, "오카다 텟신"),
    PackedLabel(0x03A30B, "쿠로사와 후토시"),
    PackedLabel(0x03A315, "코히로 마코토"),
    PackedLabel(0x03A31E, "사가미 준"),
    PackedLabel(0x03A32B, "사가미 타모츠"),
    PackedLabel(0x03A336, "세이바 카이조"),
    PackedLabel(0x03A344, "세이바 요시에"),
    PackedLabel(0x03A34F, "타카바 지로마루"),
    PackedLabel(0x03A35E, "츠치야 박사"),
    PackedLabel(0x03A366, "하라 J 마키"),
    PackedLabel(0x03A36F, "미쿠니 치이코"),
    PackedLabel(0x03A378, "미즈사와 히코사"),
    PackedLabel(0x03A386, "미니욘 파이터"),
    PackedLabel(0x03A390, "야나기 타마미"),
)


# 포인터 테이블이 지도에 표시하는 순서. 원문의 세이바케는 사용자가
# 적은 세이바테이가 아니라 실제 의미가 “세이바 집”이다.
MAP_LABELS = (
    PackedLabel(0x03AB9F, "타카바 산"),
    PackedLabel(0x03ABB4, "미쿠니 저택"),
    PackedLabel(0x03ABA8, "사가미 모형점"),
    PackedLabel(0x03AB97, "세이바 집"),
    PackedLabel(0x03ABBB, "풍륜 서킷"),
    PackedLabel(0x03ABEE, "초등학교"),
    PackedLabel(0x03ABC6, "체육관"),
    PackedLabel(0x03ABCE, "츠치야 연구소"),
    PackedLabel(0x03ABD4, "연구소 경기장"),
    PackedLabel(0x03ABDD, "공원"),
    PackedLabel(0x03ABE3, "인터내셔널"),
)


def collect_syllables() -> list[str]:
    syllables: list[str] = []
    direct_text = [row.korean for program in DIRECT_PROGRAMS for row in program.rows]
    for text in [r.korean for r in TUTORIAL_RECORDS] + direct_text:
        for ch in text:
            if "가" <= ch <= "힣" and ch not in syllables:
                syllables.append(ch)
    return syllables


def collect_text_syllables(texts: list[str]) -> list[str]:
    syllables: list[str] = []
    for text in texts:
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
    for ch in text:
        if ch == " ":
            out.append(0x00)
        elif "가" <= ch <= "힣":
            out.append(char_to_tile[ch])
        elif ch in SMALL_LITERAL_TILES:
            out.append(SMALL_LITERAL_TILES[ch])
        else:
            raise AssertionError(f"지원하지 않는 직접 타일 문자: {ch!r}")
    return bytes(out)


def encode_packed_text(text: str, char_to_tile: dict[str, int]) -> bytes:
    """00 제어를 쓰는 직접 렌더러가 아닌 고정 타일 문자열 인코딩."""
    out = bytearray()
    for ch in text:
        if ch == " ":
            out.append(0xFF)
        elif "가" <= ch <= "힣":
            out.append(char_to_tile[ch])
        elif ch in SMALL_LITERAL_TILES:
            out.append(SMALL_LITERAL_TILES[ch])
        else:
            raise AssertionError(f"지원하지 않는 고정 타일 문자: {ch!r}")
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


def direct_display_width(data: bytes) -> int:
    """탁점 오버레이(00 94/95)를 제외한 실제 화면 셀 수."""
    width = 0
    pos = 0
    while pos < len(data):
        if data[pos] == 0x00:
            assert pos + 1 < len(data) and data[pos + 1] >= 0x03
            pos += 2
            continue
        width += 1
        pos += 1
    return width


def original_program(program: DirectProgram) -> bytes:
    return b"".join(row.original + row.control for row in program.rows)


def encode_program(program: DirectProgram, char_to_tile: dict[str, int]) -> bytes:
    out = bytearray()
    for row in program.rows:
        width = direct_display_width(row.original)
        encoded = encode_text(row.korean, char_to_tile)
        assert len(encoded) <= width, (
            f"직접 라벨 슬롯 초과 PC ${program.addr:06X}: {row.korean} "
            f"{len(encoded)}>{width}셀"
        )
        # 원본 탁점 제어는 바이트를 쓰지만 화면 폭은 쓰지 않는다. 한글 뒤를
        # 원본의 실제 셀 수까지만 비운 뒤 행 이동/종료 제어를 바로 배치한다.
        out += encoded + bytes((0xFF,)) * (width - len(encoded))
        out += row.control
    original_size = len(original_program(program))
    assert len(out) <= original_size
    # 종료 제어 뒤의 고정 슬롯 잔여는 렌더러가 읽지 않는다.
    return bytes(out) + bytes((0xFF,)) * (original_size - len(out))


def patch_direct(rom: bytearray, char_to_tile: dict[str, int]) -> None:
    for program in DIRECT_PROGRAMS:
        original = original_program(program)
        end = program.addr + len(original)
        assert rom[program.addr:end] == original, (
            f"직접 메뉴 프로그램 원본 불일치 PC ${program.addr:06X}"
        )
        rom[program.addr:end] = encode_program(program, char_to_tile)


def read_packed_label(rom: bytes | bytearray, addr: int, block_end: int) -> bytes:
    end = rom.find(b"\x00\x00", addr, block_end)
    assert end >= 0, f"고정 타일 문자열 종단 없음: PC 0x{addr:06X}"
    return bytes(rom[addr:end])


def context_mapping(
    original: bytes,
    labels: tuple[PackedLabel, ...],
    block_end: int,
    extra_tiles: bytes = b"",
) -> tuple[list[str], dict[str, int], list[int]]:
    syllables = collect_text_syllables([label.korean for label in labels])
    reserved = {0x00, 0xFF, *SMALL_LITERAL_TILES.values()}
    candidates: list[int] = []

    for label in labels:
        for tile in read_packed_label(original, label.original_addr, block_end):
            if tile not in reserved and tile not in candidates:
                candidates.append(tile)

    # 원본 탁점/반탁점/가운데점은 재패킹 뒤 사라지고 FC~FE는 원본 빈 타일이다.
    for tile in bytes.fromhex("94 95 FB FC FD FE") + extra_tiles:
        if tile not in reserved and tile not in candidates:
            candidates.append(tile)

    assert len(candidates) >= len(syllables), (
        f"문맥 폰트 타일 부족: {len(candidates)} < {len(syllables)}"
    )
    used = candidates[:len(syllables)]
    return syllables, dict(zip(syllables, used, strict=True)), candidates


def glossary_pointer_fields(rom: bytes | bytearray) -> list[int]:
    fields = [0x03A143, 0x03A146, 0x03A149, 0x03A14C]
    pos = 0x03A14F
    while pos < GLOSSARY_POINTER_BLOCK[1]:
        if rom[pos] == 0xFF:
            pos += 1
            continue
        fields.append(pos + 1)
        pos += 3
    assert pos == GLOSSARY_POINTER_BLOCK[1]
    assert len(fields) == len(GLOSSARY_LABELS) == 42
    return fields


def map_pointer_fields(rom: bytes | bytearray) -> list[int]:
    fields = [0x03AB76 + i * 3 for i in range(len(MAP_LABELS))]
    for field in fields:
        assert rom[field - 1] == 0x01
    return fields


def patch_packed_labels(
    rom: bytearray,
    labels: tuple[PackedLabel, ...],
    pointer_fields: list[int],
    pointer_block: tuple[int, int],
    pointer_sha256: str,
    string_block: tuple[int, int],
    string_sha256: str,
    char_to_tile: dict[str, int],
) -> list[int]:
    pointer_start, pointer_end = pointer_block
    string_start, string_end = string_block
    assert hashlib.sha256(rom[pointer_start:pointer_end]).hexdigest() == pointer_sha256
    assert hashlib.sha256(rom[string_start:string_end]).hexdigest() == string_sha256
    assert len(pointer_fields) == len(labels)

    records = [encode_packed_text(label.korean, char_to_tile) + b"\x00\x00"
               for label in labels]
    assert sum(map(len, records)) <= string_end - string_start

    for field, label in zip(pointer_fields, labels, strict=True):
        original_addr = int.from_bytes(rom[field:field + 2], "little")
        assert original_addr == (label.original_addr & 0xFFFF), (
            f"원본 포인터 불일치 PC 0x{field:06X}: "
            f"{original_addr:04X}!={label.original_addr & 0xFFFF:04X}"
        )
        read_packed_label(rom, label.original_addr, string_end)

    rom[string_start:string_end] = b"\xFF" * (string_end - string_start)
    packed_addrs: list[int] = []
    cursor = string_start
    for field, record in zip(pointer_fields, records, strict=True):
        packed_addrs.append(cursor)
        rom[cursor:cursor + len(record)] = record
        rom[field:field + 2] = (cursor & 0xFFFF).to_bytes(2, "little")
        cursor += len(record)

    for field, addr, record in zip(pointer_fields, packed_addrs, records, strict=True):
        assert int.from_bytes(rom[field:field + 2], "little") == (addr & 0xFFFF)
        assert rom[addr:addr + len(record)] == record
    return packed_addrs


def make_font_resource(
    raw_font: bytes,
    raw_size: int,
    font: bytes,
    glyph_map: dict[str, int],
    char_to_tile: dict[str, int],
) -> tuple[bytes, bytes]:
    custom_font = bytearray(raw_font)
    for ch, tile in char_to_tile.items():
        custom_font[tile * 16:tile * 16 + 16] = glyph_2bpp(font, glyph_map, ch)

    compressed = compress(bytes(custom_font))
    resource = raw_size.to_bytes(2, "little") + compressed
    roundtrip, used = decompress(resource, 2, raw_size)
    assert roundtrip == bytes(custom_font)
    assert used == len(compressed)
    return resource, bytes(custom_font)


def patch_pea_font_pointer(rom: bytearray, at: int, bank: int, addr: int) -> None:
    assert rom[at:at + 6] == hex_bytes("F4 D9 00 F4 00 00")
    rom[at:at + 6] = bytes((0xF4, bank, 0x00, 0xF4, addr & 0xFF, addr >> 8))


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
    for program in DIRECT_PROGRAMS:
        expected = encode_program(program, char_to_tile)
        span = rom[program.addr:program.addr + len(expected)]
        assert span == expected


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

    glossary_syllables, glossary_char_to_tile, glossary_candidates = context_mapping(
        original,
        GLOSSARY_LABELS,
        GLOSSARY_STRING_BLOCK[1],
        bytes.fromhex("30 31 32 33 34 35 17 18"),
    )
    map_syllables, map_char_to_tile, map_candidates = context_mapping(
        original,
        MAP_LABELS,
        MAP_STRING_BLOCK[1],
    )

    font = FONT_BIN.read_bytes()
    glyph_map = json.loads(FONT_MAP.read_text(encoding="utf-8"))

    source = pc(*ORIGINAL_FONT)
    raw_size = int.from_bytes(original[source:source + 2], "little")
    assert raw_size == ORIGINAL_FONT_RAW_SIZE
    raw_font, original_used = decompress(original, source + 2, raw_size)
    assert hashlib.sha256(raw_font).hexdigest() == ORIGINAL_FONT_RAW_SHA256
    assert hashlib.sha256(raw_font[:0x1000]).hexdigest() == ORIGINAL_TILE_PAGE_SHA256

    world_resource, world_font = make_font_resource(
        raw_font, raw_size, font, glyph_map, char_to_tile,
    )
    glossary_resource, glossary_font = make_font_resource(
        raw_font, raw_size, font, glyph_map, glossary_char_to_tile,
    )
    map_resource, map_font = make_font_resource(
        raw_font, raw_size, font, glyph_map, map_char_to_tile,
    )
    assert len(world_resource) <= NEW_FONT_CAPACITY, (
        f"월드 폰트 자원 {len(world_resource)}B > 자유 슬롯 {NEW_FONT_CAPACITY}B"
    )

    rom = bytearray(original)
    world_target = pc(*NEW_FONT)
    assert all(b == 0xFF for b in rom[world_target:world_target + NEW_FONT_CAPACITY]), (
        "$C7:E000~FFFF 자유 영역이 0xFF가 아님"
    )
    rom[world_target:world_target + len(world_resource)] = world_resource

    context_pool = pc(*CONTEXT_FONT_POOL)
    assert all(b == 0xFF for b in rom[
        context_pool:context_pool + CONTEXT_FONT_POOL_CAPACITY
    ]), "$C2:D448~FFFF 자유 영역이 0xFF가 아님"
    glossary_font_addr = CONTEXT_FONT_POOL[1]
    map_font_addr = (glossary_font_addr + len(glossary_resource) + 0x0F) & ~0x0F
    context_end = map_font_addr + len(map_resource)
    assert context_end <= 0x10000, (
        f"문맥 폰트 풀 초과: $C2:{context_end:04X} > $C2:FFFF"
    )
    glossary_target = pc(CONTEXT_FONT_POOL[0], glossary_font_addr)
    map_target = pc(CONTEXT_FONT_POOL[0], map_font_addr)
    rom[glossary_target:glossary_target + len(glossary_resource)] = glossary_resource
    rom[map_target:map_target + len(map_resource)] = map_resource

    # 월드맵: PEA #$D9, PEA #$0000 -> PEA #$C7, PEA #$E000
    world_pointer = pc(0xC0, 0x94D4)
    patch_pea_font_pointer(rom, world_pointer, *NEW_FONT)

    # 튜토리얼 자원 스크립트: $D9:0000 -> $C7:E000
    tutorial_pointer = pc(0xC3, 0x67A8)
    assert rom[tutorial_pointer:tutorial_pointer + 3] == hex_bytes("00 00 D9")
    rom[tutorial_pointer:tutorial_pointer + 3] = hex_bytes("00 E0 C7")

    # 용어집과 지도는 진입 때마다 원래 D9 자원을 별도로 불러오는 두 호출처다.
    patch_pea_font_pointer(rom, pc(0xC3, 0x9DC5), 0xC2, glossary_font_addr)
    patch_pea_font_pointer(rom, pc(0xC3, 0xA835), 0xC2, map_font_addr)

    patch_tutorial(rom, char_to_tile)
    patch_direct(rom, char_to_tile)
    glossary_addrs = patch_packed_labels(
        rom,
        GLOSSARY_LABELS,
        glossary_pointer_fields(rom),
        GLOSSARY_POINTER_BLOCK,
        GLOSSARY_POINTER_BLOCK_SHA256,
        GLOSSARY_STRING_BLOCK,
        GLOSSARY_STRING_BLOCK_SHA256,
        glossary_char_to_tile,
    )
    map_addrs = patch_packed_labels(
        rom,
        MAP_LABELS,
        map_pointer_fields(rom),
        MAP_POINTER_BLOCK,
        MAP_POINTER_BLOCK_SHA256,
        MAP_STRING_BLOCK,
        MAP_STRING_BLOCK_SHA256,
        map_char_to_tile,
    )
    checksum, complement = update_snes_checksum(rom)

    # 출력 ROM 자체에서 세 자원과 모든 문자열을 다시 읽어 검증한다.
    for target, resource, expected_font in (
        (world_target, world_resource, world_font),
        (glossary_target, glossary_resource, glossary_font),
        (map_target, map_resource, map_font),
    ):
        out_size = int.from_bytes(rom[target:target + 2], "little")
        rebuilt_font, rebuilt_used = decompress(rom, target + 2, out_size)
        assert out_size == raw_size
        assert rebuilt_used == len(resource) - 2
        assert rebuilt_font == expected_font
    verify_patched_records(rom, char_to_tile)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(rom)
    map_path.parent.mkdir(parents=True, exist_ok=True)
    map_path.write_text(json.dumps({
        "source": str(input_path),
        "output": str(output_path),
        "font_resources": {
            "world_tutorial_setting": {
                "address": "$C7:E000",
                "size": len(world_resource),
                "syllable_count": len(syllables),
                "syllables": "".join(syllables),
                "char_to_tile": {ch: f"{tile:02X}" for ch, tile in char_to_tile.items()},
            },
            "glossary": {
                "address": f"$C2:{glossary_font_addr:04X}",
                "size": len(glossary_resource),
                "syllable_count": len(glossary_syllables),
                "candidate_tile_count": len(glossary_candidates),
                "syllables": "".join(glossary_syllables),
                "char_to_tile": {
                    ch: f"{tile:02X}" for ch, tile in glossary_char_to_tile.items()
                },
            },
            "map": {
                "address": f"$C2:{map_font_addr:04X}",
                "size": len(map_resource),
                "syllable_count": len(map_syllables),
                "candidate_tile_count": len(map_candidates),
                "syllables": "".join(map_syllables),
                "char_to_tile": {
                    ch: f"{tile:02X}" for ch, tile in map_char_to_tile.items()
                },
            },
        },
        "original_compressed_size": original_used + 2,
        "tutorial_record_count": len(TUTORIAL_RECORDS),
        "direct_label_count": sum(len(program.rows) for program in DIRECT_PROGRAMS),
        "glossary_label_count": len(GLOSSARY_LABELS),
        "glossary_packed_bytes": (
            glossary_addrs[-1]
            + len(encode_packed_text(GLOSSARY_LABELS[-1].korean, glossary_char_to_tile))
            + 2 - GLOSSARY_STRING_BLOCK[0]
        ),
        "map_label_count": len(MAP_LABELS),
        "map_packed_bytes": (
            map_addrs[-1]
            + len(encode_packed_text(MAP_LABELS[-1].korean, map_char_to_tile))
            + 2 - MAP_STRING_BLOCK[0]
        ),
        "checksum": f"{checksum:04X}",
        "complement": f"{complement:04X}",
        "crc32": f"{zlib.crc32(rom) & 0xFFFFFFFF:08X}",
        "md5": hashlib.md5(rom).hexdigest(),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"원본 검증: CRC32 {crc:08X} / MD5 {md5}")
    print(f"공통 폰트: $D9:0000 {raw_size}B 해제, 원본 압축 {original_used + 2}B")
    print(f"월드 폰트: $C7:E000 {len(world_resource)}B, LZSS 왕복 PASS")
    print(f"용어집 폰트: $C2:{glossary_font_addr:04X} {len(glossary_resource)}B")
    print(f"지도 폰트:   $C2:{map_font_addr:04X} {len(map_resource)}B")
    direct_count = sum(len(program.rows) for program in DIRECT_PROGRAMS)
    print(
        f"한글 매핑: 월드 {len(syllables)} / 용어집 {len(glossary_syllables)} / "
        f"지도 {len(map_syllables)}음절"
    )
    print(
        f"라벨: 튜토리얼 {len(TUTORIAL_RECORDS)} / 메뉴 {direct_count} / "
        f"용어집 {len(GLOSSARY_LABELS)} / 지도 {len(MAP_LABELS)}"
    )
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
