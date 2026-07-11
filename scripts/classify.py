#!/usr/bin/env python3
"""ROM을 블록 단위로 분류: 빈공간 / 압축(고엔트로피) / 폰트·타일 후보(저엔트로피·구조적) / 코드.
폰트는 보통 비압축이라 엔트로피가 낮고 0x00 비율이 중간(글리프 여백)이다."""
import sys, math
from collections import Counter

def entropy(block):
    c = Counter(block); n = len(block)
    return -sum((v/n) * math.log2(v/n) for v in c.values())

def hirom(pc): return f"${0xC0+(pc>>16):02X}:{pc&0xFFFF:04X}"

def main(path):
    data = open(path, "rb").read()
    n = len(data)
    BLK = 2048
    rows = []
    for off in range(0, n, BLK):
        b = data[off:off+BLK]
        if len(b) < BLK: break
        zero = b.count(0)/BLK
        ff = b.count(0xFF)/BLK
        ent = entropy(b)
        if zero > 0.95 or ff > 0.95:
            kind = "empty"
        elif ent > 7.3:
            kind = "compressed"
        elif ent < 5.5 and 0.05 < zero < 0.75:
            kind = "FONT?"     # 저엔트로피 + 여백 있는 구조 → 폰트/타일 후보
        else:
            kind = "code/data"
        rows.append((off, ent, zero, ff, kind))

    # 폰트 후보 연속 구간 병합
    out = ["# 블록 분류 (2KB 단위)\n"]
    font = [r for r in rows if r[4] == "FONT?"]
    out.append(f"## FONT? 후보 블록: {len(font)}개 (2KB each)")
    # 연속 구간 묶기
    spans = []
    for off, ent, zero, ff, k in font:
        if spans and off == spans[-1][1]:
            spans[-1][1] = off + BLK
            spans[-1][2].append(ent)
        else:
            spans.append([off, off+BLK, [ent]])
    spans.sort(key=lambda s: -(s[1]-s[0]))
    for s, e, ents in spans[:30]:
        out.append(f"- `0x{s:06X}-0x{e:06X}` ({(e-s)//1024:>3}KB) {hirom(s)} 평균엔트로피={sum(ents)/len(ents):.2f}")

    # 요약 카운트
    kc = Counter(r[4] for r in rows)
    out.append("\n## 전체 블록 분포")
    for k, v in kc.most_common():
        out.append(f"- {k}: {v} 블록 ({v*BLK//1024}KB, {100*v/len(rows):.1f}%)")

    open("tmp/classify_report.md","w",encoding="utf-8").write("\n".join(out)+"\n")
    print("wrote tmp/classify_report.md; FONT? spans:", len(spans))

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv)>1 else "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc")
