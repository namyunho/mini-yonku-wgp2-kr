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


DICT_LEN = 0x1FE4                 # 8164 — 딕셔너리는 씬테이블 $C6:9C57 직전에서 끝난다
MAX_IDX = 0xFFFF >> 3             # 8191 — word>>3 의 이론상한 (딕셔너리가 더 짧아 실질 제약 아님)


def compress(data, dic):
    """디컴프의 역연산. 반환 = 압축 스트림(2바이트 길이헤더 **미포함**).

    코덱: 플래그바이트(LSB first) 8비트 = 다음 8개 항목의 종류.
      비트0 = 리터럴      -> 소스 1바이트 그대로
      비트1 = 딕셔너리참조 -> 소스 2바이트 LE word = (index<<3)|(len-1), len=1..8
    참조는 2바이트를 써서 len 바이트를 내므로 **len>=3 일 때만 이득**(len1=손해, len2=본전+플래그).
    """
    from collections import defaultdict
    idx3 = defaultdict(list)
    L = len(dic)
    for i in range(L - 2):
        idx3[bytes(dic[i:i + 3])].append(i)

    out = bytearray()
    pos, n = 0, len(data)
    while pos < n:
        fp = len(out)
        out.append(0)
        fb = 0
        for b in range(8):
            if pos >= n:
                break
            best_len = best_idx = 0
            key = bytes(data[pos:pos + 3])
            if len(key) == 3:
                for c in idx3.get(key, ()):
                    if c > MAX_IDX:
                        continue
                    m, lim = 3, min(8, n - pos, L - c)
                    while m < lim and dic[c + m] == data[pos + m]:
                        m += 1
                    if m > best_len:
                        best_len, best_idx = m, c
                        if m == 8:
                            break
            if best_len >= 3:
                w = (best_idx << 3) | (best_len - 1)
                out.append(w & 0xFF); out.append((w >> 8) & 0xFF)
                fb |= (1 << b)
                pos += best_len
            else:
                out.append(data[pos]); pos += 1
        out[fp] = fb
    return bytes(out)


def compress_scene(data, dic):
    """씬 소스 형식: 2바이트 출력길이 헤더 + 압축 스트림."""
    body = compress(data, dic)
    return bytes([len(data) & 0xFF, (len(data) >> 8) & 0xFF]) + body


SCENE_TBL_SNES = (0xC6, 0x9C57)   # 씬 소스 테이블 (3B/엔트리)
N_SCENES = 250                    # id 0x00-0xF9 (단조증가 종료 지점)


def scene_src(rom, sid):
    """씬 id -> (bank, addr). 표 $C6:9C57, 엔트리 = {addr_lo, addr_hi, bank_delta}.
    로더 $C0:3D1F / cmd 0x11 핸들러 $C0:4498: addr = 워드 그대로, bank = 3번째바이트 + $C4."""
    o = foff(*SCENE_TBL_SNES) + sid * 3
    return (0xC4 + rom[o + 2]) & 0xFF, rom[o] | (rom[o + 1] << 8)


def decompress_scene(rom, bank, addr, dic_off):
    """씬 소스 디컴프. 소스 선두 2바이트 = 출력길이 헤더, 스트림은 addr+2 부터.
    (디코더 $C0:39D5: `LDA $05; BNE; LDA [$11]; STA $05` 로 A=0이면 헤더에서 길이를 읽고,
     `INC $11`×2 는 무조건 실행 → 스트림 시작은 항상 addr+2.)"""
    p = foff(bank, addr)
    out_len = rom[p] | (rom[p + 1] << 8)
    out, endp = decompress(rom, bank, (addr + 2) & 0xFFFF, out_len, dic_off)
    return out, out_len, endp


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
