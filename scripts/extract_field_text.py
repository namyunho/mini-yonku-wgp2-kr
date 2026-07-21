#!/usr/bin/env python3
"""전역 씬표 사이에 숨은 필드/NPC 압축 레코드 전량 추출.

큰 어드벤처 씬 250개는 $C6:9C57 표가 직접 가리키지만, 각 큰 씬의
압축 스트림 끝과 다음 표 엔트리 사이에는 필드 오브젝트가 직접 참조하는
작은 압축 VM 레코드가 연속 저장되어 있다. 각 숨은 레코드는 $C2 데이터의
3바이트 포인터 ``{addr_lo, addr_hi, bank-$C4}``로 참조된다.

이 스크립트는 다음을 회귀 불변식으로 검사한다.

* 원본 ROM 해시 일치
* 37개 양수 씬간 갭을 압축 레코드 경계로 잔여 0바이트까지 정확히 소진
* 마지막 전역 씬 뒤의 C2 참조 꼬리 팩 19개까지 포함
* 숨은 레코드 1,207개(C4 484/C5 290/C6 433)
* 모든 레코드에 $C2 포인터가 최소 1개 존재
* 실제 재귀 표현식 문법으로 1,187개 완주
* 유일한 비실행 꼬리 1건은 텍스트 명령이 없는 10바이트로 고정
* 디컴프레서 왕복 경계와 텍스트런 raw 경계가 ROM과 일치

산출물은 번역 입력 겸 포인터 카탈로그인
``assets/translations/field_text.json``이다.

번역 필드는 기존 축약 원장 규약(docs/15)을 따른다.

* ``text_kr_full``: 축약 전 완역본(한 번 채우면 보존)
* ``text_kr``: 실제 삽입용 문구(처음에는 full과 같고, 초과 런만 축약)
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
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
from adv_scene import read_text_run, render, walk  # noqa: E402
from decode_script import load_tbl  # noqa: E402


OUT = Path("assets/translations/field_text.json")
EXPECTED_MD5 = "acdeb2ee6ef7b460c5dfed6957f8581a"
EXPECTED_RECORDS = 1207
EXPECTED_INTERSCENE_GAPS = 37
EXPECTED_ZERO_GAPS = 212
EXPECTED_REGIONS = 38
EXPECTED_BANKS = {0xC4: 484, 0xC5: 290, 0xC6: 433}
EXPECTED_PACKED_BYTES = 76604
EXPECTED_TAIL_START = foff(0xC6, 0x6B3C)
EXPECTED_TAIL_STOP = foff(0xC6, 0x6C84)
EXPECTED_TAIL_RECORDS = 19
EXPECTED_POST_TAIL_CANDIDATES = 19
EXPECTED_CLEAN = 1206
EXPECTED_DESYNC = 1
EXPECTED_DESYNC_STOPS = {"$C4:9B72": 0x184}
EXPECTED_DESYNC_TAILS = {"$C4:9B72": "06000201290013282f00"}
EXPECTED_TEXT_RUNS = 1411
EXPECTED_UNIQUE_TEXT = 1340
EXPECTED_POINTER_REFS = 1300


def snes(pc: int) -> str:
    return f"${(pc >> 16) | 0xC0:02X}:{pc & 0xFFFF:04X}"


def run_raw(buf: bytes, run: dict) -> bytes:
    """텍스트 명령의 글리프/제어 바이트(명령 바이트 제외)를 돌려준다."""
    at = run["at"]
    if run["cmd"] == 0x21:
        _, end = read_text_run(buf, at + 1)
        return buf[at + 1:end]
    _, end = read_text_run(buf, at + 3)
    return buf[at + 3:end]


def c2_pointer_refs(rom: bytes, bank: int, addr: int) -> list[int]:
    """숨은 레코드의 정확한 3바이트 C2 포인터 위치를 모두 찾는다."""
    pattern = bytes((addr & 0xFF, addr >> 8, bank - 0xC4))
    refs: list[int] = []
    start = 0x020000
    stop = 0x030000
    while True:
        hit = rom.find(pattern, start, stop)
        if hit < 0:
            return refs
        refs.append(hit)
        start = hit + 1


def load_prior_runs() -> dict[tuple[str, int, int, str], dict]:
    """재추출해도 이미 작성한 완역/축약을 잃지 않도록 기존 run을 읽는다."""
    if not OUT.exists():
        return {}
    try:
        old = json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    prior = {}
    for record in old.get("records", []):
        src = record.get("src")
        for run in record.get("runs", []):
            key = (src, run.get("at"), run.get("cmd"), run.get("raw"))
            prior[key] = run
    return prior


def main() -> None:
    rom_path = Path(ROM)
    rom = rom_path.read_bytes()
    md5 = hashlib.md5(rom).hexdigest()
    if len(rom) != 0x200000 or md5 != EXPECTED_MD5:
        raise SystemExit(
            f"원본 ROM 불일치: size={len(rom)} md5={md5} "
            f"(expected 2097152/{EXPECTED_MD5})"
        )

    tbl = load_tbl("assets/translation_guide/glyph_table.tsv")
    dic = foff(*DICT_SNES)
    prior_runs = load_prior_runs()
    records: list[dict] = []
    gaps: list[dict] = []
    bank_counts: Counter[int] = Counter()
    all_text: list[str] = []
    pointer_count = 0
    rid = 0
    zero_gaps = 0

    if foff(*scene_src(rom, 0)) != foff(0xC4, 0x0000):
        raise SystemExit("첫 전역 씬이 $C4:0000에서 시작하지 않음")

    def append_record(pos: int, anchor_scene: int) -> int:
        """pos의 압축 레코드 하나를 검증·카탈로그하고 끝 PC를 반환."""
        nonlocal pointer_count, rid
        rec_bank = (pos >> 16) | 0xC0
        rec_addr = pos & 0xFFFF
        buf, out_len, end = decompress_scene(rom, rec_bank, rec_addr, dic)
        parsed_runs, stats, walk_end = walk(buf, strict=True)
        clean = not stats["desync"] and walk_end >= len(buf) - 1
        refs = c2_pointer_refs(rom, rec_bank, rec_addr)
        if not refs:
            raise SystemExit(f"C2 포인터 없는 숨은 레코드: {snes(pos)}")

        out_runs = []
        for run in parsed_runs:
            text_jp = render(run["text"], tbl)
            if not text_jp.strip():
                continue
            raw = run_raw(buf, run)
            key = (snes(pos), run["at"], run["cmd"], raw.hex())
            old_run = prior_runs.get(key, {})
            text_kr = old_run.get("text_kr", "")
            text_kr_full = old_run.get("text_kr_full", text_kr)
            out_runs.append(
                {
                    "at": run["at"],
                    "cmd": run["cmd"],
                    "text_jp": text_jp,
                    "text_kr_full": text_kr_full,
                    "text_kr": text_kr,
                    "orig_len": len(raw),
                    "raw": raw.hex(),
                }
            )
            all_text.append(text_jp)

        records.append(
            {
                "id": rid,
                "anchor_scene": anchor_scene,
                "src": snes(pos),
                "decomp_len": out_len,
                "comp_len": end - pos,
                "clean": clean,
                "walk_stop": walk_end,
                "stop_byte": None if walk_end >= len(buf) else buf[walk_end],
                "unparsed_tail": "" if clean else buf[walk_end:].hex(),
                "pointer_refs": [snes(ref) for ref in refs],
                "runs": out_runs,
            }
        )
        bank_counts[rec_bank] += 1
        pointer_count += len(refs)
        rid += 1
        return end

    for sid in range(N_SCENES - 1):
        bank, addr = scene_src(rom, sid)
        next_bank, next_addr = scene_src(rom, sid + 1)
        _, _, pos = decompress_scene(rom, bank, addr, dic)
        gap_end = foff(next_bank, next_addr)
        if pos > gap_end:
            raise SystemExit(
                f"전역 씬 압축영역 중첩: scene {sid} end={snes(pos)} "
                f"next={snes(gap_end)}"
            )
        if pos == gap_end:
            zero_gaps += 1
            continue

        gap_start = pos
        first_rid = rid
        while pos < gap_end:
            end = append_record(pos, sid)
            if end <= pos or end > gap_end:
                raise SystemExit(
                    f"숨은 레코드 경계 이탈: {snes(pos)} -> {snes(end)}, "
                    f"gap end {snes(gap_end)}"
                )

            pos = end

        if pos != gap_end:
            raise SystemExit(
                f"갭 잔여 발생: scene {sid} {snes(gap_start)}..{snes(gap_end)} "
                f"stop={snes(pos)}"
            )
        gaps.append(
            {
                "kind": "between_scenes",
                "anchor_scene": sid,
                "start": snes(gap_start),
                "end": snes(gap_end),
                "bytes": gap_end - gap_start,
                "first_record": first_rid,
                "record_count": rid - first_rid,
            }
        )

    # 마지막 전역 씬 뒤에도 C2가 직접 참조하는 작은 VM 레코드가 이어진다.
    # 다음 후보 $C6:6C84부터는 C2 참조가 없고 그래픽/사전 데이터이므로 거기서 종료한다.
    last_bank, last_addr = scene_src(rom, N_SCENES - 1)
    _, _, pos = decompress_scene(rom, last_bank, last_addr, dic)
    tail_start = pos
    tail_first_rid = rid
    while pos < foff(0xC6, 0x7C73):
        bank = (pos >> 16) | 0xC0
        addr = pos & 0xFFFF
        if not c2_pointer_refs(rom, bank, addr):
            break
        pos = append_record(pos, N_SCENES - 1)
    gaps.append(
        {
            "kind": "after_last_scene",
            "anchor_scene": N_SCENES - 1,
            "start": snes(tail_start),
            "end": snes(pos),
            "bytes": pos - tail_start,
            "first_record": tail_first_rid,
            "record_count": rid - tail_first_rid,
        }
    )
    if (tail_start, pos, rid - tail_first_rid) != (
        EXPECTED_TAIL_START,
        EXPECTED_TAIL_STOP,
        EXPECTED_TAIL_RECORDS,
    ):
        raise SystemExit(
            "마지막 씬 뒤 꼬리 팩 불일치: "
            f"{snes(tail_start)}..{snes(pos)} records={rid - tail_first_rid}"
        )

    # 꼬리 팩 뒤~압축 사전($C6:7C73) 사이를 역방향으로도 확인한다.
    # C2의 모든 3바이트 창 중 이 범위를 가리키는 후보를 엄격 VM으로 재검사하면
    # 19개 후보가 모두 탈락한다. 즉 꼬리 팩 뒤에 추가 필드 VM 레코드는 없다.
    post_tail_targets = sorted(
        {
            rom[i] | (rom[i + 1] << 8)
            for i in range(0x020000, 0x02FFFE)
            if rom[i + 2] == 2
            and (EXPECTED_TAIL_STOP & 0xFFFF)
            <= (rom[i] | (rom[i + 1] << 8))
            < 0x7C73
        }
    )
    post_tail_vm = []
    for addr in post_tail_targets:
        try:
            buf, _, _ = decompress_scene(rom, 0xC6, addr, dic)
        except Exception:
            continue
        _, stats, walk_end = walk(buf, strict=True)
        if not stats["desync"] and walk_end >= len(buf) - 1:
            post_tail_vm.append(addr)
    if len(post_tail_targets) != EXPECTED_POST_TAIL_CANDIDATES or post_tail_vm:
        raise SystemExit(
            "꼬리 팩 뒤 C2 후보 역검사 불일치: "
            f"candidates={len(post_tail_targets)} valid_vm={post_tail_vm}"
        )

    clean_count = sum(r["clean"] for r in records)
    desync_count = len(records) - clean_count
    desync_stops = {
        r["src"]: r["walk_stop"] for r in records if not r["clean"]
    }
    desync_tails = {
        r["src"]: r["unparsed_tail"] for r in records if not r["clean"]
    }
    actual_banks = dict(sorted(bank_counts.items()))
    checks = {
        "records": (len(records), EXPECTED_RECORDS),
        "interscene_gaps": (
            sum(g["kind"] == "between_scenes" for g in gaps),
            EXPECTED_INTERSCENE_GAPS,
        ),
        "zero_gaps": (zero_gaps, EXPECTED_ZERO_GAPS),
        "regions": (len(gaps), EXPECTED_REGIONS),
        "bank_counts": (actual_banks, EXPECTED_BANKS),
        "packed_bytes": (sum(g["bytes"] for g in gaps), EXPECTED_PACKED_BYTES),
        "clean": (clean_count, EXPECTED_CLEAN),
        "desync": (desync_count, EXPECTED_DESYNC),
        "desync_stops": (desync_stops, EXPECTED_DESYNC_STOPS),
        "desync_tails": (desync_tails, EXPECTED_DESYNC_TAILS),
        "text_runs": (len(all_text), EXPECTED_TEXT_RUNS),
        "unique_text": (len(set(all_text)), EXPECTED_UNIQUE_TEXT),
        "pointer_refs": (pointer_count, EXPECTED_POINTER_REFS),
    }
    bad = {name: pair for name, pair in checks.items() if pair[0] != pair[1]}
    if bad:
        raise SystemExit(f"숨은 레코드 회귀값 불일치: {bad}")

    payload = {
        "_note": (
            "전역 씬표 $C6:9C57의 큰 씬 사이에 저장된 필드/NPC용 숨은 압축 VM "
            "레코드. pointer_refs는 $C2의 {addr_lo,addr_hi,bank-$C4} 포인터 위치다. "
            "text_kr_full은 축약 전 완역, text_kr은 위치보존 삽입용 문구다."
        ),
        "_stats": {
            "records": len(records),
            "regions": len(gaps),
            "interscene_gaps": sum(g["kind"] == "between_scenes" for g in gaps),
            "zero_gaps": zero_gaps,
            "tail_packs": sum(g["kind"] == "after_last_scene" for g in gaps),
            "post_tail_c2_candidates_rejected": len(post_tail_targets),
            "packed_bytes": sum(g["bytes"] for g in gaps),
            "banks": {f"${bank:02X}": count for bank, count in actual_banks.items()},
            "clean": clean_count,
            "desync": desync_count,
            "text_runs": len(all_text),
            "unique_text": len(set(all_text)),
            "pointer_refs": pointer_count,
        },
        "regions": gaps,
        "records": records,
    }
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(
        f"숨은 필드 레코드 {len(records)}개 / 영역 {len(gaps)}개"
        f"(씬간 {EXPECTED_INTERSCENE_GAPS} + 꼬리 1) -> {OUT}"
    )
    print(
        f"  clean {clean_count} / desync {desync_count} / "
        f"텍스트런 {len(all_text)} / 고유원문 {len(set(all_text))}"
    )
    print(f"  C2 포인터 {pointer_count}개 / 갭 잔여 0B")


if __name__ == "__main__":
    main()
