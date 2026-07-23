#!/usr/bin/env python3
"""어드벤처 원본 카탈로그·번역·실제 VM 소비 경계의 완전성을 검사한다."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "scripts")
from adv_codec import (  # noqa: E402
    DICT_SNES,
    N_SCENES,
    ROM,
    decompress_scene,
    foff,
    scene_src,
)
from adv_extract import run_raw  # noqa: E402
from adv_scene import render, walk_catalog_scene  # noqa: E402
from decode_script import load_tbl  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets/translations/adventure.json"
KOREAN = ROOT / "assets/translations/adventure_kr.json"
GLYPH_TABLE = ROOT / "assets/translation_guide/glyph_table.tsv"

# cmd0x20 컨테이너의 operand 뒤를 과거 워커가 글자처럼 읽은 기능 바이트.
# 대사로 번역하면 VM 경계를 파괴할 수 있으므로 빈 번역이 정상이다.
NON_DIALOGUE_RUNS = {
    (0x64, 0x0039),
    (0x6B, 0x002C),
    (0xA7, 0x000D),
    (0xAC, 0x001B),
    (0xAC, 0x0060),
    (0xAD, 0x0013),
    (0xB2, 0x0023),
    (0xB2, 0x008C),
    (0xB2, 0x00D8),
    (0xB3, 0x0021),
    (0xB4, 0x0013),
    (0xB5, 0x0013),
    (0xB6, 0x0021),
    (0xB7, 0x0013),
    (0xB9, 0x0013),
    (0xBA, 0x0013),
}
DATA_ONLY_UNCLEAN_SCENES = {0x87, 0x88}
JP_LETTER = re.compile(r"[ぁ-ゖァ-ヺ一-龯]")
CONTROL = re.compile(r"\{[^}]+\}")


def controls(text: str) -> list[str]:
    return CONTROL.findall(text)


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    korean = json.loads(KOREAN.read_text(encoding="utf-8"))["scenes"]
    rom = Path(ROM).read_bytes()
    table = load_tbl(str(GLYPH_TABLE))
    dictionary = foff(*DICT_SNES)

    if len(source) != N_SCENES:
        raise SystemExit(f"원본 씬 수 {len(source)} != {N_SCENES}")

    live_runs = {}
    unclean = set()
    for sid in range(N_SCENES):
        bank, addr = scene_src(rom, sid)
        buf, out_len, _ = decompress_scene(rom, bank, addr, dictionary)
        runs, stats, end = walk_catalog_scene(buf, sid)
        clean = not stats["desync"] and end >= len(buf) - 1
        if not clean:
            unclean.add(sid)
        catalog_scene = source[sid]
        if (
            catalog_scene["scene"] != sid
            or catalog_scene["src"] != f"${bank:02X}:{addr:04X}"
            or catalog_scene["decomp_len"] != out_len
            or catalog_scene["clean"] != clean
        ):
            raise SystemExit(f"scene 0x{sid:02X}: 원본 씬 메타데이터 불일치")

        actual = []
        for run in runs:
            text_jp = render(run["text"], table)
            if not text_jp.strip():
                continue
            item = {
                "at": run["at"],
                "cmd": run["cmd"],
                "text_jp": text_jp,
                "raw": run_raw(buf, run).hex(),
            }
            actual.append(item)
            live_runs[(sid, run["at"])] = item
        if actual != catalog_scene["runs"]:
            raise SystemExit(f"scene 0x{sid:02X}: 원본 VM 런 카탈로그 불일치")

        if sid in DATA_ONLY_UNCLEAN_SCENES and 0x21 in buf:
            raise SystemExit(f"scene 0x{sid:02X}: 데이터 전용 판정 뒤 cmd0x21 후보 발견")

    if unclean != DATA_ONLY_UNCLEAN_SCENES:
        raise SystemExit(
            f"미완주 씬 집합 변경: {sorted(unclean)} != "
            f"{sorted(DATA_ONLY_UNCLEAN_SCENES)}"
        )

    korean_runs = {
        (scene["scene"], run["at"]): run
        for scene in korean
        for run in scene["runs"]
    }
    if set(korean_runs) != set(live_runs):
        missing = sorted(set(live_runs) - set(korean_runs))
        extra = sorted(set(korean_runs) - set(live_runs))
        raise SystemExit(
            f"한글 카탈로그 키 불일치: 누락 {missing[:8]}, 초과 {extra[:8]}"
        )

    blank = {key for key, run in korean_runs.items() if not run.get("text_kr")}
    if blank != NON_DIALOGUE_RUNS:
        raise SystemExit(
            f"미번역/기능런 집합 변경: {sorted(blank)} != "
            f"{sorted(NON_DIALOGUE_RUNS)}"
        )

    for key, source_run in live_runs.items():
        run = korean_runs[key]
        if run["cmd"] != source_run["cmd"] or run["text_jp"] != source_run["text_jp"]:
            raise SystemExit(f"{key[0]:02X}:{key[1]:04X}: 원문/명령 불일치")
        text_kr = run.get("text_kr", "")
        if not text_kr:
            continue
        if JP_LETTER.search(text_kr):
            raise SystemExit(f"{key[0]:02X}:{key[1]:04X}: 일본어 글자 잔존")
        if controls(text_kr) != controls(source_run["text_jp"]):
            raise SystemExit(f"{key[0]:02X}:{key[1]:04X}: 제어코드 서명 불일치")

    translated = len(live_runs) - len(blank)
    print(
        "어드벤처 완전성 PASS: "
        f"원본런 {len(live_runs)} / 번역 {translated} / "
        f"기능 cmd0x20 {len(blank)} / 데이터 전용 미완주 2씬"
    )


if __name__ == "__main__":
    main()
