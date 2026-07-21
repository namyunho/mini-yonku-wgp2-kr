#!/usr/bin/env python3
"""어드벤처 텍스트 전량 재삽입 (씬 다중 · 자유공간 배치 · 씬표 패치 · 역검증).

전제: `build_patch.py --adv-json assets/translations/adventure_kr.json` 을 먼저 돌려
      한글 폰트가 시트 $CA 에 주입되고 out/glyph_map.json (char->글리프인덱스)이 나와 있어야 한다.
      **폰트 시트는 673과 전역 공유** → 글리프 할당은 반드시 한 번에(그래서 --adv-json 필수).

경로(docs/08 SSOT):
  씬표 $C6:9C57 (3B/엔트리 {addr_lo, addr_hi, bank_delta}, bank = delta+$C4, 250엔트리)
    → 소스 선두 2B = 디컴프 출력길이 헤더, 스트림은 addr+2
    → 스크립트 VM 바이트코드. 텍스트런은 cmd 0x20/0x21 에서만 시작.

전략(PoC 검증됨):
  - 씬들은 표 순서대로 빈틈없이 연속 저장(갭0 212/249) → **in-place 확장 불가**.
  - 한글 재압축은 +10% 내외 팽창 → **자유공간으로 재배치 + 표 엔트리 3바이트만 패치**.
  - **원본 슬롯은 손대지 않는다** → 혹시 남은 참조가 있어도 최악이 원본 일본어(안전).
  - 번역이 없는 씬은 아예 건드리지 않는다(원본 그대로) → 증분 진행 가능.
"""
import sys, json, argparse, os, re
sys.path.insert(0, 'scripts')
from adv_codec import (decompress_scene, compress_scene, scene_src, foff,
                       DICT_SNES, DICT_LEN, N_SCENES)
from adv_scene import walk, render, read_text_run
from decode_script import load_tbl

SCENE_TBL = foff(0xC6, 0x9C57)

# 재배치 자유공간 풀 (bank, addr, 길이). 씬 bank = delta+$C4 라 $C4-$DF 만 가능.
# ⚠️ 프로젝트 기존 재배치 영역과 비겹침 확인 필수:
#    $C7:B49B=c7대사 / $C1:D5CB·$C1:9843=c1·메뉴 / $D0:A42F=d0대사
#    $C6:AB11·$C6:CBC4·$C6:E000=타이틀 로고·크레딧
FREE_POOL = [
    (0xCA, 0x9537, 27337),   # 폰트 시트·폭테이블($CA:9137) 뒤
    (0xC9, 0xB926, 18138),
    (0xDA, 0xBEDC, 16676),
    (0xCF, 0xBF9F, 16481),
    (0xCB, 0xC37E, 15492),   # 0x00 런
    (0xCC, 0xC9E0, 13856),
    (0xD9, 0xD239, 11719),
    (0xD4, 0xE3DF, 7201),
    (0xCC, 0xAF7E, 4229),    # 0x00 런
    (0xD3, 0xF200, 3584),
]


def enc_glyph(g):
    c = g + 0x10
    return bytes([c]) if c < 0x100 else bytes([(c >> 8) & 0xFF, c & 0xFF])


# 위치보존 패딩 글리프 = 반각 공백(글리프 idx 0 → 바이트 0x10, 1B, 블랭크).
# 전각(idx 1 → 0x11)보다 펜 전진이 작아 말미 자동 줄바꿈($4177) 위험이 낮다.
# docs/14: 한글이 원본보다 짧은 cmd0x20/0x21 런은 말미에 이 글리프로 원본 바이트길이까지 채워
#          런 총길이를 원본과 정확히 일치시킨다 → 디컴프 스크립트 길이 불변 → VM offset 보존.
PAD_CHAR = ' '   # 반각 공백(글리프 idx0 → 1바이트 0x10, 블랭크). 위치보존 패딩 문자.


_PAD_TAIL = re.compile(r'(?:\{[^}]*\}|\n)+\Z')   # 말미의 마커({..})·개행(\n) 연속

def pad_kr(kr, pad):
    """위치보존 패딩: **마지막 가시 글리프 뒤**(말미 마커·개행 블록 '앞')에 공백 pad개 삽입.
    - trailing `\\n`으로 끝나는 런(예 `…！{wait}\\n`)에 패딩을 '맨 끝'에 붙이면 패딩이 개행 뒤
      새 줄에 찍혀 **다음 런이 들여쓰기**된다(2026-07-21 사용자 실측: 츠치야 「뭐 뭐라고！/그럼…」).
      → 말미 마커·개행 블록 앞(가시 텍스트 줄 끝)에 넣어 개행 뒤엔 아무것도 안 남게 한다.
    - `{wait}{clear}`로 끝나면 {wait} 앞(=가시줄 끝)에 → 대기 중 트레일링 공백(좌측정렬 비표시) 후 clear.
    - 마커 없이 글리프로 끝나면 말미에 덧붙임(트레일링 공백)."""
    if pad <= 0:
        return kr
    m = _PAD_TAIL.search(kr)
    i = m.start() if m else len(kr)       # 마지막 가시 글리프 뒤 위치
    return kr[:i] + PAD_CHAR * pad + kr[i:]


TEXT_CMDS = (0x20, 0x21)


def text_run_bounds(buf, run):
    """텍스트 본문 [start, end) 경계. end에는 종료자 0x00까지 포함한다.

    cmd0x20의 2바이트 오퍼랜드는 텍스트가 아니므로 start 앞에 남겨 바이트 그대로 보존한다.
    cmd0x21은 명령 바로 뒤부터 본문이다.
    """
    start = run['at'] + (3 if run['cmd'] == 0x20 else 1)
    _, end = read_text_run(buf, start)
    return start, end


# 위치보존(패딩) 적용 씬 집합. None = 전 씬 적용(전 씬 확대 단계).
# 2026-07-20: 0xB0 프로토타입 실기 검증 완료(프리즈 소멸·이름칸 밀림 해소) → **전 씬 확대(None)**.
# 효과: 위치 밀림發 크래시(예 0xC7 토우키치 씬) 원천 차단. 대가: 긴 런 보유 씬은 원본유지(일본어)로
# 되돌아감 → Codex가 retranslate_longer.json의 443 긴 런을 축약하면 재빌드 시 번역 복구.
POSPRES = None


_CTRL = re.compile(r'c([0-9A-F])(?::([0-9A-F]{2}))?\Z')


def encode_text(s, ch2idx, where):
    """adv_scene.render() 의 정확한 역함수.

    {wait}=0x04 / {clear}=0x06 / \\n=0x05 / {cN}=0xN / {cN:XX}=0xN,0xXX
    (렌더는 0x07·0x08·0x09 를 1인자 {cN:XX}, 0x0A-0x0F 를 무인자 {cN} 으로 낸다)
    """
    out = bytearray(); i = 0
    while i < len(s):
        if s[i] == '\n':
            out.append(0x05); i += 1
        elif s[i] == '{':
            j = s.find('}', i)
            if j < 0:
                sys.exit("제어 마커가 안 닫힘: %r @ %s" % (s[i:i + 12], where))
            tok = s[i + 1:j]
            if tok == 'wait':
                out.append(0x04)
            elif tok == 'clear':
                out.append(0x06)
            else:
                m = _CTRL.match(tok)
                if not m:
                    sys.exit("알 수 없는 마커 {%s} @ %s" % (tok, where))
                out.append(int(m.group(1), 16))
                if m.group(2) is not None:
                    out.append(int(m.group(2), 16))
            i = j + 1
        else:
            ch = s[i]
            if ch not in ch2idx:
                sys.exit("글리프 매핑 없음: %r (U+%04X) @ %s" % (ch, ord(ch), where))
            out += enc_glyph(ch2idx[ch]); i += 1
    return bytes(out)


class Allocator:
    """자유공간 풀에서 순차 배치. 씬은 뱅크 경계를 넘어도 되지만 풀 단위로 끊어 담는다."""
    def __init__(self, pool):
        self.pool = [[b, a, n, 0] for b, a, n in pool]   # bank, addr, cap, used

    def alloc(self, size):
        for p in self.pool:
            if p[2] - p[3] >= size:
                bank, addr = p[0], p[1] + p[3]
                p[3] += size
                return bank, addr
        sys.exit("자유공간 부족: %dB 요청. FREE_POOL 확장 필요." % size)

    def report(self):
        used = sum(p[3] for p in self.pool)
        cap = sum(p[2] for p in self.pool)
        return used, cap

    def manifest(self):
        return [
            {"bank": bank, "addr": addr, "capacity": cap, "used": used,
             "next_addr": addr + used, "remaining": cap - used}
            for bank, addr, cap, used in self.pool
        ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rom', default='out/wgp2_kr.smc', help='패치 대상(=build_patch 산출)')
    ap.add_argument('--out', default='out/wgp2_kr.smc')
    ap.add_argument('--kr', default='assets/translations/adventure_kr.json')
    ap.add_argument('--glyph-map', default='out/glyph_map.json')
    ap.add_argument('--base', default="roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc",
                    help='씬 원본을 읽을 **원본 ROM**. 멱등성을 위해 씬표·씬소스는 항상 여기서 읽는다 '
                         '(자기 출력물 위에 재실행하면 이미 재배치·한글화된 씬을 다시 파싱해 깨짐).')
    a = ap.parse_args()

    rom = bytearray(open(a.rom, 'rb').read())
    base = open(a.base, 'rb').read()        # 씬표·씬소스 읽기 전용 원본
    tbl = load_tbl('assets/translation_guide/glyph_table.tsv')
    ch2idx = json.load(open(a.glyph_map, encoding='utf-8'))['char2idx']
    tbl_kr = {v: k for k, v in ch2idx.items()}      # 역검증 렌더용(패치 후 매핑)
    D = foff(*DICT_SNES)
    dic = bytes(base[D:D + DICT_LEN])

    KR = json.load(open(a.kr, encoding='utf-8'))
    kr_scenes = {s['scene']: {r['at']: r['text_kr'] for r in s['runs'] if r.get('text_kr')}
                 for s in KR['scenes']}
    catalog_keys = {(sid, at) for sid, runs in kr_scenes.items() for at in runs}
    applied_keys = set()

    al = Allocator(FREE_POOL)
    n_scene = n_msg = 0
    ok_rt = ok_render = 0
    grow = 0
    skipped = []
    reclaimed_scene_slots = []

    # ★ 인게임 실기 QA로 확정된 VM-붕괴 씬(원본유지). cmd0x20/desync 가드가 못 잡는 부류
    #  (조건분기 등 런타임 제어흐름이 텍스트 밀림으로 깨져 프리즈). 정적 탐지 불가(조건분기 씬 86개 중
    #  0xB0만 깨지는데 구별 신호 없음) → 세이브+씬트레이서로 반응적 확정 후 여기 추가.
    #  근본 재번역은 cmd 0x54 스킵 메커니즘 RE 후 후속(docs/13).
    # 0xB0(카이×라 승부 후 프리즈, 2026-07-19 실기 확정)은 위치보존(POSPRES)으로 이관 —
    # 런 바이트길이를 원본과 일치시키면 프리즈 원인(위치 밀림)이 사라진다는 가설을 실기로 검증 중.
    # 위치보존이 실기에서 실패하면 여기로 되돌린다.
    FREEZE_REVERT = set()

    longer_runs = []   # 긴 런(패딩 불가) 축약 재번역 대상 → out/retranslate_longer.json

    for sid in range(N_SCENES):
        kr = kr_scenes.get(sid)
        if not kr:
            continue                                  # 번역 없는 씬 = 원본 유지
        if sid in FREEZE_REVERT:
            skipped.append((sid, 'VM-붕괴 확정 씬 → 원본유지(프리즈 방지)'))
            continue
        bank, addr = scene_src(base, sid)                    # ★ 원본 표에서
        buf, olen, endp = decompress_scene(base, bank, addr, D)  # ★ 원본 씬 스크립트
        orig_comp = endp - foff(bank, addr)
        runs, stats, _ = walk(buf)
        desync_rebuilt = False
        # ★ desync 씬 원본유지(안전, 2026-07-19): walk가 desync하는 씬(0xA8·0xB2 등)은 워커가
        #  구조를 못 잡은 것 → 앵커 기반 재빌드는 VM 유효성 미보장(round-trip 통과해도 실기 위험).
        #  전수 안전화를 위해 **통째 원본 유지**(번역 스킵). 근본 한글화는 씬 구조 RE 후 후속.
        if stats['desync']:
            skipped.append((sid, 'desync 씬 → 원본유지(안전)'))
            continue

        # ★ cmd 0x20 컨테이너(IDA 역공학 2026-07-20, adv_scene.walk 수정): operand는 재작성하지
        #  않는다. 과거 본문 길이에 맞춰 operand를 바꾼 구현이 레벨업·학교·코스 뒤 리셋 원인이었다.
        #  현재는 cmd0x20도 헤더 3B(cmd+operand)를 그대로 복사하고 본문만 원본 바이트 길이에 맞춰
        #  번역+패딩한다. 따라서 operand·후속 VM offset·디컴프 스크립트 길이가 모두 불변이다.

        # ★ 위치보존(docs/14): 이 씬을 패딩 경로로 처리할지 여부.
        pospres = (POSPRES is None) or (sid in POSPRES)

        # 긴 런(한글 인코딩 > 원본 텍스트 바이트) 탐지 → 리포트만(retranslate_longer.json, Codex 축약 SSOT).
        #  위치보존은 **런 단위 원본유지**: 긴 런은 그 런만 원본 바이트(일본어, 정확히 원본 길이)로 두고
        #  나머지 런은 번역+패딩 → 씬 전체 위치보존 유지(크래시 없음) + 긴 런만 일본어. 씬 통째 revert 안 함.
        over = set()
        for r in runs:
            if r['cmd'] not in TEXT_CMDS or r['at'] not in kr:
                continue
            start, e2 = text_run_bounds(buf, r)
            orig_len = e2 - start - 1              # 종료자 0x00 제외한 원본 텍스트 바이트
            klen = len(encode_text(kr[r['at']], ch2idx,
                                   'scene 0x%02X @0x%04X' % (sid, r['at'])))
            if klen > orig_len:
                over.add(r['at'])
                longer_runs.append({'scene': sid, 'at': r['at'], 'orig_len': orig_len,
                                    'kr_len': klen, 'over': klen - orig_len,
                                    'text_kr': kr[r['at']]})

        out = bytearray(); prev = 0; cnt = 0; jp = 0
        expect = []          # (런 순번, 기대 text_kr) — 치환하면 오프셋이 밀리므로 **순번**으로 대조
        for ri, r in enumerate(runs):
            at = r['at']
            if at not in kr or r['cmd'] not in TEXT_CMDS:
                continue
            start, end = text_run_bounds(buf, r)
            keep_len = pospres or r['cmd'] == 0x20
            if keep_len and at in over:
                # 긴 런 → 이 런만 원본 바이트 유지(일본어, 정확히 원본 길이) → 위치보존.
                # Codex 축약(retranslate_longer.json) 후 재빌드하면 번역 복구. 렌더검증 제외(원본).
                out += buf[prev:end]                   # cmd + 원본 텍스트 + 0x00 그대로
                jp += 1; prev = end
                continue
            enc = encode_text(kr[at], ch2idx, 'scene 0x%02X @0x%04X' % (sid, at))
            # cmd0x20이면 start=at+3이므로 cmd와 2바이트 operand가 원본 그대로 복사된다.
            out += buf[prev:start]
            if keep_len:
                # 위치보존: 원본 텍스트 바이트길이까지 공백으로 패딩(런 총길이 = 원본 일치).
                # 패딩은 말미 종료 제어코드 '앞'에 삽입(pad_kr) → 표시 비침·이름칸 밀림 방지.
                pad = (end - start - 1) - len(enc)
                padded = pad_kr(kr[at], pad)
                out += encode_text(padded, ch2idx,
                                   'scene 0x%02X @0x%04X pad' % (sid, at)) + b'\x00'
                expect.append((ri, padded))
            else:
                out += enc + b'\x00'
                expect.append((ri, kr[at]))
            prev = end; cnt += 1; applied_keys.add((sid, at))
        out += buf[prev:]
        script = bytes(out)

        if pospres and len(script) != len(buf):
            sys.exit("씬 0x%02X 위치보존 길이 불일치: %d != %d" % (sid, len(script), len(buf)))
        for r in runs:
            if r['cmd'] == 0x20 and r['at'] in kr:
                at = r['at']
                if script[at + 1:at + 3] != buf[at + 1:at + 3]:
                    sys.exit("씬 0x%02X cmd0x20 operand 변경 @0x%04X" % (sid, at))

        # 번역된 런이 하나도 없으면(모든 kr 런이 긴 런→원본유지) 스크립트가 원본과 동일 → 재배치 불필요.
        if cnt == 0:
            if jp:
                skipped.append((sid, '전 런이 긴 런 → 원본유지(축약 대상)'))
            continue

        comp = compress_scene(script, dic)
        nb, na = al.alloc(len(comp))
        dst = foff(nb, na)
        rom[dst:dst + len(comp)] = comp

        e = SCENE_TBL + sid * 3
        rom[e] = na & 0xFF
        rom[e + 1] = (na >> 8) & 0xFF
        rom[e + 2] = (nb - 0xC4) & 0xFF
        # 이 씬의 모든 런타임 진입은 중앙 씬표 $C6:9C57을 경유한다. 표를 새 주소로
        # 바꾼 뒤의 원본 압축 슬롯은 필드 빌더가 2MB 내부 재배치에 사용할 수 있다.
        if addr + orig_comp <= 0x10000:
            reclaimed_scene_slots.append({
                'scene': sid, 'bank': bank, 'addr': addr, 'capacity': orig_comp,
            })

        grow += len(comp) - orig_comp
        n_scene += 1; n_msg += cnt

        # ---- 역검증 ----
        b2, a2 = scene_src(rom, sid)
        buf2, _, _ = decompress_scene(rom, b2, a2, D)
        if buf2 == script:
            ok_rt += 1
        if desync_rebuilt:
            # walk가 desync하는 씬 → round-trip(buf2==script)이 곧 렌더 보장(스크립트에 한글 글리프가 정위치).
            if buf2 == script:
                ok_render += 1
            else:
                skipped.append((sid, 'desync재빌드 round-trip 실패'))
        else:
            runs2, st2, endp2 = walk(buf2)
            if pospres and [(r['at'], r['cmd']) for r in runs2] != [
                    (r['at'], r['cmd']) for r in runs]:
                sys.exit("씬 0x%02X 위치보존 런 주소/명령 불일치" % sid)
            bad = [(ri, s, render(runs2[ri]['text'], tbl_kr))
                   for ri, s in expect
                   if ri >= len(runs2) or render(runs2[ri]['text'], tbl_kr) != s]
            if not bad:
                ok_render += 1
            else:
                skipped.append((sid, '렌더불일치 %d건 예: %r != %r' % (len(bad), bad[0][1], bad[0][2])))

    unapplied = sorted(catalog_keys - applied_keys)
    if unapplied:
        sample = ', '.join('0x%02X@0x%04X' % key for key in unapplied[:8])
        sys.exit("번역 카탈로그 미반영 %d/%d: %s%s" % (
            len(unapplied), len(catalog_keys), sample, ' …' if len(unapplied) > 8 else ''))

    os.makedirs('out', exist_ok=True)
    open(a.out, 'wb').write(rom)
    used, cap = al.report()
    open('out/adv_free_manifest.json', 'w', encoding='utf-8').write(
        json.dumps({
            'note': 'build_adv.py 재배치 결과. build_field.py는 중앙 씬표가 더는 참조하지 않는 원본 씬 슬롯만 재사용한다.',
            'pools': al.manifest(),
            'reclaimed_scene_slots': reclaimed_scene_slots,
        }, ensure_ascii=False, indent=1) + '\n')

    # 긴 런(축약 재번역 대상) 리포트 — Codex 축약 배치의 입력 SSOT.
    longer_runs.sort(key=lambda x: (-x['over'], x['scene'], x['at']))
    n_scenes_over = len({x['scene'] for x in longer_runs})
    open('out/retranslate_longer.json', 'w', encoding='utf-8').write(
        json.dumps({'count': len(longer_runs), 'scenes': n_scenes_over,
                    'note': '한글 인코딩이 원본 텍스트 바이트를 초과하는 cmd0x20/0x21 런. '
                            '의미 보존하며 원본 orig_len 바이트 이하로 축약 재번역 대상. '
                            'over = 초과 바이트(≥이만큼 줄여야 위치보존 패딩 가능).',
                    'runs': longer_runs}, ensure_ascii=False, indent=1))

    print("=== 어드벤처 재삽입 ===")
    print("  번역 카탈로그 반영 %d / %d" % (len(applied_keys), len(catalog_keys)))
    print("  번역 반영 씬 %d / 메시지 %d" % (n_scene, n_msg))
    print("  재배치 사용 %d B / 풀 %d B (%.1f%%)" % (used, cap, 100 * used / cap))
    print("  압축 증가분 합계 %+d B" % grow)
    print("  역검증 round-trip : %d / %d" % (ok_rt, n_scene))
    print("  역검증 렌더일치   : %d / %d" % (ok_render, n_scene))
    print("  긴 런(축약 대상)  : %d런 / %d씬 → out/retranslate_longer.json" % (
        len(longer_runs), n_scenes_over))
    if skipped:
        print("  ⚠️ 건너뜀 %d: %s" % (len(skipped), skipped[:5]))
    print("  -> %s" % a.out)
    if ok_rt != n_scene or ok_render != n_scene:
        sys.exit("역검증 실패")


if __name__ == '__main__':
    main()
