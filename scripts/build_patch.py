#!/usr/bin/env python3
"""한글 대사 재삽입 빌드 (재실행 가능·자동).
입력: dialogue.json(text_kr) + glyph_table.tsv + 한글 bin 폰트 + pointer_map.json.
과정: 동적 글리프 할당 → 폰트 시트 주입 → 메시지 재인코딩 → 자유공간 재배치 → 포인터 패치 → 역검증.
번역을 고치면 dialogue.json만 바꾸고 재실행하면 전부 자동 재생성된다.

Phase 1 = c7_race + c1_ui (동일 뱅크 재배치, DBR 패치 불필요).
"""
import json, struct, sys, io, os, argparse
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
# d0는 한글이 원본영역(8206B)에 들어가므로 in-place(base=$C80B) → DBR 패치 불필요.
FREE = {
    'c7_race':  (0xC7, 0xB49B, (0x07 << 16) | 0xB49B, 19301),
    'c1_ui':    (0xC1, 0x9843, (0x01 << 16) | 0x9843, 10173),
    'd0_story': (0xD0, 0xC80B, (0x10 << 16) | 0xC80B, 8206),
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
    ap.add_argument('--blocks', nargs='+', default=['c7_race', 'c1_ui', 'd0_story'])
    ap.add_argument('--out', default='out/wgp2_kr.smc')
    ap.add_argument('--kor-adv', type=int, default=13,
                    help='한글 글리프 균일 advance(px). 0 이하면 기존 글리프별 ink+2 방식.')
    ap.add_argument('--adv-json', default=None,
                    help='어드벤처 번역 JSON. 주면 그 음절도 **같은 글리프 할당**에 포함한다. '
                         '(폰트 시트는 전역 공유 → 어드벤처를 별도 할당하면 673과 충돌)')
    ap.add_argument('--glyph-map-out', default='out/glyph_map.json',
                    help='char->글리프인덱스 매핑 산출(어드벤처 빌더가 재사용)')
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

    # ---- 어드벤처 음절도 같은 할당에 포함(폰트 시트 $CA 전역 공유) ----
    # ⚠️ 단, **1바이트 슬롯 우선권은 673에 준다**(아래 alloc 참조):
    #    673 대사는 원본 슬롯에 갇혀(in-place) 1바이트 글리프가 초과 여부를 좌우하지만,
    #    어드벤처는 씬 통째로 재배치하므로 1/2바이트는 압축률(~10%)에만 영향한다.
    #    전역 빈도로 섞어 배정하면 분량 큰 어드벤처가 1바이트 슬롯을 잠식해 673 초과가 늘어난다.
    freq_adv = Counter()
    if a.adv_json:
        AD = json.load(open(a.adv_json, encoding='utf-8'))
        # 지원 포맷: {'scenes':[{'runs':[…]}]} (작업파일) / {'runs':[…]} (PoC 단일씬) / [{'runs':[…]}]
        if isinstance(AD, dict) and 'scenes' in AD:
            adv_runs = [r for s in AD['scenes'] for r in s['runs']]
        elif isinstance(AD, dict):
            adv_runs = AD['runs']
        else:
            adv_runs = [r for s in AD for r in s['runs']]
        for r in adv_runs:
            for c in strip_tok(r.get('text_kr', '') or ''):
                if 0xAC00 <= ord(c) <= 0xD7A3:
                    freq_adv[c] += 1
                elif c not in (' ', '　', '\n'):
                    used_other.add(c)

    # ---- 유지 문자 → 기존 게임 인덱스 (실제 쓰인 것만) ----
    keep_map = {'　': 0x001, ' ': 0x000}   # 전각공백 8px / 반각 4px
    for c in sorted(used_other):
        if c not in ch2idx_game:
            sys.exit(f"게임 글리프에 없는 유지 문자: {c!r} (U+{ord(c):04X})")
        keep_map[c] = ch2idx_game[c]
    kept_indices = set(keep_map.values())
    # 673 음절(빈도순) 먼저 → 그 다음 어드벤처 전용 음절(빈도순).
    # alloc = one_byte + two_byte 이므로 이 순서가 곧 **1바이트 슬롯 우선권**이 된다.
    syllables = [c for c, _ in freq.most_common()]
    syllables += [c for c, _ in freq_adv.most_common() if c not in freq]

    # ---- 동적 글리프 할당: 자유 슬롯 = 0..0x3FF - kept ----
    free_slots = [i for i in range(MAX_GLYPH) if i not in kept_indices]
    one_byte = [i for i in free_slots if i < ONE_BYTE_MAX]   # 1바이트(≤176)
    two_byte = [i for i in free_slots if i >= ONE_BYTE_MAX]
    alloc = one_byte + two_byte                              # 빈도순 배정: 앞=1바이트
    if len(syllables) > len(alloc):
        sys.exit(f"글리프 부족: 음절 {len(syllables)} > 자유슬롯 {len(alloc)}")
    kor2idx = {c: alloc[i] for i, c in enumerate(syllables)}

    char2idx = dict(keep_map); char2idx.update(kor2idx)
    if a.glyph_map_out:
        os.makedirs(os.path.dirname(a.glyph_map_out) or '.', exist_ok=True)
        json.dump({'char2idx': char2idx, 'kor_adv': a.kor_adv},
                  open(a.glyph_map_out, 'w', encoding='utf-8'), ensure_ascii=False)

    # ---- 폰트 주입 (한글 글리프 + 폭) ----
    inj = 0
    for c, idx in kor2idx.items():
        px = decode_bin_glyph(binf, gm[c], -2)   # binyshift -2 (게임 상단정렬)
        encode_glyph(rom, idx, px)
        # 한글은 모아쓰기 정사각 블록 → advance 균일 고정(기본 13px). 글리프별 ink+2는
        # 간격 불균일 + 넓어서 초상화 조언상자 잘림 유발 → 고정폭으로 교정.
        rom[WIDTH_BASE + idx] = (min(16, a.kor_adv) if a.kor_adv > 0
                                 else min(16, ink_width(px) + 2))
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

    # ---- 줄 폭 가드: 한 줄 ≤ 13 (글자=1, 반각공백=0.5, 전각공백=1) ----
    def line_units(ln): return sum(0.5 if c == ' ' else 1.0 for c in ln)
    over = []
    for bid, es in blocks.items():
        for x in es:
            for ln in re.sub(r'\{end\}|\{trunc[0-9A-Fa-f]+\}', '', x['text_kr']).split('{nl}'):
                if line_units(ln) > 13:
                    over.append((x['entry_id'], line_units(ln), ln))
    if over:
        for eid, u, ln in over[:20]:
            print(f"  줄폭초과 #{eid} u={u}: 「{ln}」")
        sys.exit(f"줄 폭 규칙 위반 {len(over)}줄 (>13). 번역 조정 필요")

    enc = {}   # entry_id -> bytes
    for bid, es in blocks.items():
        for x in es:
            enc[x['entry_id']] = encode(to_tokens(x['text_kr']))

    # ---- 하이브리드 삽입: 제자리(fit) + 자유공간 재배치(초과·커버된 것) ----
    # 원칙: 원본 포인터를 최대한 그대로 둠(주소 고정) → 미커버 포인터도 안전.
    #  - fit(한글 ≤ 원본 slot): 원래 주소에 그대로 덮어씀. 포인터 손 안 댐.
    #  - 초과 + 포인터 커버됨: 자유공간(동일 뱅크)으로 옮기고 그 포인터만 패치.
    #       원본 slot은 손대지 않음 → 혹시 숨은 미커버 포인터가 있어도 (엉뚱한 한글이 아니라)
    #       원본 일본어를 읽어 최악이 '깨진 글자'에 그침(잘못된 대사 아님).
    #  - 초과 + 미커버: 옮길 포인터를 몰라 재배치 불가 → 원본 유지(추후 축약/발굴).
    # 재배치 자유공간(동일 뱅크, 텍스트/코드와 비겹침 확인): 0xFF 런.
    RELOC = {
        'c7_race':  (0xC7, 0xB49B, 0x10000 - 0xB49B),   # 19301B
        'c1_ui':    (0xC1, 0xD5CB, 0x10000 - 0xD5CB),   # 10805B
        'd0_story': (0xD0, 0xA42F, 0xB000  - 0xA42F),   # 3025B (텍스트 $C80B 앞의 미사용 런)
    }
    report = {}
    overflow_uncov = []
    verify = []          # (bank, addr, entry_id) 검증 대상 (fit + reloc)
    for bid, es in blocks.items():
        bank = int(es[0]['addr'].split(':')[0].replace('$', ''), 16)
        rbank, rstart, rcap = RELOC[bid]
        targets = {}
        for loc, t, kind in pmap[bid]['pointers']:
            targets.setdefault(t, []).append(loc)
        cur = rstart
        written = reloc = ov = 0
        for x in es:
            addr = int(x['addr'].split(':')[1], 16)
            b = enc[x['entry_id']]
            if len(b) <= x['n_bytes']:                      # fit → 제자리
                o = foff(bank, addr); rom[o:o + len(b)] = b
                verify.append((bank, addr, x['entry_id'])); written += 1
            elif addr in targets:                           # 초과+커버 → 재배치
                if cur - rstart + len(b) > rcap:
                    sys.exit(f"{bid}: 재배치 공간 부족 ({cur - rstart + len(b)} > {rcap})")
                o = foff(rbank, cur); rom[o:o + len(b)] = b
                for loc in targets[addr]:
                    struct.pack_into('<H', rom, loc, cur)   # 포인터 패치
                verify.append((rbank, cur, x['entry_id'])); cur += len(b); reloc += 1
            else:                                           # 초과+미커버 → 원본 유지
                overflow_uncov.append((bid, x['entry_id'], addr, x['n_bytes'], len(b), x['text_kr']))
                ov += 1
        report[bid] = (len(es), written, reloc, ov, bank, cur - rstart, rcap)

    # ---- 출력 ----
    os.makedirs('out', exist_ok=True)
    open(a.out, 'wb').write(rom)

    # ---- 역검증: 각 삽입/재배치 위치에서 재디코드 == text_kr ----
    idx2char = {i: c for c, i in char2idx.items()}
    enc_of = {x['entry_id']: x for es in blocks.values() for x in es}
    def decode_at(bank, addr):
        o = foff(bank, addr); s = o
        while rom[o] != 0x00:
            b = rom[o]; o += 2 if (1 <= b <= 4 or b == 7) else 1
        return render(decode(rom[s:o + 1]), idx2char)
    vloc = {eid: (bk, ad) for bk, ad, eid in verify}
    print(f"\n=== 폰트: 한글 {inj} 글리프 주입 (자유슬롯 {len(alloc)}, 음절 {len(syllables)}) ===")
    total_ok = total_ins = total = 0
    for bid, (nmsg, written, reloc, ov, bank, rused, rcap) in report.items():
        ok = 0; ins = written + reloc
        for x in blocks[bid]:
            if x['entry_id'] not in vloc:
                continue                                    # 미커버 초과 → 검증 제외
            bk, ad = vloc[x['entry_id']]
            got = decode_at(bk, ad)
            exp = re.sub(r'\{trunc[0-9A-Fa-f]+\}', '{end}', x['text_kr'])
            if not exp.endswith('{end}'): exp += '{end}'
            ok += (got == exp)
        total_ok += ok; total_ins += ins; total += nmsg
        print(f"{bid:8s}: msgs {nmsg} | 제자리 {written} + 재배치 {reloc}({rused}/{rcap}B) "
              f"| 미커버초과 {ov} | 역검증 {ok}/{ins}")
    print(f"\n역검증 합계(삽입분): {total_ok}/{total_ins}  | 전체메시지 {total}  -> {a.out}")
    if overflow_uncov:
        print(f"\n⚠️ 미커버 초과 {len(overflow_uncov)}개 (포인터 미상 → 재배치 불가, 원본 유지):")
        for bid, eid, addr, slot, klen, kr in overflow_uncov:
            print(f"  [{bid}] id={eid} @${addr:04X} slot={slot} kr={klen} (+{klen - slot}) {kr!r}")
    if total_ok != total_ins:
        sys.exit("역검증 실패 (삽입분 일부 불일치)")

if __name__ == '__main__':
    main()
