# 다음 세션 이어하기 — 미니욘쿠 WGP2 한글패치

> 갱신: 2026-07-20. docs/14(위치보존)·docs/13·docs/15(축약원장)·docs/16(RE MCP)·tasks/lessons.md·메모리 먼저 읽고 시작.

## ✅ 완료 (2026-07-20) — 크래시 원천차단 + 어드벤처 번역 복구
- **위치보존 전 씬 확대**(런 단위 원본유지 + `pad_kr` 말미패딩): 스크립트 길이 불변 → VM offset 보존 →
  위치 밀림發 **크래시/리셋 원천차단**(전 씬 216/216 위치보존). 0xB0·0xC7·파츠지급 리셋 해결.
- **cmd0x20 컨테이너 RE(IDA)**: operand 재작성이 리셋 원인 규명 → walk 관통 + 재추출로 중첩 런 노출 →
  메뉴/선택지 한글화 경로 확보. adv_scene.walk·adv_extract 수정.
- **긴 런 444 Codex 3라운드 축약**(화자·바이트·마커·글리프 게이트) → **1690 메시지 번역**(긴 런 0). 208 화자명 결함 수정.
- 축약 원장(`shortening_ledger.json`) before→after 기록. 사용자 **스테이지8까지 실기: 크래시 없음**. ROM CRC 1A00E9F2.

## ✅ 완료 (2026-07-21 세션) — 스테이지8 피드백 1~3 처리
- **1. 토우키치 말투 다양화** ✅ Codex 137런(옵쇼 단조→팔레트 분포), glossary §1.5 개정. 커밋 7b1f24e.
- **2. 불필요 공백** ✅ **근본 원인 = pad_kr가 trailing `\n` 뒤에 패딩→다음 런 들여쓰기**(스크린샷 실측). 말미 마커/개행 앞 삽입으로 수정, 들여쓰기 런 0. 커밋 e2d2784.
- **3. 선택지·분기 대사** ✅ cmd0x20 중첩 25런 번역(카이조·지로마루 아크). 커밋 70e72cd.
- 현재 ROM: 228씬/1715 메시지, 위치보존 227/227, 긴 런 0.
- **Codex-RE 분산 셋업 완료** ✅ (docs/16 §6): idalib+승인+.i64+바이패스로 Codex가 disasm 가능. RE 반복작업 위임 가능.

## ✅ 완료 (2026-07-21 세션 B) — UI 갭 발굴·복구 4건 (푸시됨 origin/master 766b63b)
- **역디코드 기법 확립**: 깨진 한글 → (out/glyph_map char2idx) 글리프인덱스 → (glyph_table.tsv) 원문. 트레이스 없이 갭 내용 복원. 소스 바이트 재구성→ROM 검색으로 주소도 특정.
- **트레이스 도구** `scripts/lua/trace_field_src.lua`: 파서$C1:9554/씬표$C6:9C57/디코더$C0:39D5 동시 후킹, 화면 P/S/D 카운터로 엔진 육안판별. **맵 NPC 갭에 재사용**.
- **포메이션 안내** `$C1:CFAF`(파서, 포인터카탈로거 분기 미탐 고아) → dialogue.json id673 + pointer_map. 커밋 9bea57e.
- **세팅 프리셋4+평가문3** `$C1:C501` 테이블 후미 7엔트리(앞 6개 머신명만 캡처됐던 것) → in-place 삽입. 커밋 fe971bf.
- **옵션 부품 14종**(SJIS $C0:EE28~) + **SJIS 슬롯 0x86 확장(189→224)**: 리드바이트 0x86 도입(2차 변환블록 $C1:D7F3). **남은 대형 SJIS 작업 unblock**. 커밋 766b63b. ⚠️ **회귀 의심 1순위 단서 = docs/12 §"0x86 확장"·[[sjis-0x86-expansion-suspect]]**.
- ⚠️ **결합 회귀 주의(재확인)**: 673 대사 추가/수정 시 어드벤처 글리프 할당 흔들려 긴 런↑ → **build_adv까지 돌려 긴 런 baseline 비교**, 회귀 시 글리프-중립 재작성(tasks/lessons.md). 현 ROM: 681 정적·1715 어드벤처·긴 런 0.

## 🔴 다음 최우선
4. **광역 "월드맵/맵 NPC 대사"** (Task 4 잔여) — $C1 개러지 서브시스템 밖 **별도 표시경로**. 방법=맵에서 NPC 대화 화면 띄우고 `trace_field_src.lua` 무장 → P/S/D+소스주소 캡처 → 역디코드/오프라인 디코드 → 갭 열거·번역([[npc-field-dialogue-gap]]). 대량이면 Codex 분산.
5. **(검수 보류)** 축약發 어색한 말투·토우키치 지요 우세 일부 — **최종 전수 검수**에서 손봄(사용자 세밀 검수 예정).
6. **그래픽 에셋 주입은 보류** — 사용자 수작업 검수·캡처 중. **모든 대사 번역 완료 후 사용자 요청 시**에만.

> 순서: 4(월드맵/맵 NPC 대사 발굴·번역) → 최종 검수. 반복 disasm/축약은 Codex 분산([[dual-ai-translation-workflow]]·docs/16 §6).

## 먼저 읽을 것
- **`docs/14-position-preserving-translation.md`** ← 이번 세션 핵심 방침(위치보존 번역). **최우선 구현 대상.**
- `docs/13-adventure-reverted-scenes.md` — 현재 원본유지(번역 보류)된 19씬 목록·재번역 대상.
- `CLAUDE.md`, `docs/08`(어드벤처 VM), `docs/12`(SJIS·알려진 이슈).
- 메모리: `adv-cmd20-overread-bug`, `npc-field-dialogue-gap`, `crlf-migration-artifact`, `dual-ai-translation-workflow`.

## 현재 상태 (git origin/master = c88af29)
- ✅ **SJIS UI 한글화 완료**(메뉴·이름·머신·팀·행성·다이얼로그) + VRAM 로더 커버리지 + 글리프정렬.
- ✅ **어드벤처 치명 크래시 임시안정화**: 리셋 3종(레벨업 0x69 등)·프리즈(0xB0) 해결 —
  단 **"일본어로 롤백"한 것**(cmd0x20 16 + desync 2 + 0xB0 = **19씬 원본유지**, 번역 미적용). 진짜 번역 아님.
- ✅ 그래픽 추출도구(LZSS 23블롭 → `img_tile/extract/`), 크레딧·타이틀 로고 한글화.
- ⚠️ **`out/wgp2_kr.smc`는 디버깅 중 테스트 빌드로 덮여 있을 수 있음** → 새 세션 시작 시
  `python3 scripts/build_all.py`로 정식 재빌드(정상 CRC는 build_all 출력 확인).

## 최우선 작업: 위치보존 번역 구현 (docs/14)
번역이 런 바이트길이를 바꿔 위치가 밀리면 VM(cmd0x20·cmd0x54 조건분기·루프)이 깨져 크래시.
**정적 탐지 불가**(조건분기 86씬 중 어느 게 깨질지 신호 없음). → **위치를 안 밀면 원천 차단.**

1. **build_adv.py 확장**: cmd 0x21 런에서 `encode_text(kr)`가 원본 텍스트길이보다
   - **짧으면** 말미(마지막 제어코드 뒤·`0x00` 앞)에 **공백글리프(1바이트: 전각 `0x11`/반각 `0x10`)**
     패딩해 원본 길이와 **정확히 일치** → 위치 100% 보존.
   - **길면** → 그 씬 원본유지 + **축약목록 산출**(`out/retranslate_longer.json`: scene·at·초과바이트·text_kr).
2. **0xB0 프로토타입 먼저**: 0xB0 긴 런 3개(@0x020A +4·@0x0369 +3·@0x0443 +5)만 축약 →
   전체 패딩 → **Mesen 실기로 프리즈 소멸+번역 유지+말미공백 안 보임 확인**. 되면 전 씬 적용.
   - ⚠️ 패딩 말미공백이 대화상자에 보이는지 **반드시 실기 확인**(안 보이면 방식 확정).
3. 감사 수치(참고): 번역 cmd0x21 런 1686개 중 **88% 길이 불일치**, **447개가 한글이 더 김**(축약 대상).
4. 축약 재번역은 `dual-ai-translation-workflow` 방식으로 대량 처리 가능(의미 보존, ≤원본 바이트).

## ★ 롤백 부분 우선 재번역 (잊지 말 것) — 사용자 지침 1
작업 중 **일본어로 롤백한 부분을 최우선으로 재번역 복구**한다(쌓이면 잊어버림). 추적 SSOT = **`docs/13`**.
- **롤백 19씬**(cmd0x20 16·desync 2·0xB0)은 위치보존/컨테이너RE로 **진짜 번역 복구**가 1순위 백로그.
- **447 긴 런**(한글>원본)도 축약 재번역 대상. 이 둘을 매 세션 체크리스트로 삼아 소진할 것.
- 재번역 완료분은 docs/13에서 제거하고 실기 검증 기록.

## 병렬 작업 원칙 (Codex 협력) — 사용자 지침 2·3
수천 줄 규모의 **반복 작업(대사 정렬/축약/번역)은 Claude가 하지 말고 Codex가** 처리한다.
**이유: Codex의 일일·주간 토큰 리밋이 Claude보다 훨씬 널널**하다. 역할 분담:
- **Claude** = 사용자 요청 해석 → **전략·정확한 스펙·배치 브리핑·검증 게이트** 설계(반복량 직접 처리 금지).
- **Codex** = 방대한 반복량 실행(축약/번역/정렬). 도구: `codex:rescue`(또는 `codex:codex-rescue` 에이전트),
  기존 `dual-ai-translation-workflow` 메모리 절차.
- ⚠️ **Codex도 품질 지침을 반드시 참조**하게 컨트롤: 각 배치 브리핑에 **`assets/translation_guide/glossary.md`
  (인명·머신·팀·용어·말투)와 기존 작업 규칙(문장부호 전각·줄길이·바이트길이 상한)을 명시 포함**시켜
  Codex가 내 지시뿐 아니라 용어집·기존 컨벤션을 따르게 한다. 산출물은 Claude가 게이트(바이트길이·용어·글리프)로
  검증 후 병합.
- 예) 447 긴 런 축약: Claude가 (원본바이트·현재 한글·의미·글자수규칙·glossary 발췌) 브리핑 JSON 배치 →
  Codex 축약안 → Claude 바이트길이/용어 게이트 → build_adv 반영.
- 맵 NPC 대량 번역도 동일(Claude=소스식별·추출·게이트·glossary브리핑, Codex=번역 배치).

## 그다음: 미번역 대사 발굴·번역 (남은 번역량 ≈ 지금까지 한 만큼)
- **맵 NPC 대화(System ①)**: 스토리 무관하게 맵에서 만나는 사람들 대화가 **하나도 번역 안 됨**.
  깨진 한글로 렌더됨(원본 일본어 글리프가 한글로 교체된 $CA 시트 참조). 673/1725 캡처 밖.
  → **소스 재분석 필요**(씬표 $C6:9C57 밖인지·다른 텍스트 엔진인지). `npc-field-dialogue-gap` 메모리 참조.
  Mesen 트레이스로 맵 NPC 대화의 파서/디코더 경유·소스주소 캡처가 첫 스텝.
- 중간중간 **선택지 대사**도 미번역 다수.

## ✅ 해소(관찰): 포메이션 메뉴 스프라이트 깨짐 (docs/12)
Team Running Formation 메뉴 스프라이트 깨짐(BG 정상·OBJ만)이 **2026-07-19 클린 full `build_all.py`
재빌드본에서 재현 안 됨**(사용자 실기 확인). 유력 원인 = 직전 ROM이 프리즈 격리 중 스테일/부분 디버그
빌드였을 가능성(원인 단정 안 함). 재발 대비 원 가설·확인법은 docs/12에 보존. → 재발 시에만 트레이스.

## 작업 환경 / 도구
- **Mesen(맥, arm64)** `/Applications/Mesen.app/Contents/MacOS/Mesen`. CLI: `Mesen <rom> <lua>`.
  설정 `~/Library/Application Support/Mesen2/settings.json`: `AllowIoOsAccess=true`(io쓰기),
  `ScriptTimeout` 상향, `AutoStartScriptOnLoad=true`.
- **⚠️ 세이브 스테이트는 파일명(`wgp2_kr.smc`)에 묶임** → 테스트 ROM도 반드시 `out/wgp2_kr.smc` 파일명 유지해야
  사용자 세이브 로드됨(다른 파일명이면 세이브 안 됨). 이게 프리즈 지점 빠른 재현의 핵심.
- 트레이서: `scripts/lua/trace_scene_id.lua`(씬표 읽기 후킹→현재 씬 id, 프리즈 순간 범인 특정),
  `scripts/lua/trace_garage_vram.lua`(VRAM DMA·khook2 exec·자동스샷).
- 빌드: `python3 scripts/build_all.py`(전체) / `scripts/test_roundtrip.py`(673 무손실) /
  `scripts/build_adv.py`(어드벤처만, `--rom`/`--out`/`--base`).
- 커밋: CRLF 오염 파일(adventure.json·pointer_*·일부 스크립트) **명시적 git add 제외**, `git commit -a` 금지.

## 디버깅 방법론(이번에 검증됨)
1. 프리즈/리셋 재현(세이브 활용) → `trace_scene_id.lua`로 마지막 씬 id 캡처.
2. 격리: no-SJIS ROM(build 1~6단계) / 어드벤처 통째 원본(씬표 원복) / 창 바이섹션 / 단일 씬 원복.
   각 테스트 ROM은 `out/wgp2_kr.smc` 파일명 유지(세이브).
3. round-trip 통과 ≠ VM 유효 — 반드시 실기 확인.
