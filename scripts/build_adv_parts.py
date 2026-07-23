#!/usr/bin/env python3
"""어드벤처 파츠 획득용 동적 이름 조각 27개를 원래 C0 영역에 재패킹한다.

메뉴/SJIS 이름과 별개로, cmd0x20의 {c7:00} 표현식은 $C0:627E에서
$C0:62EE~631F의 네 포인터 테이블과 $C0:6324~6398의 길이-prefix 문자열을
조합한다. 이 빌더는 그 171바이트 연속 영역 밖을 건드리지 않는다.
"""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, "scripts")
from build_adv import encode_text

ORIG = "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
ROM = "out/wgp2_kr.smc"
KR = "assets/translations/adv_parts_fragments.json"
GLYPH_MAP = "out/glyph_map.json"
ORIG_MD5 = "acdeb2ee6ef7b460c5dfed6957f8581a"


def parse_hex(value):
    return int(value, 16)


def parse_snes(value):
    bank, addr = value.removeprefix("$").split(":")
    return int(bank, 16), int(addr, 16)


def foff(bank, addr):
    return ((bank & 0x3F) << 16) | addr


def decode_text(data, idx2char, where):
    out = []
    pos = 0
    while pos < len(data):
        lead = data[pos]
        if 1 <= lead <= 4:
            if pos + 1 >= len(data):
                sys.exit(f"잘린 2바이트 글리프 @ {where}+{pos}")
            code = (lead << 8) | data[pos + 1]
            pos += 2
        else:
            if lead < 0x10:
                sys.exit(f"이름 조각에 제어코드 0x{lead:02X} @ {where}+{pos}")
            code = lead
            pos += 1
        idx = code - 0x10
        if idx not in idx2char:
            sys.exit(f"역매핑 없는 글리프 0x{idx:03X} @ {where}")
        out.append(idx2char[idx])
    return "".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom", default=ROM)
    ap.add_argument("--out", default=ROM)
    ap.add_argument("--base", default=ORIG)
    ap.add_argument("--kr", default=KR)
    ap.add_argument("--glyph-map", default=GLYPH_MAP)
    a = ap.parse_args()

    base = Path(a.base).read_bytes()
    if hashlib.md5(base).hexdigest() != ORIG_MD5:
        sys.exit("원본 ROM MD5 불일치")
    before = Path(a.rom).read_bytes()
    if len(before) != len(base):
        sys.exit(f"ROM 크기 불일치: {len(before)} != {len(base)}")
    if before[0xFFD7] != base[0xFFD7]:
        sys.exit("ROM 크기 헤더가 원본과 다름")

    doc = json.loads(Path(a.kr).read_text(encoding="utf-8"))
    region = doc["region"]
    start = parse_hex(region["file_offset"])
    payload_start = parse_hex(region["payload_file_offset"])
    end = parse_hex(region["end_file_offset"])
    if end - start != region["capacity"] or end - payload_start != region["payload_capacity"]:
        sys.exit("원장 region 용량 계산 불일치")
    for key, off in (("start", start), ("payload_start", payload_start),
                     ("end_exclusive", end)):
        if foff(*parse_snes(region[key])) != off:
            sys.exit(f"원장 {key} SNES/파일 오프셋 불일치")

    ch2idx = json.loads(Path(a.glyph_map).read_text(encoding="utf-8"))["char2idx"]
    idx2char = {}
    for char, idx in ch2idx.items():
        if idx in idx2char and idx2char[idx] != char:
            sys.exit(f"글리프 인덱스 중복: 0x{idx:03X}={idx2char[idx]!r}/{char!r}")
        idx2char[idx] = char

    # 원본 포인터·길이·raw를 먼저 전량 검증한다. 엔트리는 원본 payload를 빈틈없이 덮어야 한다.
    cursor = payload_start
    entries = []
    for table in doc["tables"]:
        table_off = parse_hex(table["file_offset"])
        if foff(*parse_snes(table["pointer_table"])) != table_off:
            sys.exit(f"{table['id']}: 포인터 테이블 주소 불일치")
        if table["count"] != len(table["entries"]):
            sys.exit(f"{table['id']}: count 불일치")
        for index, entry in enumerate(table["entries"]):
            if entry["index"] != index:
                sys.exit(f"{table['id']}: index 순서 불일치")
            ptr_off = table_off + index * 2
            ptr = struct.unpack_from("<H", base, ptr_off)[0]
            ptr_bank, asset_ptr = parse_snes(entry["pointer"])
            if ptr_bank != 0xC0 or ptr != asset_ptr or ptr != cursor:
                sys.exit(f"{table['id']}[{index}]: 원본 포인터 불일치")
            raw = bytes.fromhex(entry["raw_hex"])
            if len(raw) != entry["length"]:
                sys.exit(f"{table['id']}[{index}]: raw 길이 불일치")
            if base[ptr] != len(raw) or base[ptr + 1:ptr + 1 + len(raw)] != raw:
                sys.exit(f"{table['id']}[{index}]: 원본 길이-prefix/raw 불일치")
            entries.append((table["id"], index, ptr_off, entry))
            cursor += 1 + len(raw)
    if cursor != end:
        sys.exit(f"원본 payload 전량 카탈로그 실패: 0x{cursor:06X} != 0x{end:06X}")
    if len(entries) != 27:
        sys.exit(f"엔트리 수 불일치: {len(entries)} != 27")

    # 원본 영역을 바탕으로 새 포인터와 payload만 만든다. 남는 꼬리 바이트는 원본 그대로 보존한다.
    expected = bytearray(base[start:end])
    cursor = payload_start
    encoded = []
    for table_id, index, ptr_off, entry in entries:
        text = entry["text_kr"]
        data = encode_text(text, ch2idx, f"{table_id}[{index}]")
        if not data or len(data) > 0xFF:
            sys.exit(f"{table_id}[{index}]: 잘못된 인코딩 길이 {len(data)}")
        if cursor + 1 + len(data) > end:
            sys.exit(f"파츠 조각 영역 부족: 0x{cursor + 1 + len(data):06X} > 0x{end:06X}")
        struct.pack_into("<H", expected, ptr_off - start, cursor & 0xFFFF)
        expected[cursor - start] = len(data)
        expected[cursor + 1 - start:cursor + 1 + len(data) - start] = data
        encoded.append((table_id, index, cursor, data, text))
        cursor += 1 + len(data)

    base_region = base[start:end]
    expected_region = bytes(expected)
    current_region = before[start:end]
    if current_region not in (base_region, expected_region):
        diffs = [start + i for i, (x, y, z) in enumerate(zip(current_region, base_region, expected_region))
                 if x != y and x != z]
        sample = ", ".join(f"0x{x:06X}" for x in diffs[:8])
        sys.exit(f"파츠 영역에 예상 밖 선행 변경 {len(diffs)}B: {sample}")

    rom = bytearray(before)
    rom[start:end] = expected_region
    after = bytes(rom)
    if after[:start] != before[:start] or after[end:] != before[end:]:
        sys.exit("허용 영역 밖 변경 감지")
    if len(after) != len(base) or after[0xFFD7] != base[0xFFD7]:
        sys.exit("2MB 크기/헤더 보존 실패")

    ok = 0
    for table_id, index, ptr, data, text in encoded:
        table = next(t for t in doc["tables"] if t["id"] == table_id)
        actual_ptr = struct.unpack_from("<H", after, parse_hex(table["file_offset"]) + index * 2)[0]
        if actual_ptr != ptr or after[ptr] != len(data):
            sys.exit(f"{table_id}[{index}]: 빌드 후 포인터/길이 불일치")
        got_raw = after[ptr + 1:ptr + 1 + len(data)]
        got = decode_text(got_raw, idx2char, f"{table_id}[{index}]")
        if got != text:
            sys.exit(f"{table_id}[{index}]: 역검증 불일치 {got!r} != {text!r}")
        ok += 1

    Path(a.out).write_bytes(after)
    used = cursor - payload_start
    changed = sum(x != y for x, y in zip(before[start:end], after[start:end]))
    print("=== 어드벤처 파츠 획득 동적 이름 ===")
    print(f"  원본 카탈로그 검증 : {len(entries)} / 27")
    print(f"  한글 역검증        : {ok} / 27")
    print(f"  payload 사용       : {used} / {end - payload_start} B (여유 {end - cursor} B)")
    print(f"  변경 범위          : $C0:62EE~$C0:6398 내부 {changed} B, ROM 2MB 유지")
    print(f"  -> {a.out}")


if __name__ == "__main__":
    main()
