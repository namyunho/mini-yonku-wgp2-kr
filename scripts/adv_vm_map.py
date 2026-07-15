#!/usr/bin/env python3
"""어드벤처 씬 VM — 명령/표현식 계층의 바이트 소비량 자동 추론 (정적 디스어셈블).

씬 인터프리터는 3계층이다(docs/08 SSOT):
  1) 명령   : 상태0 핸들러 $C0:3F40 이 1바이트 페치 → JSR ($3E3E,X)   (표 $C0:3E3E, 129엔트리)
  2) 표현식 : $C0:5B4A 가 서브옵을 0x00 만날 때까지 루프 → JSR ($5B7C,X) (표 $C0:5B7C, 104엔트리)
  3) 텍스트 : 프린터 $C0:4022 가 코드 페치 → JMP ($413F,X)            (표 $C0:413F, 16엔트리)

각 핸들러를 선형 디스어셈블(VM 전역 REP #$30 → M=0/X=0 고정)해 스크립트 커서 $7E:9A47
전진량을 순서대로 뽑는다. 산출 = 명령별 "소비 프로그램"(consumption program):
  ('b', n)  고정 n바이트 오퍼랜드
  ('expr',) $5B4A 표현식 (가변 — 워커가 재귀 파싱)
  ('cond',) $5AC6 조건부 (op≠0 이면 워드 2바이트 추가)
"""
import sys
sys.path.insert(0, 'scripts')
from disasm import disasm

ROM = "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
CMD_TBL, N_CMD = 0x3E3E, 129
EXPR_TBL, N_EXPR = 0x5B7C, 104
CURSOR = "$9A47"


def body_of(line):
    b = line.split("  ", 2)[-1].strip()
    return b[:-2].strip() if b.endswith(" ?") else b


def trace_handler(rom, addr, limit=0x140):
    """핸들러를 선형 디스어셈블해 첫 RTS/RTL까지의 소비 프로그램을 뽑는다."""
    prog = []
    iny = 0
    reading = False          # LDY $9A47 ~ STY $9A47 구간
    for l in disasm(rom, addr, limit, 0xC0, False, False):
        b = body_of(l)
        if b.startswith("LDY " + CURSOR):
            reading, iny = True, 0
        elif b == "INY" and reading:
            iny += 1
        elif b.startswith("STY " + CURSOR) and reading:
            prog.append(('b', iny)); reading = False
        elif b.startswith("JSR $5B4A"):
            prog.append(('expr',))
        elif b.startswith("JSR $5AC6"):
            prog.append(('cond',))
        elif b.startswith("JSR $5F2D") or b.startswith("JSR $5F43"):
            pass
        elif b in ("RTS", "RTL"):
            break
    return prog


def trace_expr_subop(rom, addr, limit=0x40):
    """표현식 서브옵: $5B4A 가 이미 Y=커서로 세팅해 호출 → 핸들러 내 INY 수가 소비량."""
    iny = 0
    saw = False
    for l in disasm(rom, addr, limit, 0xC0, False, False):
        b = body_of(l)
        if b == "INY":
            iny += 1
        elif b.startswith("STY " + CURSOR):
            saw = True; break
        elif b in ("RTS", "RTL"):
            break
    return iny if saw else 0


def main():
    rom = open(ROM, 'rb').read()

    print("=== 1) 명령 계층 (표 $C0:3E3E) ===")
    cmds = {}
    for i in range(N_CMD):
        o = CMD_TBL + i * 2
        h = rom[o] | (rom[o + 1] << 8)
        if not h:
            continue
        prog = trace_handler(rom, h)
        cmds[i] = prog
        desc = " + ".join(("%dB" % p[1]) if p[0] == 'b' else p[0].upper() for p in prog) or "0B"
        print("  cmd %02X  $C0:%04X  %s" % (i, h, desc))

    print()
    print("=== 2) 표현식 계층 (표 $C0:5B7C) ===")
    exprs = {}
    for i in range(N_EXPR):
        o = EXPR_TBL + i * 2
        h = rom[o] | (rom[o + 1] << 8)
        if not h:
            continue
        n = 0 if i == 0 else trace_expr_subop(rom, h)
        exprs[i] = n
        if n:
            print("  sub %02X  $C0:%04X  %dB" % (i, h, n))
    nz = {k: v for k, v in exprs.items() if v}
    print("  (그 외 %d개 서브옵 = 0바이트 = 스택 연산자)" % (len(exprs) - len(nz)))

    print()
    print("CMD_PROG = " + repr(cmds))
    print()
    print("EXPR_ARG = " + repr(nz))


if __name__ == '__main__':
    main()
