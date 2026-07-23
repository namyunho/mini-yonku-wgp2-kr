#!/usr/bin/env python3
"""월드맵 퀴즈 70문항·고정 UI·정답 판정의 최종 ROM 회귀 검사."""

from __future__ import annotations

import json
import operator
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_worldmap import (  # noqa: E402
    BANK,
    FIXED_MAX_LINE_PIXELS,
    GLYPH_MAP,
    PTR_ADDR,
    PTR_COUNT,
    QUESTION_MAX_LINE_PIXELS,
    WIDTH_BASE,
    foff,
    line_pixels,
    to_tokens,
)
from decode_script import decode, encode, render  # noqa: E402


ORIGINAL = ROOT / "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
BUILT = ROOT / "out/wgp2_kr.smc"
DATA = ROOT / "assets/translations/worldmap_text.json"
MENU4_MAP = ROOT / "out/menu4_reclean_glyph_map.json"

CHOICE_INIT_SIGNATURE = bytes.fromhex(
    "A9 01 02 8D E3 73 A9 03 04 8D E5 73"
)
ANSWER_CHECK_SIGNATURE = bytes.fromhex(
    "AE D2 73 BD E3 73 29 FF 00 3A F0 21"
)
STATUS_EXPECTED_PREFIX = bytes.fromhex(
    "FF 1B 1E FF FF FF FF FF FF FF 2F 01 FF FF FF 9A"
)
THREE_MONKEYS_EXPECTED = (
    ("言わザル{end}", "입 막은 원숭이{end}", "입 막은{end}"),
    ("聞かザル{end}", "귀 막은 원숭이{end}", "귀 막은{end}"),
    ("見ザル{end}", "눈 가린 원숭이{end}", "눈 가린{end}"),
    ("三国藤吉{end}", "미쿠니 토우키치{end}", "토우키치{end}"),
)
LORE_TERMINOLOGY_EXPECTED = {
    205: (
        "レース場の開店記念Tシャツを{nl}いつも着ている子は？{end}",
        "레이스장 개장 기념 티셔츠를{nl}늘 입는 아이는？{end}",
        "레이스장 개장 기념{nl}티셔츠를 늘 입는 아이는？{end}",
    ),
    225: (
        "光蝦のリーチとポンの{nl}見分け方は？{end}",
        "공키의 리치와 폰을{nl}구별하는 특징은？{end}",
        "공키의 리치와 폰을{nl}구별하는 특징은？{end}",
    ),
    251: ("ゾーラ{end}", "졸라{end}", "졸라{end}"),
    271: ("肉まん{end}", "고기만두{end}", "고기만두{end}"),
    311: ("ハダカおどり{end}", "알몸춤{end}", "알몸춤{end}"),
}


def visible(text: str) -> str:
    return text.replace("{end}", "").replace("{nl}", "\n")


def verify_math_answer(question: str, answer: str) -> None:
    expression = visible(question).replace("＝", "")
    answer_value = int(visible(answer))
    operations = {
        "＋": operator.add,
        "－": operator.sub,
        "×": operator.mul,
        "÷": operator.floordiv,
    }
    for symbol, operation in operations.items():
        if symbol in expression:
            left, right = map(int, expression.split(symbol, 1))
            result = operation(left, right)
            if answer_value != result:
                raise SystemExit(
                    f"산수 정답 불일치: {expression} → {answer_value} != {result}"
                )
            return
    raise SystemExit(f"산수 연산자를 찾지 못함: {expression}")


def main() -> None:
    original = ORIGINAL.read_bytes()
    built = BUILT.read_bytes()
    data = json.loads(DATA.read_text(encoding="utf-8"))
    glyph_data = json.loads((ROOT / GLYPH_MAP).read_text(encoding="utf-8"))
    char2idx = {char: int(index) for char, index in glyph_data["char2idx"].items()}
    idx2char = {index: char for char, index in char2idx.items()}
    entries = data["entries"]
    fixed_messages = data["fixed_messages"]

    if len(original) != 0x200000 or len(built) != len(original):
        raise SystemExit("원본/빌드 ROM은 같은 헤더리스 2MB여야 함")
    if len(entries) != PTR_COUNT or len(fixed_messages) != 7:
        raise SystemExit("퀴즈 DB 350개·고정 메시지 7개가 아님")

    question_count = 0
    answer_count = 0
    pointer_offset = foff(BANK, PTR_ADDR)
    for question_base in range(0, PTR_COUNT, 5):
        group = entries[question_base:question_base + 5]
        if [row["role"] for row in group] != [
            "question", "choice_1", "choice_2", "choice_3", "choice_4"
        ]:
            raise SystemExit(f"문항 {question_base // 5}: 1+4 구조 불일치")
        question_count += 1
        answer_count += 1
        if group[0]["cluster"].startswith("math_"):
            verify_math_answer(group[0]["kr"], group[1]["kr"])

    monkey_group = entries[320:325]
    if monkey_group[0]["jp"] != "三国家前にある石像の{nl}真ん中はなに？{end}":
        raise SystemExit("세 원숭이 문항 원문 불일치")
    actual_monkeys = tuple(
        (entry["jp"], entry["kr_full"], entry["kr"])
        for entry in monkey_group[1:]
    )
    if actual_monkeys != THREE_MONKEYS_EXPECTED:
        raise SystemExit(
            f"세 원숭이 선택지 원문/완역/삽입본 불일치: {actual_monkeys!r}"
        )
    for entry_id, expected in LORE_TERMINOLOGY_EXPECTED.items():
        entry = entries[entry_id]
        actual = (entry["jp"], entry["kr_full"], entry["kr"])
        if actual != expected:
            raise SystemExit(
                f"정보 퀴즈 용어 #{entry_id} 원문/완역/삽입본 불일치: "
                f"{actual!r} != {expected!r}"
            )

    for entry in entries:
        pointer = int.from_bytes(
            built[
                pointer_offset + entry["entry_id"] * 2:
                pointer_offset + entry["entry_id"] * 2 + 2
            ],
            "little",
        )
        encoded = encode(to_tokens(entry["kr"], char2idx))
        got = built[foff(BANK, pointer):foff(BANK, pointer) + len(encoded)]
        if got != encoded or render(decode(got), idx2char) != entry["kr"]:
            raise SystemExit(f"#{entry['entry_id']}: 최종 ROM 문자열/역디코드 불일치")
        lines = visible(entry["kr"]).splitlines()
        max_lines = 2 if entry["role"] == "question" else 1
        if len(lines) > max_lines:
            raise SystemExit(f"#{entry['entry_id']}: 줄 수 {len(lines)}>{max_lines}")
        for line in lines:
            width = line_pixels(line, char2idx, built)
            if width > QUESTION_MAX_LINE_PIXELS:
                raise SystemExit(
                    f"#{entry['entry_id']}: {width}px>{QUESTION_MAX_LINE_PIXELS}px"
                )

    for message in fixed_messages:
        encoded = encode(to_tokens(message["kr"], char2idx))
        pointer_values = set()
        for pointer_field in message["pointer_fields"]:
            pointer_addr = int(pointer_field.split(":")[1], 16)
            raw_pointer = built[
                foff(BANK, pointer_addr):foff(BANK, pointer_addr) + 3
            ]
            if raw_pointer[2] != BANK:
                raise SystemExit(f"{message['id']}: 포인터 뱅크 불일치")
            pointer_values.add(int.from_bytes(raw_pointer[:2], "little"))
        if len(pointer_values) != 1:
            raise SystemExit(f"{message['id']}: 공유 포인터 목적지가 서로 다름")
        pointer = pointer_values.pop()
        got = built[foff(BANK, pointer):foff(BANK, pointer) + len(encoded)]
        if got != encoded or render(decode(got), idx2char) != message["kr"]:
            raise SystemExit(f"{message['id']}: 최종 ROM 문자열/역디코드 불일치")
        for line in visible(message["kr"]).splitlines():
            width = line_pixels(line, char2idx, built)
            if width > FIXED_MAX_LINE_PIXELS:
                raise SystemExit(
                    f"{message['id']}: {width}px>{FIXED_MAX_LINE_PIXELS}px"
                )

    # $C0:8E6D가 [1,2,3,4]를 만든 뒤 셔플하고, $C0:8F39가 선택값을
    # DEC/BEQ로 검사한다. 따라서 화면 버튼 위치와 무관하게 원본 choice_1이 정답이다.
    if original[0x008E6D:0x008E6D + len(CHOICE_INIT_SIGNATURE)] != (
        CHOICE_INIT_SIGNATURE
    ):
        raise SystemExit("선택지 초기값 [1,2,3,4] 코드 시그니처 불일치")
    if original[0x008F39:0x008F39 + len(ANSWER_CHECK_SIGNATURE)] != (
        ANSWER_CHECK_SIGNATURE
    ):
        raise SystemExit("정답 판정 DEC/BEQ 코드 시그니처 불일치")

    status_addr = int(data["status_line"]["file_offset"], 16)
    status = built[status_addr:status_addr + len(bytes.fromhex(data["status_line"]["raw_hex"]))]
    if status[:len(STATUS_EXPECTED_PREFIX)] != STATUS_EXPECTED_PREFIX:
        raise SystemExit("퀴즈 상태줄 `문제/시간` 직접 타일 패치 불일치")
    menu4 = json.loads(MENU4_MAP.read_text(encoding="utf-8"))
    if menu4["font_resources"]["world_tutorial_setting"]["char_to_tile"]["회"] != "69":
        raise SystemExit("월드맵 소형폰트 `회` 타일 매핑 회귀")
    if menu4["font_resources"]["world_tutorial_setting"]["char_to_tile"]["시"] != "2F":
        raise SystemExit("월드맵 소형폰트 `시` 타일 매핑 회귀")
    if menu4["font_resources"]["world_tutorial_setting"]["char_to_tile"]["간"] != "01":
        raise SystemExit("월드맵 소형폰트 `간` 타일 매핑 회귀")
    if menu4["font_resources"]["world_tutorial_setting"]["char_to_tile"]["문"] != "1B":
        raise SystemExit("월드맵 소형폰트 `문` 타일 매핑 회귀")
    if menu4["font_resources"]["world_tutorial_setting"]["char_to_tile"]["제"] != "1E":
        raise SystemExit("월드맵 소형폰트 `제` 타일 매핑 회귀")

    adapted_entries = sum(bool(entry["abbreviated"]) for entry in entries)
    adapted_fixed = sum(bool(message["abbreviated"]) for message in fixed_messages)
    print("=== 월드맵 퀴즈 최종 회귀 ===")
    print(f"  문항 {question_count}/70, 정답 {answer_count}/70(choice_1) OK")
    print(f"  문자열 {len(entries)}/350 + 고정 UI {len(fixed_messages)}/7 OK")
    print(
        f"  줄 폭 ≤{QUESTION_MAX_LINE_PIXELS}px / "
        f"고정 UI ≤{FIXED_MAX_LINE_PIXELS}px OK"
    )
    print(f"  표시 조정 원장: 문항 {adapted_entries} + 고정 UI {adapted_fixed}")
    print("  상태줄 동적 숫자 보존 + `문제/시간` 타일 패치 OK")


if __name__ == "__main__":
    main()
