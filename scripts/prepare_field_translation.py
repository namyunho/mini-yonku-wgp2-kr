#!/usr/bin/env python3
"""필드/NPC 고유 원문 번역 원장 생성·갱신.

``field_text.json``의 1,411개 run을 일본어 원문 기준 1,340개로 중복 제거한다.
기존 ``field_kr.json``의 번역은 원문 키로 병합해 재실행해도 유실하지 않는다.

필드 규약:
  text_kr_full = 축약 전 완역본(영구 보존)
  text_kr      = 실제 삽입용 문구(처음에는 full과 동일, 긴 런만 축약)
"""

from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path


FIELD = Path("assets/translations/field_text.json")
ADV = Path("assets/translations/adventure_kr.json")
OUT = Path("assets/translations/field_kr.json")


def load_old() -> dict[str, dict]:
    if not OUT.exists():
        return {}
    data = json.loads(OUT.read_text(encoding="utf-8"))
    return {entry["text_jp"]: entry for entry in data.get("entries", [])}


def load_adv_memory() -> dict[str, str]:
    data = json.loads(ADV.read_text(encoding="utf-8"))
    return {
        run["text_jp"]: run["text_kr"]
        for scene in data["scenes"]
        for run in scene["runs"]
        if run.get("text_kr")
    }


def controls(text: str) -> list[str]:
    out = []
    p = 0
    while p < len(text):
        if text[p] == "{":
            end = text.find("}", p)
            if end < 0:
                raise SystemExit(f"닫히지 않은 제어 마커: {text!r}")
            out.append(text[p : end + 1])
            p = end + 1
        else:
            p += 1
    return out


def main() -> None:
    field = json.loads(FIELD.read_text(encoding="utf-8"))
    old = load_old()
    adv = load_adv_memory()
    grouped: OrderedDict[str, dict] = OrderedDict()

    for record in field["records"]:
        for run in record["runs"]:
            jp = run["text_jp"]
            if jp not in grouped:
                grouped[jp] = {
                    "raw": run["raw"],
                    "orig_len": run["orig_len"],
                    "controls": controls(jp),
                    "occurrences": [],
                }
            item = grouped[jp]
            if (run["raw"], run["orig_len"]) != (item["raw"], item["orig_len"]):
                raise SystemExit(f"같은 원문에 raw/길이 변형 존재: {jp!r}")
            item["occurrences"].append(
                {
                    "record_id": record["id"],
                    "src": record["src"],
                    "at": run["at"],
                    "cmd": run["cmd"],
                }
            )

    entries = []
    seeded = translated = shortened = 0
    for index, (jp, item) in enumerate(grouped.items()):
        prev = old.get(jp, {})
        full = prev.get("text_kr_full", "")
        fitted = prev.get("text_kr", "")
        status = prev.get("status", "pending")
        source = prev.get("translation_source", "")

        if not full and jp in adv:
            full = fitted = adv[jp]
            status = "translated"
            source = "adventure_exact"
        if source == "adventure_exact":
            seeded += 1
        if full:
            translated += 1
            if fitted and fitted != full:
                shortened += 1

        entries.append(
            {
                "id": f"F{index:04d}",
                "status": status,
                "translation_source": source,
                "text_jp": jp,
                "text_kr_full": full,
                "text_kr": fitted,
                "orig_len": item["orig_len"],
                "controls": item["controls"],
                "occurrences": item["occurrences"],
            }
        )

    payload = {
        "_note": (
            "필드/NPC 고유 원문 번역 SSOT. text_kr_full=축약 전 완역, "
            "text_kr=위치보존 삽입문. 축약할 때 full을 덮어쓰지 않는다."
        ),
        "_rules": (
            "용어·말투=glossary.md. 제어마커 순서 보존, 줄폭≤16, 원문보다 줄 수 증가 금지. "
            "삽입문은 인코딩 후 orig_len(종료자 포함) 이하."
        ),
        "_stats": {
            "entries": len(entries),
            "occurrences": sum(len(x["occurrences"]) for x in entries),
            "seeded_from_adventure": seeded,
            "translated_existing": translated,
            "shortened_existing": shortened,
        },
        "entries": entries,
    }
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(
        f"필드 고유 원문 {len(entries)}개 / 발생 {payload['_stats']['occurrences']}개 "
        f"-> {OUT}"
    )
    print(f"  어드벤처 정확일치 시드 {seeded}개 / 기존 번역 보존 {translated}개")


if __name__ == "__main__":
    main()
