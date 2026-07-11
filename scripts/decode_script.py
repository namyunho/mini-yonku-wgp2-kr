#!/usr/bin/env python3
"""대사 스크립트 인코딩 디코더 (정적 모델 · 파서 $C1:9554 역공학 결과).

인코딩 모델 (뱅크 $C7 바이트 스트림):
  0x00        = 종료자(end)
  0x01..0x04  = 2바이트 글리프 프리픽스 → glyph = (byte<<8 | next) - 0x10
                (즉 값 (glyph+0x10)을 빅엔디언 가변길이로 저장, 상위바이트가 프리픽스)
  0x05        = 개행(newline)  {nl}
  0x06        = 즉시 반환/대기  {wait}
  0x07 NN     = 렌더 파라미터(1인자, $7E9A64)  {p:NN}
  0x08..0x0F  = 미정의(실스크립트 미사용 추정)  {op:XX}
  0x10..0xFF  = 단일바이트 글리프 → glyph = byte - 0x10  (인덱스 0x00..0xEF)

glyph 인덱스 → 문자: 폰트 시트($CA:1137) 배열 순서 표(별도, glyph_table.tsv) 참조.
"""
import sys, re

def decode(data, tbl=None):
    """data: bytes. tbl: {glyph_index:int -> char:str} or None.
    반환: list of tokens. 각 토큰 = ('glyph', idx, nbytes) | ('ctrl', name, args_bytes)."""
    out = []
    i = 0
    while i < len(data):
        b = data[i]
        if b == 0x00:
            out.append(('ctrl', 'end', b'')); i += 1; break
        elif 0x01 <= b <= 0x04:
            if i + 1 >= len(data):
                out.append(('ctrl', f'trunc{b:02X}', b'')); i += 1; break
            g = ((b << 8) | data[i+1]) - 0x10
            out.append(('glyph', g, 2)); i += 2
        elif b == 0x05:
            out.append(('ctrl', 'nl', b'')); i += 1
        elif b == 0x06:
            out.append(('ctrl', 'wait', b'')); i += 1
        elif b == 0x07:
            arg = data[i+1:i+2]
            out.append(('ctrl', 'param', arg)); i += 2
        elif 0x08 <= b <= 0x0F:
            out.append(('ctrl', f'op{b:02X}', b'')); i += 1
        else:  # 0x10..0xFF
            g = b - 0x10
            out.append(('glyph', g, 1)); i += 1
    return out

def render(tokens, tbl=None):
    s = []
    for t in tokens:
        if t[0] == 'glyph':
            idx = t[1]
            if tbl and idx in tbl:
                s.append(tbl[idx])
            else:
                s.append(f'[{idx:03X}]')
        else:
            name, args = t[1], t[2]
            if args:
                s.append('{%s:%s}' % (name, args.hex().upper()))
            else:
                s.append('{%s}' % name)
    return ''.join(s)

import re
# render() 출력 토큰화: [HEX]=글리프, {name} 또는 {name:HEXARGS}=제어코드
_TOKEN_RE = re.compile(r'\[([0-9A-Fa-f]+)\]|\{([^}]*)\}')

def parse(text):
    """render(tbl=None) 출력 문자열 → 토큰 리스트 (render의 역)."""
    tokens = []
    for m in _TOKEN_RE.finditer(text):
        if m.group(1) is not None:
            tokens.append(('glyph', int(m.group(1), 16), 0))
        else:
            body = m.group(2)
            if ':' in body:
                name, hexargs = body.split(':', 1)
                tokens.append(('ctrl', name, bytes.fromhex(hexargs)))
            else:
                tokens.append(('ctrl', body, b''))
    return tokens

def encode(tokens):
    """토큰 리스트 → 바이트 (decode의 역). 글리프 인코딩은 canonical(가변길이 결정적)."""
    out = bytearray()
    for t in tokens:
        if t[0] == 'glyph':
            v = t[1] + 0x10
            if v < 0x100:
                out.append(v)                    # 1바이트 글리프
            else:
                out.append((v >> 8) & 0xFF)       # 2바이트: 프리픽스 0x01..0x04
                out.append(v & 0xFF)
        else:  # ('ctrl', name, args)
            name, args = t[1], t[2]
            if name == 'end':    out.append(0x00)
            elif name == 'nl':   out.append(0x05)
            elif name == 'wait': out.append(0x06)
            elif name == 'param':
                out.append(0x07); out += args
            elif name.startswith('op') and len(name) == 4:      # op08..op0F
                out.append(int(name[2:], 16))
            elif name.startswith('trunc'):                       # 블록끝 잘린 프리픽스
                out.append(int(name[5:], 16)); out += args
            else:
                raise ValueError(f'알 수 없는 제어코드: {name!r}')
    return bytes(out)

def load_tbl(path):
    tbl = {}
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n')
            if not line or line.startswith('#'): continue
            parts = line.split('\t')
            if len(parts) < 2: continue
            idx = int(parts[0], 0); tbl[idx] = parts[1]
    return tbl

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('hex', help='공백/줄바꿈 포함 hex 문자열, 또는 @파일')
    ap.add_argument('--tbl', default=None, help='glyph_index<TAB>char 표')
    a = ap.parse_args()
    if a.hex.startswith('@'):
        raw = open(a.hex[1:]).read()
    else:
        raw = a.hex
    data = bytes.fromhex(re.sub(r'[^0-9A-Fa-f]', '', raw))
    tbl = load_tbl(a.tbl) if a.tbl else None
    toks = decode(data, tbl)
    print(render(toks, tbl))
    # 글리프 인덱스 목록도 출력
    gid = [f'{t[1]:03X}' for t in toks if t[0] == 'glyph']
    print('glyph indices:', ' '.join(gid))

if __name__ == '__main__':
    main()
