# 다음 세션 이어하기 — 미니욘쿠 WGP2 한글패치

> 갱신: 2026-07-19. 이 파일 + `docs/14`(위치보존 번역) + `docs/13`(롤백 씬) + 메모리를 먼저 읽고 시작.

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

## 병렬 작업 원칙 (Codex 협력) — 사용자 지침
수천 줄 규모의 **대사 정렬/축약/번역**은 Claude 혼자 하지 말고 **Codex와 병렬로**.
Claude는 **정확한 스펙·배치 지시·게이트(검증)**를 설계하고, Codex가 방대한 양을 처리 → 토큰 절약.
- 도구: `codex:rescue`(또는 `codex:codex-rescue` 에이전트), 기존 `dual-ai-translation-workflow` 메모리 절차.
- 예) 447 긴 런 축약: Claude가 (원본길이·현재 한글·의미·글자수 규칙) 브리핑 JSON을 배치로 만들어 Codex에
  분담 → Codex가 축약안 산출 → Claude가 바이트길이 게이트로 검증·병합 → build_adv 반영.
- 맵 NPC 대량 번역도 동일(Claude=소스식별·추출·게이트, Codex=번역 배치).

## 그다음: 미번역 대사 발굴·번역 (남은 번역량 ≈ 지금까지 한 만큼)
- **맵 NPC 대화(System ①)**: 스토리 무관하게 맵에서 만나는 사람들 대화가 **하나도 번역 안 됨**.
  깨진 한글로 렌더됨(원본 일본어 글리프가 한글로 교체된 $CA 시트 참조). 673/1725 캡처 밖.
  → **소스 재분석 필요**(씬표 $C6:9C57 밖인지·다른 텍스트 엔진인지). `npc-field-dialogue-gap` 메모리 참조.
  Mesen 트레이스로 맵 NPC 대화의 파서/디코더 경유·소스주소 캡처가 첫 스텝.
- 중간중간 **선택지 대사**도 미번역 다수.

## 보류(경미): 포메이션 메뉴 스프라이트 깨짐 (docs/12)
Team Running Formation 메뉴 상단 "TEAM RUNNING" 그래픽이 반각카타카나 쓰레기로 깨짐(BG 정상·OBJ만).
트레이스상 **SJIS khook2·DA9E1F는 배제**(khook2 exec=0, DA9E1F md5 원본일치, 우리 재배치 소스가
스프라이트 영역 DMA 안 함). 원인 미규명. → 타일뷰어로 **우리 vs 원본 스프라이트 CHR export 대조** 필요.
치명도 낮음(타이틀 그래픽 1개). 위치보존·미번역 발굴 후 처리.

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
