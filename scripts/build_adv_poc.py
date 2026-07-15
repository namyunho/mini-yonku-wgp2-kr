#!/usr/bin/env python3
"""④재삽입 PoC — 어드벤처 오프닝 씬(id 0xC0)을 한글로 재삽입.

전제: `build_patch.py --adv-json assets/translations/adventure_poc.json` 을 먼저 돌려
      (a) 한글 폰트가 시트 $CA 에 주입되고 (b) out/glyph_map.json (char->글리프인덱스)이 나와 있어야 한다.
      폰트 시트는 673과 **전역 공유**이므로 할당은 반드시 한 번에 해야 한다.

과정:
  1) 씬 소스 표 $C6:9C57 에서 id 0xC0 소스 → 헤더인식 디컴프 → 스크립트 바이트코드
  2) VM 워크로 텍스트런(cmd 0x21) 위치 확정 → 한글 바이트로 치환
  3) 재압축(2B 길이헤더 + 플래그LZ) → 한글은 일본어향 딕셔너리와 안 맞아 ~1.5배로 팽창
  4) 원본 슬롯에 안 들어가므로 **자유공간으로 재배치 + 표 엔트리 3바이트만 패치**
     (원본 슬롯은 손대지 않음 → 혹시 남은 참조가 있어도 원본 일본어가 나올 뿐 안전)
  5) 역검증: 패치된 표를 다시 읽어 디컴프→워크→렌더가 text_kr 과 일치하는지
"""
import sys, json, argparse
sys.path.insert(0, 'scripts')
from adv_codec import (decompress_scene, compress_scene, scene_src, foff,
                       DICT_SNES, DICT_LEN)
from adv_scene import walk, render, read_text_run
from decode_script import load_tbl

SCENE = 0xC0
SCENE_TBL = foff(0xC6, 0x9C57)
# 재배치 목적지: 0xFF 런(18138B). 프로젝트 기존 재배치 영역과 비겹침
#   (사용중: $C7:B49B=c7, $C1:D5CB/$C1:9843=c1·메뉴, $D0:A42F=d0, $C6:AB11/$C6:CBC4/$C6:E000=타이틀)
RELOC = (0xC9, 0xB926)


def enc_glyph(g):
    c = g + 0x10
    return bytes([c]) if c < 0x100 else bytes([(c >> 8) & 0xFF, c & 0xFF])


def encode_text(s, ch2idx):
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
            if ch not in ch2idx:
                sys.exit("글리프 매핑 없음: %r (U+%04X) — build_patch --adv-json 을 먼저 돌렸나?"
                         % (ch, ord(ch)))
            out += enc_glyph(ch2idx[ch]); i += 1
    return bytes(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rom', default='out/wgp2_kr.smc')
    ap.add_argument('--out', default='out/adv_poc.smc')
    a = ap.parse_args()

    rom = bytearray(open(a.rom, 'rb').read())
    tbl = load_tbl('assets/translation_guide/glyph_table.tsv')
    gm = json.load(open('out/glyph_map.json', encoding='utf-8'))
    ch2idx = {k: v for k, v in gm['char2idx'].items()}
    D = foff(*DICT_SNES)
    dic = bytes(rom[D:D + DICT_LEN])

    poc = json.load(open('assets/translations/adventure_poc.json', encoding='utf-8'))
    kr = {r['at']: r['text_kr'] for r in poc['runs']}

    bank, addr = scene_src(rom, SCENE)
    buf, olen, endp = decompress_scene(rom, bank, addr, D)
    orig_comp = endp - foff(bank, addr)
    runs, stats, _ = walk(buf)

    # ---- 텍스트런 치환 ----
    out = bytearray(); prev = 0; n = 0
    for r in runs:
        at = r['at']
        if at not in kr or r['cmd'] != 0x21:
            continue
        _, end = read_text_run(buf, at + 1)
        out += buf[prev:at + 1]
        out += encode_text(kr[at], ch2idx) + b'\x00'
        prev = end; n += 1
    out += buf[prev:]
    script = bytes(out)

    comp = compress_scene(script, dic)
    rb, ra = RELOC
    dst = foff(rb, ra)

    # 목적지가 정말 비었는지 확인
    if any(b != 0xFF for b in rom[dst:dst + len(comp)]):
        sys.exit("재배치 목적지 $%02X:%04X 가 비어있지 않음" % (rb, ra))
    rom[dst:dst + len(comp)] = comp

    # ---- 표 엔트리 3바이트 패치 ----
    e = SCENE_TBL + SCENE * 3
    old = bytes(rom[e:e + 3])
    rom[e] = ra & 0xFF
    rom[e + 1] = (ra >> 8) & 0xFF
    rom[e + 2] = (rb - 0xC4) & 0xFF

    open(a.out, 'wb').write(rom)

    # ---- 역검증: 패치된 표로 다시 읽어 렌더 비교 ----
    rom2 = bytes(rom)
    b2, a2 = scene_src(rom2, SCENE)
    buf2, olen2, _ = decompress_scene(rom2, b2, a2, D)
    ok_rt = (buf2 == script)
    runs2, st2, endp2 = walk(buf2)
    # ⚠️ 렌더는 반드시 **패치 후 매핑**(idx->한글)으로. 원본 glyph_table.tsv 로 렌더하면
    #    한글을 주입한 슬롯이 옛 일본어 글자로 나와 거짓 불일치가 난다.
    tbl_kr = {v: k for k, v in ch2idx.items()}
    kr_list = [r['text_kr'] for r in poc['runs']]
    got_list = [render(r['text'], tbl_kr) for r in runs2
                if render(r['text'], tbl_kr).strip()]
    same = sum(1 for x, y in zip(kr_list, got_list) if x == y)

    print("=== ④ PoC 재삽입 — 씬 0x%02X ===" % SCENE)
    print("  원본 소스   : $%02X:%04X  압축 %dB / 디컴프 %dB" % (bank, addr, orig_comp, olen))
    print("  한글 스크립트: %dB (%+d)   재압축 %dB (%+d, %+.1f%%)" % (
        len(script), len(script) - olen, len(comp), len(comp) - orig_comp,
        100 * (len(comp) - orig_comp) / orig_comp))
    print("  재배치      : $%02X:%04X (파일 0x%06X)  표엔트리 %s -> %s" % (
        rb, ra, dst, old.hex(' '), bytes(rom[e:e + 3]).hex(' ')))
    print()
    print("  역검증 decompress(recompress)==script : %s" % ("PASS" if ok_rt else "**FAIL**"))
    print("  역검증 워크 : %s  (stop@0x%04X/%04X)" % (
        "clean" if not st2['desync'] and endp2 >= len(buf2) - 1 else "**DESYNC**", endp2, len(buf2)))
    print("  렌더 일치   : %d / %d 메시지" % (same, len(kr_list)))
    print()
    print("  -> %s" % a.out)
    if same != len(kr_list):
        for i, (x, y) in enumerate(zip(kr_list, got_list)):
            if x != y:
                print("   [%d] 기대: %r" % (i, x)); print("       실제: %r" % y); break


if __name__ == '__main__':
    main()
