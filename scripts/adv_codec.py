#!/usr/bin/env python3
"""어드벤처/스토리 텍스트 압축 코덱 (엔진 $C0:39E0~ 오프라인 포팅).

$C0:39E0 디코더 정밀 디스어셈블(hand-decoded)에서 도출한 코덱:
  - 소스는 [$11-$13] 롱포인터에서 바이트 단위로 읽는 단일 인터리브 스트림.
  - 플래그 비트 버퍼($03): 8비트마다 소스에서 플래그 바이트 1개를 읽어 채운다(LSB first).
      * 플래그 비트 0 = 리터럴: 소스 1바이트를 그대로 출력.
      * 플래그 비트 1 = 딕셔너리 참조: 소스 2바이트(LE) = word →
            index = word >> 3,  len = (word & 7) + 1
            딕셔너리 $C6:7C73[index] 에서 len 바이트를 출력에 복사.
  - Y(출력수) == $05(목표 글리프수) 될 때까지 반복.
출력 바이트열은 파서(1바이트 가변길이) 인코딩과 동일: 0x00=끝, 0x01-04=2바이트글리프
프리픽스, 0x05=개행, 0x06/07=제어(1인자), 그 외 glyph=byte-0x10.
"""
import sys
sys.path.insert(0, 'scripts')
from decode_script import load_tbl

ROM = "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
DICT_SNES = (0xC6, 0x7C73)


def foff(bank, addr):
    return ((bank & 0x3F) << 16) | addr


def decompress(rom, src_bank, src_addr, out_len, dic_off):
    """out_len 개의 출력 바이트를 생성해 반환."""
    p = foff(src_bank, src_addr)
    out = bytearray()
    flags = 0          # $03 (16비트 비트버퍼, 상위바이트 0xFF 센티넬)
    while len(out) < out_len:
        flags >>= 1                       # LSR $03
        if not (flags & 0x0100):          # BIT #$0100 == 0 → 리필
            flags = rom[p] | 0xFF00       # 새 플래그 바이트 | 센티넬
            p += 1
        if flags & 0x0001:                # 딕셔너리 참조
            word = rom[p] | (rom[p + 1] << 8)
            p += 2
            idx = word >> 3
            n = (word & 7) + 1
            out += rom[dic_off + idx: dic_off + idx + n]
        else:                             # 리터럴
            out.append(rom[p])
            p += 1
    return bytes(out), p


def render(seg, tbl):
    o = ''; i = 0
    while i < len(seg):
        b = seg[i]
        if 1 <= b <= 4:
            g = ((b << 8) | seg[i + 1]) - 0x10; o += tbl.get(g, '□'); i += 2
        elif b == 0: o += '{end}'; i += 1
        elif b == 5: o += '\n'; i += 1
        elif b in (6, 7): o += '{c%02X:%02X}' % (b, seg[i + 1]); i += 2
        else: o += tbl.get(b - 0x10, '□'); i += 1
    return o


if __name__ == '__main__':
    rom = open(ROM, 'rb').read()
    tbl = load_tbl('assets/translation_guide/glyph_table.tsv')
    dic_off = foff(*DICT_SNES)
    bank = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0xC5
    addr = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x5950
    olen = int(sys.argv[3]) if len(sys.argv) > 3 else 400
    out, endp = decompress(rom, bank, addr, olen, dic_off)
    print("src %02X:%04X -> %02X:%04X  out=%dB" % (bank, addr, bank, endp & 0xFFFF, len(out)))
    print(render(out, tbl))
