# 문서 지도와 정본(SSOT) 구분

이 디렉터리는 현재 구현 명세와 역공학 근거, 시행착오 기록, 자동 생성 검수표를 함께 보존한다.
과거 수치와 당시의 “다음 단계”는 재현에 필요한 기록이므로 삭제하지 않되, 현재 상태로 오해하지
않도록 아래와 같이 역할을 구분한다.

## 현재 상태를 확인할 곳

| 용도 | 정본 |
|---|---|
| 배포·기능·빌드 현황 | 루트 [`README.md`](../README.md), [`CLAUDE.md`](../CLAUDE.md) |
| 정적 대사 원문·번역·바이트 | [`assets/translations/dialogue.json`](../assets/translations/dialogue.json) |
| 어드벤처·월드맵·필드 번역 | `assets/translations/*_kr.json`, 각 시스템 구현 문서 |
| 포인터와 주소 | [`assets/translations/pointer_catalog.json`](../assets/translations/pointer_catalog.json), 각 RE 문서 |
| 완역과 실제 삽입문 비교 | [`22-shortened-translation-comparison.md`](22-shortened-translation-comparison.md) |
| 월드맵 퀴즈 문항·정답 | [`23-worldmap-quiz-audit.md`](23-worldmap-quiz-audit.md) |

현재 기준 핵심 수치는 정적 대사 **681개**, 어드벤처 **235씬·1,782메시지**,
월드맵 **70문항·350문자열 + 고정 UI 7개**, 필드/NPC **1,207레코드·1,411런·고유
1,340문자열**, 완역–실삽입 조정문 **959건**, 실제 엔딩 **45행 + 현지화 메시지 12행**이다.

## 문서 분류

### 기반 조사와 정적 대사

- [`01-media-survey.md`](01-media-survey.md) — ROM 무결성·HiROM 주소 변환.
- [`02-text-survey.md`](02-text-survey.md) — 초기 텍스트 영역 조사.
- [`03-font-survey.md`](03-font-survey.md) — 본문 폰트와 렌더 경로.
- [`04-dialogue-encoding.md`](04-dialogue-encoding.md) — 정적 대사 인코딩.
- [`05-poc-hangul-font.md`](05-poc-hangul-font.md) — 한글 렌더 PoC.
- [`06-dialogue-extraction.md`](06-dialogue-extraction.md) — 초기 651개 추출의 역사적 스냅샷.
- [`07-dialogue-completeness.md`](07-dialogue-completeness.md) — 현재 정적 대사 681개와 포인터 완전성 정본.

### 어드벤처와 위치보존

- [`08-adventure-text-engine.md`](08-adventure-text-engine.md) — 씬 VM·코덱·현재 재삽입 결과.
- [`09-textbox-clip-investigation.md`](09-textbox-clip-investigation.md) — 포인터 오배치로 생긴 클리핑 사고 기록.
- [`13-adventure-reverted-scenes.md`](13-adventure-reverted-scenes.md) — 원복·desync 복구의 역사적 사건 원장.
- [`14-position-preserving-translation.md`](14-position-preserving-translation.md) — 현재 위치보존 구현과 회귀 불변식.

### 메뉴·그래픽·엔딩

- [`10-graphics-assets.md`](10-graphics-assets.md) — 범용 그래픽 자원과 재삽입 카탈로그.
- [`11-sjis-menu.md`](11-sjis-menu.md) — 시작·저장 메뉴.
- [`12-sjis-ui-hangul.md`](12-sjis-ui-hangul.md) — SJIS UI 전체.
- [`17-stage-title-localization.md`](17-stage-title-localization.md) — 세이브 제목과 챕터 인트로.
- [`18-menu-tile-font-labels.md`](18-menu-tile-font-labels.md) — 소형 직접타일 메뉴. 앞부분의 마커 훅은 폐기된 설계이며 후반의 문맥별 글꼴 재압축이 현재 구현이다.
- [`19-menu4-context-font.md`](19-menu4-context-font.md) — 하위 브랜치에서 처음 문맥 글꼴을 안정화한 역사 기록.
- [`20-manual-setting-xmenu-handoff.md`](20-manual-setting-xmenu-handoff.md) — 수동 세팅 공유 글꼴 실패 실험·초기 인계 기록.
- [`24-ending-credits-analysis.md`](24-ending-credits-analysis.md) — 실제 엔딩 크레딧·베스트타임·현지화 메시지.

### 월드맵·필드·검수 산출물

- [`19-worldmap-quiz-text.md`](19-worldmap-quiz-text.md) — 월드맵 퀴즈의 주소·렌더·재삽입 구현.
- [`23-worldmap-quiz-audit.md`](23-worldmap-quiz-audit.md) — 위 구현에서 자동 생성하는 70문항 검수표.
- [`20-field-npc-hidden-records.md`](20-field-npc-hidden-records.md) — 필드/NPC 숨은 레코드 발굴과 완전성 증명.
- [`21-field-position-preserving-translation.md`](21-field-position-preserving-translation.md) — 필드/NPC 번역·재삽입 정본.
- [`15-shortening-ledger.md`](15-shortening-ledger.md) — 축약 정책과 과거 바이트 상한 원장 설명.
- [`22-shortened-translation-comparison.md`](22-shortened-translation-comparison.md) — 현재 전체 시스템 959건 비교표(자동 생성).
- [`16-reverse-engineering-mcp.md`](16-reverse-engineering-mcp.md) — IDA·Ghidra·Mesen2 도구 선택과 재현 환경.

## 중복처럼 보이는 문서의 관계

| 조사·역사 기록 | 현재 정본 또는 생성물 | 구분 |
|---|---|---|
| 06 초기 추출 | 07 완전성 | 651개 탐색 과정 / 현재 681개 |
| 13 원복 사건 | 14 위치보존 | 실패·복구 내역 / 현재 안전 규칙 |
| 15 축약 원장 | 22 전수 비교 | 정책·당시 바이트 제약 / 현재 959건 생성 결과 |
| 19 퀴즈 구현 | 23 퀴즈 감사 | 주소·코드 / 문항·선택지·정답 |
| 20 필드 발굴 | 21 필드 재삽입 | 완전성 증명 / 현재 빌드 방식 |
| 10 그래픽 카탈로그 | 24 실제 엔딩 | 범용 그래픽 / 엔딩 전용 스트림 |

새로운 수치나 번역은 기계 판독 가능한 `assets/translations/`에 먼저 반영하고, 자동 생성 문서는
생성 스크립트로 갱신한다. 역사 문서의 과거 수치를 현재 수치로 소급 변경하지 않는다.
