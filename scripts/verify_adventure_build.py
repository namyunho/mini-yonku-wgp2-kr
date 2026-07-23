#!/usr/bin/env python3
"""최종 통합 ROM의 어드벤처 1,782런을 다시 해제해 원장과 대조한다."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "scripts")
from adv_codec import DICT_SNES, decompress_scene, foff, scene_src  # noqa: E402
from adv_scene import render, walk_catalog_scene  # noqa: E402
from build_adv import encode_text, pad_kr, text_run_bounds  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT / "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
BUILT = ROOT / "out/wgp2_kr.smc"
KOREAN = ROOT / "assets/translations/adventure_kr.json"
GLYPH_MAP = ROOT / "out/glyph_map.json"


def main() -> None:
    base = ORIGINAL.read_bytes()
    built = BUILT.read_bytes()
    if len(built) != len(base) or len(built) != 2 * 1024 * 1024:
        raise SystemExit("최종 어드벤처 검증: ROM 2MB 크기 보존 실패")

    dictionary = foff(*DICT_SNES)
    char2idx = json.loads(GLYPH_MAP.read_text(encoding="utf-8"))["char2idx"]
    index2char = {index: char for char, index in char2idx.items()}
    korean = json.loads(KOREAN.read_text(encoding="utf-8"))["scenes"]

    verified_scenes = 0
    verified_runs = 0
    for scene in korean:
        sid = scene["scene"]
        translated = {
            run["at"]: run["text_kr"]
            for run in scene["runs"]
            if run.get("text_kr")
        }
        if not translated:
            continue

        src_bank, src_addr = scene_src(base, sid)
        original_script, _, _ = decompress_scene(
            base, src_bank, src_addr, dictionary
        )
        original_runs, original_stats, original_end = walk_catalog_scene(
            original_script, sid
        )
        if original_stats["desync"] or original_end < len(original_script) - 1:
            raise SystemExit(f"scene 0x{sid:02X}: 원본 워커 미완주")

        dst_bank, dst_addr = scene_src(built, sid)
        built_script, _, _ = decompress_scene(
            built, dst_bank, dst_addr, dictionary
        )
        built_runs, built_stats, built_end = walk_catalog_scene(built_script, sid)
        if built_stats["desync"] or built_end < len(built_script) - 1:
            raise SystemExit(f"scene 0x{sid:02X}: 최종 ROM 워커 미완주")
        if len(built_script) != len(original_script):
            raise SystemExit(f"scene 0x{sid:02X}: 위치보존 스크립트 길이 불일치")
        if [(run["at"], run["cmd"]) for run in built_runs] != [
            (run["at"], run["cmd"]) for run in original_runs
        ]:
            raise SystemExit(f"scene 0x{sid:02X}: 최종 ROM 런 위치/명령 불일치")

        built_by_at = {run["at"]: run for run in built_runs}
        for run in original_runs:
            at = run["at"]
            if at not in translated:
                continue
            start, end = text_run_bounds(original_script, run)
            capacity = end - start - 1
            encoded = encode_text(
                translated[at],
                char2idx,
                f"scene 0x{sid:02X} at 0x{at:04X}",
            )
            pad = capacity - len(encoded)
            if pad < 0:
                raise SystemExit(
                    f"scene 0x{sid:02X} at 0x{at:04X}: 원본 길이 {capacity} 초과"
                )
            expected = pad_kr(translated[at], pad)
            actual = render(built_by_at[at]["text"], index2char)
            if actual != expected:
                raise SystemExit(
                    f"scene 0x{sid:02X} at 0x{at:04X}: "
                    f"최종 ROM 역렌더 불일치 {actual!r} != {expected!r}"
                )
            verified_runs += 1
        verified_scenes += 1

    if (verified_scenes, verified_runs) != (235, 1782):
        raise SystemExit(
            f"최종 어드벤처 검증 건수 {(verified_scenes, verified_runs)} "
            "!= (235, 1782)"
        )
    print(
        "최종 통합 ROM 어드벤처 PASS: "
        f"{verified_scenes}씬 / {verified_runs}메시지 / 위치·명령·역렌더 일치"
    )


if __name__ == "__main__":
    main()
