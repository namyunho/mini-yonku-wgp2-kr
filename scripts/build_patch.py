#!/usr/bin/env python3
"""한글 대사 재삽입 빌드 (재실행 가능·자동).
입력: dialogue.json(text_kr) + glyph_table.tsv + 한글 bin 폰트 + pointer_map.json.
과정: 동적 글리프 할당 → 폰트 시트 주입 → 메시지 재인코딩 → 자유공간 재배치 → 포인터 패치 → 역검증.
번역을 고치면 dialogue.json만 바꾸고 재실행하면 전부 자동 재생성된다.

Phase 1 = c7_race + c1_ui (동일 뱅크 재배치, DBR 패치 불필요).
"""
import json, struct, sys, io, argparse
from collections import Counter
sys.path.insert(0, 'scripts')
from decode_script import decode, render, encode, load_tbl

ROMPATH = "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
FONT_BASE = 0x0A1137      # $CA:1137 폰트 시트
WIDTH_BASE = 0x0A9137     # $CA:9137 폭 테이블
MAX_GLYPH = 0x400         # 0x000..0x3FF (시트↔폭테이블 경계)
ONE_BYTE_MAX = 0xF0       # idx < 0xF0 → 1바이트 인코딩
BIN_GLYPH_BYTES = 32

# 재배치 자유공간 (뱅크, snes주소, 파일오프셋, 용량)
FREE = {
    'c7_race': (0xC7, 0xB49B, (0x07 << 16) | 0xB49B, 19301),
    'c1_ui':   (0xC1, 0x9843, (0x01 << 16) | 0x9843, 10173),
}

def foff(b, a): return ((b & 0x3F) << 16) | a

# ---- 폰트 인코딩 (poc_font.rs 포팅) ----
def base03(n): return 16 * (((n & ~7) * 2) + (n & 7))

def encode_glyph(rom, n, px):
    base = FONT_BASE + base03(n)
    for rf in range(16):
        block = base if rf < 8 else base + 0x80
        r = rf & 7
        left = right = 0
        for c in range(8):
            if px[rf][c]:      left |= 1 << (7 - c)
            if px[rf][8 + c]:  right |= 1 << (7 - c)
        rom[block + 2*r + 1] = left
        rom[block + 2*r]     = right

def decode_bin_glyph(bin_, bin_idx, yshift):
    off = bin_idx * BIN_GLYPH_BYTES
    g = bin_[off:off + BIN_GLYPH_BYTES]
    out = [[0]*16 for _ in range(16)]
    for r in range(16):
        tr = r + yshift
        if not (0 <= tr < 16): continue
        left, right = g[2*r], g[2*r+1]
        for c in range(8):
            out[tr][c]     = (left  >> (7 - c)) & 1
            out[tr][8 + c] = (right >> (7 - c)) & 1
    return out

def ink_width(px):
    """오른쪽 잉크 경계 → advance(px). 없으면 최소."""
    right = 0
    for r in range(16):
        for c in range(15, -1, -1):
            if px[r][c]: right = max(right, c + 1); break
    return right

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--blocks', nargs='+', default=['c7_race', 'c1_ui'])
    ap.add_argument('--out', default='out/wgp2_kr.smc')
    a = ap.parse_args()

    rom = bytearray(open(ROMPATH, 'rb').read())
    D = json.load(open('assets/translations/dialogue.json', encoding='utf-8'))
    tbl = load_tbl('assets/translation_guide/glyph_table.tsv')          # idx -> char (게임)
    ch2idx_game = {}
    for i, c in tbl.items():
        ch2idx_game.setdefault(c, i)
    binf = open('assets/fonts/x12y12pxMaruMinyaHangul_2350.bin', 'rb').read()
    gm = json.load(open('assets/fonts/x12y12pxMaruMinyaHangul_glyphmap.json', encoding='utf-8'))
    pmap = json.load(open('assets/translations/pointer_map.json', encoding='utf-8'))

    entries = {x['entry_id']: x for x in D['entries']}
    blocks = {}
    for bid in a.blocks:
        blocks[bid] = [x for x in D['entries']
                       if x['table_id'] == bid or (bid == 'c1_ui' and x['table_id'].startswith('c1_'))]

    # ---- 대상 블록 text_kr에 실제 쓰인 문자 수집 ----
    import re
    def strip_tok(s): return re.sub(r'\{[^}]*\}', '', s)
    freq = Counter(); used_other = set()
    for bid, es in blocks.items():
        for x in es:
            for c in strip_tok(x['text_kr']):
                if 0xAC00 <= ord(c) <= 0xD7A3:
                    freq[c] += 1
                elif c not in (' ', '　'):
                    used_other.add(c)

    # ---- 유지 문자 → 기존 게임 인덱스 (실제 쓰인 것만) ----
    keep_map = {'　': 0x001, ' ': 0x000}   # 전각공백 8px / 반각 4px
    for c in sorted(used_other):
        if c not in ch2idx_game:
            sys.exit(f"게임 글리프에 없는 유지 문자: {c!r} (U+{ord(c):04X})")
        keep_map[c] = ch2idx_game[c]
    kept_indices = set(keep_map.values())
    syllables = [c for c, _ in freq.most_common()]   # 빈도 내림차순

    # ---- 동적 글리프 할당: 자유 슬롯 = 0..0x3FF - kept ----
    free_slots = [i for i in range(MAX_GLYPH) if i not in kept_indices]
    one_byte = [i for i in free_slots if i < ONE_BYTE_MAX]   # 1바이트(≤176)
    two_byte = [i for i in free_slots if i >= ONE_BYTE_MAX]
    alloc = one_byte + two_byte                              # 빈도순 배정: 앞=1바이트
    if len(syllables) > len(alloc):
        sys.exit(f"글리프 부족: 음절 {len(syllables)} > 자유슬롯 {len(alloc)}")
    kor2idx = {c: alloc[i] for i, c in enumerate(syllables)}

    char2idx = dict(keep_map); char2idx.update(kor2idx)

    # ---- 폰트 주입 (한글 글리프 + 폭) ----
    inj = 0
    for c, idx in kor2idx.items():
        px = decode_bin_glyph(binf, gm[c], -2)   # binyshift -2 (게임 상단정렬)
        encode_glyph(rom, idx, px)
        rom[WIDTH_BASE + idx] = min(16, ink_width(px) + 2)   # advance
        inj += 1

    # ---- 메시지 재인코딩 ----
    _TOK = re.compile(r'\[|\]|\{[^}]*\}')
    def to_tokens(text):
        toks, i = [], 0
        for m in re.finditer(r'\{([^}]*)\}|([^{]+)', text):
            if m.group(1) is not None:
                name = m.group(1)
                if name.startswith('trunc'):
                    toks.append(('ctrl', 'end', b''))       # 블록끝 잘림 → 정상 종료로
                else:
                    toks.append(('ctrl', name, b''))
            else:
                for ch in m.group(2):
                    if ch not in char2idx:
                        raise KeyError(f"미매핑 문자 {ch!r} (U+{ord(ch):04X})")
                    toks.append(('glyph', char2idx[ch], 0))
        if not toks or toks[-1] != ('ctrl', 'end', b''):
            toks.append(('ctrl', 'end', b''))
        return toks

    enc = {}   # entry_id -> bytes
    for bid, es in blocks.items():
        for x in es:
            enc[x['entry_id']] = encode(to_tokens(x['text_kr']))

    # ---- 재배치 + 포인터 패치 ----
    report = {}
    for bid, es in blocks.items():
        bank, snes0, file0, cap = FREE[bid]
        es_sorted = sorted(es, key=lambda x: int(x['addr'].split(':')[1], 16))
        old2new = {}
        cur = snes0
        blob = bytearray()
        for x in es_sorted:
            old = int(x['addr'].split(':')[1], 16)
            old2new[old] = cur
            b = enc[x['entry_id']]
            blob += b
            cur += len(b)
        if len(blob) > cap:
            sys.exit(f"{bid}: 재배치 {len(blob)}B > 자유공간 {cap}B")
        rom[file0:file0 + len(blob)] = blob
        # 포인터 패치
        patched = 0
        for loc, old_target, kind in pmap[bid]['pointers']:
            if old_target in old2new:
                struct.pack_into('<H', rom, loc, old2new[old_target])
                patched += 1
        report[bid] = (len(es), len(blob), cap, patched, len(pmap[bid]['pointers']), old2new, bank)

    # ---- 출력 ----
    import os
    os.makedirs('out', exist_ok=True)
    open(a.out, 'wb').write(rom)

    # ---- 역검증: 새 위치에서 재디코드 == text_kr ----
    idx2char = {i: c for c, i in char2idx.items()}
    def decode_at(bank, addr):
        o = foff(bank, addr); s = o
        while rom[o] != 0x00:
            b = rom[o]; o += 2 if (1 <= b <= 4 or b == 7) else 1
        toks = decode(rom[s:o+1])
        return render(toks, idx2char)
    print(f"\n=== 폰트: 한글 {inj} 글리프 주입 (자유슬롯 {len(alloc)}, 음절 {len(syllables)}) ===")
    total_ok = total = 0
    for bid, (nmsg, blen, cap, patched, nptr, old2new, bank) in report.items():
        ok = 0
        for x in blocks[bid]:
            old = int(x['addr'].split(':')[1], 16)
            got = decode_at(bank, old2new[old])
            want = render(decode(bytes.fromhex('')), None)  # placeholder
            # 기대값 = text_kr에서 {trunc}→{end} 정규화 후 렌더 비교
            exp = re.sub(r'\{trunc[0-9A-Fa-f]+\}', '{end}', x['text_kr'])
            if not exp.endswith('{end}'): exp += '{end}'
            ok += (got == exp)
        total_ok += ok; total += nmsg
        print(f"{bid:8s}: msgs {nmsg} | 재배치 {blen}/{cap}B | 포인터패치 {patched}/{nptr} | 역검증 {ok}/{nmsg}")
    print(f"\n역검증 합계: {total_ok}/{total}  -> {a.out}")
    if total_ok != total:
        sys.exit("역검증 실패 (일부 메시지 불일치)")

if __name__ == '__main__':
    main()
