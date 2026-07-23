# AGENTS.md — 미니욘쿠 WGP2 한글 패치 (도구 공용 지침)

> 이 파일은 Codex 등 `AGENTS.md` 규약 에이전트용 진입점이다.
> **정본(SSOT)은 [CLAUDE.md](CLAUDE.md) + [docs 문서 지도](docs/README.md)** — 착수 전 반드시 CLAUDE.md를 끝까지 읽을 것.
> (Claude Code와 Codex가 같은 리포를 공유한다. 아래는 도구 무관 핵심 요약이며, 상세·근거는 docs가 정본.)

## 무엇을 하는 프로젝트인가
SNES 「ミニ四駆 レッツ&ゴー!! POWER WGP2」(HiROM+FastROM, 헤더리스 2MB)의 한글 팬 번역 패치.
역공학은 대부분 끝났고 지금은 **번역 → 재삽입 → 빌드** 단계.

## 하드 불변식 (어기면 안 됨)
1. **원본 ROM·패치 적용 이미지는 절대 커밋하지 않는다.** 배포는 BPS/xdelta 차분(flips). `.gitignore`가 `roms/`·카트리지 확장자 전부 차단 — 유지할 것.
2. **round-trip 우선.** 텍스트 수정 전 `encode(parse(text)) == raw_hex == ROM` 무손실을 항상 유지. 회귀 게이트 = `python scripts/test_roundtrip.py` (현재 681 전량 PASS). 재삽입 변경마다 재실행.
3. **HiROM 주소 변환은 하나의 공식만**: `PC = ((bank & 0x3F) << 16) | addr`. LoROM 공식 금지.
4. **PoC 게이트 통과 후에만 되돌리기 비싼 작업**(폰트/포인터 대량 패치)을 시작. (PoC는 이미 통과 — docs/05.)

## 원본 ROM 조달 (비커밋이라 각 머신에서 직접 배치)
- 경로: `roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc`
- 무결성: **CRC32 `4459D4D0` / MD5 `acdeb2ee6ef7b460c5dfed6957f8581a`** (헤더리스 2MB). `cargo run -- info --rom <파일>`로 검증.

## 현재 상태 (2026-07-24)
- ✅ 정적 대사 **681**, 어드벤처 **235씬·1,782메시지**, 월드맵 퀴즈 **70문항·350문자열**, 필드/NPC 고유 **1,340문자열**의 번역·재삽입·역검증 완료.
- ✅ SJIS 메뉴/UI, 소형 타일폰트 메뉴, Result 선수명, 챕터 인트로 10종, 경기장명·포메이션·능력치·개러지·경기 HUD·타이틀·인터미션 그래픽 통합 완료.
- ✅ 실제 엔딩 크레딧·베스트타임 **45행**과 현지화 메시지 **12행**을 엔딩 전용 글꼴·재배치 스트림으로 반영. 런타임 기록과 원본 154레코드 순서 보존.
- ✅ 완역–실삽입 조정문 **959건**의 원문·완역·삽입문 분리 보존. 미처리 축약 대기 0건.
- ✅ 원본과 동일한 헤더리스 **2MiB** 통합 ROM에서 전체 회귀 통과. v0.9 xdelta 역적용 결과가 최종 ROM과 바이트 단위로 일치.
- ✅ v0.9 선언 범위의 번역·재삽입·실기 QA·차분 패치 배포 완료. 계획된 잔여 작업은 없고 이후 제보는 유지보수로 처리한다.

## 도구 실행
- Python 3.14 (`scripts/`, 탐색·추출·디코드). Windows 콘솔 인코딩 이슈 시 `PYTHONIOENCODING=utf-8`.
  - 디코더/인코더: `scripts/decode_script.py` (`parse`/`encode`/`decode`/`render`/`load_tbl`).
  - 추출: `scripts/extract_dialogue.py` → dialogue.json. 카탈로그: `scripts/final_catalog.py`.
  - 회귀: `scripts/test_roundtrip.py`.
- Rust(GNU 1.97, clap) — 주 파이프라인. `cargo run -- info|render|poc-font ...` (`src/commands/`). GNU 링크에 mingw-w64 binutils가 PATH에 필요(설치됨).
- Mesen2 2.1.1 — Lua 스크립팅이 주 디버깅 수단(GDB 미지원). `scripts/lua/`. QA 검증용.
- Flips v198 — BPS 패치 생성/적용.
- xdelta3 3.2.0 — v0.9 xdelta 생성/역적용 검증.
- **역공학(RE) 도구 = IDA + Ghidra 상보**. `idalib-mcp`(주력: 빠른 disasm·xref·바이트 질의·자동화, SNES `$BB:aaaa`=`0xBBaaaa`) + `ghidra`(디컴파일 크로스체크 — IDA는 65816 Hex-Rays 미지원). **태스크별로 유리한 도구를 스스로 판단해 선택**하고, M/X 폭 오싱크 시 교차검증. 상세·원칙 = **docs/16 §"도구 선택 원칙"**(정본). Codex도 이 원칙을 따를 것.

## 도구 간 협업 (Claude Code ↔ Codex)
- 이 리포는 GitHub 원격과 연결돼 있다. 교차 작업은 기능 브랜치와 커밋으로 상태를 주고받고, 병합 전 원격 동기화와 회귀 검증을 수행한다. ROM은 `.gitignore`로 계속 제외한다.
- 인계 규약: 큰 결정·상태 변화는 **docs/에 기록**(정본), CLAUDE.md/AGENTS.md 상태표 갱신. (Claude Code의 개인 메모리는 Codex로 넘어가지 않으므로, 공유해야 할 사실은 반드시 리포 안 문서에 둘 것.)
- 번역은 분량이 크니 블록 단위(c7 → d0 → c1)로 나눠 진행하면 충돌·리뷰가 쉽다.
