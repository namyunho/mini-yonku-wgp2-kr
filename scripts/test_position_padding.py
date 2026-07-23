#!/usr/bin/env python3
"""분할 대사 접두 런의 위치보존 패딩이 다음 본문을 들여쓰기하지 않는지 검증한다."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "scripts")
from adv_codec import DICT_SNES, decompress_scene, foff, scene_src  # noqa: E402
from adv_scene import walk  # noqa: E402
from build_adv import encode_text, pad_kr, text_run_bounds  # noqa: E402


ORIG = Path("roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc")
GLYPH = Path("out/glyph_map.json")
FIELD = Path("assets/translations/field_kr.json")
ADVENTURE = Path("assets/translations/adventure_kr.json")
SPLIT_PREFIX = re.compile(r"\n[「『（【〈《]\Z")
EXPECTED_FIELD = {
    "F0868": 2,
    "F0873": 1,
    "F0878": 1,
    "F0893": 1,
    "F0898": 2,
    "F0903": 1,
    "F0913": 1,
    "F0919": 1,
    "F0929": 2,
    "F0934": 1,
    "F0939": 1,
    "F0944": 1,
    "F0949": 1,
    "F0954": 1,
    "F0959": 4,
    "F0974": 1,
    "F0979": 3,
    "F0984": 1,
}
EXPECTED_ADVENTURE = {
    (0x61, 0x0000): 1,
    (0x64, 0x0000): 2,
}


def assert_safe(text: str, pad: int, char2idx: dict[str, int], where: str) -> None:
    padded = pad_kr(text, pad)
    match = SPLIT_PREFIX.search(text)
    if not match:
        raise SystemExit(f"{where}: 분할 접두 런 패턴 불일치")
    insert_at = match.start()
    expected = text[:insert_at] + (" " * pad) + text[insert_at:]
    if padded != expected:
        raise SystemExit(f"{where}: 패딩이 화자명 행 끝으로 이동하지 않음: {padded!r}")
    if re.search(r"[「『（【〈《] +\Z", padded):
        raise SystemExit(f"{where}: 여는 괄호 뒤 들여쓰기 패딩 잔존")
    before = encode_text(text, char2idx, where)
    after = encode_text(padded, char2idx, where + " padded")
    if len(after) != len(before) + pad:
        raise SystemExit(f"{where}: 패딩 바이트 수 불일치")
    # 패딩 외 제어 바이트의 값과 순서는 바뀌지 않아야 한다.
    controls_before = [b for b in before if b < 0x10]
    controls_after = [b for b in after if b < 0x10]
    if controls_after != controls_before:
        raise SystemExit(f"{where}: 제어 바이트 순서 변경")


def main() -> None:
    char2idx = json.loads(GLYPH.read_text(encoding="utf-8"))["char2idx"]

    field = json.loads(FIELD.read_text(encoding="utf-8"))
    actual_field: dict[str, int] = {}
    for entry in field["entries"]:
        text = entry["text_kr"]
        if not SPLIT_PREFIX.search(text):
            continue
        encoded = encode_text(text, char2idx, entry["id"])
        pad = entry["orig_len"] - 1 - len(encoded)
        if pad > 0:
            actual_field[entry["id"]] = pad
            assert_safe(text, pad, char2idx, f"field {entry['id']}")
    if actual_field != EXPECTED_FIELD:
        raise SystemExit(
            f"필드 분할 접두 런 기준선 변경: {actual_field!r} != {EXPECTED_FIELD!r}"
        )

    base = ORIG.read_bytes()
    dict_pc = foff(*DICT_SNES)
    adventure = json.loads(ADVENTURE.read_text(encoding="utf-8"))
    actual_adventure: dict[tuple[int, int], int] = {}
    for scene in adventure["scenes"]:
        translated = {
            run["at"]: run["text_kr"]
            for run in scene["runs"]
            if run.get("text_kr")
        }
        if not translated:
            continue
        bank, addr = scene_src(base, scene["scene"])
        buf, _, _ = decompress_scene(base, bank, addr, dict_pc)
        runs, stats, _ = walk(buf)
        if stats["desync"]:
            continue
        for run in runs:
            text = translated.get(run["at"])
            if not text or not SPLIT_PREFIX.search(text):
                continue
            start, end = text_run_bounds(buf, run)
            capacity = end - start - 1
            pad = capacity - len(
                encode_text(text, char2idx, f"scene {scene['scene']:02X}:{run['at']:04X}")
            )
            if pad > 0:
                key = (scene["scene"], run["at"])
                actual_adventure[key] = pad
                assert_safe(
                    text,
                    pad,
                    char2idx,
                    f"scene 0x{scene['scene']:02X} at 0x{run['at']:04X}",
                )
    if actual_adventure != EXPECTED_ADVENTURE:
        raise SystemExit(
            "어드벤처 분할 접두 런 기준선 변경: "
            f"{actual_adventure!r} != {EXPECTED_ADVENTURE!r}"
        )

    print(
        "분할 대사 위치보존 패딩 PASS: "
        f"필드 {len(actual_field)} / 어드벤처 {len(actual_adventure)} / "
        "여는 괄호 뒤 패딩 0"
    )


if __name__ == "__main__":
    main()
