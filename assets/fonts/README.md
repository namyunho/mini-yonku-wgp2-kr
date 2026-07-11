# 폰트 자산 (assets/fonts)

한글 글리프 자산과 라이선스·귀속 정보. 주입 경로는 두 가지: (1) **사전 렌더 `.bin` 직접 주입**(주력), (2) TTF를 `cargo run -- poc-font`로 래스터화(대안·검증용).

## 파일

| 파일 | 내용 | 용도 |
|------|------|------|
| `x12y12pxMaruMinyaHangul_2350.bin` | **KS X 1001 완성형 한글 2350자, 16×16 1bpp, 32B/글리프** 사전 렌더 | **주력 주입 소스** — 게임 폰트 포맷과 동일 |
| `x12y12pxMaruMinyaHangul_glyphmap.json` | 문자→인덱스 맵 `{"가":0,"각":1,…}` (유니코드/KS 순, 2350 엔트리) | `.bin` 글리프 색인 |
| `x12y12pxMaruMinyaHangul_preview.png` | 폰트 프리뷰(480×360) | 육안 확인 |
| `x12y12pxMaruMinyaHangul.ttf` | 원본 아웃라인 TTF | fontdue 래스터화(대안), 신규 글자 생성 |

### `.bin` 포맷 (실측 확정)

- **2350 글리프 × 32바이트 = 75,200바이트, 헤더 없음.** 글리프 g의 데이터 = `bin[g*32 : g*32+32]`.
- **선형 행우선 16행 × 2바이트/행**: 행 r(0~15)에서 `byte[2r]` = 좌측 8px, `byte[2r+1]` = 우측 8px, **MSB=최좌측 픽셀, 1bpp**.
- 게임 시트($CA:1137)는 각 글리프를 상단블록(행0-7)+하단블록(행8-15, +0x80)으로 쪼개고 행 내 좌/우 바이트 순서가 **반대**(좌=block+2r+1, 우=block+2r)다. 그러므로 **`.bin` 글리프 → 16×16 픽셀 배열로 디코드 → `encode_glyph`(base03, `src/commands/poc_font.rs`)로 재인코딩**해 주입한다. 바이트 순서·블록 분할 차이는 이 경로가 흡수한다.
- **세로 정렬 필수**: 이 `.bin`은 전 2350자가 **일률적으로 잉크 행 2~12**(상단 2px 여백)다. 게임 원본 규약은 상단 정렬(잉크 행 0~10, 하단 ~5px=줄간격). 그대로 주입하면 하단 ~2px가 줄간격 영역으로 밀려 화면에서 잘린다 → 주입 시 **`--binyshift -2`**(2px 위로)로 행0~10에 맞춘다.
- 인덱스↔문자는 `_glyphmap.json`으로 얻는다(예: '골' → `map["골"]`=80 → `bin[80*32:]`).

> 다음 세션 작업 예정: `poc-font`에 `--bin/--glyphmap` 입력 모드를 추가해 TTF 대신 이 사전 렌더 세트를 쓰도록. 상세는 `docs/05-poc-hangul-font.md`.

## 폰트: x12y12pxMaruMinyaHangul

- **디자이너/저작권**: The x12y12pxMaruMinya Project Authors; quiple (hicchicc). Copyright (c) 2026.
- **출처**: https://github.com/hicchicc/x12y12pxMaruMinya · https://quiple.dev
- **라이선스**: **SIL Open Font License, Version 1.1** — https://openfontlicense.org
- **버전**: 2026-04-23. **메트릭**: unitsPerEm=1200, ascent=1200/descent=0. 12×12 픽셀 디자인.
- **왜 이 폰트인가**: 본문 폰트 셀이 16×16(유효 잉크 ~11×11, 좌상단 정렬 — `docs/03-font-survey.md`)이라 12~14px 픽셀 한글이 셀에 자연스럽게 들어가고, OFL이라 패치 배포에 문제없다. 사전 렌더 `.bin`이 2350자 완성형을 이미 16×16으로 담고 있어 즉시 주입 가능.

## TTF 래스터화 파라미터 (대안·신규 글자용)

- **`--px 12`**: unitsPerEm 1200·12px 디자인 → 디자인 픽셀 1개 = 출력 1px로 1:1 정렬(스미어 없음, `--thr` 무관하게 선명).
- **`--thr 128`**: 아웃라인/AA 폰트(맑은 고딕 등)는 50% 근처가 깔끔. 픽셀 폰트는 아무 값이나.
- **`--xoff 1 --yoff 1`**: 좌상단 정렬. advance는 폭 테이블($CA:9137) 값으로 별도 제어(13 권장).
- 대조/테스트용 시스템 폰트: `C:\Windows\Fonts\malgun.ttf`(맑은 고딕, `--px 14 --thr 100`) — **배포 불가, 최종 미사용.**

## OFL 준수 / 커밋 정책

- 재배포(패치 동봉) 시 OFL 전문(`OFL.txt`)과 위 저작권 고지를 함께 포함하고, 예약 폰트명(Reserved Font Name)을 변형본에 그대로 쓰지 않는다. ROM에 글리프 임베드는 OFL 허용 범위(문서/소프트웨어 임베딩). 배포 패키지 작성 시 `OFL.txt`를 이 디렉토리에 추가할 것(현재 미포함 — 출처에서 취득).
- OFL 자산이라 저장소 커밋 가능(원본 ROM과 달리 저작 제약 없음). `.gitignore`는 폰트를 제외하지 않는다(의도적). 커밋하지 않을 경우 위 출처에서 재취득.
