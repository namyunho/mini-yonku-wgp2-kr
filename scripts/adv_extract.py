#!/usr/bin/env python3
"""어드벤처/스토리 텍스트 전량 추출 → assets/translations/adventure.json

경로(docs/08 SSOT):
  씬 소스 테이블 $C6:9C57 (3B/엔트리 {addr_lo, addr_hi, bank_delta}, bank = delta+$C4, 250엔트리)
    → 소스 선두 2바이트 = 디컴프 출력길이 헤더, 스트림은 addr+2
    → adv_codec.decompress_scene() 로 씬 스크립트 바이트코드 복원
    → adv_scene.walk() 로 VM 워크 → 텍스트런(cmd 0x20/0x21) 추출

산출 JSON: [{scene, src, decomp_len, clean, runs:[{at, cmd, text_jp, raw}]}]
  text_jp = 렌더 문자열({nl}=개행, {wait}=입력대기, {clear}=박스클리어)
  raw     = 텍스트런 원바이트 hex (재삽입·라운드트립 검증용)
  화자명 = text_jp 의 첫 줄(별도 네임박스 없음 — docs/08)
"""
import sys, json
sys.path.insert(0, 'scripts')
from adv_codec import decompress_scene, scene_src, foff, ROM, DICT_SNES, N_SCENES
from adv_scene import walk, render, read_text_run
from decode_script import load_tbl

OUT = 'assets/translations/adventure.json'


def run_raw(buf, r):
    """텍스트런의 원바이트 구간을 되짚어 hex 로."""
    if r['cmd'] == 0x21:
        _, end = read_text_run(buf, r['at'] + 1)
        return buf[r['at'] + 1:end]
    # cmd0x20 컨테이너: operand(2B) 뒤 텍스트(커서+2=at+3 부터 0x00까지). walk 관통 방식과 일치.
    _, end = read_text_run(buf, r['at'] + 3)
    return buf[r['at'] + 3:end]


def main():
    rom = open(ROM, 'rb').read()
    tbl = load_tbl('assets/translation_guide/glyph_table.tsv')
    dic = foff(*DICT_SNES)
    scenes = []
    n_clean = n_runs = n_glyph = n_unm = 0
    for sid in range(N_SCENES):
        bank, addr = scene_src(rom, sid)
        try:
            buf, olen, _ = decompress_scene(rom, bank, addr, dic)
        except Exception:
            continue
        runs, stats, endp = walk(buf)
        clean = (not stats['desync']) and endp >= len(buf) - 1
        n_clean += clean
        out_runs = []
        for r in runs:
            txt = render(r['text'], tbl)
            if not txt.strip():
                continue                      # 빈 런 제외
            for k, v in r['text']:
                if k == 'g':
                    n_glyph += 1
                    if v not in tbl:
                        n_unm += 1
            out_runs.append({
                'at': r['at'], 'cmd': r['cmd'],
                'text_jp': txt,
                'raw': run_raw(buf, r).hex(),
            })
        n_runs += len(out_runs)
        scenes.append({
            'scene': sid, 'src': '$%02X:%04X' % (bank, addr),
            'decomp_len': olen, 'clean': clean, 'runs': out_runs,
        })
    json.dump(scenes, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print("씬 %d개 -> %s" % (len(scenes), OUT))
    print("  완주 %d / %d" % (n_clean, len(scenes)))
    print("  텍스트런 %d   글리프 %d   미매핑 %d (%.5f%%)" % (
        n_runs, n_glyph, n_unm, 100 * n_unm / max(n_glyph, 1)))


if __name__ == '__main__':
    main()
