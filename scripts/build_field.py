#!/usr/bin/env python3
"""필드/NPC 숨은 압축 VM 레코드 위치보존 재삽입기.

원본 디컴프레스 버퍼의 텍스트 런 길이와 오프셋을 그대로 유지한다. 재압축본이
모든 레코드를 build_adv가 중앙 씬표를 새 주소로 패치한 뒤 더는 참조되지 않는
어드벤처 원본 씬 슬롯에 2MB ROM 안에서 다시 패킹하고, C2의 3바이트 포인터를
전수 패치한다. 크기가 줄어든 레코드도 필드 원본 슬롯에는 쓰지 않는다. 필드 원본
슬롯과 추정 자유공간은 재사용하지 않는다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "scripts")
from adv_codec import DICT_LEN, DICT_SNES, compress_scene, decompress_scene, foff  # noqa: E402
from adv_scene import read_text_run, render  # noqa: E402
from build_adv import enc_glyph, encode_text, pad_kr  # noqa: E402


ORIG = "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
FIELD = "assets/translations/field_text.json"
KR = "assets/translations/field_kr.json"
GLYPH_MAP = "out/glyph_map.json"
ADV_MANIFEST = "out/adv_free_manifest.json"
OUT = "out/wgp2_kr.smc"
CTRL_TAIL = re.compile(r"(?:\{[^}]*\}|\n)+\Z")


def parse_snes(value: str) -> tuple[int, int]:
    bank, addr = value.removeprefix("$").split(":")
    return int(bank, 16), int(addr, 16)


def pointer_bytes(bank: int, addr: int) -> bytes:
    return bytes((addr & 0xFF, addr >> 8, bank - 0xC4))


class Allocator:
    def __init__(self, manifest: dict):
        self.pools = [
            {
                "bank": item["bank"],
                "addr": item["addr"],
                "capacity": item["capacity"],
                "used": 0,
                "kind": "reclaimed-adv-scene",
                "scene": item["scene"],
            }
            for item in manifest.get("reclaimed_scene_slots", [])
        ]
        if not self.pools:
            raise SystemExit("어드벤처 회수 씬 슬롯 manifest가 비어 있음")
        self._assert_nonoverlap()

    def _assert_nonoverlap(self) -> None:
        spans = sorted(
            (foff(p["bank"], p["addr"]), foff(p["bank"], p["addr"]) + p["capacity"], p)
            for p in self.pools
        )
        for (_, prev_end, prev), (start, _, cur) in zip(spans, spans[1:]):
            if start < prev_end:
                raise SystemExit(f"필드 할당 풀 중복: {prev} / {cur}")

    def pack(self, items: list[tuple[str, int]]) -> dict[str, tuple[int, int]]:
        """큰 레코드부터 남는 크기가 가장 작은 슬롯에 넣는 best-fit decreasing."""
        result = {}
        for key, size in sorted(items, key=lambda item: (-item[1], item[0])):
            candidates = [
                (p["capacity"] - p["used"] - size, i, p)
                for i, p in enumerate(self.pools)
                if p["capacity"] - p["used"] >= size
            ]
            if not candidates:
                raise SystemExit(f"2MB 내부 필드 재배치 공간 부족: {key} {size}B")
            _, _, pool = min(candidates, key=lambda item: (item[0], item[1]))
            bank = pool["bank"]
            addr = pool["addr"] + pool["used"]
            pool["used"] += size
            if addr + size > 0x10000:
                raise SystemExit(f"자유공간 뱅크 경계 이탈: ${bank:02X}:{addr:04X}+{size}")
            result[key] = (bank, addr)
        return result

    def report(self) -> tuple[int, int]:
        return sum(p["used"] for p in self.pools), sum(p["capacity"] for p in self.pools)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom", default=OUT)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--base", default=ORIG)
    ap.add_argument("--field", default=FIELD)
    ap.add_argument("--kr", default=KR)
    ap.add_argument("--glyph-map", default=GLYPH_MAP)
    ap.add_argument("--adv-manifest", default=ADV_MANIFEST)
    args = ap.parse_args()

    base = Path(args.base).read_bytes()
    rom = bytearray(Path(args.rom).read_bytes())
    if len(rom) != len(base):
        raise SystemExit(f"필드 통합 ROM 크기 불일치: input={len(rom)} original={len(base)}")
    catalog = json.loads(Path(args.field).read_text(encoding="utf-8"))
    kr_data = json.loads(Path(args.kr).read_text(encoding="utf-8"))
    ch2idx = json.loads(Path(args.glyph_map).read_text(encoding="utf-8"))["char2idx"]
    idx2char = {idx: char for char, idx in ch2idx.items()}
    manifest = json.loads(Path(args.adv_manifest).read_text(encoding="utf-8"))

    by_jp = {entry["text_jp"]: entry for entry in kr_data["entries"]}
    if len(by_jp) != 1340 or any(not entry.get("text_kr") for entry in by_jp.values()):
        raise SystemExit("필드 번역 원장이 1340/1340 완성 상태가 아님")

    dict_pc = foff(*DICT_SNES)
    dic = base[dict_pc : dict_pc + DICT_LEN]
    prepared = []
    longer = []
    translated_runs = 0

    for record in catalog["records"]:
        if not record["runs"]:
            continue
        src_bank, src_addr = parse_snes(record["src"])
        src_pc = foff(src_bank, src_addr)
        buf, out_len, end_pc = decompress_scene(base, src_bank, src_addr, dict_pc)
        if out_len != record["decomp_len"] or end_pc - src_pc != record["comp_len"]:
            raise SystemExit(f"원본 레코드 경계 불일치: {record['src']}")

        script = bytearray(buf)
        expected = []
        for run in record["runs"]:
            entry = by_jp.get(run["text_jp"])
            if entry is None:
                raise SystemExit(f"번역 원장 누락: {record['src']}+0x{run['at']:04X}")
            text = entry["text_kr"]
            at = run["at"]
            start = at + (3 if run["cmd"] == 0x20 else 1)
            raw = bytes.fromhex(run["raw"])
            end = start + len(raw)
            if bytes(buf[start:end]) != raw or raw[-1] != 0:
                raise SystemExit(f"런 raw 불일치: {record['src']}+0x{at:04X}")
            encoded = encode_text(text, ch2idx, f"field {entry['id']} {record['src']}+0x{at:04X}")
            capacity = len(raw) - 1
            if len(encoded) > capacity:
                longer.append(
                    {
                        "entry_id": entry["id"],
                        "record_id": record["id"],
                        "src": record["src"],
                        "at": at,
                        "orig_bytes": capacity,
                        "kr_bytes": len(encoded),
                        "over_bytes": len(encoded) - capacity,
                        "text_kr_full": entry["text_kr_full"],
                        "text_kr": text,
                    }
                )
                continue
            padded = pad_kr(text, capacity - len(encoded))
            encoded_padded = encode_text(
                padded, ch2idx, f"field {entry['id']} {record['src']}+0x{at:04X} pad"
            )
            if len(encoded_padded) != capacity:
                raise SystemExit(f"패딩 길이 불일치: {entry['id']}")
            script[start:end] = encoded_padded + b"\x00"
            expected.append((start, run["cmd"], padded, entry["id"]))
            translated_runs += 1

        comp = compress_scene(bytes(script), dic)
        prepared.append((record, src_bank, src_addr, src_pc, bytes(script), expected, comp))

    Path("out").mkdir(exist_ok=True)
    Path("out/field_retranslate_longer.json").write_text(
        json.dumps(
            {
                "count": len(longer),
                "unique_entries": len({item["entry_id"] for item in longer}),
                "note": "필드 위치보존 런의 원본 바이트 상한을 넘는 삽입본. text_kr_full을 보존하고 text_kr만 축약한다.",
                "runs": sorted(longer, key=lambda item: (-item["over_bytes"], item["entry_id"])),
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    if longer:
        print(
            f"필드 긴 런 {len(longer)}개 / 고유 {len({item['entry_id'] for item in longer})}개 "
            "→ out/field_retranslate_longer.json"
        )
        raise SystemExit("필드 위치보존 바이트 상한 초과")

    # 필드 원본 압축 슬롯은 텍스트 외 타일/OBJ 로더가 별도로 참조할 가능성을 배제하지
    # 못했다. 실기에서 원본 슬롯을 대량 재사용했을 때 스프라이트가 깨졌고, 재사용을
    # 28개로 줄이자 일부가 복구되었다. 따라서 크기와 무관하게 전 레코드를 재배치한다.
    relocated_items = prepared
    allocator = Allocator(manifest)
    placements = allocator.pack([(item[0]["id"], len(item[6])) for item in relocated_items])

    relocated = pointer_patches = verified = 0
    comp_orig = comp_new = 0
    destinations = {}
    for record, src_bank, src_addr, src_pc, script, expected, comp in prepared:
        comp_orig += record["comp_len"]
        comp_new += len(comp)
        if bytes(rom[src_pc : src_pc + record["comp_len"]]) != bytes(
            base[src_pc : src_pc + record["comp_len"]]
        ):
            raise SystemExit(f"필드 원본 슬롯이 빌드 전에 이미 변경됨: {record['src']}")
        dst_bank, dst_addr = placements[record["id"]]
        dst_pc = foff(dst_bank, dst_addr)
        rom[dst_pc : dst_pc + len(comp)] = comp
        relocated += 1
        destinations[record["id"]] = (dst_bank, dst_addr, dst_pc, comp, script, expected)

    # 모든 압축 데이터를 먼저 쓴 뒤 C2 참조를 전수 패치한다.
    for record, src_bank, src_addr, _, _, _, _ in relocated_items:
        dst_bank, dst_addr, _, _, _, _ = destinations[record["id"]]
        old_ptr = pointer_bytes(src_bank, src_addr)
        new_ptr = pointer_bytes(dst_bank, dst_addr)
        for ref_text in record["pointer_refs"]:
            ref_bank, ref_addr = parse_snes(ref_text)
            ref_pc = foff(ref_bank, ref_addr)
            if bytes(rom[ref_pc : ref_pc + 3]) != old_ptr:
                raise SystemExit(f"C2 포인터 원본 불일치: {ref_text} -> {record['src']}")
            rom[ref_pc : ref_pc + 3] = new_ptr
            if bytes(rom[ref_pc : ref_pc + 3]) != new_ptr:
                raise SystemExit(f"C2 포인터 패치 실패: {ref_text}")
            pointer_patches += 1

    for record, _, _, _, _, _, _ in prepared:
        dst_bank, dst_addr, dst_pc, comp, script, expected = destinations[record["id"]]
        decoded, decoded_len, decoded_end = decompress_scene(rom, dst_bank, dst_addr, dict_pc)
        if decoded != script or decoded_len != len(script) or decoded_end - dst_pc != len(comp):
            raise SystemExit(f"압축 왕복 실패: {record['src']}")
        for start, cmd, padded, entry_id in expected:
            text_start = start
            codes, _ = read_text_run(decoded, text_start)
            actual = render(codes, idx2char)
            if actual != padded:
                raise SystemExit(f"렌더 역검증 실패: {entry_id} {actual!r} != {padded!r}")
        verified += 1

    Path(args.out).write_bytes(rom)
    Path("out/field_reinsertion_manifest.json").write_text(
        json.dumps(
            {
                "note": "전 필드 레코드 재배치. 최종 병합 뒤 원본 슬롯·목적지·포인터 재검증용.",
                "rejected_false_pointer_refs": catalog.get("_stats", {}).get(
                    "rejected_false_pointer_refs", []
                ),
                "records": [
                    {
                        "id": record["id"],
                        "src": record["src"],
                        "src_comp_len": record["comp_len"],
                        "dst": f"${destinations[record['id']][0]:02X}:{destinations[record['id']][1]:04X}",
                        "dst_comp_len": len(destinations[record["id"]][3]),
                        "dst_sha256": hashlib.sha256(destinations[record["id"]][3]).hexdigest(),
                        "pointer_refs": record["pointer_refs"],
                    }
                    for record, *_ in prepared
                ],
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    used, capacity = allocator.report()
    print("=== 필드/NPC 재삽입 ===")
    print(f"  텍스트 레코드 {len(prepared)} / 런 {translated_runs}")
    print(f"  원본 슬롯 수정 0 / 재배치 {relocated} / C2 포인터 패치 {pointer_patches}")
    print(f"  압축 합계 원본 {comp_orig}B → 한글 {comp_new}B")
    print(f"  어드벤처 원본 씬 회수슬롯 사용 {used}B / 가용 {capacity}B")
    print(f"  디컴프·런 위치·렌더 역검증 {verified}/{len(prepared)} PASS")
    print(f"  -> {args.out}")


if __name__ == "__main__":
    main()
