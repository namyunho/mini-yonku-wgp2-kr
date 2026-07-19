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

    al = Allocator(FREE_POOL)
    n_scene = n_msg = 0
    ok_rt = ok_render = 0
    grow = 0
    skipped = []

    # ★ 인게임 실기 QA로 확정된 VM-붕괴 씬(원본유지). cmd0x20/desync 가드가 못 잡는 부류
    #  (조건분기 등 런타임 제어흐름이 텍스트 밀림으로 깨져 프리즈). 정적 탐지 불가(조건분기 씬 86개 중
    #  0xB0만 깨지는데 구별 신호 없음) → 세이브+씬트레이서로 반응적 확정 후 여기 추가.
    #  근본 재번역은 cmd 0x54 스킵 메커니즘 RE 후 후속(docs/13).
    FREEZE_REVERT = {0xB0}   # 카이×라 승부 후 카이 대화 프리즈(2026-07-19 실기 확정)

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

        # ★ cmd 0x20 씬 가드(치명 버그 수정 2026-07-19, 인게임 리셋/행 규명):
        #  cmd 0x20은 op 크기와 무관하게 **단순 텍스트런이 아니라 특수 명령**이다 — 아이템 지급,
        #  레벨업 표시(씬 0x69 "레벨이 올랐다" 6런), 메뉴 컨테이너(op 상위 0x02/0x31 플래그, 내부에
        #  0x21 임베드) 등. build_adv가 이를 `newop=len(body)+2`로 재작성하면 VM 구조가 깨져
        #  **씬 종료 후 리셋(레벨업/튜토리얼/코스 후) 또는 선택메뉴 미표시·행**(사용자 실측 다수).
        #  앞 텍스트런만 번역해도 씬 길이가 밀려 위치 의존 컨테이너가 깨진다.
        #  → **cmd 0x20 런을 가진 씬은 통째 원본 유지**(바이트 조작 0). 플레이 가능성 우선.
        #  근본 한글화는 cmd 0x20 명령 포맷 역공학 후 후속 과제.
        if any(r['cmd'] == 0x20 and r['at'] in kr for r in runs):
            skipped.append((sid, 'cmd0x20 특수명령 씬 → 원본유지(리셋/행 방지)'))
            continue

        out = bytearray(); prev = 0; cnt = 0
        expect = []          # (런 순번, 기대 text_kr) — 치환하면 오프셋이 밀리므로 **순번**으로 대조
        for ri, r in enumerate(runs):
            at = r['at']
            if at not in kr:
                continue
            expect.append((ri, kr[at]))
            if r['cmd'] == 0x21:
                _, end = read_text_run(buf, at + 1)
                out += buf[prev:at + 1]
                out += encode_text(kr[at], ch2idx, 'scene 0x%02X @0x%04X' % (sid, at)) + b'\x00'
            else:                                     # cmd 0x20: 2B 오퍼랜드 = 스킵량
                op = buf[at + 1] | (buf[at + 2] << 8)
                end = at + 1 + op
                body = encode_text(kr[at], ch2idx, 'scene 0x%02X @0x%04X' % (sid, at)) + b'\x00'
                newop = len(body) + 2                 # 커서 = p+1+op ⇒ op = 2 + 본문
                out += buf[prev:at + 1]
                out += bytes([newop & 0xFF, (newop >> 8) & 0xFF]) + body
            prev = end; cnt += 1
        out += buf[prev:]
        script = bytes(out)

        comp = compress_scene(script, dic)
        nb, na = al.alloc(len(comp))
        dst = foff(nb, na)
        rom[dst:dst + len(comp)] = comp

        e = SCENE_TBL + sid * 3
        rom[e] = na & 0xFF
        rom[e + 1] = (na >> 8) & 0xFF
        rom[e + 2] = (nb - 0xC4) & 0xFF

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
            bad = [(ri, s, render(runs2[ri]['text'], tbl_kr))
                   for ri, s in expect
                   if ri >= len(runs2) or render(runs2[ri]['text'], tbl_kr) != s]
            if not bad:
                ok_render += 1
            else:
                skipped.append((sid, '렌더불일치 %d건 예: %r != %r' % (len(bad), bad[0][1], bad[0][2])))

    os.makedirs('out', exist_ok=True)
    open(a.out, 'wb').write(rom)
    used, cap = al.report()

    print("=== 어드벤처 재삽입 ===")
    print("  번역 반영 씬 %d / 메시지 %d" % (n_scene, n_msg))
    print("  재배치 사용 %d B / 풀 %d B (%.1f%%)" % (used, cap, 100 * used / cap))
    print("  압축 증가분 합계 %+d B" % grow)
    print("  역검증 round-trip : %d / %d" % (ok_rt, n_scene))
    print("  역검증 렌더일치   : %d / %d" % (ok_render, n_scene))
    if skipped:
        print("  ⚠️ 건너뜀 %d: %s" % (len(skipped), skipped[:5]))
    print("  -> %s" % a.out)
    if ok_rt != n_scene or ok_render != n_scene:
        sys.exit("역검증 실패")


if __name__ == '__main__':
    main()
