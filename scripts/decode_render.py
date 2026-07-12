#!/usr/bin/env python3
"""box_render.txt(펜 X 로그)를 실제 텍스트로 디코드.
build_patch.py의 글리프 할당을 그대로 재현해 idx→char 역매핑을 만든 뒤,
로그를 base(라인)별로 묶어 각 줄의 시작 penX와 텍스트를 출력."""
import json, re, sys
from collections import Counter
sys.path.insert(0, 'scripts')
from decode_script import load_tbl

MAX_GLYPH = 0x400
ONE_BYTE_MAX = 0xF0

def build_char2idx():
    D = json.load(open('assets/translations/dialogue.json', encoding='utf-8'))
    tbl = load_tbl('assets/translation_guide/glyph_table.tsv')
    ch2idx_game = {}
    for i, c in tbl.items():
        ch2idx_game.setdefault(c, i)
    def strip_tok(s): return re.sub(r'\{[^}]*\}', '', s)
    blocks = {}
    for bid in ['c7_race', 'c1_ui', 'd0_story']:
        blocks[bid] = [x for x in D['entries']
                       if x['table_id'] == bid or (bid == 'c1_ui' and x['table_id'].startswith('c1_'))]
    freq = Counter(); used_other = set()
    for bid, es in blocks.items():
        for x in es:
            for c in strip_tok(x['text_kr']):
                if 0xAC00 <= ord(c) <= 0xD7A3: freq[c] += 1
                elif c not in (' ', '　'): used_other.add(c)
    keep_map = {'　': 0x001, ' ': 0x000}
    for c in sorted(used_other):
        keep_map[c] = ch2idx_game[c]
    kept = set(keep_map.values())
    syllables = [c for c, _ in freq.most_common()]
    free_slots = [i for i in range(MAX_GLYPH) if i not in kept]
    alloc = [i for i in free_slots if i < ONE_BYTE_MAX] + [i for i in free_slots if i >= ONE_BYTE_MAX]
    kor2idx = {c: alloc[i] for i, c in enumerate(syllables)}
    char2idx = dict(keep_map); char2idx.update(kor2idx)
    return {i: c for c, i in char2idx.items()}, tbl

def main():
    idx2char, tbl = build_char2idx()
    def ch(g):
        if g in idx2char: return idx2char[g]
        return tbl.get(g, '□')  # 유지 글리프(로그에 원본 일본어 idx로 찍힌 경우 폴백)
    rows = []
    for ln in open('tmp/trace/box_render.txt', encoding='utf-8'):
        m = re.match(r'f=(\d+) base=\$([0-9A-Fa-f]+) penX=(\d+) glyph=\$([0-9A-Fa-f]+)', ln)
        if m: rows.append((int(m[1]), int(m[2],16), int(m[3]), int(m[4],16)))
    # 라인 그룹: penX가 감소(리셋)하거나 base가 바뀌면 새 줄
    lines = []; cur = []
    prev_base = prev_pen = None
    for f, base, pen, g in rows:
        if cur and (base != prev_base or pen < prev_pen):
            lines.append(cur); cur = []
        cur.append((f, base, pen, g)); prev_base, prev_pen = base, pen
    if cur: lines.append(cur)
    def hangul_ratio(t):
        h = sum(1 for c in t if 0xAC00 <= ord(c) <= 0xD7A3)
        return h / max(1, len(t))

    if '--kr' in sys.argv:
        print('clean-KR 라인의 시작 penX 분포:')
        for grp in lines:
            t = ''.join(ch(g) for _,_,_,g in grp)
            if hangul_ratio(t) >= 0.4 and len(grp) >= 2:
                print('  f=%-5d startX=%-3d len=%-2d 「%s」' % (grp[0][0], grp[0][2], len(grp), t))
        return
    # 마지막 40줄 출력
    for grp in lines[-40:]:
        f0 = grp[0][0]; base = grp[0][1]; x0 = grp[0][2]
        txt = ''.join(ch(g) for _,_,_,g in grp)
        print('f=%-5d base=$%04X startX=%-3d  「%s」' % (f0, base, x0, txt))

if __name__ == '__main__':
    main()
