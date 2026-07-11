#!/usr/bin/env python3
"""초기 조사용 일회성 분석 스크립트 (탐색 격리 — 빌드 경로에 넣지 않음).

- 바이트 히스토그램 / 0xFF·0x00 빈공간 런 분석
- Shift-JIS 텍스트 후보 영역 스캔 (kana 밀도 우선, kanji 보조)

usage: python scripts/survey.py "roms/<파일>.smc" [출력.md]
결과는 UTF-8 마크다운 파일로 저장한다(콘솔이 cp949라 직접 출력 불가).
HiROM 변환: PC = ((bank & 0x3F) << 16) | addr.
"""
import sys
from collections import Counter

OUT = []
def emit(s=""): OUT.append(s)

def hirom_addr(pc: int) -> str:
    return f"${0xC0 + (pc >> 16):02X}:{pc & 0xFFFF:04X}"

def is_sjis_lead(b): return 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC
def is_sjis_trail(b): return (0x40 <= b <= 0x7E) or (0x80 <= b <= 0xFC)

def classify(hi, lo):
    if not (is_sjis_lead(hi) and is_sjis_trail(lo)):
        return None
    try:
        ch = bytes([hi, lo]).decode("shift_jis")
    except UnicodeDecodeError:
        return None
    c = ord(ch)
    if 0x3040 <= c <= 0x30FF: return "kana"
    if 0x4E00 <= c <= 0x9FFF: return "kanji"
    if 0xFF00 <= c <= 0xFFEF or 0x3000 <= c <= 0x303F: return "punct"
    return "other"

def main(path, outpath):
    data = open(path, "rb").read()
    n = len(data)
    emit(f"# 텍스트/바이트 조사 — {path}")
    emit(f"\n크기: {n} B ({n//1024} KB)\n")

    # --- 히스토그램 ---
    hist = Counter(data)
    emit("## 상위 바이트값 빈도 (top 10)")
    for b, c in hist.most_common(10):
        emit(f"- `0x{b:02X}`: {c:>8} ({100*c/n:5.2f}%)")

    # --- 빈공간 런 ---
    emit("\n## 빈공간 런 (0xFF/0x00 연속 >= 1024B)")
    runs = []
    i = 0
    while i < n:
        b = data[i]
        if b in (0x00, 0xFF):
            j = i
            while j < n and data[j] == b: j += 1
            if j - i >= 1024: runs.append((i, j, b))
            i = j
        else:
            i += 1
    total_free = sum(j - i for i, j, _ in runs)
    for i, j, b in sorted(runs, key=lambda r: -(r[1]-r[0]))[:25]:
        emit(f"- `0x{i:06X}-0x{j:06X}` ({j-i:>6}B) fill=0x{b:02X}  {hirom_addr(i)}")
    emit(f"\n**빈공간 합계: {total_free} B ({100*total_free/n:.1f}% of ROM), 런 {len(runs)}개**")

    # --- SJIS 스캔 ---
    kind = bytearray(n)   # 1=kana, 2=kanji, 3=punct
    i = 0
    while i < n - 1:
        cls = classify(data[i], data[i + 1])
        if cls == "kana": kind[i] = 1; i += 2
        elif cls == "kanji": kind[i] = 2; i += 2
        elif cls == "punct": kind[i] = 3; i += 2
        else: i += 1

    def scan(min_kana, label):
        WIN, STEP = 64, 16
        regs = []
        i = 0
        while i < n - WIN:
            w = kind[i:i + WIN]
            kana = w.count(1); jp = kana + w.count(2) + w.count(3)
            if kana >= min_kana and jp >= 16:
                regs.append((i, i + WIN, kana, jp))
            i += STEP
        merged = []
        for s, e, k, j in regs:
            if merged and s <= merged[-1][1] + WIN:
                merged[-1] = (merged[-1][0], e, merged[-1][2] + k, merged[-1][3] + j)
            else:
                merged.append((s, e, k, j))
        emit(f"\n## {label} — {len(merged)}개 영역")
        for s, e, k, j in sorted(merged, key=lambda r: -(r[1]-r[0]))[:20]:
            sample = data[s:s+50].decode("shift_jis", errors="replace").replace("\n"," ")
            emit(f"- `0x{s:06X}-0x{e:06X}` ({e-s:>5}B) {hirom_addr(s)} kana={k} «{sample}»")
        return merged

    scan(6, "Shift-JIS 텍스트 후보 (kana>=6/64 — 본문 대사류)")
    scan(0, "SJIS-유효 밀집 영역 (kana 무관 — 한자 테이블/코드 오검출 포함)")

    with open(outpath, "w", encoding="utf-8") as f:
        f.write("\n".join(OUT) + "\n")
    print("wrote", outpath, "lines", len(OUT))

if __name__ == "__main__":
    rom = sys.argv[1] if len(sys.argv) > 1 else "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
    out = sys.argv[2] if len(sys.argv) > 2 else "tmp/survey_report.md"
    main(rom, out)
