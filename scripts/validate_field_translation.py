#!/usr/bin/env python3
"""필드/NPC 번역 원장의 비인코딩 품질 게이트.

글리프 배정 전에도 제어마커, 줄 수, 줄폭, full/삽입문 분리 규칙을 검사한다.
바이트 상한은 필드 글리프를 배정한 뒤 build_field.py가 별도로 검사한다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


PATH = Path("assets/translations/field_kr.json")
CTRL = re.compile(r"\{[^}]*\}")
HALF_PUNCT = re.compile(r"[!?~]")


def width(line: str) -> float:
    line = CTRL.sub("", line)
    return sum(0.5 if ch == " " else 1 for ch in line)


def main() -> None:
    data = json.loads(PATH.read_text(encoding="utf-8"))
    bad = []
    translated = shortened = 0
    for entry in data["entries"]:
        full = entry.get("text_kr_full", "")
        fitted = entry.get("text_kr", "")
        if not full and not fitted:
            continue
        translated += 1
        if not full or not fitted:
            bad.append((entry["id"], "full/삽입문 한쪽만 존재"))
            continue
        if fitted != full:
            shortened += 1
        expected = entry["controls"]
        for label, text in (("full", full), ("text_kr", fitted)):
            if CTRL.findall(text) != expected:
                bad.append((entry["id"], f"{label} 제어마커 순서 불일치"))
            if text.count("\n") > entry["text_jp"].count("\n"):
                bad.append((entry["id"], f"{label} 원문보다 줄 수 증가"))
            if HALF_PUNCT.search(CTRL.sub("", text)):
                bad.append((entry["id"], f"{label} 반각 !/?/~ 사용"))
            for line_no, line in enumerate(text.splitlines(), 1):
                if width(line) > 16:
                    bad.append(
                        (entry["id"], f"{label} {line_no}행 폭 {width(line):g}>16")
                    )

    print(
        f"필드 번역 게이트: 번역 {translated}/{len(data['entries'])}, "
        f"축약 {shortened}, 오류 {len(bad)}"
    )
    if bad:
        for item in bad[:30]:
            print("  ", item)
        raise SystemExit("필드 번역 비인코딩 게이트 실패")


if __name__ == "__main__":
    main()
