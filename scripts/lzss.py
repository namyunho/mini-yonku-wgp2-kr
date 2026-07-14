#!/usr/bin/env python3
"""오프닝 그래픽 LZSS 코덱 (엔진 $C0:0D91~0E1x 포팅) — 해제/재압축.
포맷(표준 LZSS, 4KB 링버퍼):
  - 링버퍼 4096B($7F:0000), 시작 위치 r=0xFEE, 초기값 0(부팅 WRAM 클리어).
  - 플래그 비트 LSB first: 1=리터럴(소스1B), 0=매치(소스2B LE word →
      pos=word>>4(12bit 링위치), len=(word&0xF)+3). 링에서 len바이트 복사.
  - out_len 도달까지.
소스 위치(원본 ROM, 트레이스 확정):
  $C7:1574 len 12800 / $C7:347C 2048 / $C7:382F 4096 / $C7:3A3F 8192
  $C7:1218 4096 / $C7:1148 640 / $C7:0D11 2048
"""
import sys

def foff(bank, addr): return ((bank & 0x3F) << 16) | addr

def decompress(rom, src_off, out_len):
    ring = bytearray(4096)
    r = 0xFEE
    out = bytearray()
    p = src_off
    flags = 0
    while len(out) < out_len:
        flags >>= 1
        if not (flags & 0x100):
            flags = rom[p] | 0xFF00; p += 1
        if flags & 1:                      # 리터럴
            b = rom[p]; p += 1
            out.append(b); ring[r] = b; r = (r + 1) & 0xFFF
        else:                              # 매치
            word = rom[p] | (rom[p + 1] << 8); p += 2
            length = (word & 0xF) + 3
            pos = word >> 4
            for _ in range(length):
                b = ring[pos]; pos = (pos + 1) & 0xFFF
                out.append(b); ring[r] = b; r = (r + 1) & 0xFFF
    return bytes(out[:out_len]), p - src_off   # (해제결과, 소비한 소스바이트수)

def compress(data, use_matches=True):
    """표준 LZSS 재압축. 디컴프레서($C0:0D91)와 바이트 호환 스트림 생성.
    - 링버퍼는 디컴프레서와 동일하게 미러링(시작 0, r=0xFEE).
    - 매치 검증은 인트라매치 오버랩(주기 d 반복)까지 정확히 시뮬레이션.
    - use_matches=False면 전량 리터럴(항상 정확, ~9/8배)."""
    ring = bytearray(4096)
    r = 0xFEE
    out = bytearray()
    n = len(data)
    i = 0
    flagpos = -1
    flagbit = 0

    def emit_flag(bit):
        nonlocal flagpos, flagbit
        if flagbit == 0:
            out.append(0); flagpos = len(out) - 1
        if bit:
            out[flagpos] |= (1 << flagbit)
        flagbit = (flagbit + 1) & 7

    def put_literal():
        nonlocal r, i
        emit_flag(1)
        out.append(data[i])
        ring[r] = data[i]; r = (r + 1) & 0xFFF
        i += 1

    def match_len(pos, maxlen):
        # 디컴프레서가 pos에서 복사할 때 실제 산출되는 바이트가 data[i:]와 일치하는 길이.
        # d=(r-pos)&0xFFF: k>=d 부터는 방금 쓴 값(주기 d 반복)을 읽음.
        d = (r - pos) & 0xFFF
        if d == 0:
            return 0
        l = 0
        while l < maxlen:
            src = ring[(pos + l) & 0xFFF] if l < d else data[i + l - d]
            if src != data[i + l]:
                break
            l += 1
        return l

    while i < n:
        if not use_matches:
            put_literal(); continue
        best_len, best_pos = 0, 0
        maxlen = min(18, n - i)
        if maxlen >= 3:
            for pos in range(4096):
                l = match_len(pos, maxlen)
                if l > best_len:
                    best_len, best_pos = l, pos
                    if l == maxlen:
                        break
        if best_len >= 3:
            emit_flag(0)
            word = (best_pos << 4) | (best_len - 3)
            out.append(word & 0xFF); out.append((word >> 8) & 0xFF)
            for k in range(best_len):
                ring[r] = data[i + k]; r = (r + 1) & 0xFFF
            i += best_len
        else:
            put_literal()
    return bytes(out)

SOURCES = [   # (name, bank, addr, out_len, vram)
    ('main_0000', 0xC7, 0x1574, 12800, 0x0000),
    ('vram_3000', 0xC7, 0x347C, 2048,  0x3000),
    ('vram_4000', 0xC7, 0x382F, 4096,  0x4000),
    ('vram_7000', 0xC7, 0x3A3F, 8192,  0x7000),
    ('blob_1218', 0xC7, 0x1218, 4096,  None),
    ('blob_1148', 0xC7, 0x1148, 640,   None),
    ('blob_0D11', 0xC7, 0x0D11, 2048,  None),
]

if __name__ == '__main__':
    ROM = "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
    rom = open(ROM, 'rb').read()
    import os
    os.makedirs('tmp/gfx', exist_ok=True)
    for name, bank, addr, olen, vram in SOURCES:
        out, used = decompress(rom, foff(bank, addr), olen)
        open(f'tmp/gfx/{name}.bin', 'wb').write(out)
        # 왕복 검증: 재압축→해제 == 원본
        rt, _ = decompress(compress(out) + b'\x00' * 4, 0, olen)
        ok = 'RT_OK' if rt == out else 'RT_FAIL'
        print(f'{name}: src $%02X:%04X {used}B -> {olen}B  {ok}' % (bank, addr))
