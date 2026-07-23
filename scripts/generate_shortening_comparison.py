#!/usr/bin/env python3
"""현재 빌드 정본의 완역문과 실제 조정·삽입문이 다른 항목만 Markdown으로 목록화한다.

완역은 text_kr_full 또는 shortening ledger의 before_kr에서 읽고, 실제 삽입문은
항상 현재 빌드 입력(dialogue/adventure_kr/field_kr)의 text_kr에서 다시 읽는다.
따라서 과거 ledger의 after_kr 스냅샷보다 현재 ROM에 들어가는 문구가 우선한다.
바이트 축약뿐 아니라 안전한 줄바꿈·들여쓰기 정리로 달라진 문장도 함께 싣는다.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRANS = ROOT / "assets" / "translations"
OUT = ROOT / "docs" / "22-shortened-translation-comparison.md"


def load(name: str):
    return json.loads((TRANS / name).read_text(encoding="utf-8"))


@dataclass(frozen=True)
class Row:
    system: str
    sort_key: tuple
    ident: str
    full: str
    inserted: str


def text_cell(text: str) -> str:
    """표 안에서 제어코드와 줄 경계를 잃지 않는 HTML/Markdown 셀."""
    text = text.replace("\r", "").replace("　", "␠")
    text = text.replace("{nl}", "{nl}\n")
    lines = text.split("\n")
    rendered = []
    for line in lines:
        escaped = html.escape(line, quote=False).replace("|", "&#124;")
        rendered.append(f"<code>{escaped or '↵'}</code>")
    return "<br>".join(rendered)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    dialogue = load("dialogue.json")
    adventure = load("adventure_kr.json")
    field = load("field_kr.json")
    parts = load("adv_parts_fragments.json")
    menu_extra = load("menu_extra_labels.json")
    worldmap = load("worldmap_text.json")
    ledger = load("shortening_ledger.json")
    field_ledger = load("field_shortening_ledger.json")
    layout_ledger = load("dialogue_layout_ledger.json")

    if ledger["done_count"] != len(ledger["done"]) or ledger["pending_count"] != 0:
        raise SystemExit("shortening_ledger count/pending 불변식 위반")
    if (field_ledger["done_count"] != len(field_ledger["done"])
            or field_ledger["pending_count"] != 0):
        raise SystemExit("field_shortening_ledger count/pending 불변식 위반")
    if (layout_ledger["entry_count"] != len(layout_ledger["entries"])
            or layout_ledger["entry_count"] != 229):
        raise SystemExit("dialogue_layout_ledger count 불변식 위반")

    dialogue_by_id = {x["entry_id"]: x for x in dialogue["entries"]}
    adventure_by_key = {
        (scene["scene"], run["at"]): run
        for scene in adventure["scenes"]
        for run in scene["runs"]
    }
    field_by_id = {x["id"]: x for x in field["entries"]}
    layout_by_id = {x["id"]: x for x in layout_ledger["entries"]}
    if len(layout_by_id) != len(layout_ledger["entries"]):
        raise SystemExit("dialogue_layout_ledger 중복 키")

    for item in layout_ledger["entries"]:
        if item["system"] == "dialogue":
            current = dialogue_by_id[item["entry_id"]]
        elif item["system"] == "adventure":
            current = adventure_by_key[(item["scene"], item["at"])]
        elif item["system"] == "field":
            current = field_by_id[item["entry_id"]]
        else:
            raise SystemExit(f"알 수 없는 layout system: {item['system']}")
        if current["text_kr"] != item["after_kr"]:
            raise SystemExit(f"레이아웃 원장 현재 삽입문 불일치: {item['id']}")
        if current["text_kr_full"] != item["text_kr_full"]:
            raise SystemExit(f"레이아웃 원장 완역문 불일치: {item['id']}")

    rows: dict[tuple, Row] = {}

    def add(system: str, key, ident: str, full: str, inserted: str, sort_key: tuple) -> None:
        if full == inserted:
            return
        record_key = (system, key)
        row = Row(system, sort_key, ident, full, inserted)
        old = rows.get(record_key)
        if old and old != row:
            raise SystemExit(f"중복 완역 불일치: {record_key}")
        rows[record_key] = row

    # 과거 위치보존/결합축약 원장: before_kr은 유실되면 안 되는 완역본이다.
    for item in ledger["done"]:
        if item["system"] == "adventure":
            key = (item["scene"], item["at"])
            if key not in adventure_by_key:
                raise SystemExit(f"현재 adventure_kr에 없는 축약 키: {key}")
            run = adventure_by_key[key]
            add(
                "adventure", key,
                f"scene 0x{item['scene']:02X} / at 0x{item['at']:04X}",
                item["before_kr"], run["text_kr"], key,
            )
        elif item["system"] == "dialogue":
            key = item["entry_id"]
            if key not in dialogue_by_id:
                raise SystemExit(f"현재 dialogue에 없는 축약 키: {key}")
            entry = dialogue_by_id[key]
            add(
                "dialogue", key,
                f"entry {key} / {entry['table_id']} / {entry['addr']}",
                item["before_kr"], entry["text_kr"], (key,),
            )
        else:
            raise SystemExit(f"알 수 없는 shortening system: {item['system']}")

    # 필드 원장은 before_kr == text_kr_full이어야 한다. 삽입문은 현재 field_kr를 사용한다.
    for item in field_ledger["done"]:
        key = item["entry_id"]
        if key not in field_by_id:
            raise SystemExit(f"현재 field_kr에 없는 축약 키: {key}")
        entry = field_by_id[key]
        if item["before_kr"] != entry["text_kr_full"]:
            raise SystemExit(f"필드 완역 원장 불일치: {key}")
        if item["after_kr"] != entry["text_kr"]:
            layout = layout_by_id.get(f"field:{key}")
            if not layout or (layout["before_kr"] != item["after_kr"]
                              or layout["after_kr"] != entry["text_kr"]):
                raise SystemExit(f"필드 축약→레이아웃→삽입 원장 불일치: {key}")
        number = int(re.search(r"\d+", key).group())
        add("field", key, key, entry["text_kr_full"], entry["text_kr"], (number,))

    # 최근에 각 빌드 원장에 직접 추가된 full/삽입 쌍도 빠짐없이 합친다.
    for entry in dialogue["entries"]:
        full = entry.get("text_kr_full")
        inserted = entry.get("text_kr")
        if isinstance(full, str) and isinstance(inserted, str) and full != inserted:
            add(
                "dialogue", entry["entry_id"],
                f"entry {entry['entry_id']} / {entry['table_id']} / {entry['addr']}",
                full, inserted, (entry["entry_id"],),
            )
    for scene in adventure["scenes"]:
        for run in scene["runs"]:
            full = run.get("text_kr_full")
            inserted = run.get("text_kr")
            if isinstance(full, str) and isinstance(inserted, str) and full != inserted:
                key = (scene["scene"], run["at"])
                add(
                    "adventure", key,
                    f"scene 0x{scene['scene']:02X} / at 0x{run['at']:04X}",
                    full, inserted, key,
                )
    for entry in field["entries"]:
        full = entry.get("text_kr_full")
        inserted = entry.get("text_kr")
        if isinstance(full, str) and isinstance(inserted, str) and full != inserted:
            number = int(re.search(r"\d+", entry["id"]).group())
            add("field", entry["id"], entry["id"], full, inserted, (number,))

    # 파츠 동적 이름도 같은 규칙으로 감사한다(현재는 27건 모두 완역 그대로라 목록 0건).
    for table in parts["tables"]:
        for entry in table["entries"]:
            full = entry.get("text_kr_full")
            inserted = entry.get("text_kr")
            if isinstance(full, str) and isinstance(inserted, str) and full != inserted:
                key = (table["id"], entry["index"])
                add(
                    "parts", key, f"{table['id']}[{entry['index']}]",
                    full, inserted, (table["id"], entry["index"]),
                )

    # 소형 메뉴의 직접 타일·내장 그래픽도 원문/완역/실삽입 3본을 같은 표에서 감사한다.
    for entry in menu_extra["entries"]:
        full = entry.get("text_kr_full")
        inserted = entry.get("text_kr")
        if isinstance(full, str) and isinstance(inserted, str) and full != inserted:
            add(
                "menu_extra", entry["id"],
                f"{entry['id']} / {entry['source']}",
                full, inserted, (entry["id"],),
            )

    # 월드맵 퀴즈는 350개 DB와 DB 밖 고정 UI·상태줄을 한 원장에서 감사한다.
    for entry in worldmap["entries"]:
        full = entry.get("kr_full")
        inserted = entry.get("kr")
        if isinstance(full, str) and isinstance(inserted, str) and full != inserted:
            add(
                "worldmap", ("entry", entry["entry_id"]),
                f"quiz entry {entry['entry_id']} / {entry['addr']}",
                full, inserted, (0, entry["entry_id"]),
            )
    for message in worldmap["fixed_messages"]:
        full = message.get("kr_full")
        inserted = message.get("kr")
        if isinstance(full, str) and isinstance(inserted, str) and full != inserted:
            add(
                "worldmap", ("fixed", message["id"]),
                f"quiz UI {message['id']} / {message['addr']}",
                full, inserted, (1, message["id"]),
            )
    status = worldmap["status_line"]
    if status["text_kr_full"] != status["text_kr"]:
        add(
            "worldmap", ("status", status["program_addr"]),
            f"quiz status / {status['program_addr']}",
            status["text_kr_full"], status["text_kr"], (2, status["program_addr"]),
        )

    counts = {system: sum(r.system == system for r in rows.values())
              for system in (
                  "adventure", "dialogue", "field", "parts", "menu_extra", "worldmap"
              )}
    expected = {
        "adventure": 566,
        "dialogue": 27,
        "field": 351,
        "parts": 0,
        "menu_extra": 1,
        "worldmap": 13,
    }
    if counts != expected or len(rows) != 958:
        raise SystemExit(f"축약 목록 규모 불일치: {counts}, total={len(rows)}")

    inputs = [
        TRANS / "shortening_ledger.json",
        TRANS / "field_shortening_ledger.json",
        TRANS / "dialogue_layout_ledger.json",
        TRANS / "dialogue.json",
        TRANS / "adventure_kr.json",
        TRANS / "field_kr.json",
        TRANS / "adv_parts_fragments.json",
        TRANS / "menu_extra_labels.json",
        TRANS / "worldmap_text.json",
    ]
    lines = [
        "# 22 · 완역문–실삽입 조정문 전수 비교",
        "",
        "> 생성일: 2026-07-23",
        "> 생성 명령: `python3 scripts/generate_shortening_comparison.py`",
        "",
        "현재 통합 빌드의 번역 입력을 기준으로 **완역문과 실제 ROM 삽입문이 다른 항목만** 모은 사람용 비교표다.",
        "완역은 `text_kr_full` 또는 축약 원장의 `before_kr`, 실제 삽입문은 항상 현재 빌드 입력의",
        "`text_kr`에서 읽는다. 따라서 과거 축약 원장의 `after_kr` 이후 말투·표기가 교정된 경우도",
        "이 문서의 **실제 삽입문** 열에는 최신 문구가 나온다.",
        "",
        "## 범위와 판정 규칙",
        "",
        "- `완역문 == 실제 삽입문`인 항목은 싣지 않는다.",
        "- 필드 발생 레코드 `field_text.json` 1,411건은 고유 번역 `field_kr.json` 1,340건의 파생 자료이므로 중복 기재하지 않는다.",
        "- `␠`는 원문 데이터의 전각 공백이다. `{nl}`, `{wait}`, `{clear}`, `{cN:XX}`, `{end}`는 실제 제어마커다.",
        "- 축약 대기 항목은 두 축약 원장 모두 0건이며, 줄바꿈·들여쓰기 변경은 `dialogue_layout_ledger.json`에 전후 문장을 보존한다.",
        "- 이 목록은 번역 품질 검토용이다. 바이트 상한·위치보존 통과 여부는 각 기계 원장과 빌드 게이트가 담당한다.",
        "",
        "## 요약",
        "",
        "| 시스템 | 비교 항목 | 완역 보존 위치 | 실제 삽입 위치 |",
        "|---|---:|---|---|",
        f"| 어드벤처 씬 | {counts['adventure']} | `shortening_ledger.json:before_kr` / 일부 `text_kr_full` | `adventure_kr.json:text_kr` |",
        f"| 정적 대사 | {counts['dialogue']} | `shortening_ledger.json:before_kr` 또는 `dialogue.json:text_kr_full` | `dialogue.json:text_kr` |",
        f"| 필드/NPC | {counts['field']} | `field_kr.json:text_kr_full` | `field_kr.json:text_kr` |",
        f"| 파츠 획득 동적 이름 | {counts['parts']} | `adv_parts_fragments.json:text_kr_full` | `adv_parts_fragments.json:text_kr` |",
        f"| 소형 메뉴 직접 타일·그래픽 | {counts['menu_extra']} | `menu_extra_labels.json:text_kr_full` | `menu_extra_labels.json:text_kr` |",
        f"| 월드맵 퀴즈·고정 UI | {counts['worldmap']} | `worldmap_text.json:kr_full/text_kr_full` | `worldmap_text.json:kr/text_kr` |",
        f"| **합계** | **{len(rows)}** |  |  |",
        "",
    ]

    section_names = {
        "adventure": "어드벤처 씬",
        "dialogue": "정적 대사",
        "field": "필드/NPC",
        "menu_extra": "소형 메뉴 직접 타일·그래픽",
        "worldmap": "월드맵 퀴즈·고정 UI",
    }
    for system in ("adventure", "dialogue", "field", "menu_extra", "worldmap"):
        selected = sorted((r for r in rows.values() if r.system == system),
                          key=lambda r: r.sort_key)
        lines.extend([
            f"## {section_names[system]} ({len(selected)}건)",
            "",
            "| # | 식별자 | 완역문 | 실제 삽입문 |",
            "|---:|---|---|---|",
        ])
        for number, row in enumerate(selected, 1):
            lines.append(
                f"| {number} | `{row.ident}` | {text_cell(row.full)} | {text_cell(row.inserted)} |"
            )
        lines.append("")

    lines.extend([
        "## 생성 입력 무결성",
        "",
        "| 파일 | SHA-256 |",
        "|---|---|",
    ])
    for path in inputs:
        lines.append(f"| `{path.relative_to(ROOT)}` | `{digest(path)}` |")
    lines.extend([
        "",
        "이 문서는 위 입력에서 다시 생성할 수 있다. 생성기는 두 축약 원장의 완료/대기 수, 레이아웃 원장 229건,",
        "현재 빌드 키 존재 여부, 필드 `before_kr == text_kr_full`, 중복 키, 시스템별 예상 건수",
        "(566/27/351/0/1/13)를 검사하고 하나라도",
        "어긋나면 문서를 쓰지 않고 실패한다.",
        "",
    ])

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"축약 비교 문서 생성: {OUT.relative_to(ROOT)}")
    print(f"  어드벤처 {counts['adventure']} / 정적 {counts['dialogue']} / "
          f"필드 {counts['field']} / 파츠 {counts['parts']} / "
          f"소형 메뉴 {counts['menu_extra']} / 월드맵 {counts['worldmap']} / "
          f"합계 {len(rows)}")


if __name__ == "__main__":
    main()
