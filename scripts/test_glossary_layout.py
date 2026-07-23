#!/usr/bin/env python3
"""용어집 미쿠니 치이코 소개문 배치 회귀 검사.

scene 0x21의 첫 설명줄은 실기에서 오른쪽 테두리를 넘었다. 번역 내용과
인코딩 길이는 유지하면서 기존 반각공백 1바이트를 개행 1바이트로 바꾼
배치가 번역 원장과 최종 ROM 양쪽에 남아 있는지 검증한다.
"""

import json
import re
import sys

sys.path.insert(0, "scripts")
from adv_codec import DICT_SNES, decompress_scene, foff, scene_src
from adv_scene import render, walk
from build_adv import encode_text


SCENE_ID = 0x21
RUN_AT = 5
WIDTH_BASE = 0x0A9137
BROKEN_LINE = "『토우키치 여동생이자 레츠 광팬"
FIXED_FIRST = "『토우키치 여동생이자"
FIXED_SECOND = "레츠 광팬"
FIXED_FRAGMENT = FIXED_FIRST + "\n" + FIXED_SECOND + "{wait}"
CTRL = re.compile(r"\{[^}]*\}")


def fail(message):
    raise SystemExit("용어집 치이코 배치 검증 실패: " + message)


def line_width(line, char2idx, rom):
    visible = CTRL.sub("", line)
    try:
        return sum(rom[WIDTH_BASE + char2idx[ch]] for ch in visible)
    except KeyError as exc:
        fail(f"글리프 매핑 없음: {exc.args[0]!r}")


def main():
    kr_path = "assets/translations/adventure_kr.json"
    glyph_path = "out/glyph_map.json"
    rom_path = "out/wgp2_kr.smc"

    catalog = json.load(open(kr_path, encoding="utf-8"))
    matches = [
        run
        for scene in catalog["scenes"]
        if scene["scene"] == SCENE_ID
        for run in scene["runs"]
        if run["at"] == RUN_AT
    ]
    if len(matches) != 1:
        fail(f"scene 0x{SCENE_ID:02X} @0x{RUN_AT:04X} 엔트리 {len(matches)}개")
    entry = matches[0]
    text = entry["text_kr"]
    if BROKEN_LINE in text:
        fail("테두리를 넘던 한 줄 배치가 다시 들어옴")
    if FIXED_FRAGMENT not in text:
        fail("승인 개행 배치가 번역 원장에 없음")

    glyph = json.load(open(glyph_path, encoding="utf-8"))
    char2idx = glyph["char2idx"]
    rom = open(rom_path, "rb").read()
    if len(rom) != 0x200000:
        fail(f"최종 ROM 크기 {len(rom)}")

    broken_text = text.replace(FIXED_FRAGMENT, BROKEN_LINE + "{wait}", 1)
    fixed_encoded = encode_text(text, char2idx, "glossary scene 0x21")
    broken_encoded = encode_text(broken_text, char2idx, "glossary scene 0x21 baseline")
    if len(fixed_encoded) != len(broken_encoded):
        fail(f"개행 전후 인코딩 길이 변화 {len(broken_encoded)}→{len(fixed_encoded)}")

    broken_width = line_width(BROKEN_LINE, char2idx, rom)
    first_width = line_width(FIXED_FIRST, char2idx, rom)
    second_width = line_width(FIXED_SECOND, char2idx, rom)
    if max(first_width, second_width) >= broken_width:
        fail(
            f"개행 뒤 최대폭 {max(first_width, second_width)}px >= 이전 {broken_width}px"
        )

    bank, addr = scene_src(rom, SCENE_ID)
    script, _, _ = decompress_scene(rom, bank, addr, foff(*DICT_SNES))
    runs, stats, _ = walk(script)
    if stats["desync"]:
        fail("최종 ROM 씬 워크 desync")
    built = next((run for run in runs if run["at"] == RUN_AT), None)
    if built is None:
        fail("최종 ROM에서 대상 런을 찾지 못함")
    rendered = render(built["text"], {idx: ch for ch, idx in char2idx.items()})
    if FIXED_FRAGMENT not in rendered:
        fail("최종 ROM 역렌더에 승인 개행 배치가 없음")

    print(
        "용어집 치이코 소개: PASS "
        f"{broken_width}px → {first_width}px/{second_width}px, "
        f"인코딩 {len(fixed_encoded) + 1}B(종료자 포함) 위치보존"
    )


if __name__ == "__main__":
    main()
