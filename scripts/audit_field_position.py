#!/usr/bin/env python3
"""필드 번역 전 위치보존 구조 감사.

번역과 무관하게 원본 run 경계·종료자·중복 원문 상한·포인터 정보를 검사해
빌더가 의존할 입력 계약을 고정한다.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict


FIELD = "assets/translations/field_text.json"
KR = "assets/translations/field_kr.json"


def main() -> None:
    field = json.load(open(FIELD, encoding="utf-8"))
    kr = json.load(open(KR, encoding="utf-8"))
    by_jp = {entry["text_jp"]: entry for entry in kr["entries"]}
    if len(by_jp) != 1340 or len(kr["entries"]) != 1340:
        raise SystemExit("고유 원문 키 중복/개수 불일치")

    occurrences = defaultdict(list)
    cmd_counts = Counter()
    text_records = 0
    comp_bytes = decomp_bytes = raw_bytes = 0
    for record in field["records"]:
        if record["runs"]:
            text_records += 1
            comp_bytes += record["comp_len"]
            decomp_bytes += record["decomp_len"]
        prev_end = -1
        for run in record["runs"]:
            raw = bytes.fromhex(run["raw"])
            if len(raw) != run["orig_len"] or not raw or raw[-1] != 0:
                raise SystemExit(f"raw 길이/종료자 불일치: {record['src']}+{run['at']:04X}")
            start = run["at"] + (3 if run["cmd"] == 0x20 else 1)
            end = start + len(raw)
            if start < prev_end:
                raise SystemExit(f"텍스트 run 중첩: {record['src']}+{run['at']:04X}")
            if end > record["decomp_len"]:
                raise SystemExit(f"텍스트 run 경계 이탈: {record['src']}+{run['at']:04X}")
            prev_end = end
            cmd_counts[run["cmd"]] += 1
            raw_bytes += len(raw)
            occurrences[run["text_jp"]].append((run["raw"], run["orig_len"]))
            if run["text_jp"] not in by_jp:
                raise SystemExit(f"번역 원장 누락: {run['text_jp']!r}")

    variants = {jp: set(values) for jp, values in occurrences.items() if len(set(values)) != 1}
    if variants:
        raise SystemExit(f"동일 원문 raw/상한 변형: {list(variants)[:3]}")
    if sum(len(v) for v in occurrences.values()) != 1411:
        raise SystemExit("발생 수 불일치")

    translated = sum(bool(x.get("text_kr_full")) for x in kr["entries"])
    shortened = sum(
        bool(x.get("text_kr_full")) and x.get("text_kr") != x.get("text_kr_full")
        for x in kr["entries"]
    )
    print("=== 필드 위치보존 입력 감사 ===")
    print(f"  텍스트 레코드 {text_records} / run 1411 / 고유 1340")
    print(f"  cmd21 {cmd_counts[0x21]} / cmd20 {cmd_counts[0x20]}")
    print(f"  원본 run raw {raw_bytes}B / 디컴프 {decomp_bytes}B / 압축 {comp_bytes}B")
    print(f"  번역 {translated}/1340 / 축약 {shortened}")
    print("  raw 길이·종료자·비중첩·고유원문 상한: PASS")


if __name__ == "__main__":
    main()
