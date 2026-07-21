#!/usr/bin/env python3
"""어드벤처 씬 VM 워커 — 디컴프 스트림을 구조화 메시지로 파싱.

씬 인터프리터 역공학 결과(docs/08 SSOT)에 따른 오프라인 재현:
  - 디컴프 버퍼($7E:9DDE)는 텍스트가 아니라 **씬 스크립트 VM 바이트코드**.
  - 상태0 핸들러 $C0:3F40 이 1바이트(명령)를 페치 → JSR ($3E3E,X).
  - 텍스트런은 두 명령으로만 시작한다:
      cmd 0x20 ($C0:3FE6, 상태9)  : 2바이트 오퍼랜드 = 스킵량.
                                    텍스트 = [cursor+2, cursor+operand), 커서 += operand.
      cmd 0x21 ($C0:400A, 상태0A) : 오퍼랜드 없음. 텍스트 = cursor부터 code 0x00까지.
                                    종료 후 커서 = 0x00 다음(핸들러 $C0:40B7).
  - 텍스트런 내부 인코딩(프린터 $C0:4022 / 제어표 $C0:413F):
      code >= 0x10        -> 글리프 = code - 0x10
      code 01/02/03       -> 2바이트 글리프 = (code<<8|next) - 0x10   ($C0:40CF)
      code 04 xx          -> 제어 + 1인자   ($C0:40E5; xx=00 박스/화자, 05 페이지, 06 메시지끝)
      code 05             -> 개행           ($C0:40EA)
      code 06 / 07 xx     -> 제어           ($C0:40EF / $C0:40F4, 07은 1인자)
      code 08 / 09        -> 제어           ($C0:4117 / $C0:4135)
      code 00             -> 텍스트런 종료  ($C0:40B7)
  - 그 외 바이트는 전부 스크립트 명령 → 오퍼랜드 크기표(scripts/adv_vm_map.py 산출)대로 스킵.
"""
import sys
sys.path.insert(0, 'scripts')
from adv_codec import decompress, foff, ROM, DICT_SNES
from decode_script import load_tbl

# 명령별 "소비 프로그램" (scripts/adv_vm_map.py 정적 산출):
#   ('b', n) = 고정 n바이트 오퍼랜드 / ('expr',) = $C0:5B4A 표현식(가변) / ('cond',) = $C0:5AC6 조건부
CMD_PROG = {
    0x00: [], 0x01: [('expr',)], 0x02: [('b', 2)], 0x03: [('b', 4), ('expr',)],
    0x04: [('b', 2), ('expr',)], 0x05: [('b', 4)], 0x06: [], 0x07: [('b', 4), ('expr',)],
    0x08: [('b', 8), ('expr',), ('expr',)], 0x09: [('b', 4)],
    # cmd 0x10 ($C0:444E) = 씬 **점프**(tail jump). cmd 0x11 과 같은 표 $C6:9C57 조회 + JSL $C03D4B
    # 이지만 복귀 프레임을 안 만든다 → 이 스크립트는 여기서 끝(새 씬 버퍼로 교체, 커서 0 리셋).
    # 오퍼랜드 = 씬 id 워드 2바이트.
    0x10: [('b', 2)],
    # cmd 0x11 ($C0:4498) = 서브스크립트 호출. 오퍼랜드 = 씬 id 워드(표 $C6:9C57 색인).
    # 핸들러가 $9A47 을 직접 안 올리고 프레임에 '커서+2'를 저장($9A68,X) → 복귀시 $3F84 가 복원.
    # ⇒ 부모 스크립트 기준 실질 소비 = 2바이트.
    0x11: [('b', 2)],
    0x12: [], 0x13: [], 0x14: [], 0x15: [], 0x16: [('b', 1)], 0x17: [('b', 1)],
    0x20: [], 0x21: [], 0x22: [('b', 1)], 0x23: [], 0x24: [], 0x25: [],
    0x26: [('expr',), ('expr',)], 0x28: [], 0x29: [('b', 2)], 0x2A: [('b', 3)],
    0x2B: [('expr',), ('expr',), ('b', 3)], 0x2C: [('b', 2)], 0x2D: [('b', 2)],
    0x2E: [], 0x2F: [], 0x30: [], 0x31: [('b', 4)], 0x32: [('b', 1)], 0x33: [],
    0x34: [], 0x35: [('b', 1)], 0x36: [('b', 1)], 0x37: [], 0x38: [('b', 1)],
    0x39: [('b', 1)], 0x40: [('b', 3)], 0x41: [('b', 1)], 0x42: [('b', 2)],
    0x43: [('expr',)], 0x44: [('expr',)], 0x45: [('expr',)], 0x46: [('expr',)],
    # 0x50/0x51 은 핸들러가 상태만 push 하고 실제 바이트는 그 상태가 먹는다:
    #   cmd 0x50 -> 상태16 $C0:5268: 카운터 0x80회 후 'LDA $9A47; ADC #$0010' = 16바이트 블록
    #   cmd 0x51 -> 상태17 $C0:52B6: 1바이트씩 읽다 0x00 이면 pop = 0x00종료 바이트리스트
    # cmd 0x52 ($C0:52D1) = 커서에서 1바이트를 읽고 즉시 커서를 1 올린 뒤 게임 상태를 갱신.
    # cmd 0x53 ($C0:52F2) = 1바이트 고정. JSR $5AC6 뒤 BCC 는 곧장 RTS 로 가고, 캐리셋
    # 경로도 추가 바이트를 안 읽는다(플래그 셋만) → 조건부 워드를 읽는 건 cmd 0x54 뿐.
    0x47: [('expr',)], 0x50: [('b', 16)], 0x51: [('list0',)], 0x52: [('b', 1)], 0x53: [('b', 1)],
    0x54: [('cond',)], 0x55: [('b', 1)], 0x56: [('b', 1)], 0x57: [('b', 2)],
    # cmd 0x58 ($C0:5758): 첫 식 1개 + 런타임 분기 양쪽에서 각각 식 3개.
    # 선형 디스어셈블에는 JSR $5B4A가 7회 보이지만 두 분기는 상호배타라 직렬화 인자는 총 4식이다.
    0x58: [('expr',), ('expr',), ('expr',), ('expr',)],
    0x59: [('b', 1), ('expr',), ('expr',)], 0x5A: [('b', 1), ('b', 1)],
    0x5D: [('expr',), ('expr',)], 0x5E: [('b', 1), ('expr',)], 0x5F: [('b', 1)],
    0x80: [('b', 1)],
}

# 표현식 서브옵 소비 프로그램(표 $C0:5B7C).
# $C0:5B4A 는 0x00까지 한 표현식을 읽지만, 일부 서브옵 핸들러가 다시 $5B4A를
# 호출하므로 문법은 평면 바이트열이 아니라 재귀 prefix 식이다. 예:
#   44 01 0E 00 00 01 04 00 1F 00
#   └44 [중첩식: 01 0E00 00] 01 0400 1F 00
# ('expr',) 수는 각 핸들러의 JSR $5B4A 호출 수, ('b', n)은 커서 직접 소비량이다.
EXPR_PROG = {
    0x01: [('b', 2)], 0x02: [('b', 1)],
    0x40: [('b', 1)], 0x41: [('expr',)], 0x42: [('expr',), ('expr',)],
    0x43: [('expr',)], 0x44: [('expr',)], 0x45: [('expr',), ('expr',)],
    0x46: [('expr',)], 0x47: [('expr',)], 0x48: [('expr',)],
    0x4B: [('b', 1)], 0x4E: [('b', 1)], 0x50: [('b', 1)],
    0x51: [('b', 1)], 0x52: [('b', 1)], 0x53: [('expr',)],
    0x55: [('expr',)], 0x56: [('expr',), ('expr',)],
    0x57: [('expr',), ('expr',)], 0x58: [('b', 2)],
    0x59: [('expr',)], 0x5A: [('expr',)], 0x5C: [('b', 2)],
    0x5D: [('expr',)], 0x5F: [('b', 2)], 0x60: [('expr',)],
    0x61: [('expr',)], 0x62: [('b', 1)], 0x63: [('b', 1)],
    0x64: [('b', 2)], 0x66: [('expr',)], 0x67: [('b', 4)],
}
VALID_EXPR_SUBOPS = frozenset(
    (0x00, 0x01, 0x02, *range(0x10, 0x34), *range(0x40, 0x68))
)

# 기존 adventure_kr 카탈로그는 분기 뒤 비실행 블록까지 관대하게 선형 탐색한 옛 워커의
# run 위치를 SSOT로 쓴다. 새 필드 레코드에는 아래 호환 규칙을 쓰지 않고 실제 소비 규칙을 쓴다.
LEGACY_CMD_OVERRIDES = {
    0x52: [],
    0x58: [('expr',), ('expr',), ('expr',), ('expr',), ('expr',), ('expr',), ('expr',)],
}
LEGACY_EXPR_ARG = {
    0x01: 2, 0x02: 1, 0x40: 1, 0x4B: 1, 0x4E: 1, 0x50: 1, 0x51: 1, 0x52: 1,
    0x58: 2, 0x5C: 2, 0x5F: 2, 0x62: 1, 0x63: 1, 0x64: 2, 0x67: 4,
}
TEXT_CMDS = (0x20, 0x21)

# 오퍼랜드 크기가 조건부인 명령 (핸들러가 JSR $C0:5AC6 으로 판정 — ROM 전역 2곳뿐):
#   $5AC6: op바이트≠0 → 캐리SET → 워드 2바이트 추가소비(총 3)
#          op바이트==0 → 런타임 $7E:99A5 에 의존(0이면 캐리CLEAR=1바이트)
# 정적 워크에서는 op≠0 → 3, op==0 → 1 로 본다(후자는 런타임 의존이라 근사).
COND_CMDS = (0x53, 0x54)   # CMD_PROG 의 ('cond',) 로 처리


def read_text_run(buf, p, end=None):
    """텍스트런을 [코드…] 리스트로 파싱. 반환 (codes, next_p)."""
    codes = []
    while p < len(buf):
        if end is not None and p >= end:
            return codes, p
        b = buf[p]
        if b == 0x00 and end is None:
            return codes, p + 1               # cmd 0x21: 종료자까지
        if b == 0x00:
            p += 1; continue                  # cmd 0x20: 길이로 한정 → 0x00은 그냥 종료표시
        if b in (0x01, 0x02, 0x03):
            codes.append(('g', ((b << 8) | buf[p + 1]) - 0x10)); p += 2
        elif b == 0x04:
            codes.append(('wait', None)); p += 1     # $40E5 -> $49B1: 상태0E push (입력대기)
        elif b == 0x05:
            codes.append(('nl', None)); p += 1       # $40EA -> $4A1C: 펜X=좌마진 (개행)
        elif b == 0x06:
            codes.append(('clear', None)); p += 1    # $40EF -> $4979: 상태0C push (박스클리어)
        elif b == 0x07:
            codes.append(('c7', buf[p + 1])); p += 2  # $40F4: JSR $415F = 1인자
        elif b == 0x08:
            codes.append(('c8', buf[p + 1])); p += 2  # $4117: 1인자 (표 $C0:3ACF -> $9A5E)
        elif b == 0x09:
            codes.append(('c9', buf[p + 1])); p += 2  # $4135: 1인자 (ASL -> $9A64)
        elif b < 0x10:
            codes.append(('c%X' % b, None)); p += 1   # 0A-0F: $40AA no-op
        else:
            codes.append(('g', b - 0x10)); p += 1
    return codes, p


def render(codes, tbl):
    o = ''
    for k, v in codes:
        if k == 'g':
            o += tbl.get(v, '□<%03X>' % v)
        elif k == 'nl':
            o += '\n'
        elif k == 'wait':
            o += '{wait}'
        elif k == 'clear':
            o += '{clear}'
        else:
            o += '{%s%s}' % (k, '' if v is None else ':%02X' % v)
    return o


class ParseError(Exception):
    """VM/표현식 문법에서 벗어난 바이트 위치."""

    def __init__(self, at):
        super().__init__(at)
        self.at = at


def read_expr_recursive(buf, p):
    """$C0:5B4A 재귀 표현식 하나를 종료자 0x00까지 소비."""
    while p < len(buf):
        at = p
        sub = buf[p]; p += 1
        if sub == 0x00:
            return p
        if sub not in VALID_EXPR_SUBOPS:
            raise ParseError(at)
        for step in EXPR_PROG.get(sub, ()):
            if step[0] == 'b':
                p += step[1]
                if p > len(buf):
                    raise ParseError(at)
            elif step[0] == 'expr':
                p = read_expr_recursive(buf, p)
    raise ParseError(len(buf))


def read_expr(buf, p):
    """기존 adventure_kr run 주소 호환용 평면 표현식 파서."""
    while p < len(buf):
        sub = buf[p]; p += 1
        if sub == 0x00:
            return p
        p += LEGACY_EXPR_ARG.get(sub, 0)
    return p


def consume(buf, p, cmd, strict=False):
    """명령 바이트 다음 위치 p 에서 오퍼랜드를 소비하고 다음 명령 위치를 반환."""
    prog = CMD_PROG[cmd] if strict else LEGACY_CMD_OVERRIDES.get(cmd, CMD_PROG[cmd])
    for step in prog:
        if step[0] == 'b':
            p += step[1]
        elif step[0] == 'expr':
            p = read_expr_recursive(buf, p) if strict else read_expr(buf, p)
        elif step[0] == 'cond':
            op = buf[p]; p += 1          # $5AC6: op≠0 → 캐리SET → 워드 2B 추가
            if op != 0:
                p += 2
        elif step[0] == 'list0':         # 상태17: 0x00 종료 바이트리스트
            while p < len(buf) and buf[p] != 0x00:
                p += 1
            p += 1
    return p


def walk(buf, start=0, limit=None, strict=False):
    """스크립트를 선형 워크. strict=True면 실제 재귀 표현식 문법을 적용."""
    p = start
    runs = []
    stats = {'cmds': 0, 'desync': 0}
    n = len(buf) if limit is None else min(len(buf), limit)
    while p < n:
        cmd = buf[p]
        if cmd not in CMD_PROG:
            stats['desync'] += 1
            return runs, stats, p            # 미정의 명령 = 워크 이탈
        stats['cmds'] += 1
        if cmd == 0x21:
            codes, p2 = read_text_run(buf, p + 1)
            runs.append({'cmd': 0x21, 'at': p, 'text': codes})
            p = p2
        elif cmd == 0x20:
            # cmd0x20 컨테이너($C0:3FE6, IDA 역공학 2026-07-20): operand(2B) 뒤 텍스트런
            # (커서+2=p+3 부터 0x00까지). 런타임 operand는 스킵값이나 **컨테이너 본문은 정상 중첩
            # VM 스크립트**(cmd0x21 런들+선택지 {c8:07}…{c8:00}+cmd0x00)라 0x00 뒤부터 계속 워크한다.
            # (operand만큼 스킵하던 옛 방식은 over-read → 중첩 런을 못 잡아 원본유지밖에 못 했음.)
            # 근거·경로: docs/13, [[adv-cmd20-overread-bug]] 메모리. 텍스트=p+3, 헤더=cmd+operand 3B.
            codes, p2 = read_text_run(buf, p + 3)
            runs.append({'cmd': 0x20, 'at': p, 'text': codes})
            p = p2
        else:
            try:
                p = consume(buf, p + 1, cmd, strict=strict)
            except ParseError as exc:
                stats['desync'] += 1
                return runs, stats, exc.at
    return runs, stats, p


def main():
    rom = open(ROM, 'rb').read()
    tbl = load_tbl('assets/translation_guide/glyph_table.tsv')
    bank = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0xC5
    addr = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x5950
    olen = int(sys.argv[3]) if len(sys.argv) > 3 else 1200
    buf, _ = decompress(rom, bank, addr, olen, foff(*DICT_SNES))
    runs, stats, endp = walk(buf)
    print("src $%02X:%04X  decomp=%dB  cmds=%d  text_runs=%d  stop@0x%04X %s" % (
        bank, addr, len(buf), stats['cmds'], len(runs), endp,
        '(DESYNC)' if stats['desync'] else '(clean)'))
    print()
    for r in runs:
        print("[0x%04X cmd%02X] %s" % (r['at'], r['cmd'], render(r['text'], tbl).replace('\n', ' / ')))


if __name__ == '__main__':
    main()
