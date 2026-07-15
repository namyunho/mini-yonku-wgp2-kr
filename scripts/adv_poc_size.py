#!/usr/bin/env python3
"""④재삽입 PoC — 한글 씬 재압축 크기의 **최악 가정 추정** (ROM 미변경).

⚠️ 이 스크립트는 한글을 전부 2바이트 글리프로 가정한다(보수적 상한).
   실제 build_patch.py 는 자유슬롯을 **빈도순**으로 배정해 상위 음절이 1바이트 슬롯을 받으므로
   실측은 훨씬 작다(씬 0xC0: 이 추정 +52% vs 실측 **+10.1%**). 실측은 scripts/build_adv_poc.py 참조.

측정 대상: 어드벤처 오프닝 씬 id 0xC0 ($C5:594E). 번역 = assets/translations/adventure_poc.json.
한글 글리프는 기존 673 빌드와 동일 가정(자유슬롯=고인덱스 → **2바이트 글리프**, 보수적).
기존 글리프(숫자·라틴·문장부호)는 glyph_table.tsv 의 실제 인덱스 사용.
"""
import sys, json
sys.path.insert(0, 'scripts')
from adv_codec import (decompress_scene, compress_scene, scene_src, foff,
                       ROM, DICT_SNES, DICT_LEN)
from adv_scene import walk, read_text_run
from decode_script import load_tbl

SCENE = 0xC0
# 한글 글리프 배정: 673 빌드와 동일하게 시트 자유슬롯(고인덱스)에 **음절마다 고유 인덱스**.
# ⚠️ 같은 placeholder 를 재사용하면 `01 00` 반복이 딕셔너리에 과도하게 걸려 압축률이 거짓으로 좋아진다.
KOR_BASE = 0x100         # 2바이트 인코딩 영역(>=0xF0). 순차 배정.
ADV_LINE_MAX = 16        # 어드벤처 줄폭 상한(음절): (0xF0-0x14)/13 = 16.9
_kor_alloc = {}


def kor_index(ch):
    if ch not in _kor_alloc:
        _kor_alloc[ch] = KOR_BASE + len(_kor_alloc)
    return _kor_alloc[ch]


def enc_glyph(g):
    """글리프 인덱스 -> 캐노니컬 가변길이 바이트(파서/프린터 공용)."""
    c = g + 0x10
    return bytes([c]) if c < 0x100 else bytes([(c >> 8) & 0xFF, c & 0xFF])


def encode_text(s, rev):
    """한글 텍스트 -> 텍스트런 바이트열(종료자 0x00 미포함)."""
    out = bytearray()
    i = 0
    while i < len(s):
        if s.startswith('{wait}', i):
            out.append(0x04); i += 6
        elif s.startswith('{clear}', i):
            out.append(0x06); i += 7
        elif s[i] == '\n':
            out.append(0x05); i += 1
        else:
            ch = s[i]
            g = rev.get(ch)
            if g is None:
                g = kor_index(ch)    # 신규 한글 → 자유슬롯 고유 인덱스 배정
            out += enc_glyph(g)
            i += 1
    return bytes(out)


def line_len(line):
    """줄폭 카운트: 글자=1, 반각공백=0.5, 전각공백=1 (glossary §4)."""
    n = 0.0
    for ch in line:
        n += 0.5 if ch == ' ' else 1.0
    return n


def main():
    rom = open(ROM, 'rb').read()
    tbl = load_tbl('assets/translation_guide/glyph_table.tsv')
    rev = {v: k for k, v in tbl.items()}
    D = foff(*DICT_SNES)
    dic = rom[D:D + DICT_LEN]

    poc = json.load(open('assets/translations/adventure_poc.json', encoding='utf-8'))
    kr = {r['at']: r['text_kr'] for r in poc['runs']}

    bank, addr = scene_src(rom, SCENE)
    buf, olen, endp = decompress_scene(rom, bank, addr, D)
    orig_comp = endp - foff(bank, addr)
    runs, stats, _ = walk(buf)

    # 줄폭 검사
    over = []
    for at, s in kr.items():
        for ln in s.replace('{wait}', '').replace('{clear}', '').split('\n'):
            if line_len(ln) > ADV_LINE_MAX:
                over.append((at, ln, line_len(ln)))

    # 스크립트 재구성: 각 텍스트런 구간을 한글 바이트로 치환
    out = bytearray()
    prev = 0
    n_run = jp_b = kr_b = 0
    for r in runs:
        at = r['at']
        if at not in kr:
            continue
        if r['cmd'] != 0x21:
            continue                                  # PoC 씬은 전부 cmd 0x21
        _, end = read_text_run(buf, at + 1)            # end = 0x00 종료자 다음
        out += buf[prev:at + 1]                        # cmd 0x21 까지 그대로
        new = encode_text(kr[at], rev) + b'\x00'
        out += new
        jp_b += end - (at + 1); kr_b += len(new); n_run += 1
        prev = end
    out += buf[prev:]

    new_comp = compress_scene(bytes(out), dic)

    print("=== ④재삽입 PoC 크기 측정 — 씬 0x%02X ($%02X:%04X) ===" % (SCENE, bank, addr))
    print()
    print("  치환한 텍스트런 : %d / %d" % (n_run, len(runs)))
    print("  텍스트 바이트   : JP %d  ->  KR %d   (%+d B, %+.1f%%)" % (
        jp_b, kr_b, kr_b - jp_b, 100 * (kr_b - jp_b) / jp_b))
    print("  스크립트(디컴프): %d  ->  %d   (%+d B)" % (olen, len(out), len(out) - olen))
    print("  압축 소스       : %d  ->  %d   (%+d B, %+.1f%%)" % (
        orig_comp, len(new_comp), len(new_comp) - orig_comp,
        100 * (len(new_comp) - orig_comp) / orig_comp))
    print()
    print("  in-place 가능?  : %s (원본 슬롯 %dB)" % (
        "예" if len(new_comp) <= orig_comp else "**아니오 → 재배치 필요**", orig_comp))
    print("  줄폭 위반(>%d)  : %d" % (ADV_LINE_MAX, len(over)))
    for at, ln, n in over[:5]:
        print("     0x%04X (%.1f): %s" % (at, n, ln))


if __name__ == '__main__':
    main()
