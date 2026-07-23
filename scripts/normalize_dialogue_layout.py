#!/usr/bin/env python3
"""전체 대사에서 고립된 짧은 줄과 비기능성 선행 공백을 안전하게 정리한다.

대상:
  - 정적 대사 dialogue.json: 한 줄 13단위
  - 어드벤처 adventure_kr.json: 한 줄 16단위
  - 필드/NPC field_kr.json: 한 줄 16단위

판정:
  - 합친 줄이 소비 경로별 폭 한도 안에 있고 한쪽이 3단위 이하인 경계만 후보
  - {wait}/{clear}/{cN} 뒤, 선택지, 화자명·대진표·의도적 2행 표기는 보존
  - 개행 1바이트를 반각 공백 1바이트로 바꾸므로 위치보존 런 길이는 불변
  - 여는 괄호·말줄임표·접미사 앞은 공백 없이 개행만 제거
  - 원문과 완역은 보존하고 실제 삽입문만 바꾼다

사용:
  python3 scripts/normalize_dialogue_layout.py --write
  python3 scripts/normalize_dialogue_layout.py --check
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRANS = ROOT / "assets" / "translations"
DIALOGUE_PATH = TRANS / "dialogue.json"
ADVENTURE_PATH = TRANS / "adventure_kr.json"
FIELD_PATH = TRANS / "field_kr.json"
SHORTENING_PATH = TRANS / "shortening_ledger.json"
LAYOUT_LEDGER_PATH = TRANS / "dialogue_layout_ledger.json"

CTRL = re.compile(r"\{[^}]*\}")
LEADING = re.compile(r"(^|\n)[ 　]+(?=\S)")
TERMINAL = set("!?！？。.…〜♥♪」』）")
OPENERS = set("「『（【〈《")
EXPECTED_COUNTS = {"dialogue": 6, "adventure": 142, "field": 83}
EXPECTED_CHOICE_COUNTS = {
    "adventure": (19, 45),
    "field": (27, 57),
}

# A8:0223은 결혼반지 탐색 장면에서 화자명이 앞 런에 있는 연속 대사다.
# 일반 16단위 검사는 통과했지만 실기에서 오른쪽 테두리를 넘었다. 개행을
# 옮긴 수정본의 최대 12.5단위를 기준으로 13단위 상한을 별도 고정한다.
# 75:0410은 제8전 카이전 뒤 츠치야 브리핑 분기다. 14단위였던 한 행이
# 초상화 뒤 본문 영역을 넘은 실측에 따라 개행을 옮겼고, 수정본의 최대
# 13.5단위를 회귀 상한으로 고정한다.
ADVENTURE_LINE_LIMIT_OVERRIDES = {
    "75:0410": 13.5,
    "A8:0223": 13,
}

# 튜토리얼의 괄호 안내문은 중앙 정렬된 별도 UI다.
DIALOGUE_LEADING_EXCEPTIONS = {
    444, 445, 446, 447, 455, 456, 457, 460, 463, 467, 468,
    471, 472, 473, 474, 477, 480, 481, 482, 483, 484,
}

# 팀·선수 소개, 화자 전환, 대진표처럼 짧아도 2행 자체가 의미인 경계.
DIALOGUE_KEEP_IDS = {
    148, 153, 159, 160, 161, 162, 163, 164, 170, 171, 172,
    174, 175, 176, 177, 178, 179, 180, 181, 182, 183, 184,
    185, 186, 187, 188, 189, 190, 192, 193, 194, 195, 196,
    197, 198,
}

ADVENTURE_KEEP = {
    ("56:009B", "중학생들 사이에도 유행이", "듯해요"),
    ("7B:026F", "배짱이잖아", "너희들"),
    ("7E:02B5", "엔션트 포스와", "우리가"),
    ("7E:0366", "료", "예전에 라한테 도전받았을 때"),
    ("A4:0130", "편지", "세이바 고 님께"),
    ("AE:035E", "료", "이 산 코스를 2바퀴"),
    ("AE:0385", "「오프로드인가요", "좋네요"),
    ("AE:0385", "좋네요", "지지 않을 거예요"),
    ("B8:005D", "료", "아침 갓 잡은"),
    ("C5:0475", "순진하고 착한 아이죠", "제이는"),
    ("C9:01C2", "그 힘을 내", "거예요"),
    ("E7:0045", "챔피언", "우리 TRF 빅토리즈다！"),
    ("E9:0027", "TRF 빅토리즈", "대"),
    ("E9:0027", "대", "NA 아스트로 레인저스다！"),
    ("EA:0045", "TRF 빅토리즈", "대"),
    ("EA:0045", "대", "사반나 솔져스다！"),
    ("EF:0174", "흔들릴 만큼", "않아！"),
    ("F4:017A", "무슨 얘긴가 했더니", "프랑스"),
}

FIELD_KEEP = {
    ("F0132", "너희를 꺾는 건", "우리"),
    ("F0308", "WGP에선 온힘을다해", "응원해"),
    ("F0310", "「WGP에선 온 힘을 다해", "응원해"),
    ("F0757", "괜찮아", "내 연인은미니사구니까"),
    ("F0859", "고마워", "좋은 데이터를 얻었어"),
    ("F0951", "그래도 다시 힘내면 된다", "정말로"),
    ("F1155", "갔는데", "아직 완성되지 않았대"),
    ("F1195", "찾아낸", "최신 정보인데！"),
    ("F1218", "마키에게 부탁하면", "될지도"),
    ("F1310", "「내일 준과 응원하러 갈게", "힘내"),
}

# 이 경계는 한국어 띄어쓰기가 아니라 괄호/말줄임표/접미사 결합이다.
NO_SPACE = {
    ("adventure", "9C:0227", "「", "준한테 부탁해도 소용없잖아！"),
    ("adventure", "AB:026B", "「", "시끄러운 녀석이야"),
    ("adventure", "C5:0309", "아까 그 오일 말인데요", "…"),
    ("adventure", "C5:0421", "심술은 그쯤 해두시죠", "…"),
    ("adventure", "CE:0243", "「", "늘 하는 심부름이지요"),
    ("adventure", "D2:02C6", "달린단 생각은 안 들지요", "만…"),
    ("adventure", "EE:0045", "오늘", "이곳 캐슬 스타디움에서"),
}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )


def visible(text: str) -> str:
    return CTRL.sub("", text).strip(" 　")


def line_units(text: str) -> float:
    text = CTRL.sub("", text)
    return sum(0.5 if char == " " else 1.0 for char in text)


def is_candidate(left: str, right: str, limit: int) -> bool:
    left_visible = CTRL.sub("", left).rstrip()
    right_visible = CTRL.sub("", right).lstrip(" 　")
    if not left_visible or not right_visible:
        return False
    if right_visible[0] in OPENERS or left_visible[-1] in TERMINAL:
        return False
    if re.search(r"\{[^}]*\}\s*$", left) or right.startswith("{"):
        return False
    combined = left_visible + " " + right_visible
    return (
        line_units(combined) <= limit
        and min(line_units(left_visible), line_units(right_visible)) <= 3
    )


def normalize_text(
    text: str,
    separator: str,
    limit: int,
    system: str,
    key: str,
    keep: set[tuple[str, str, str]],
) -> tuple[str, int]:
    """고립 줄이 더 생기지 않을 때까지 왼쪽부터 안전 경계를 합친다."""
    total = 0
    while True:
        lines = text.split(separator)
        output = [lines[0]]
        changed = 0
        for right in lines[1:]:
            left = output[-1]
            pair = (key, visible(left), visible(right))
            if is_candidate(left, right, limit) and pair not in keep:
                signature = (system, key, visible(left), visible(right))
                joiner = "" if signature in NO_SPACE else " "
                if joiner:
                    left = left.rstrip(" 　")
                    right = right.lstrip(" 　")
                output[-1] = left + joiner + right
                changed += 1
            else:
                output.append(right)
        text = separator.join(output)
        total += changed
        if not changed:
            return text, total


def signatures_equal(before: str, after: str) -> bool:
    """개행·공백 외 가시문자와 비개행 제어 토큰이 같은지 확인한다."""
    before_tokens = [token for token in CTRL.findall(before) if token != "{nl}"]
    after_tokens = [token for token in CTRL.findall(after) if token != "{nl}"]
    before_visible = CTRL.sub("", before).replace("\n", "")
    after_visible = CTRL.sub("", after).replace("\n", "")
    for blank in (" ", "　"):
        before_visible = before_visible.replace(blank, "")
        after_visible = after_visible.replace(blank, "")
    return before_tokens == after_tokens and before_visible == after_visible


def layout_entry(
    system: str,
    key: str,
    before: str,
    after: str,
    full: str,
    joined: int,
    leading_removed: int,
) -> dict:
    item = {
        "id": f"{system}:{key}",
        "system": system,
        "before_kr": before,
        "after_kr": after,
        "text_kr_full": full,
        "joined_line_breaks": joined,
        "leading_spaces_removed": leading_removed,
        "reason": "고립된 짧은 줄 정리 및 비기능성 선행 공백 제거",
        "status": "done",
        "date": "2026-07-23",
    }
    if system == "dialogue":
        item["entry_id"] = int(key)
    elif system == "adventure":
        scene, at = key.split(":")
        item["scene"] = int(scene, 16)
        item["at"] = int(at, 16)
    else:
        item["entry_id"] = key
    return item


def current_by_layout_id(
    dialogue: dict, adventure: dict, field: dict,
) -> dict[str, tuple[str, str]]:
    result = {}
    for entry in dialogue["entries"]:
        key = f"dialogue:{entry['entry_id']}"
        result[key] = (entry.get("text_kr_full", entry["text_kr"]), entry["text_kr"])
    for scene in adventure["scenes"]:
        for run in scene["runs"]:
            key = f"adventure:{scene['scene']:02X}:{run['at']:04X}"
            result[key] = (run.get("text_kr_full", run["text_kr"]), run["text_kr"])
    for entry in field["entries"]:
        key = f"field:{entry['id']}"
        result[key] = (entry["text_kr_full"], entry["text_kr"])
    return result


def assert_widths(dialogue: dict, adventure: dict, field: dict) -> None:
    for entry in dialogue["entries"]:
        for line in entry["text_kr"].split("{nl}"):
            if line_units(line) > 13:
                raise SystemExit(
                    f"정적 대사 #{entry['entry_id']} 줄 폭 {line_units(line)}>13: {line!r}"
                )
    for scene in adventure["scenes"]:
        for run in scene["runs"]:
            key = f"{scene['scene']:02X}:{run['at']:04X}"
            limit = ADVENTURE_LINE_LIMIT_OVERRIDES.get(key, 16)
            for line in run["text_kr"].split("\n"):
                if line_units(line) > limit:
                    raise SystemExit(
                        f"어드벤처 {scene['scene']:02X}:{run['at']:04X} "
                        f"줄 폭 {line_units(line)}>{limit}: {line!r}"
                    )
    for entry in field["entries"]:
        for line in entry["text_kr"].split("\n"):
            if line_units(line) > 16:
                raise SystemExit(
                    f"필드 {entry['id']} 줄 폭 {line_units(line)}>16: {line!r}"
                )


def choice_option_lines(text: str, where: str) -> list[str]:
    if "{c8:07}" not in text:
        return []
    if text.count("{c8:07}") != 1 or text.count("{c8:00}") != 1:
        raise SystemExit(f"{where}: 선택지 제어 마커 개수 불일치")
    body = text.split("{c8:07}", 1)[1].split("{c8:00}", 1)[0]
    options = [line for line in body.split("\n") if line]
    if not options:
        raise SystemExit(f"{where}: 선택지 본문 없음")
    return options


def assert_choice_indents(adventure: dict, field: dict) -> dict[str, tuple[int, int]]:
    """선택 커서가 첫 글자를 가리지 않도록 모든 선택지 앞 1칸 이상을 보장."""
    counts: dict[str, tuple[int, int]] = {}
    adventure_blocks = adventure_options = 0
    for scene in adventure["scenes"]:
        for run in scene["runs"]:
            key = f"어드벤처 {scene['scene']:02X}:{run['at']:04X}"
            options = choice_option_lines(run["text_kr"], key)
            if not options:
                continue
            adventure_blocks += 1
            adventure_options += len(options)
            for option in options:
                if not option.startswith((" ", "　")):
                    raise SystemExit(f"{key}: 선택지 선행 공백 0칸: {option!r}")
    counts["adventure"] = (adventure_blocks, adventure_options)

    field_blocks = field_options = 0
    for entry in field["entries"]:
        key = f"필드 {entry['id']}"
        options = choice_option_lines(entry["text_kr"], key)
        if not options:
            continue
        field_blocks += 1
        field_options += len(options)
        for option in options:
            if not option.startswith((" ", "　")):
                raise SystemExit(f"{key}: 선택지 선행 공백 0칸: {option!r}")
    counts["field"] = (field_blocks, field_options)

    if counts != EXPECTED_CHOICE_COUNTS:
        raise SystemExit(
            f"선택지 모집단 변경: {counts!r} != {EXPECTED_CHOICE_COUNTS!r}"
        )
    return counts


def assert_leading_spaces(dialogue: dict, adventure: dict, field: dict) -> None:
    for entry in dialogue["entries"]:
        normalized = entry["text_kr"].replace("{nl}", "\n")
        if (
            LEADING.search(normalized)
            and not entry["table_id"].startswith("c1_")
            and entry["entry_id"] not in DIALOGUE_LEADING_EXCEPTIONS
        ):
            raise SystemExit(f"정적 대사 #{entry['entry_id']}: 비기능성 선행 공백")
    for scene in adventure["scenes"]:
        for run in scene["runs"]:
            text = run["text_kr"]
            if "{c8:" not in text and LEADING.search(text):
                raise SystemExit(
                    f"어드벤처 {scene['scene']:02X}:{run['at']:04X}: "
                    "비기능성 선행 공백"
                )
    for entry in field["entries"]:
        text = entry["text_kr"]
        if "{c8:" not in text and LEADING.search(text):
            raise SystemExit(f"필드 {entry['id']}: 비기능성 선행 공백")


def assert_fixed_point(dialogue: dict, adventure: dict, field: dict) -> None:
    for entry in dialogue["entries"]:
        text = entry["text_kr"]
        if entry["table_id"].startswith("c1_") or LEADING.search(
            text.replace("{nl}", "\n")
        ):
            continue
        keep = set()
        if entry["entry_id"] in DIALOGUE_KEEP_IDS:
            lines = text.split("{nl}")
            keep = {
                (str(entry["entry_id"]), visible(left), visible(right))
                for left, right in zip(lines, lines[1:])
            }
        normalized, _ = normalize_text(
            text, "{nl}", 13, "dialogue", str(entry["entry_id"]), keep
        )
        if normalized != text:
            raise SystemExit(f"정적 대사 #{entry['entry_id']}: 미정리 고립 줄")

    for scene in adventure["scenes"]:
        for run in scene["runs"]:
            text = run["text_kr"]
            if not text or "{c8:" in text:
                continue
            key = f"{scene['scene']:02X}:{run['at']:04X}"
            normalized, _ = normalize_text(
                text, "\n", 16, "adventure", key, ADVENTURE_KEEP
            )
            if normalized != text:
                raise SystemExit(f"어드벤처 {key}: 미정리 고립 줄")

    for entry in field["entries"]:
        text = entry["text_kr"]
        if "{c8:" in text:
            continue
        normalized, _ = normalize_text(
            text, "\n", 16, "field", entry["id"], FIELD_KEEP
        )
        if normalized != text:
            raise SystemExit(f"필드 {entry['id']}: 미정리 고립 줄")


def check(
    dialogue: dict,
    adventure: dict,
    field: dict,
    layout_ledger: dict,
) -> None:
    counts = Counter(item["system"] for item in layout_ledger["entries"])
    if dict(counts) != EXPECTED_COUNTS:
        raise SystemExit(f"레이아웃 원장 건수 불일치: {dict(counts)}")
    if layout_ledger["entry_count"] != len(layout_ledger["entries"]):
        raise SystemExit("레이아웃 원장 entry_count 불일치")

    current = current_by_layout_id(dialogue, adventure, field)
    seen = set()
    for item in layout_ledger["entries"]:
        key = item["id"]
        if key in seen or key not in current:
            raise SystemExit(f"레이아웃 원장 중복/미존재 키: {key}")
        seen.add(key)
        full, inserted = current[key]
        if item["text_kr_full"] != full or item["after_kr"] != inserted:
            raise SystemExit(f"레이아웃 원장 현재값 불일치: {key}")
        if not signatures_equal(item["before_kr"], item["after_kr"]):
            raise SystemExit(f"레이아웃 정리 중 가시문자/제어 토큰 변경: {key}")

    assert_leading_spaces(dialogue, adventure, field)
    choice_counts = assert_choice_indents(adventure, field)
    assert_fixed_point(dialogue, adventure, field)
    assert_widths(dialogue, adventure, field)
    print(
        "전체 대사 레이아웃 PASS: "
        f"정적 {counts['dialogue']} / 어드벤처 {counts['adventure']} / "
        f"필드 {counts['field']} / 선행 공백 0(기능성 UI 제외) / "
        f"선택지 들여쓰기 어드벤처 {choice_counts['adventure'][1]}·"
        f"필드 {choice_counts['field'][1]}"
    )


def apply() -> None:
    dialogue = load(DIALOGUE_PATH)
    adventure = load(ADVENTURE_PATH)
    field = load(FIELD_PATH)
    shortening = load(SHORTENING_PATH)

    full_dialogue = {
        item["entry_id"]: item["before_kr"]
        for item in shortening["done"]
        if item["system"] == "dialogue"
    }
    full_adventure = {
        (item["scene"], item["at"]): item["before_kr"]
        for item in shortening["done"]
        if item["system"] == "adventure"
    }

    records = []

    for entry in dialogue["entries"]:
        text = entry["text_kr"]
        if entry["table_id"].startswith("c1_") or LEADING.search(
            text.replace("{nl}", "\n")
        ):
            continue
        keep = set()
        if entry["entry_id"] in DIALOGUE_KEEP_IDS:
            lines = text.split("{nl}")
            keep = {
                (str(entry["entry_id"]), visible(left), visible(right))
                for left, right in zip(lines, lines[1:])
            }
        after, joined = normalize_text(
            text, "{nl}", 13, "dialogue", str(entry["entry_id"]), keep
        )
        if after == text:
            continue
        full = full_dialogue.get(
            entry["entry_id"], entry.get("text_kr_full", text)
        )
        entry["text_kr_full"] = full
        entry["text_kr"] = after
        records.append(
            layout_entry(
                "dialogue", str(entry["entry_id"]), text, after, full, joined, 0
            )
        )

    for scene in adventure["scenes"]:
        for run in scene["runs"]:
            text = run["text_kr"]
            if not text or "{c8:" in text:
                continue
            key = f"{scene['scene']:02X}:{run['at']:04X}"
            after, joined = normalize_text(
                text, "\n", 16, "adventure", key, ADVENTURE_KEEP
            )
            leading_removed = 0
            if key == "A4:0189":
                after, leading_removed = re.subn(r"\n　(?=\S)", "\n", after)
            if after == text:
                continue
            full = full_adventure.get(
                (scene["scene"], run["at"]), run.get("text_kr_full", text)
            )
            run["text_kr_full"] = full
            run["text_kr"] = after
            records.append(
                layout_entry(
                    "adventure", key, text, after, full, joined, leading_removed
                )
            )

    for entry in field["entries"]:
        text = entry["text_kr"]
        if "{c8:" in text:
            continue
        after, joined = normalize_text(
            text, "\n", 16, "field", entry["id"], FIELD_KEEP
        )
        if after == text:
            continue
        entry["text_kr"] = after
        records.append(
            layout_entry(
                "field",
                entry["id"],
                text,
                after,
                entry["text_kr_full"],
                joined,
                0,
            )
        )

    counts = Counter(item["system"] for item in records)
    if dict(counts) != EXPECTED_COUNTS:
        if not records and LAYOUT_LEDGER_PATH.exists():
            check(dialogue, adventure, field, load(LAYOUT_LEDGER_PATH))
            return
        raise SystemExit(
            f"예상하지 않은 레이아웃 변경 범위: {dict(counts)} "
            f"!= {EXPECTED_COUNTS}"
        )

    field["_stats"]["shortened_existing"] = sum(
        entry["text_kr_full"] != entry["text_kr"]
        for entry in field["entries"]
    )
    records.sort(key=lambda item: item["id"])
    layout_ledger = {
        "schema": 1,
        "note": (
            "원문·완역은 보존하고 실제 삽입문의 불필요한 개행과 "
            "비기능성 선행 공백만 정리한 전수 감사 원장."
        ),
        "rules": {
            "dialogue_max_units": 13,
            "adventure_field_max_units": 16,
            "candidate_short_side_max_units": 3,
            "functional_choice_indent_preserved": True,
            "functional_choice_min_indent_tiles": 1,
            "non_newline_controls_preserved": True,
        },
        "entry_count": len(records),
        "entries": records,
    }

    check(dialogue, adventure, field, layout_ledger)
    write(DIALOGUE_PATH, dialogue)
    write(ADVENTURE_PATH, adventure)
    write(FIELD_PATH, field)
    write(LAYOUT_LEDGER_PATH, layout_ledger)
    print(f"레이아웃 정리 원장 생성: {LAYOUT_LEDGER_PATH.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.write:
        apply()
        return
    check(
        load(DIALOGUE_PATH),
        load(ADVENTURE_PATH),
        load(FIELD_PATH),
        load(LAYOUT_LEDGER_PATH),
    )


if __name__ == "__main__":
    main()
