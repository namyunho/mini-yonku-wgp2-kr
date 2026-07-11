#!/usr/bin/env python3
"""대사 추출기 — 확정 대사 블록들(BLOCKS)을 종료자 워크로 전수 추출·디코드.

역공학 근거(docs/04·06):
- 인코딩 = 1바이트 가변길이(공통 글리프 표), 종료자 0x00. 여러 뱅크에 블록 분산.
- 확정 블록: c7_race($C7, 레이스/메뉴), d0_story($D0, 스토리/배틀), c1_form($C1, 포메이션).
  (ROM 전역 클린런 스캔 + 실측 디코드로 확정. 더 있을 수 있음 — docs/06 완전성 주석.)
- $C7 블록은 $C3 VM opcode `EF CB`($CBEF)/`D4 CB`($CBD4) 뒤 2바이트로 포인터 교차검증.

산출: assets/translations/dialogue.json (raw 보존+일본어 text_jp), tmp/trace/extract_report.md
"""
import json, struct, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from decode_script import decode, render, load_tbl

GLYPH_TBL = "assets/translation_guide/glyph_table.tsv"

ROM_PATH = "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
C7_BASE = 0x070000          # $C7:0000 파일 오프셋 (HiROM 뱅크 0x07)
C3_LO, C3_HI = 0x030000, 0x040000
SET_MSG_OPS = {"EFCB": "$CBEF", "D4CB": "$CBD4"}  # set-message VM opcodes ($C7 블록 참조)

# 확정 대사 블록 (완전성 닫힘 — 파서 $C1:9554 호출처 7곳 역추적, docs/07). file_start..file_end.
# 정적 텍스트 뱅크 = $C7/$D0/$C1 셋뿐. 같은 커스텀 인코딩·글리프 표를 공유.
# c1는 연속 블록이 아니라 대사 4클러스터가 바이너리 데이터로 분리 → 클러스터별 별도 열거
# (이전 단일 c1_form $CFAF는 포메이션 클러스터만 본 오류; 데이터 구간 제외).
BLOCKS = [
    # id,             snes,      file_start, file_end,  설명
    ("c7_race",     "$C7:89E2", 0x0789E2, 0x07A001, "레이스 중계·조작 안내(VM $C3 EF CB/D4 CB + 테이블 $C7:A1AD)"),
    ("d0_story",    "$D0:C80B", 0x10C80B, 0x10E828, "스토리/배틀 대사(터치콜 테이블 $D0:C778, 스토리 $D0:F78B군)"),
    ("c1_setting",  "$C1:C868", 0x01C868, 0x01C980, "c1 클러스터1: 세팅 세이브/로드 UI"),
    ("c1_machines", "$C1:C981", 0x01C981, 0x01C9C0, "c1 클러스터2: 플레이어 마신명(테이블 $C1:C501)"),
    ("c1_garage",   "$C1:CE53", 0x01CE53, 0x01CF1E, "c1 클러스터3: 가레지/그리드 선택 UI"),
    ("c1_formation","$C1:CFDC", 0x01CFDC, 0x01D183, "c1 클러스터4: 포메이션 메뉴/도움말(테이블 $C1:CF90)"),
]

def scan_c7_pointers(rom):
    """$C3 VM 스트림에서 set-message opcode 뒤 2바이트 $C7 포인터 수집(c7_race 블록용)."""
    ptrs = {}  # c7_ptr(뱅크상대) -> list of (src_file_off, opcode)
    for op_hex, opname in SET_MSG_OPS.items():
        op = bytes.fromhex(op_hex)
        i = C3_LO
        while True:
            j = rom.find(op, i)
            if j < 0 or j >= C3_HI:
                break
            p = struct.unpack_from("<H", rom, j + 2)[0]
            ptrs.setdefault(p, []).append((j, opname))
            i = j + 1
    return ptrs

def walk_block(rom, fstart, fend):
    """파일오프셋 fstart..fend 구간을 종료자 0x00로 메시지 분할(종료자 포함)."""
    msgs = []
    i = fstart
    while i < fend:
        s = i
        while i < fend and rom[i] != 0x00:
            b = rom[i]
            i += 2 if (0x01 <= b <= 0x04 or b == 0x07) else 1
        raw = bytes(rom[s:i + 1])  # include terminator
        msgs.append((s, raw))
        i += 1
    return msgs

def suspect_flags(toks):
    """경계 노이즈·비대사 신호: 미매핑 글리프(>0x3EF) 또는 미정의 op(0x08-0x0F)."""
    fl = []
    if any(t[0] == "glyph" and t[1] > 0x3EF for t in toks):
        fl.append("unmapped_glyph")
    if any(t[0] == "ctrl" and t[1].startswith("op") for t in toks):
        fl.append("undefined_op")
    return fl

def main():
    rom = open(ROM_PATH, "rb").read()
    tbl = load_tbl(GLYPH_TBL) if os.path.exists(GLYPH_TBL) else None
    c7_ptrs = scan_c7_pointers(rom)  # 뱅크상대 주소 키

    tables = []
    all_entries = []
    eid = 0
    for tid, snes, fstart, fend, desc in BLOCKS:
        bank_base = fstart & 0xFF0000
        msgs = walk_block(rom, fstart, fend)
        boundaries = {s & 0xFFFF for s, _ in msgs}
        # $C7 블록만 포인터 카탈로그 교차검증
        refs_map, off_boundary = {}, []
        if tid == "c7_race":
            for p, srcs in c7_ptrs.items():
                if p in boundaries:
                    refs_map[bank_base | p] = srcs
                else:
                    off_boundary.append(p)
        entries = []
        for s, raw in msgs:
            toks = decode(raw)
            refs = refs_map.get(s, [])
            fl = suspect_flags(toks)
            if not refs and tid == "c7_race":
                fl.append("no_pointer_ref")
            entries.append({
                "entry_id": eid,
                "table_id": tid,
                "addr": f"{snes[:4]}{s & 0xFFFF:04X}",
                "file_offset": f"0x{s:06X}",
                "raw_hex": raw.hex().upper(),
                "n_bytes": len(raw),
                "n_glyphs": sum(1 for t in toks if t[0] == "glyph"),
                "text": render(toks),
                "text_jp": render(toks, tbl) if tbl else None,
                "referenced_by": [f"0x{o:06X}:{nm}" for o, nm in refs],
                "flags": fl,
            })
            eid += 1
        suspect = sum(1 for e in entries if e["flags"] and e["flags"] != ["no_pointer_ref"])
        tables.append({
            "table_id": tid, "snes": snes, "desc": desc,
            "file_start": f"0x{fstart:06X}", "file_end": f"0x{fend:06X}",
            "messages": len(msgs), "suspect_entries": suspect,
            "pointers_found": sum(len(v) for v in refs_map.values()) if tid == "c7_race" else None,
            "pointers_off_boundary": len(off_boundary) if tid == "c7_race" else None,
        })
        all_entries.extend(entries)

    out = {
        "encoding": "1byte-varlen (docs/04)", "terminator": "00",
        "glyph_table": GLYPH_TBL,
        "tables": tables,
        "stats": {"total_messages": len(all_entries),
                  "total_suspect": sum(t["suspect_entries"] for t in tables)},
        "entries": all_entries,
    }
    os.makedirs("assets/translations", exist_ok=True)
    with open("assets/translations/dialogue.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    os.makedirs("tmp/trace", exist_ok=True)
    with open("tmp/trace/extract_report.md", "w", encoding="utf-8") as f:
        f.write("# 대사 추출 리포트 (다중 블록)\n\n")
        f.write("| 블록 | 위치 | 메시지 | suspect | 포인터 |\n|---|---|---|---|---|\n")
        for t in tables:
            f.write(f"| {t['table_id']} | {t['snes']}..{t['file_end']} | {t['messages']} | {t['suspect_entries']} | {t['pointers_found']} |\n")
        f.write(f"\n**총 메시지 {len(all_entries)}개** (suspect {out['stats']['total_suspect']})\n\n")
        for t in tables:
            f.write(f"## {t['table_id']} — {t['desc']}\n\n")
            for e in [x for x in all_entries if x['table_id'] == t['table_id']][:12]:
                mark = " ⚠" + ",".join(e['flags']) if e['flags'] else ""
                f.write(f"- {e['addr']} ({e['n_glyphs']}g): `{(e['text_jp'] or e['text'])[:70]}`{mark}\n")
            f.write("\n")

    print(f"총 메시지 {len(all_entries)}개 (블록 {len(tables)}개), suspect {out['stats']['total_suspect']}")
    for t in tables:
        print(f"  {t['table_id']}: {t['messages']}개 ({t['snes']}..{t['file_end']}), suspect {t['suspect_entries']}")
    print("→ assets/translations/dialogue.json, tmp/trace/extract_report.md")

if __name__ == "__main__":
    main()
