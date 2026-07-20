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

### GhidraMCP 사용 순서
1. `ghidraRun`으로 Ghidra 실행 → 프로젝트에 ROM import·분석.
2. CodeBrowser에서 프로그램 열고 GhidraMCP 플러그인 활성화(File→Configure→Miscellaneous, 또는 자동) → HTTP 8080 기동.
3. Claude Code(재시작 후)에서 `ghidra` MCP 도구 사용.

### SNES 이점
Ghidra는 커뮤니티 65816/SNES 프로세서·로더가 있어(별도 확장) HiROM 매핑 분석에 IDA보다 진입장벽이 낮을 수 있음.

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

## 재현/재설치 메모
- `.mcp.json` 서버 핸드셰이크 재검증: scratchpad `mcp_probe.py`가 각 서버에 `initialize`를 보내 `serverInfo` 확인.
- IDA 플러그인 재설치: `ida-pro-mcp --install`. 설정 JSON: `ida-pro-mcp --config`.
