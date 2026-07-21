#!/usr/bin/env python3
"""한글 대사·스테이지 제목 재삽입 빌드 (재실행 가능·자동).
입력: dialogue.json(text_kr) + stage_titles.json(text_kr) + worldmap_text.json(kr)
      + field_kr.json(text_kr)
      + glyph_table.tsv
      + 한글 bin 폰트 + pointer_map.json.
과정: 동적 글리프 할당 → 폰트 시트 주입 → 메시지/제목 재인코딩
      → 자유공간 재배치 → 포인터 패치 → 역검증.
번역을 고치면 번역 JSON만 바꾸고 재실행하면 전부 자동 재생성된다.

Phase 1 = c7_race + c1_ui (동일 뱅크 재배치, DBR 패치 불필요).
"""
import json, struct, sys, io, os, argparse
from collections import Counter
sys.path.insert(0, 'scripts')
from decode_script import decode, render, encode, load_tbl

ROMPATH = "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
STAGE_TITLE_PATH = "assets/translations/stage_titles.json"
FONT_BASE = 0x0A1137      # $CA:1137 폰트 시트
WIDTH_BASE = 0x0A9137     # $CA:9137 폭 테이블
MAX_GLYPH = 0x3F0         # 0x000..0x3EF (+0x10 인코딩이 prefix 0x01..0x03 안에 드는 상한)
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

def decode_game_glyph(rom, n):
    """원본 $CA 글리프를 16x16 1bpp 픽셀로 복원한다."""
    base = FONT_BASE + base03(n)
    out = [[0]*16 for _ in range(16)]
    for rf in range(16):
        block = base if rf < 8 else base + 0x80
        r = rf & 7
        right = rom[block + 2*r]
        left = rom[block + 2*r + 1]
        for c in range(8):
            out[rf][c] = (left >> (7 - c)) & 1
            out[rf][8 + c] = (right >> (7 - c)) & 1
    return out

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
    ap.add_argument('--worldmap-json', default=None,
                    help='월드맵 퀴즈 JSON. 기존 정적/어드벤처 글리프 인덱스를 보존한 채 '
                         '신규 음절·기호를 할당 끝에만 추가한다.')
    ap.add_argument('--field-json', default=None,
                    help='필드/NPC 번역 원장. 기존 정적/어드벤처/월드맵 글리프 인덱스를 '
                         '보존한 채 신규 음절·기호를 할당 끝에만 추가한다.')
    ap.add_argument('--glyph-map-out', default='out/glyph_map.json',
                    help='char->글리프인덱스 매핑 산출(어드벤처 빌더가 재사용)')
    a = ap.parse_args()

    rom = bytearray(open(ROMPATH, 'rb').read())
    source_rom = bytes(rom)  # 월드맵 전용 유지문자 복제는 주입 전 원본 글리프에서 읽는다.
    D = json.load(open('assets/translations/dialogue.json', encoding='utf-8'))
    ST = json.load(open(STAGE_TITLE_PATH, encoding='utf-8'))
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

    # ---- 스테이지 제목 원본·포인터 테이블 불변식 ----
    stage_titles = ST['entries']
    if len(stage_titles) != 10 or [x['stage'] for x in stage_titles] != list(range(1, 11)):
        sys.exit(f"{STAGE_TITLE_PATH}: stage 1..10 순서의 엔트리 10개가 필요")
    pt = ST['pointer_table']
    if pt['count'] != 10 or pt['entry_size'] != 2:
        sys.exit(f"{STAGE_TITLE_PATH}: 포인터 테이블 규격 불일치")
    pt_off = int(pt['file_offset'], 16)
    for i, x in enumerate(stage_titles):
        raw = bytes.fromhex(x['raw_hex'])
        off = int(x['file_offset'], 16)
        addr = int(x['addr'].split(':')[1], 16)
        if len(raw) != x['n_bytes']:
            sys.exit(f"stage {x['stage']}: raw 길이 {len(raw)} != n_bytes {x['n_bytes']}")
        if rom[off:off + len(raw)] != raw:
            sys.exit(f"stage {x['stage']}: raw_hex != 원본 ROM @0x{off:06X}")
        if struct.unpack_from('<H', rom, pt_off + i * 2)[0] != addr:
            sys.exit(f"stage {x['stage']}: 포인터 테이블 값 != {x['addr']}")

    # ---- 대상 블록 text_kr에 실제 쓰인 문자 수집 ----
    import re
    def strip_tok(s): return re.sub(r'\{[^}]*\}', '', s)
    freq_titles = Counter(); freq = Counter(); used_other = set()
    for x in stage_titles:
        for c in strip_tok(x['text_kr']):
            if 0xAC00 <= ord(c) <= 0xD7A3:
                freq_titles[c] += 1
            elif c not in (' ', '　'):
                used_other.add(c)
    for bid, es in blocks.items():
        for x in es:
            for c in strip_tok(x['text_kr']):
                if 0xAC00 <= ord(c) <= 0xD7A3:
                    freq[c] += 1
                elif c not in (' ', '　'):
                    used_other.add(c)

    # ---- 어드벤처 음절도 같은 할당에 포함(폰트 시트 $CA 전역 공유) ----
    # ⚠️ 단, **1바이트 슬롯 우선권은 정적 대사에 준다**(아래 alloc 참조):
    #    정적 대사는 원본 슬롯에 갇혀(in-place) 1바이트 글리프가 초과 여부를 좌우하지만,
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

    # ---- 월드맵 퀴즈 코퍼스: 기존 할당을 흔들지 않는 append-only 입력 ----
    # 이 코퍼스를 freq/used_other에 섞으면 1바이트 경계의 기존 음절이 밀려
    # 어드벤처 위치보존 런이 다시 길어질 수 있다. 기존 할당을 먼저 완성한 뒤
    # 월드맵 전용 신규 음절과, 기존 패치에서 보존하지 않은 원본 기호(9/÷/＝ 등)를
    # 끝 슬롯에만 추가한다.
    freq_world = Counter()
    other_world = Counter()
    if a.worldmap_json:
        WD = json.load(open(a.worldmap_json, encoding='utf-8'))
        for x in WD['entries']:
            for c in strip_tok(x['kr']):
                if 0xAC00 <= ord(c) <= 0xD7A3:
                    freq_world[c] += 1
                elif c not in (' ', '　', '\n'):
                    other_world[c] += 1

    # ---- 필드/NPC 코퍼스: 월드맵 뒤 append-only 입력 ----
    freq_field = Counter()
    other_field = Counter()
    if a.field_json:
        FD = json.load(open(a.field_json, encoding='utf-8'))
        for x in FD['entries']:
            for c in strip_tok(x['text_kr']):
                if 0xAC00 <= ord(c) <= 0xD7A3:
                    freq_field[c] += 1
                elif c not in (' ', '　', '\n'):
                    other_field[c] += 1

    # ---- 유지 문자 → 기존 게임 인덱스 (실제 쓰인 것만) ----
    keep_map = {'　': 0x001, ' ': 0x000}   # 전각공백 8px / 반각 4px
    for c in sorted(used_other):
        if c not in ch2idx_game:
            sys.exit(f"게임 글리프에 없는 유지 문자: {c!r} (U+{ord(c):04X})")
        keep_map[c] = ch2idx_game[c]
    kept_indices = set(keep_map.values())
    # 정적 대사 음절(빈도순) → 어드벤처 전용 음절 → 제목 전용 음절 순.
    # 기존 두 영역의 글리프 인덱스를 절대 흔들지 않는 것이 우선이다. 제목에만 새로
    # 등장하는 음절은 마지막에 추가하며, 실제 슬롯 적합 여부는 아래에서 엄격히 검사한다.
    # alloc = one_byte + two_byte 이므로 이 순서가 곧 **1바이트 슬롯 우선권**이 된다.
    syllables = [c for c, _ in freq.most_common()]
    syllables += [c for c, _ in freq_adv.most_common() if c not in freq]
    syllables += [c for c, _ in freq_titles.most_common()
                  if c not in freq and c not in freq_adv]
    base_syllable_count = len(syllables)
    world_syllables = [c for c, _ in freq_world.most_common() if c not in syllables]
    syllables += world_syllables
    field_syllables = [c for c, _ in freq_field.most_common() if c not in syllables]
    syllables += field_syllables

    # 월드맵에서만 쓰이며 기존 keep_map에 없던 비한글 글리프는 원본 타일을
    # 새 슬롯으로 복제한다. 기존 슬롯을 뒤늦게 kept_indices에 넣지 않으므로
    # 정적/어드벤처 char2idx가 바뀌지 않는다.
    append_other = other_world + other_field
    world_copy_chars = []
    for c, _ in append_other.most_common():
        if c in keep_map:
            continue
        if c not in ch2idx_game:
            sys.exit(f"월드맵 원본 글리프에 없는 유지 문자: {c!r} (U+{ord(c):04X})")
        world_copy_chars.append(c)

    # ---- 동적 글리프 할당: 자유 슬롯 = 0..0x3FF - kept ----
    free_slots = [i for i in range(MAX_GLYPH) if i not in kept_indices]
    one_byte = [i for i in free_slots if i < ONE_BYTE_MAX]   # 1바이트(≤176)
    two_byte = [i for i in free_slots if i >= ONE_BYTE_MAX]
    alloc = one_byte + two_byte                              # 빈도순 배정: 앞=1바이트
    needed = len(syllables) + len(world_copy_chars)
    if needed > len(alloc):
        sys.exit(f"글리프 부족: 음절+추가기호 {needed} > 자유슬롯 {len(alloc)}")
    kor2idx = {c: alloc[i] for i, c in enumerate(syllables)}
    world_other2idx = {
        c: alloc[len(syllables) + i] for i, c in enumerate(world_copy_chars)
    }

    char2idx = dict(keep_map); char2idx.update(kor2idx); char2idx.update(world_other2idx)
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
    for c, idx in world_other2idx.items():
        src_idx = ch2idx_game[c]
        encode_glyph(rom, idx, decode_game_glyph(source_rom, src_idx))
        rom[WIDTH_BASE + idx] = source_rom[WIDTH_BASE + src_idx]

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

    # ---- 스테이지 제목 10개 동일 영역 재패킹 ----
    # 원본 10개 문자열이 연속으로 차지한 $C0:8234..$C0:82C8(149B) 안에서만
    # 다시 패킹하고 $C0:830F의 첫 10개 포인터를 갱신한다. 뒤따르는 별도
    # 문자열($C0:82C9~)과 포인터 테이블의 나머지 항목은 건드리지 않는다.
    stage_verify = []
    stage_start = int(stage_titles[0]['file_offset'], 16)
    stage_end = int(stage_titles[-1]['file_offset'], 16) + stage_titles[-1]['n_bytes']
    stage_cap = stage_end - stage_start
    stage_encoded = [(x, encode(to_tokens(x['text_kr']))) for x in stage_titles]
    stage_used = sum(len(b) for _, b in stage_encoded)
    if stage_used > stage_cap:
        sys.exit(f"스테이지 제목 영역 부족: {stage_used} > {stage_cap}B")
    cur = stage_start
    for i, (x, b) in enumerate(stage_encoded):
        addr = cur & 0xFFFF
        rom[cur:cur + len(b)] = b
        struct.pack_into('<H', rom, pt_off + i * 2, addr)
        stage_verify.append((x, len(b), addr))
        cur += len(b)

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
    print(f"\n=== 폰트: 한글 {inj} 글리프 주입 "
          f"(기존코퍼스 {base_syllable_count} + 월드맵 신규 {len(world_syllables)}), "
          f"월드맵 원본기호 복제 {len(world_other2idx)}, 자유슬롯 {len(alloc)} ===")
    stage_ok = 0
    for x, nenc, addr in stage_verify:
        got = decode_at(0xC0, addr)
        exp = x['text_kr'] if x['text_kr'].endswith('{end}') else x['text_kr'] + '{end}'
        stage_ok += (got == exp)
        print(f"stage {x['stage']:2d}: ${addr:04X} {nenc:2d}B | {got}")
    print(f"스테이지 제목 역검증: {stage_ok}/{len(stage_verify)} "
          f"| 영역 {stage_used}/{stage_cap}B")
    if stage_ok != len(stage_verify):
        sys.exit("스테이지 제목 역검증 실패")
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
        sys.exit("정적 대사 번역 미반영: 미커버 초과를 축약하거나 포인터를 발굴해야 함")
    if total_ok != total_ins:
        sys.exit("역검증 실패 (삽입분 일부 불일치)")

if __name__ == '__main__':
    main()
