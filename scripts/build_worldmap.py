#!/usr/bin/env python3
"""월드맵 퀴즈 DB 한글 재삽입.

원본 350개 포인터를 같은 $C6 뱅크의 자유공간으로 전량 리포인트한다.
질문마다 원본 슬롯 길이에 맞추는 대신 포인터 테이블을 갱신하므로 번역 길이
변동에 안전하다. $C0:6634가 문자열을 256B WRAM 버퍼로 복사하므로 개별
인코딩은 종료자 포함 256B 미만이어야 한다.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import struct
import sys
from collections import Counter

sys.path.insert(0, "scripts")
from decode_script import decode, encode, render


ORIG = "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
DATA = "assets/translations/worldmap_text.json"
GLYPH_MAP = "out/glyph_map.json"
WIDTH_BASE = 0x0A9137
BANK = 0xC6
PTR_ADDR = 0xA08D
PTR_COUNT = 350
RELOC_ADDR = 0xE200
RELOC_END = 0x10000
QUESTION_MAX_LINE_PIXELS = 156
FIXED_MAX_LINE_PIXELS = 178


def foff(bank: int, addr: int) -> int:
    return ((bank & 0x3F) << 16) | addr


def non_layout_markers(text: str) -> list[str]:
    """자동 개행 변경은 허용하고 그 밖의 제어코드는 원문과 동일하게 유지한다."""
    return [
        marker for marker in re.findall(r"\{[^}]+\}", text)
        if marker != "{nl}"
    ]


def line_pixels(line: str, char2idx: dict[str, int], rom: bytes) -> int:
    return sum(rom[WIDTH_BASE + char2idx[ch]] for ch in line)


def to_tokens(text: str, char2idx: dict[str, int]):
    toks = []
    for m in re.finditer(r"\{([^}]*)\}|([^{]+)", text):
        if m.group(1) is not None:
            name = m.group(1)
            if name == "end":
                toks.append(("ctrl", "end", b""))
            elif name == "nl":
                toks.append(("ctrl", "nl", b""))
            elif name == "wait":
                toks.append(("ctrl", "wait", b""))
            elif name.startswith("p:"):
                toks.append(("ctrl", "param", bytes.fromhex(name.split(":", 1)[1])))
            else:
                raise ValueError(f"지원하지 않는 월드맵 제어코드: {{{name}}}")
        else:
            for ch in m.group(2):
                if ch not in char2idx:
                    raise KeyError(f"미매핑 문자 {ch!r} (U+{ord(ch):04X})")
                toks.append(("glyph", char2idx[ch], 0))
    if not toks or toks[-1] != ("ctrl", "end", b""):
        toks.append(("ctrl", "end", b""))
    return toks


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom", default="out/wgp2_kr.smc")
    ap.add_argument("--out", default="out/wgp2_kr.smc")
    ap.add_argument("--data", default=DATA)
    ap.add_argument("--glyph-map", default=GLYPH_MAP)
    args = ap.parse_args()

    orig = open(ORIG, "rb").read()
    rom = bytearray(open(args.rom, "rb").read())
    data = json.load(open(args.data, encoding="utf-8"))
    char2idx = json.load(open(args.glyph_map, encoding="utf-8"))["char2idx"]
    char2idx = {c: int(idx) for c, idx in char2idx.items()}
    idx2char = {idx: c for c, idx in char2idx.items()}
    entries = data["entries"]
    fixed_messages = data.get("fixed_messages", [])

    if len(orig) != 0x200000 or len(rom) != len(orig):
        sys.exit(f"ROM 크기 불일치: orig={len(orig)} input={len(rom)}")
    if len(entries) != PTR_COUNT or [e["entry_id"] for e in entries] != list(range(PTR_COUNT)):
        sys.exit("worldmap_text.json은 entry_id 0..349 전량이 필요")
    if len(fixed_messages) != 7:
        sys.exit("worldmap_text.json은 시작·정답·오답 고정 메시지 7개가 필요")

    # 원본 추출물·포인터 불변식. 빌드 입력에서도 이 영역은 선행 단계가 건드리면 안 된다.
    pt_off = foff(BANK, PTR_ADDR)
    for i, e in enumerate(entries):
        addr = int(e["addr"].split(":")[1], 16)
        raw = bytes.fromhex(e["raw_hex"])
        off = int(e["file_offset"], 16)
        if orig[off:off + len(raw)] != raw:
            sys.exit(f"#{i} {e['addr']}: raw_hex != 원본 ROM")
        if rom[off:off + len(raw)] != raw:
            sys.exit(f"#{i} {e['addr']}: 선행 빌드가 원본 문자열 영역을 변경함")
        if struct.unpack_from("<H", orig, pt_off + i * 2)[0] != addr:
            sys.exit(f"#{i}: 원본 포인터 != {e['addr']}")
        if struct.unpack_from("<H", rom, pt_off + i * 2)[0] != addr:
            sys.exit(f"#{i}: 선행 빌드가 포인터 테이블을 변경함")

    # 350개 DB와 별개인 시작 안내·정답·오답 7문자열과 24-bit 포인터.
    for message in fixed_messages:
        off = int(message["file_offset"], 16)
        raw = bytes.fromhex(message["raw_hex"])
        addr = int(message["addr"].split(":")[1], 16)
        if orig[off:off + len(raw)] != raw:
            sys.exit(f"{message['id']}: raw_hex != 원본 ROM")
        if rom[off:off + len(raw)] != raw:
            sys.exit(f"{message['id']}: 선행 빌드가 원본 고정 메시지를 변경함")
        expected_pointer = addr.to_bytes(2, "little") + bytes((BANK,))
        for pointer_field in message["pointer_fields"]:
            pointer_addr = int(pointer_field.split(":")[1], 16)
            pointer_off = foff(BANK, pointer_addr)
            if orig[pointer_off:pointer_off + 3] != expected_pointer:
                sys.exit(f"{message['id']}: 원본 24-bit 포인터 불일치 {pointer_field}")
            if rom[pointer_off:pointer_off + 3] != expected_pointer:
                sys.exit(f"{message['id']}: 선행 빌드가 포인터를 변경함 {pointer_field}")

    encoded = []
    width_errors = []
    marker_errors = []
    for e in entries:
        if non_layout_markers(e["jp"]) != non_layout_markers(e["kr"]):
            marker_errors.append(e["entry_id"])
        visible = e["kr"].replace("{end}", "")
        lines = visible.split("{nl}")
        max_lines = 2 if e["role"] == "question" else 1
        if len(lines) > max_lines:
            sys.exit(
                f"#{e['entry_id']} {e['role']}: {len(lines)}줄 > 화면 상한 {max_lines}줄"
            )
        for line_no, line in enumerate(lines, 1):
            pixels = line_pixels(line, char2idx, rom)
            if pixels > QUESTION_MAX_LINE_PIXELS:
                width_errors.append((e["entry_id"], line_no, pixels, line))
        try:
            b = encode(to_tokens(e["kr"], char2idx))
        except (KeyError, ValueError) as ex:
            sys.exit(f"#{e['entry_id']} {e['addr']}: {ex}")
        if len(b) >= 256:
            sys.exit(f"#{e['entry_id']} {e['addr']}: WRAM 256B 복사 상한 초과 ({len(b)}B)")
        encoded.append(b)
    if marker_errors:
        sys.exit(f"원문 비레이아웃 제어코드와 다른 번역: {marker_errors[:20]}")
    if width_errors:
        for eid, line_no, pixels, line in width_errors[:20]:
            print(f"  줄폭초과 #{eid} {line_no}행 {pixels}px: 「{line}」")
        sys.exit(
            f"월드맵 퀴즈 줄 폭 규칙 위반 {len(width_errors)}줄 "
            f"(>{QUESTION_MAX_LINE_PIXELS}px)"
        )

    fixed_encoded = []
    fixed_width_errors = []
    for message in fixed_messages:
        if non_layout_markers(message["jp"]) != non_layout_markers(message["kr"]):
            sys.exit(f"{message['id']}: 원문 비레이아웃 제어코드와 다른 번역")
        lines = message["kr"].replace("{end}", "").split("{nl}")
        if len(lines) > 2:
            sys.exit(f"{message['id']}: {len(lines)}줄 > 고정 메시지 상한 2줄")
        for line_no, line in enumerate(lines, 1):
            pixels = line_pixels(line, char2idx, rom)
            if pixels > FIXED_MAX_LINE_PIXELS:
                fixed_width_errors.append(
                    (message["id"], line_no, pixels, line)
                )
        try:
            encoded_message = encode(to_tokens(message["kr"], char2idx))
        except (KeyError, ValueError) as ex:
            sys.exit(f"{message['id']} {message['addr']}: {ex}")
        if len(encoded_message) >= 256:
            sys.exit(
                f"{message['id']} {message['addr']}: "
                f"WRAM 256B 복사 상한 초과 ({len(encoded_message)}B)"
            )
        fixed_encoded.append(encoded_message)
    if fixed_width_errors:
        for message_id, line_no, pixels, line in fixed_width_errors:
            print(f"  줄폭초과 {message_id} {line_no}행 {pixels}px: 「{line}」")
        sys.exit(
            f"퀴즈 고정 메시지 줄 폭 규칙 위반 {len(fixed_width_errors)}줄 "
            f"(>{FIXED_MAX_LINE_PIXELS}px)"
        )

    used = sum(len(b) for b in encoded) + sum(len(b) for b in fixed_encoded)
    cap = RELOC_END - RELOC_ADDR
    if used > cap:
        sys.exit(f"월드맵 재배치 공간 부족: {used} > {cap}B")
    reloc_off = foff(BANK, RELOC_ADDR)
    occupied = [i for i, b in enumerate(rom[reloc_off:reloc_off + used]) if b != 0xFF]
    if occupied:
        first = RELOC_ADDR + occupied[0]
        sys.exit(f"월드맵 재배치 영역이 비어 있지 않음: $C6:{first:04X}")

    cur = RELOC_ADDR
    locations = []
    fixed_locations = []
    cluster_bytes = Counter()
    for i, (e, b) in enumerate(zip(entries, encoded)):
        off = foff(BANK, cur)
        rom[off:off + len(b)] = b
        struct.pack_into("<H", rom, pt_off + i * 2, cur)
        locations.append(cur)
        cluster_bytes[e["cluster"]] += len(b)
        cur += len(b)
    for message, encoded_message in zip(
        fixed_messages, fixed_encoded, strict=True
    ):
        off = foff(BANK, cur)
        rom[off:off + len(encoded_message)] = encoded_message
        pointer = cur.to_bytes(2, "little") + bytes((BANK,))
        for pointer_field in message["pointer_fields"]:
            pointer_addr = int(pointer_field.split(":")[1], 16)
            pointer_off = foff(BANK, pointer_addr)
            rom[pointer_off:pointer_off + 3] = pointer
        fixed_locations.append(cur)
        cluster_bytes["fixed_ui"] += len(encoded_message)
        cur += len(encoded_message)

    # 삽입 위치에서 종료자까지 역디코드한 결과가 kr과 정확히 같아야 한다.
    verified = 0
    for e, addr, expected in zip(entries, locations, encoded):
        off = foff(BANK, addr)
        got = bytes(rom[off:off + len(expected)])
        if got != expected:
            sys.exit(f"#{e['entry_id']} ${BANK:02X}:{addr:04X}: 기록 바이트 불일치")
        text = render(decode(got), idx2char)
        exp = e["kr"] if e["kr"].endswith("{end}") else e["kr"] + "{end}"
        if text != exp:
            sys.exit(f"#{e['entry_id']} ${BANK:02X}:{addr:04X}: 역디코드 불일치\n{text!r}\n{exp!r}")
        if struct.unpack_from("<H", rom, pt_off + e["entry_id"] * 2)[0] != addr:
            sys.exit(f"#{e['entry_id']}: 포인터 역검증 실패")
        verified += 1

    fixed_verified = 0
    for message, addr, expected in zip(
        fixed_messages, fixed_locations, fixed_encoded, strict=True
    ):
        off = foff(BANK, addr)
        got = bytes(rom[off:off + len(expected)])
        if got != expected:
            sys.exit(
                f"{message['id']} ${BANK:02X}:{addr:04X}: 기록 바이트 불일치"
            )
        text = render(decode(got), idx2char)
        expected_text = (
            message["kr"]
            if message["kr"].endswith("{end}")
            else message["kr"] + "{end}"
        )
        if text != expected_text:
            sys.exit(
                f"{message['id']} ${BANK:02X}:{addr:04X}: "
                f"역디코드 불일치\n{text!r}\n{expected_text!r}"
            )
        expected_pointer = addr.to_bytes(2, "little") + bytes((BANK,))
        for pointer_field in message["pointer_fields"]:
            pointer_addr = int(pointer_field.split(":")[1], 16)
            pointer_off = foff(BANK, pointer_addr)
            if rom[pointer_off:pointer_off + 3] != expected_pointer:
                sys.exit(f"{message['id']}: 포인터 역검증 실패 {pointer_field}")
        fixed_verified += 1

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    open(args.out, "wb").write(rom)
    print("=== 월드맵 퀴즈 재삽입 ===")
    print(f"  문자열 {len(entries)} / 문항 {len(entries)//5} "
          f"(산수 40 + 정보 30)")
    print(f"  재배치 $C6:{RELOC_ADDR:04X}..${cur - 1:04X} "
          f"{used}/{cap}B")
    for name in ("math_add_sub", "math_mul_div", "lore_quiz"):
        print(f"    {name:14s} {cluster_bytes[name]}B")
    print(f"    {'fixed_ui':14s} {cluster_bytes['fixed_ui']}B")
    print(f"  포인터 350/350 + 역디코드 {verified}/{len(entries)} OK")
    print(
        f"  고정 UI 24-bit 포인터·역디코드 "
        f"{fixed_verified}/{len(fixed_messages)} OK"
    )
    print(
        f"  실측 줄 폭: 문항·선택지 ≤{QUESTION_MAX_LINE_PIXELS}px, "
        f"고정 메시지 ≤{FIXED_MAX_LINE_PIXELS}px"
    )
    print(f"  -> {args.out}")


if __name__ == "__main__":
    main()
