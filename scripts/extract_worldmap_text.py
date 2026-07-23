#!/usr/bin/env python3
"""월드맵 퀴즈 DB 추출 → worldmap_text.json.

실측 구조:
  - 포인터 테이블: $C6:A08D, 350 × 16-bit little-endian in-bank pointer
  - 문자열 영역  : $C6:A349..$C6:AB10 (마지막 다음 주소 $AB11)
  - 5문자열/문항: 질문 1 + 선택지 4
  - 문항 구성    : 덧셈·뺄셈 20 + 곱셈·나눗셈 20 + 정보 30

$C6:7C73..9C56은 어드벤처 압축 딕셔너리다. 그 구간에서 보이는
일본어 조각을 독립 문자열로 오인하지 않도록 이 추출기는 포인터로
증명된 DB만 다룬다.
"""
from __future__ import annotations

import hashlib
import json
import sys
import zlib
from pathlib import Path

sys.path.insert(0, "scripts")
from decode_script import decode, encode, load_tbl, parse, render


ROM_PATH = Path("roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc")
KR_PATH = Path("assets/translations/worldmap_kr.json")
OUT_PATH = Path("assets/translations/worldmap_text.json")

BANK = 0xC6
PTR_ADDR = 0xA08D
PTR_COUNT = 350
TEXT_START = 0xA349
TEXT_END = 0xAB11
GROUPS = (
    ("math_add_sub", 0, 100, 20),
    ("math_mul_div", 100, 200, 20),
    ("lore_quiz", 200, 350, 30),
)
FIXED_MESSAGES = (
    # id, original address, exclusive end, 24-bit pointer fields in bank $C6
    ("math_prompt", 0xA017, 0xA035, (0x9F92, 0x9FD0)),
    ("math_correct", 0xA035, 0xA040, (0x9F95,)),
    ("math_mul_correct", 0xA040, 0xA044, (0x9FD3,)),
    ("math_wrong", 0xA044, 0xA04D, (0x9F98, 0x9FD6)),
    ("lore_prompt", 0xA04D, 0xA06C, (0xA00E,)),
    ("lore_correct", 0xA06C, 0xA073, (0xA011,)),
    ("lore_wrong", 0xA073, 0xA07B, (0xA014,)),
)
STATUS_PROGRAM_ADDR = 0x8D8A
STATUS_PROGRAM_RAW = bytes.fromhex(
    "FF FF 01 14 FF FF 23 2E FF FF 47 39 58 FF FF 9A "
    "FF FF FF FF 05 13 12 07 FF FF FF FF 00"
)

# glyph_table.tsv의 알려진 라벨/원문 결락. raw/tokens는 바꾸지 않고 사람이
# 검수하는 jp 필드만 문맥상 확정 원문으로 교정한다.
JP_FIXES = {
    200: ("開会武", "開会式"),
    205: ("著て", "着て"),
    320: ("石　の", "石像の"),
}


def foff(bank: int, addr: int) -> int:
    return ((bank & 0x3F) << 16) | addr


def fixed_jp(entry_id: int, decoded_jp: str) -> str:
    if entry_id not in JP_FIXES:
        return decoded_jp
    old, new = JP_FIXES[entry_id]
    if old not in decoded_jp:
        raise SystemExit(f"JP_FIXES #{entry_id}: {old!r}가 디코드 결과에 없음")
    return decoded_jp.replace(old, new)


def main() -> None:
    rom = ROM_PATH.read_bytes()
    if len(rom) != 2 * 1024 * 1024:
        raise SystemExit(f"원본 ROM 크기 불일치: {len(rom)}")
    crc = zlib.crc32(rom) & 0xFFFFFFFF
    md5 = hashlib.md5(rom).hexdigest()
    if crc != 0x4459D4D0 or md5 != "acdeb2ee6ef7b460c5dfed6957f8581a":
        raise SystemExit(f"원본 ROM 해시 불일치: CRC32 {crc:08X} MD5 {md5}")

    tbl = load_tbl("assets/translation_guide/glyph_table.tsv")
    poff = foff(BANK, PTR_ADDR)
    ptrs = [int.from_bytes(rom[poff + 2 * i:poff + 2 * i + 2], "little")
            for i in range(PTR_COUNT)]
    if ptrs[0] != TEXT_START or ptrs[-1] != 0xAB0A:
        raise SystemExit(f"포인터 경계 불일치: ${ptrs[0]:04X}..${ptrs[-1]:04X}")
    if ptrs != sorted(set(ptrs)):
        raise SystemExit("포인터가 엄격 오름차순·고유가 아님")

    kr_data = json.loads(KR_PATH.read_text(encoding="utf-8"))
    lore_sets = kr_data.get("lore_sets", [])
    if len(lore_sets) != 30:
        raise SystemExit(f"정보 퀴즈 번역은 30세트여야 함: {len(lore_sets)}")
    quiz_ui = kr_data.get("quiz_ui", {})
    ui_translations = quiz_ui.get("fixed_messages", [])
    if [row.get("id") for row in ui_translations] != [
        row[0] for row in FIXED_MESSAGES
    ]:
        raise SystemExit("quiz_ui.fixed_messages의 ID·순서가 원본 고정 메시지와 다름")

    entries = []
    roundtrip_ok = 0
    for entry_id, addr in enumerate(ptrs):
        end = ptrs[entry_id + 1] if entry_id + 1 < PTR_COUNT else TEXT_END
        raw = rom[foff(BANK, addr):foff(BANK, end)]
        if not raw or raw[-1] != 0x00:
            raise SystemExit(f"#{entry_id} ${addr:04X}: 0x00 종료 슬롯이 아님")
        toks = decode(raw)
        # 2바이트 글리프의 두 번째 바이트는 0x00일 수 있다(예: glyph $1F0).
        # 따라서 raw 내부의 0x00을 단순 검색하지 않고 디코더가 슬롯 끝까지 정확히
        # 소비했는지로 조기 종료를 판정한다.
        if encode(toks) != raw or not toks or toks[-1] != ("ctrl", "end", b""):
            raise SystemExit(f"#{entry_id} ${addr:04X}: 디코더 소비/종료 경계 불일치")
        undefined = [t for t in toks if t[0] == "ctrl" and t[1].startswith("op")]
        unmapped = [t[1] for t in toks if t[0] == "glyph" and t[1] not in tbl]
        if undefined or unmapped:
            raise SystemExit(
                f"#{entry_id} ${addr:04X}: 미정의op={undefined} 미매핑={unmapped}"
            )
        token_text = render(toks)
        if encode(parse(token_text)) != raw:
            raise SystemExit(f"#{entry_id} ${addr:04X}: encode(parse) 라운드트립 실패")
        roundtrip_ok += 1
        decoded_jp = render(toks, tbl)
        jp = fixed_jp(entry_id, decoded_jp)

        if entry_id < 100:
            cluster = "math_add_sub"
            local = entry_id
            kr = jp
            kr_full = kr
        elif entry_id < 200:
            cluster = "math_mul_div"
            local = entry_id - 100
            kr = jp
            kr_full = kr
        else:
            cluster = "lore_quiz"
            local = entry_id - 200
            qidx, slot = divmod(local, 5)
            trans = lore_sets[qidx]
            expected_addr = trans.get("addr")
            actual_addr = f"$C6:{ptrs[200 + qidx * 5]:04X}"
            if expected_addr != actual_addr:
                raise SystemExit(
                    f"정보 문항 {qidx}: 번역 주소 {expected_addr!r} != {actual_addr}"
                )
            kr = trans["question"] if slot == 0 else trans["choices"][slot - 1]
            kr_full = (
                trans.get("question_full", trans["question"])
                if slot == 0 else kr
            )

        qidx, slot = divmod(local, 5)
        row = {
            "entry_id": entry_id,
            "cluster": cluster,
            "question_index": qidx,
            "role": "question" if slot == 0 else f"choice_{slot}",
            "pointer_addr": f"$C6:{PTR_ADDR + entry_id * 2:04X}",
            "addr": f"$C6:{addr:04X}",
            "file_offset": f"0x{foff(BANK, addr):06X}",
            "n_bytes": len(raw),
            "raw_hex": raw.hex().upper(),
            "text": token_text,
            "jp": jp,
            "kr_full": kr_full,
            "kr": kr,
            "abbreviated": kr_full != kr,
        }
        if jp != decoded_jp:
            row["jp_raw_render"] = decoded_jp
        entries.append(row)

    fixed_messages = []
    fixed_roundtrip_ok = 0
    for (message_id, addr, end, pointer_fields), trans in zip(
        FIXED_MESSAGES, ui_translations, strict=True
    ):
        raw = rom[foff(BANK, addr):foff(BANK, end)]
        toks = decode(raw)
        if encode(toks) != raw or not toks or toks[-1] != ("ctrl", "end", b""):
            raise SystemExit(
                f"퀴즈 UI {message_id} ${BANK:02X}:{addr:04X}: "
                "디코더 소비/종료 경계 불일치"
            )
        jp = render(toks, tbl)
        for pointer_addr in pointer_fields:
            pointer = rom[foff(BANK, pointer_addr):foff(BANK, pointer_addr) + 3]
            expected = addr.to_bytes(2, "little") + bytes((BANK,))
            if pointer != expected:
                raise SystemExit(
                    f"퀴즈 UI {message_id} 포인터 ${BANK:02X}:{pointer_addr:04X} "
                    f"{pointer.hex().upper()} != {expected.hex().upper()}"
                )
        text_kr_full = trans["text_kr_full"]
        text_kr = trans["text_kr"]
        fixed_messages.append({
            "id": message_id,
            "addr": f"${BANK:02X}:{addr:04X}",
            "file_offset": f"0x{foff(BANK, addr):06X}",
            "pointer_fields": [
                f"${BANK:02X}:{pointer_addr:04X}"
                for pointer_addr in pointer_fields
            ],
            "n_bytes": len(raw),
            "raw_hex": raw.hex().upper(),
            "text": render(toks),
            "jp": jp,
            "kr_full": text_kr_full,
            "kr": text_kr,
            "abbreviated": text_kr_full != text_kr,
        })
        fixed_roundtrip_ok += 1

    status_raw = rom[
        foff(0xC0, STATUS_PROGRAM_ADDR):
        foff(0xC0, STATUS_PROGRAM_ADDR) + len(STATUS_PROGRAM_RAW)
    ]
    if status_raw != STATUS_PROGRAM_RAW:
        raise SystemExit(
            f"퀴즈 상태줄 프로그램 $C0:{STATUS_PROGRAM_ADDR:04X} 원본 불일치"
        )
    status_translation = quiz_ui.get("status_line", {})
    for field in ("text_jp_full", "text_kr_full", "text_kr", "abbreviated"):
        if field not in status_translation:
            raise SystemExit(f"quiz_ui.status_line.{field} 누락")

    # 5개 단위와 클러스터 경계는 소비 루틴의 question*10B 계산과 직결된다.
    for name, start, end, questions in GROUPS:
        block = entries[start:end]
        if len(block) != questions * 5:
            raise SystemExit(f"{name}: {len(block)} != {questions}*5")
        if any(e["cluster"] != name for e in block):
            raise SystemExit(f"{name}: 클러스터 태그 불일치")

    out = {
        "schema": 1,
        "encoding": "system1 variable glyph (00 end, 05 nl, 01-04 prefix)",
        "source": {
            "bank": "$C6",
            "pointer_table": "$C6:A08D",
            "pointer_count": PTR_COUNT,
            "pointer_format": "16-bit little-endian, in-bank",
            "text_span": "$C6:A349..$C6:AB10",
            "renderer": "$C0:8EAD -> $C0:6634/$C0:6699 -> glyph fetch $C0:6827",
            "copy_buffer_limit": 256,
        },
        "clusters": [
            {"id": name, "entry_start": start, "entry_count": end - start,
             "question_count": questions}
            for name, start, end, questions in GROUPS
        ],
        "stats": {
            "entries": len(entries),
            "questions": len(entries) // 5,
            "roundtrip_ok": roundtrip_ok,
            "translated_lore_entries": 150,
            "fixed_messages": len(fixed_messages),
            "fixed_roundtrip_ok": fixed_roundtrip_ok,
        },
        "fixed_messages": fixed_messages,
        "status_line": {
            "program_addr": f"$C0:{STATUS_PROGRAM_ADDR:04X}",
            "file_offset": f"0x{foff(0xC0, STATUS_PROGRAM_ADDR):06X}",
            "raw_hex": STATUS_PROGRAM_RAW.hex().upper(),
            **status_translation,
        },
        "entries": entries,
    }
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"월드맵 퀴즈 {len(entries)}문자열 / {len(entries)//5}문항 -> {OUT_PATH}")
    print("  산수 40문항(표기 보존) + 정보 30문항(한글 번역)")
    print(f"  raw==ROM + encode(parse): {roundtrip_ok}/{len(entries)} PASS")
    print(
        f"  시작·정답·오답 고정 메시지 round-trip: "
        f"{fixed_roundtrip_ok}/{len(fixed_messages)} PASS"
    )
    print(f"  상태줄 직접 타일 프로그램 $C0:{STATUS_PROGRAM_ADDR:04X} 원본 일치")


if __name__ == "__main__":
    main()
