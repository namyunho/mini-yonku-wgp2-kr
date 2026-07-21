# 16 · 역공학 도구 MCP 셋업 (IDA Pro · Ghidra · asar)

2026-07-20 macOS(arm64, Tahoe 26.5)에서 역공학 도구를 **Claude Code에 MCP로 연결**하고 보조 도구를 정비한 기록. SSOT.

## 요약

| 도구 | 버전 | 역할 | MCP 서버명 |
|------|------|------|-----------|
| IDA Pro | Professional 9.4 | 주 디스어셈블러(GUI 브리지 + headless) | `ida-pro-mcp`, `idalib-mcp` |
| Ghidra | 12.1.2 (brew) | 보조 디스어셈블러/디컴파일러 크로스체크 | `ghidra` |
| asar | 1.91 (brew) | 65816 어셈블러(패치/훅 빌드) | — (CLI) |
| Mesen2 | 2.x | 동적 디버깅·QA (기존) | — (Lua) |

MCP 등록은 프로젝트 루트 [`.mcp.json`](../.mcp.json)(project scope). **Claude Code 재시작 후** 활성화되며, 최초 사용 시 project MCP 서버 승인이 필요하다.

세 서버 모두 `initialize` 핸드셰이크 검증 통과:
```
[ida-pro-mcp] OK -> ida-pro-mcp 1.0.0
[idalib-mcp]  OK -> ida-pro-mcp 1.0.0
[ghidra]      OK -> ghidra-mcp 1.28.1
```

## 1. IDA Pro MCP (mrexodia/ida-pro-mcp 2.0.0)

**아키텍처 2계층**: (1) IDA 안에서 도는 플러그인(HTTP 서버 127.0.0.1:13337) + (2) Claude가 띄우는 stdio 브리지가 그 HTTP에 붙음.

- 설치: `pipx install "https://github.com/mrexodia/ida-pro-mcp/archive/refs/heads/main.zip"` → ida-pro-mcp 2.0.0
- IDA 플러그인: `ida-pro-mcp --install` → `~/.idapro/plugins/ida_mcp.py`(pipx venv로 심볼릭 링크). **IDA 재시작 필요**.
- pipx venv: `~/Library/Application Support/pipx/venvs/ida-pro-mcp/`

### 두 가지 사용 경로
- **`ida-pro-mcp`** (GUI 브리지): IDA GUI에서 ROM/DB를 연 상태여야 함. 브리지가 13337로 프록시. 사람이 IDA를 띄워두고 협업.
- **`idalib-mcp`** (headless): IDA GUI 없이 에이전트가 직접 바이너리를 열어 분석. **자동화에 유리**.
  - 활성화: pipx venv에 `idapro` 휠 주입(`pipx inject`) + `py-activate-idalib.py` 실행으로 IDA 설치 경로 바인딩. 검증: `python -c "import idapro"` OK.
  - 실행 형태: `idalib-mcp --stdio` (worker 데이터베이스 관리; `--unsafe`는 쓰기 도구 활성 — 위험, 기본 비활성).

### ✅ SNES/65816 로더 — 동작 확인 (2026-07-20)
`idalib-mcp`(headless)로 원본 ROM을 `idb_open`(mode=force_headless) → **SNES HiROM 로더가 정상 매핑**:
- 세그먼트 `.C0`~`.DF`가 `0xC00000`~`0xE00000`에 뱅크별로 배치. `ppu`($2100)·`apu`·`wram`($7E0000)·`dma`($4300) 하드웨어 영역 정의. 리셋벡터 `Emulation_mode_RESET @ 0xC0FF7C` 인식.
- **★ 주소 규약: SNES `$BB:aaaa` = IDA 주소 `0xBBaaaa` 직접 대응**(HiROM 파일오프셋 변환 불필요). 예: cmd0x54 `$C0:56A0` → IDA `0xC056A0`.
- **Hex-Rays 디컴파일러는 65816 미지원**(`hexrays_ready=false`) → `decompile` 말고 `disasm`/`get_bytes`/`define_func` 사용. VM 코드가 `REP #$30`(M/X=16) 전제라 IDA가 대체로 16비트로 정확히 디코드(폭 오싱크 시 수동 정의).
- **자동분석은 함수 소수만 탐지**(SNES M/X 토글 탓) → 알려진 주소를 `define_func`로 정의 후 `disasm`.
- 검증 실적: cmd0x54 핸들러($C0:56A0)+조건평가기($C0:5AC6) 디스어셈블이 docs/08 손디스어셈블과 일치. **씬 스크립트는 런타임 디컴프 데이터라 IDA에 없음** → 씬 제어흐름은 Python `adv_scene` 워커, VM 인터프리터는 IDA로 분담.
- 세션: `idb_open` → `session_id` 반환. 이후 도구 호출에 `database=<id>` 필요. `.i64` DB가 ROM 옆에 생성됨.

## 2. Ghidra 12.1.2 + GhidraMCP

- 설치: `brew install ghidra` (의존성 `openjdk@21` 자동 설치). launcher: `/opt/homebrew/Cellar/ghidra/12.1.2/libexec/ghidraRun`, headless: `.../support/analyzeHeadless`.
- **JDK 경로(중요)**: `openjdk@21`은 keg-only라 기본 PATH에 없다 → `~/.zshrc`에 영구 추가:
  ```
  export JAVA_HOME="/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home"
  export PATH="$JAVA_HOME/bin:$PATH"
  ```
- 사용자 설정 디렉토리: `~/Library/ghidra/ghidra_12.1.2_PUBLIC/`

### GhidraMCP (LaurieWired 1.4) — 버전 패치
공식 릴리스 1.4의 확장은 **Ghidra 11.3.2 대상**. 설치된 12.1.2와 불일치라 그대로면 로드 거부됨.
- **패치 적용**: 확장 `extension.properties`의 `version`/`ghidraVersion`을 `11.3.2 → 12.1.2`로 수정 후 재패키징.
- 설치 위치: `~/Library/ghidra/ghidra_12.1.2_PUBLIC/Extensions/GhidraMCP/`
- 브리지(stdio): `~/tools/ghidra-mcp/bridge_mcp_ghidra.py` + 전용 venv(`mcp[cli]`, `requests`). Ghidra 내 확장이 여는 HTTP(127.0.0.1:8080)에 연결.
- 패치본 백업: `~/tools/ghidra-mcp/GhidraMCP-12.1.2.zip`

> **폴백**: 12.1.2에서 플러그인이 런타임에 로드 실패하면(콘솔 오류), 버전 정합을 위해 **Ghidra 11.3.2를 별도 설치**하고 확장을 무패치로 넣는다. GhidraMCP는 HTTP 기반이라 브리지는 버전 무관하게 동일.

### 65816/SNES 확장 (ghidra-snes v1.3.2) — 2026-07-21 설치 (디컴파일 언락)

기본 Ghidra엔 65816 프로세서·SNES 로더가 **없다**(6502만) → 우리 ROM 디컴파일 불가였음. 커뮤니티 확장 [`joshleaves/ghidra-snes`](https://github.com/joshleaves/ghidra-snes)로 해결:
- 한 확장에 **SNES 로더 + 65816 SLEIGH + 메모리헬퍼(MMIO/WRAM/미러)**. **HiROM `C0–FF:0000–FFFF` 매핑**(우리 ROM 일치), LoROM/HiROM 스코어 자동판정, SMC 헤더 옵션.
- 소스: `~/tools/ghidra-snes/`. 빌드 `GHIDRA_INSTALL_DIR=/opt/homebrew/opt/ghidra/libexec ./gradlew clean buildExtension` → `dist/*.zip`.
- ⚠️ 저장소 compat=12.0.4 → `gradle.properties`·`extension.properties`의 `version`을 **12.1.2로 수정 후 재빌드**(GhidraMCP와 동일 패치 패턴, 안 하면 로드 거부). 설치 = zip을 유저 확장 디렉토리에 unzip.
- ROM import 시 로더 포맷 **"SNES ROM Loader"** 선택.

### ⚠️ Ghidra 경로 정정 (2026-07-21)

- **실제 설치(GHIDRA_INSTALL_DIR) = `/opt/homebrew/opt/ghidra/libexec`**(brew Cellar; `support/buildExtension.gradle`·`Ghidra/Processors/`·`ghidraRun` 여기). 확장 빌드 시 이 경로 지정.
- **유저 확장/설정 디렉토리 = `~/Library/ghidra/ghidra_12.1.2_PUBLIC/`**(`Extensions/`·로그). GhidraMCP·ghidra-snes 확장은 여기 `Extensions/`에 설치됨. (위 §GhidraMCP "설치 위치"는 이 유저 확장 디렉토리를 가리킨 것 — 빌드용 설치 경로와 구분.)

### GhidraMCP 사용 순서
1. `ghidraRun`으로 Ghidra 실행 → 프로젝트에 ROM import(**"SNES ROM Loader"** 포맷)·분석.
2. CodeBrowser에서 프로그램 열고 GhidraMCP 플러그인 활성화(File→Configure→Miscellaneous, 또는 자동) → HTTP 8080 기동. (신설치 확장은 File→Install Extensions에서 체크·재시작 필요할 수 있음.)
3. Claude Code(재시작 후)에서 `ghidra` MCP 도구 사용.

### SNES 이점
Ghidra는 커뮤니티 65816/SNES 프로세서·로더가 있어(별도 확장) HiROM 매핑 분석에 IDA보다 진입장벽이 낮을 수 있음.

## ★ 도구 선택 원칙 (Claude·Codex 공통 — 2026-07-21 사용자 지침)

IDA와 Ghidra는 **대체가 아니라 상보**다. 에이전트(Claude·Codex 공통)는 **태스크별로 유리한 도구를 스스로 판단해 선택**한다. 기준:

- **IDA + idalib-mcp = 주력** — 빠른 disasm·xref·`get_bytes`·`define_func`·에이전트 자동화(headless). SNES `$BB:aaaa` = `0xBBaaaa` 직접. 짧은 루틴·데이터표·바이트 질의·대량 반복은 IDA가 빠르고 자동화에 유리.
- **Ghidra + GhidraMCP = 디컴파일이 필요할 때 투입** — **IDA는 65816 Hex-Rays 미지원**(`hexrays_ready=false`)이라 의사-C가 아예 안 나옴. 긴/꼬인 게임로직, base·포인터·스택프레임 전달이 복잡한 루틴, SPC700(사운드)·압축코덱은 Ghidra 디컴파일로 크로스체크. GhidraMCP는 GUI+HTTP 8080 선기동 필요(§2 절차).
- ⚠️ **공통 함정 = M/X 플래그 폭(REP/SEP, 8↔16bit)**: 둘 다 문맥 추적이 불완전해 폭 오싱크 시 **그럴듯하게 틀린** 디스어셈블/디컴파일을 낸다. 애매하면 다른 도구로 교차검증하고, 필요하면 폭을 수동 지정.
- **실전 패턴**: IDA로 빠르게 뜨다가 "이 루틴 로직이 안 읽힌다" 싶으면 그 함수 하나만 Ghidra로 디컴파일해 대조. Codex도 동일하게 판단·선택할 것.

## 3. asar 1.91
- `brew install asar` — RPGHacker의 SNES 65816 어셈블러(⚠️ npm/Electron `asar`과 이름만 같지만, **Homebrew core `asar`는 올바른 SNES 어셈블러**로 확인됨).
- 용도: 향후 폰트/VWF **ASM 훅** 삽입, 패치 빌드. 현재 재삽입 파이프라인은 Python/Rust 바이트 패치라 즉시 필요는 아니나 훅 단계 표준 도구.

## 4. 보류(요청 시 설치)
- **bsnes-plus**: brew 미제공, Apple Silicon 빌드 난이도 높음(구형 Qt). SNES 디버깅은 Mesen2가 커버 → 보류. 크로스체크 필요 시 소스 빌드.
- **aseprite**: cask 삭제(유료·소스빌드). 타일 편집용이나 폰트 파이프라인이 TTF 기반이라 필수 아님 → 보류. 라이선스 보유 시 소스 빌드 지원.

## 5. Mesen2 권한 선취득 (macOS)
- **스크립트 IO 플래그**(`~/Library/Application Support/Mesen2/settings.json`): `Debug.ScriptWindow.AllowIoOsAccess=true`·`AutoStartScriptOnLoad=true` 이미 설정됨. `ScriptTimeout` 10→**60** 상향(긴 덤프/트레이스 루프 대비). ※ 편집은 Mesen 종료 상태에서만(실행 중이면 종료 시 덮어씀).
- **Gatekeeper**: `Mesen.app`의 quarantine 속성 제거(`xattr -dr com.apple.quarantine`) — 실행/스크립팅 차단 방지.
- **macOS TCC(사용자 조치 필요)**: OS 레벨 화면 기록/자동화 권한은 코드로 못 켠다.
  - Mesen 자체 스크린샷(Lua `emu.takeScreenshot()`/단축키)은 자기 프레임버퍼 캡처라 **TCC 불필요**.
  - OS `screencapture`로 창을 찍으려면 호스트 앱(터미널/VSCode)에 **시스템 설정 → 개인정보 보호 및 보안 → 화면 기록** 허용 필요. AppleScript로 창 제어 시 **손쉬운 사용/자동화** 허용 필요.

## 6. Codex에 RE 도구 분산 (2026-07-21)

토큰 절약을 위해 **RE 작업을 Codex에도 분산**한다. Codex CLI는 `~/.codex/config.toml`의 `[mcp_servers.*]`로 MCP를 로드.
- **기존**: `[mcp_servers.ghidra]`(→HTTP 8080 GhidraMCP 브리지), `[plugins."ida-pro-mcp@mrexodia"]`(IDA GUI HTTP 13337).
  둘 다 **GUI 앱(Ghidra/IDA)이 켜져 HTTP 서버가 떠 있어야** 작동 → 미기동 시 사용 불가.
- **추가(headless)**: `[mcp_servers.idalib-mcp]`(command=pipx의 `idalib-mcp`, args=`["--stdio"]`) → **GUI 없이 Codex가 직접 RE**.
  Claude의 `.mcp.json` idalib과 동일 바이너리. 백업: scratchpad `codex_config.backup.toml`.
- **⚠️ .i64 락 충돌 방지**: Claude와 Codex가 **같은 ROM을 idalib으로 동시에 열면 `.i64` 락 충돌**. →
  Codex는 **사본 `roms/re_codex.smc`**(비커밋)를 열게 한다(Claude는 원본). 각자 독립 `.i64`.
- **⚠️⚠️ headless idalib은 '신선 SNES ROM'의 `.i64`를 못 만든다**(SNES 로더 자동선택 불가 → `Failed to open database`).
  이미 만들어진 `.i64`만 연다. 원본 `.i64`는 과거 IDA GUI에서 SNES 로더로 생성됨. **사본은 `.i64`가 없어 열기 실패** →
  **원본 `.i64`를 사본용으로 복사**하면 됨(내용 동일이라 유효): `cp '…(J) (NP).smc.i64' roms/re_codex.smc.i64`.
  (실패한 open이 남긴 부분 DB `re_codex.smc.id0/id1/id2/nam/til`는 먼저 삭제.) 검증: idalib idb_open(re_codex.smc) OK.
- **MCP 승인**(Codex): idalib 첫 도구 호출 시 승인 프롬프트 → **대화형 Codex에서 1회 "Always allow"** 하면
  비대화형(백그라운드) 실행까지 신뢰가 persist됨(2026-07-21 확인). `approval_policy` 전역 변경 불필요.
- **⚠️ Codex 샌드박스가 IDA 파일 I/O 차단**: Codex 기본 workspace-write 샌드박스는 idalib이 여는 `~/.idapro`·`/tmp`
  쓰기를 막아 `Failed to open database`. → RE 태스크는 **`--dangerously-bypass-approvals-and-sandbox`로 실행**
  (RE=읽기전용 ROM 분석이라 저위험). `codex exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check "<task>"`.

### ✅ 작동 확인 레시피 (2026-07-21)
1. Codex config에 `[mcp_servers.idalib-mcp]` 등록(위). 2. 대화형 Codex 1회 "Always allow"로 idalib 신뢰.
3. `roms/re_codex.smc`(원본 사본) + `cp 원본.i64 → re_codex.smc.i64`. **부분 DB(`re_codex.smc.id0/id1/...`)가 있으면 삭제**
   (강제종료·실패한 open이 남긴 잔재가 재개방을 막음 — 실제 원인이었음).
4. `codex exec --dangerously-bypass-approvals-and-sandbox` 로 RE 태스크 → idalib idb_open(re_codex.smc)+disasm 성공.
   실측: 0xC0400A(cmd0x21 핸들러) `LDA #$A / JSR $3E13 / LDA $9A47 / ADC $7E0001 / STA $9A6C,X` 정확히 디스어셈블.
5. **Claude와 Codex가 re_codex.smc.i64를 동시 개방 금지**(락). Claude는 원본, Codex는 사본으로 분리.
- **Codex RE 브리프 규약**(cold-start): idb_open(input_path=`roms/re_codex.smc` 절대경로, mode=`force_headless`) →
  session_id를 database 인자로. **SNES `$BB:aaaa`=IDA `0xBBaaaa` 직접**. `decompile` 금지(65816 Hex-Rays 미지원)→`disasm`.
  알려진 주소는 `define_func` 후 `disasm`. 결과는 파일(scratchpad json)로 쓰게 해 Claude가 게이트/대조.
- 분업: Claude=전략·게이트·정답대조, Codex=반복 디스어셈블/xref 수집. 관련 [[ida-snes-re-workflow]].

## 재현/재설치 메모
- `.mcp.json` 서버 핸드셰이크 재검증: scratchpad `mcp_probe.py`가 각 서버에 `initialize`를 보내 `serverInfo` 확인.
- IDA 플러그인 재설치: `ida-pro-mcp --install`. 설정 JSON: `ida-pro-mcp --config`.
