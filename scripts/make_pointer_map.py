#!/usr/bin/env python3
"""완전 포인터 지도 생성 (재삽입용).
각 대사 메시지를 가리키는 모든 '검증된' 포인터의 파일오프셋·타깃·종류를 열거한다.
포인터 형식: VM opcode 오퍼랜드 / ROM 포인터 테이블 엔트리 / 인라인 즉치(LDA# 0xA9) / PEA# (0xF4).
거짓양성 방지: 타깃이 해당 블록의 실제 메시지 시작주소(dialogue.json addr)여야 하고,
즉치·PEA는 오피코드 문맥으로 검증. 산출 assets/translations/pointer_map.json.
"""
import struct, json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ROM = open("roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc", 'rb').read()
def foff(b, a): return ((b & 0x3F) << 16) | a
def rd16(o): return ROM[o] | (ROM[o+1] << 8)

D = json.load(open('assets/translations/dialogue.json', encoding='utf-8'))

def block_msgs(pred):
    """{addr16: (entry_id, file_offset)} in address order."""
    m = {}
    for x in D['entries']:
        if pred(x['table_id']):
            bank = int(x['addr'].split(':')[0].lstrip('$'), 16)
            a = int(x['addr'].split(':')[1], 16)
            m[a] = (x['entry_id'], foff(bank, a), bank)
    return m

def find_all(pat, lo=0, hi=None):
    hi = hi or len(ROM); out = []; i = lo
    while True:
        j = ROM.find(pat, i)
        if j < 0 or j >= hi: break
        out.append(j); i = j + 1
    return out

def scan_immediates(S, lo, hi):
    """bank code 영역 [lo,hi)에서 A9(LDA#)·F4(PEA#) 뒤 imm16 ∈ S 를 포인터로 수집."""
    ptrs = []
    for op, kind in ((0xA9, 'lda'), (0xF4, 'pea')):
        for j in find_all(bytes([op]), lo, hi):
            v = rd16(j+1)
            if v in S:
                ptrs.append((j+1, v, kind))
    return ptrs

def vm_pointers_c7(S):
    """VM opcode: 뱅크 $C3 (file 0x03xxxx) EF CB / D4 CB 뒤 2바이트."""
    ptrs = []
    for opx in (b'\xEF\xCB', b'\xD4\xCB'):
        for j in find_all(opx, 0x030000, 0x040000):
            v = rd16(j+2)
            if v in S:
                ptrs.append((j+2, v, 'vm'))
    return ptrs

def table_pointers(bank, addr, count, S):
    base = foff(bank, addr); ptrs = []
    for k in range(count):
        v = rd16(base + 2*k)
        if v in S:
            ptrs.append((base + 2*k, v, f'table_{bank:02X}{addr:04X}'))
    return ptrs

def dedup(ptrs):
    seen = {};
    for loc, v, k in ptrs:
        seen[loc] = (loc, v, k)   # 동일 위치 중복 제거
    return sorted(seen.values())

def coverage(S, ptrs, msgs):
    """포인터로 직접 커버된 메시지 + 워크 연속(주소순 직전 메시지가 커버되고 인접)"""
    ptgt = {v for _, v, _ in ptrs}
    addrs = sorted(S)
    # adjacency: msg[i] 바로 뒤 = msg[i].file_end == msg[i+1].file_start
    covered = set(a for a in addrs if a in ptgt)
    changed = True
    # walk-continuation: 인접(연속 배치) 메시지는 앞이 커버되면 뒤도 도달
    # msg end offset:
    def end_off(a):
        o = msgs[a][1]
        while ROM[o] != 0x00:
            b = ROM[o]; o += 2 if (1 <= b <= 4 or b == 7) else 1
        return o + 1  # past terminator
    while changed:
        changed = False
        for i in range(len(addrs)-1):
            a, b = addrs[i], addrs[i+1]
            if a in covered and b not in covered and end_off(a) == msgs[b][1]:
                covered.add(b); changed = True
    return covered, ptgt

out = {}
# ---- c7_race ----
c7 = block_msgs(lambda t: t == 'c7_race'); S7 = set(c7)
p7 = vm_pointers_c7(S7) + table_pointers(0xC7, 0xA1AD, 87, S7)
p7 = dedup(p7)
cov7, tgt7 = coverage(S7, p7, c7)
out['c7_race'] = {"bank": 0xC7, "pointers": [[l, v, k] for l, v, k in p7]}
print(f"c7_race: {len(c7)} msgs | pointers {len(p7)} (distinct targets {len(tgt7)}) | covered {len(cov7)}")
print("  c7 미커버:", sorted(f'{a:04X}' for a in S7 - cov7))

# ---- c1_ui ----
c1 = block_msgs(lambda t: t.startswith('c1_')); S1 = set(c1)
p1 = table_pointers(0xC1, 0xC501, 6, S1) + table_pointers(0xC1, 0xCF90, 8, S1)
p1 += scan_immediates(S1, 0x010000, 0x020000)   # bank $C1 code
p1 = dedup(p1)
cov1, tgt1 = coverage(S1, p1, c1)
out['c1_ui'] = {"bank": 0xC1, "pointers": [[l, v, k] for l, v, k in p1]}
from collections import Counter
print(f"\nc1_ui: {len(c1)} msgs | pointers {len(p1)} (distinct targets {len(tgt1)}) | covered {len(cov1)}")
print("  종류:", Counter(k.split('_')[0] for _, _, k in p1))
print("  c1 미커버:", sorted(f'{a:04X}' for a in S1 - cov1))

# ---- d0_story ----
d0 = block_msgs(lambda t: t == 'd0_story'); S0 = set(d0)
PC = json.load(open('assets/translations/pointer_catalog.json', encoding='utf-8'))
p0 = []
for t in PC['blocks']['d0_story']['sources']['tables']:      # 카탈로그 테이블 위치(검증)
    bank = int(t['at'].split(':')[0], 16); addr = int(t['at'].split(':')[1], 16)
    p0 += table_pointers(bank, addr, t['count'], S0)
p0 += scan_immediates(S0, 0x100000, 0x110000)                # 뱅크 $D0 코드 LDA#/PEA#
p0 = dedup(p0)
cov0, tgt0 = coverage(S0, p0, d0)
out['d0_story'] = {"bank": 0xD0, "pointers": [[l, v, k] for l, v, k in p0]}
print(f"\nd0_story: {len(d0)} msgs | pointers {len(p0)} (distinct targets {len(tgt0)}) | covered {len(cov0)}")
print("  종류:", Counter(k.split('_')[0] for _, _, k in p0))
print("  d0 미커버:", sorted(f'{a:04X}' for a in S0 - cov0)[:30])

json.dump(out, open('assets/translations/pointer_map.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print("\n-> assets/translations/pointer_map.json")
