#!/usr/bin/env python3
"""최종 통합 뒤 필드 원본 슬롯·재배치 데이터·C2 포인터를 다시 검증한다."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from adv_codec import foff


ORIG = "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
OUT = "out/wgp2_kr.smc"
MANIFEST = "out/field_reinsertion_manifest.json"


def parse_snes(value: str) -> tuple[int, int]:
    bank, addr = value.removeprefix("$").split(":")
    return int(bank, 16), int(addr, 16)


def pointer_bytes(bank: int, addr: int) -> bytes:
    return bytes((addr & 0xFF, addr >> 8, bank - 0xC4))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom", default=OUT)
    ap.add_argument("--base", default=ORIG)
    ap.add_argument("--manifest", default=MANIFEST)
    args = ap.parse_args()

    original = Path(args.base).read_bytes()
    rom = Path(args.rom).read_bytes()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))

    for ref_text in manifest.get("rejected_false_pointer_refs", []):
        ref_bank, ref_addr = parse_snes(ref_text)
        ref = foff(ref_bank, ref_addr)
        if rom[ref:ref + 3] != original[ref:ref + 3]:
            raise SystemExit(f"필드 포인터 오탐 데이터 변경 감지: {ref_text}")

    for record in manifest["records"]:
        src_bank, src_addr = parse_snes(record["src"])
        src = foff(src_bank, src_addr)
        src_end = src + record["src_comp_len"]
        if rom[src:src_end] != original[src:src_end]:
            raise SystemExit(f"필드 원본 슬롯 변경 감지: {record['id']} {record['src']}")

        dst_bank, dst_addr = parse_snes(record["dst"])
        dst = foff(dst_bank, dst_addr)
        data = rom[dst:dst + record["dst_comp_len"]]
        if hashlib.sha256(data).hexdigest() != record["dst_sha256"]:
            raise SystemExit(f"필드 재배치 데이터 후속 덮어쓰기 감지: {record['id']} {record['dst']}")

        expected = pointer_bytes(dst_bank, dst_addr)
        for ref_text in record["pointer_refs"]:
            ref_bank, ref_addr = parse_snes(ref_text)
            ref = foff(ref_bank, ref_addr)
            if rom[ref:ref + 3] != expected:
                raise SystemExit(f"필드 포인터 후속 변경 감지: {ref_text} -> {record['dst']}")

    print(f"필드 최종 무결성 {len(manifest['records'])}레코드 PASS "
          f"(원본 슬롯·재배치 데이터·C2 포인터, 오탐 보존 "
          f"{len(manifest.get('rejected_false_pointer_refs', []))})")


if __name__ == "__main__":
    main()
