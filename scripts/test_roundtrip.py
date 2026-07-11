#!/usr/bin/env python3
"""라운드트립 검증 — 대사 추출물의 무손실성 증명.

핵심 불변식(create-kr-patch 텍스트추출 §5):
    encode(parse(text)) == raw_hex == 원본 ROM의 해당 바이트

전 엔트리에 대해 세 값의 일치를 확인한다. 하나라도 불일치면 실패(비영 종료).
추출기·인코딩 모델 수정 시마다 실행하는 회귀 게이트.
"""
import json, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from decode_script import parse, encode

ROM_PATH = "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
JSON_PATH = "assets/translations/dialogue.json"

def main():
    rom = open(ROM_PATH, "rb").read()
    data = json.load(open(JSON_PATH, encoding="utf-8"))
    entries = data["entries"]
    n = len(entries)
    fail_rt = []   # encode(parse(text)) != raw
    fail_rom = []  # raw != ROM
    total_bytes = 0

    for e in entries:
        raw = bytes.fromhex(e["raw_hex"])
        total_bytes += len(raw)
        # 1) raw == ROM 파일 바이트
        off = int(e["file_offset"], 16)
        if rom[off:off + len(raw)] != raw:
            fail_rom.append(e["entry_id"])
        # 2) encode(parse(text)) == raw
        try:
            reenc = encode(parse(e["text"]))
        except Exception as ex:
            fail_rt.append((e["entry_id"], f"exc: {ex}")); continue
        if reenc != raw:
            fail_rt.append((e["entry_id"], f"got {reenc.hex().upper()} want {e['raw_hex']}"))

    print(f"엔트리 {n}개, 총 {total_bytes} 바이트")
    print(f"  raw==ROM      : {'OK' if not fail_rom else f'FAIL {len(fail_rom)}건'}")
    print(f"  encode(parse)  : {'OK' if not fail_rt else f'FAIL {len(fail_rt)}건'}")
    if fail_rom:
        print("  raw≠ROM 엔트리:", fail_rom[:20])
    if fail_rt:
        print("  라운드트립 실패:")
        for eid, msg in fail_rt[:20]:
            print(f"    #{eid}: {msg}")
    ok = not fail_rom and not fail_rt
    print("결과:", "✅ PASS: lossless (all entries match)" if ok else "❌ FAIL: mismatch")
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
