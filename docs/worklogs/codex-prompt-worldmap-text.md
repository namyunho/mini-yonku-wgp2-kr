# Codex 단독 실행 프롬프트 — 월드맵/퀴즈 서브시스템 텍스트 한글화

> 아래 `====` 사이 전체를 Codex에 붙여넣어 단독 실행. Codex는 콜드 스타트 가정 — 맥락 전부 포함.
> (Claude 분석·발굴 완료분을 인계. Claude는 주간 토큰 리밋으로 대기 중.)

====

너는 SNES HiROM 게임 「ミニ四駆 レッツ&ゴー!! POWER WGP2」한글 팬번역 패치의 **미번역 텍스트 발굴·번역·재삽입**을 맡는다. **모든 응답·주석은 한국어**로.

## 작업 환경
- 리포 루트: `/Users/namyunho/Developer/mini-yonku-wgp2-kr` (macOS arm64).
- 원본 ROM: `roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc`(헤더리스 2MB, MD5 acdeb2ee…). 비커밋.
- **HiROM 주소 변환(SSOT)**: `PC = ((bank & 0x3F) << 16) | addr`.
- 빌드: `python3 scripts/build_all.py` → `out/wgp2_kr.smc`. round-trip: `python3 scripts/test_roundtrip.py`.
- RE: idalib(`roms/re_codex.smc.i64`), docs/16 §6.
- 번역 품질: `assets/translation_guide/glossary.md`(인명·머신·팀·용어·말투) **반드시 준수**.

## 대상 (Claude 분석·정적 발굴 완료 — 재조사 불필요)
게임 텍스트는 4경로다(CLAUDE.md). 이번 대상 = **캡처 밖 미번역 갭**:
- 정적 대사 673(System①·$C7/$D0/$C1), 어드벤처 1715(씬VM $C4/$C5), SJIS UI($C0/$C1)는 **이미 번역**.
- **미번역 갭 = 뱅크 $C6/$C7의 월드맵 서브시스템 텍스트**. System①(1바이트 가변길이 글리프) 인코딩이라
  현재 $CA 한글폰트 시트를 참조해 **깨진 한글로 렌더**된다.

### 확정 위치(정적 발굴)
- **퀴즈/정보 DB `$C6:A646~`** — "무엇을 알고 싶나요?" 시스템. 35+ 질문. 예(디코드 완료):
  - `$C6:A646` 開会式のチケットをたくさん持っていたのは？
  - `$C6:A6A1` 土屋研究所で研究員のまえだがくれるパーツは？
  - `$C6:A757` 光蝦の監督の名前は？ / `$C6:A907` 烈＆豪の父がなくしたものは？ …
- **월드맵 메뉴/액션 `$C6:8Bxx`** — レースをする/やめて/コース… (경계 파싱 필요)
- **장소·NPC명** — 風輪サーキット·土屋研究所 등 `$C6:8xxx`·`$C7:8Cxx`·`$C7:9Fxx`

## 인코딩·발굴 기법 (Claude 검증 완료)
- **글리프표**: `assets/translation_guide/glyph_table.tsv` = 원본 JP 글리프표(1008엔트리, `idx→JP문자`).
- **인코딩**: 1바이트 가변길이. `glyph = byte - 0x10`. glyph≥0xF0이면 2바이트(프리픽스 `0x01~0x04`:
  `glyph = (b0<<8|b1) - 0x10`). 종료 `0x00`, 개행 `0x05`, 제어 `0x06/0x07`.
- **순방향 발굴**: JP검색어를 glyph_table로 인코딩(byte=idx+0x10) → ROM 바이트열 검색 → 위치 특정.
  (Claude가 研究所·風輪·コース로 검증 성공 → $C6 매칭 다수.)
- **역디코드**(참고): `out/glyph_map.json`의 `char2idx`는 **번역본(한글) 매핑** — 깨진 한글 스크린샷을
  char→idx→원문으로 역산할 때 사용.

## 작업 순서
1. **추출**: 뱅크 $C6/$C7 텍스트 클러스터의 **문자열 경계·주소·JP원문**을 엄격 스캔으로 JSON화
   (유효글리프율 높고 `0x00` 종료·카나/한자 포함으로 판정. 정적 스캔은 그래픽 오탐 많으니 엄격 기준 필수).
   산출 예: `assets/translations/worldmap_text.json` (`{addr, jp, kr}` 배열, 클러스터별).
2. **포인터 규명**: 이 문자열들의 참조 방식(순차 배열/포인터 테이블). 퀴즈 DB는 순차 유력.
   재삽입이 in-place(원본 슬롯 내)로 되는지, 포인터 패치가 필요한지 RE로 확정.
3. **번역**(glossary 준수): 퀴즈 35+·월드맵 메뉴·장소/NPC명. 전각 문장부호. 화면 폭·바이트길이 상한 준수
   (한글이 원본보다 길면 축약 or 재배치).
4. **재삽입**: System① 인코딩으로 재인코딩. in-place면 슬롯 맞춤, 아니면 포인터 패치(카탈로그 방식은
   docs/07·scripts/final_catalog.py 참조).

## 검증 게이트 (전부 실행·보고)
1. `python3 scripts/build_all.py` → "충돌 0" + CRC.
2. `python3 scripts/test_roundtrip.py` → 무손실 PASS.
3. `python3 scripts/build_adv.py` → 긴 런 0(어드벤처 회귀 없음).
4. **실기(사용자)**: 월드맵에서 퀴즈/정보·장소·NPC 대화가 **정상 한글**로 뜨는지. 통과 전 커밋 금지.

## 제약
- **커밋·푸시는 실기 검증 후**. CRLF 오염 파일(adventure_poc.json·pointer_catalog.json 등) 건드리지 말 것.
- Claude 커밋분(수동 세팅 X메뉴 `build_setbox.py`·SJIS `build_sjis.py`)과 Codex reclean(`build_menu4_reclean.py`)은
  **건드리지 말 것**. 이 작업은 **별도 텍스트 파이프라인**(dialogue/pointer 계열)이다.
- 대량 반복(추출·번역)은 Codex가 처리하되 glossary·기존 컨벤션 준수.

## 완료 보고
추출 문자열 수·클러스터, 포인터 방식(in-place/패치), 번역 진행, 게이트 1~3 결과, 블로커.

====
