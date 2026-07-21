#!/usr/bin/env python3
"""스테이지 1~10 제목 추출물의 원본 ROM/포인터/인코딩 회귀 테스트."""
import argparse
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))
from decode_script import decode, encode, load_tbl, render

ROM_PATH = "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
JSON_PATH = "assets/translations/stage_titles.json"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--built-rom", help="최종 빌드 ROM의 한글 제목 10개도 역검증")
    parser.add_argument("--glyph-map", default="out/glyph_map.json")
    args = parser.parse_args()

    rom = open(ROM_PATH, "rb").read()
    data = json.load(open(JSON_PATH, encoding="utf-8"))
    entries = data["entries"]
    tbl = load_tbl("assets/translation_guide/glyph_table.tsv")
    failures = []
    if len(entries) != 10 or [x["stage"] for x in entries] != list(range(1, 11)):
        failures.append("엔트리가 stage 1..10 순서의 10개가 아님")

    pointer = data["pointer_table"]
    pointer_off = int(pointer["file_offset"], 16)
    previous_end = None
    for i, entry in enumerate(entries):
        raw = bytes.fromhex(entry["raw_hex"])
        off = int(entry["file_offset"], 16)
        addr = int(entry["addr"].split(":")[1], 16)
        if len(raw) != entry["n_bytes"]:
            failures.append(f"stage {entry['stage']}: raw 길이 != n_bytes")
        if rom[off:off + len(raw)] != raw:
            failures.append(f"stage {entry['stage']}: raw != ROM")
        if struct.unpack_from("<H", rom, pointer_off + i * 2)[0] != addr:
            failures.append(f"stage {entry['stage']}: 원본 포인터 != addr")
        if previous_end is not None and off != previous_end:
            failures.append(f"stage {entry['stage']}: 원본 문자열 영역이 연속하지 않음")
        previous_end = off + len(raw)
        tokens = decode(raw)
        if render(tokens, tbl) != entry["text_jp"]:
            failures.append(f"stage {entry['stage']}: raw 디코드 != text_jp")
        if encode(tokens) != raw:
            failures.append(f"stage {entry['stage']}: encode(decode(raw)) != raw")

    print(f"스테이지 제목 {len(entries)}개")
    print(f"  raw==ROM / pointer / decode+encode: {'OK' if not failures else 'FAIL'}")
    if args.built_rom:
        built = open(args.built_rom, "rb").read()
        glyph_map = json.load(open(args.glyph_map, encoding="utf-8"))["char2idx"]
        idx2char = {index: char for char, index in glyph_map.items()}
        built_failures = []
        for i, entry in enumerate(entries):
            addr = struct.unpack_from("<H", built, pointer_off + i * 2)[0]
            off = addr  # bank $C0의 HiROM file offset은 16-bit addr와 동일
            end = off
            while end < len(built):
                byte = built[end]
                end += 2 if 1 <= byte <= 4 or byte == 7 else 1
                if byte == 0:
                    break
            got = render(decode(built[off:end]), idx2char)
            expected = entry["text_kr"]
            if not expected.endswith("{end}"):
                expected += "{end}"
            if got != expected:
                built_failures.append(f"stage {entry['stage']}: {got!r} != {expected!r}")
        failures.extend(built_failures)
        print(f"  최종 ROM 한글 역검증: "
              f"{'OK 10/10' if not built_failures else f'FAIL {len(built_failures)}건'}")
    if failures:
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("결과: ✅ PASS: stage title source is lossless")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
