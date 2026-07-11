# 01 · 매체 조사 (Media Survey)

초기 조사 1단계(매체). 이미지 포맷 식별과 무결성 고정. 이 문서의 오프셋·매핑 공식은 이후 모든 분석의 전제다.

## 원본 식별

| 항목 | 값 |
|------|-----|
| 제목(No-Intro) | Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP) |
| 플랫폼 | SNES / Super Famicom |
| 배포 | Nintendo Power (SF Memory, 재기록 플래시 카트 배포판) |
| 파일 | `roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc` |
| 크기 | 2,097,152 B = 2MB = 16Mbit (정확) |
| 카피어 헤더 | **없음** (크기 mod 512 = 0, mod 1024 = 0 → 헤더리스 클린 덤프) |

> 확장자는 `.smc`지만 512B 카피어 헤더가 없는 헤더리스 이미지다. 이후 패치·오프셋은 전부 **헤더리스 기준**으로 고정한다.

## 해시 (무결성 고정)

| 알고리즘 | 값 |
|----------|-----|
| CRC32 | `4459D4D0` |
| MD5 | `acdeb2ee6ef7b460c5dfed6957f8581a` |
| SHA1 | `e84ab48b9a0024b90fd9d789a8b8cf94f879d195` |

빌드 도구는 시작 시 입력 ROM의 이 해시를 검증하고, 불일치하면 즉시 중단한다.

## 내부 헤더 (HiROM, @ 0xFFC0)

LoROM 후보($7FC0)는 코드 바이트로 채워져 있고 체크섬이 0xFFFF가 아니다. HiROM 후보($FFC0)가 유효 → **HiROM 확정**.

| 오프셋 | 필드 | 값 | 해석 |
|--------|------|-----|------|
| $FFC0-D4 | 게임 타이틀 | `MINI4KU LETS&GO WGP2 1` | 21바이트 |
| $FFD5 | 매핑 모드 | `0x31` | **HiROM(bit0) + FastROM(bit4)** |
| $FFD6 | ROM 타입 | `0x02` | ROM + RAM + Battery (SRAM 세이브) |
| $FFD7 | ROM 크기 | `0x0B` | 2^11 KB = 2048KB = 2MB ✓ 파일 크기 일치 |
| $FFD8 | SRAM 크기 | `0x03` | 2^3 KB = 8KB SRAM |
| $FFD9 | 국가 | `0x00` | 일본 (NTSC) |
| $FFDA | 제작사 ID | `0x33` | 확장 헤더 사용 표식 |
| $FFDC-DD | 체크섬 보수 | `0x7D89` | |
| $FFDE-DF | 체크섬 | `0x8276` | 0x8276 + 0x7D89 = **0xFFFF ✓ 유효** |

확장 헤더 @ $FFB0: maker=`01`(Nintendo), game code=`BM4J`.

### 인터럽트 벡터 (emulation/native)

| 벡터 | 오프셋 | 값 |
|------|--------|-----|
| RESET | $FFFC | `$FF7C` |
| NMI (native) | $FFEA | `$FF6D` |
| IRQ (native) | $FFEE | `$FF77` |

NMI 핸들러($FF6D 부근)는 통상 DMA 큐 실행을 담당한다 — 폰트/텍스트 DMA 경로 추적의 시작점.

## HiROM 주소 변환 (SSOT)

이 ROM은 **HiROM**이다. 스킬 SNES 레퍼런스의 LoROM 예시 공식(`& 0x7F`, `-0x8000`)을 **쓰면 안 된다**. HiROM 통일 공식:

```
# SNES 주소 → 파일 오프셋 (헤더리스 HiROM)
PC = ((bank & 0x3F) << 16) | addr

# 파일 오프셋 → SNES 주소 (정규: 뱅크 $C0+)
bank = 0xC0 + (PC >> 16)
addr = PC & 0xFFFF

# 검증: RESET $00:$FF7C → (0x00 & 0x3F)<<16 | 0xFF7C = 0x00FF7C
#       $C0:$FF7C 도 동일 오프셋 (미러)
```

- 뱅크 $C0-$DF (2MB = 32뱅크 × 64KB)가 ROM 본체. $00-$3F / $80-$BF의 $8000-$FFFF는 상위 절반 미러.
- 변환 함수는 하나만 두고(SSOT) 전 코드가 그것만 쓴다. FastROM이므로 실행 뱅크는 $C0-$FF 계열이 주류.

## 다음 단계

- [ ] round-trip 검증: 추출 → 무수정 재조립 → 원본 바이트 일치 (매체 단계 필수 게이트)
- [ ] 텍스트 위치·인코딩 조사 (`docs/02-*` 예정) — Shift-JIS 디코드 시도로 후보 영역 식별
- [ ] 폰트 경로 조사 — 16×16 본문 폰트 여부, 타일 포맷/배치, DMA 루틴
- [ ] 훅 지점·수용량·베이크드 텍스트 비율 판정
