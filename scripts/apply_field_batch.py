#!/usr/bin/env python3
"""표준입력의 ID<TAB>번역 묶음을 필드 번역 원장에 안전하게 반영한다."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


PATH = Path("assets/translations/field_kr.json")
CTRL = re.compile(r"\{[^}]*\}")


def main() -> None:
    updates: dict[str, str] = {}
    for line_no, raw in enumerate(sys.stdin, 1):
        raw = raw.rstrip("\n")
        if not raw or raw.startswith("#"):
            continue
        try:
            entry_id, encoded = raw.split("\t", 1)
        except ValueError as exc:
            raise SystemExit(f"{line_no}행: ID와 번역을 탭으로 구분해야 합니다") from exc
        if entry_id in updates:
            raise SystemExit(f"{line_no}행: 중복 ID {entry_id}")
        updates[entry_id] = encoded.replace("\\n", "\n")

    data = json.loads(PATH.read_text(encoding="utf-8"))
    by_id = {entry["id"]: entry for entry in data["entries"]}
    unknown = sorted(set(updates) - set(by_id))
    if unknown:
        raise SystemExit(f"알 수 없는 ID: {', '.join(unknown)}")

    applied = 0
    for entry_id, text in updates.items():
        entry = by_id[entry_id]
        if entry.get("text_kr") or entry.get("text_kr_full"):
            if entry.get("translation_source") == "adventure_exact":
                continue
            raise SystemExit(f"기존 번역 덮어쓰기 거부: {entry_id}")
        if CTRL.findall(text) != entry["controls"]:
            raise SystemExit(
                f"{entry_id}: 제어마커 불일치 "
                f"{CTRL.findall(text)!r} != {entry['controls']!r}"
            )
        entry["status"] = "translated"
        entry["translation_source"] = "codex_manual"
        entry["text_kr_full"] = text
        entry["text_kr"] = text
        applied += 1

    translated = sum(bool(entry.get("text_kr_full")) for entry in data["entries"])
    shortened = sum(
        bool(entry.get("text_kr_full"))
        and entry.get("text_kr") != entry.get("text_kr_full")
        for entry in data["entries"]
    )
    data["_stats"]["translated_existing"] = translated
    data["_stats"]["shortened_existing"] = shortened
    PATH.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"필드 번역 {applied}개 반영: 누계 {translated}/{len(data['entries'])}")


if __name__ == "__main__":
    main()
