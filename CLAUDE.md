# Mini Yonku Let's & Go!! - Power WGP 2 · 한글 패치 프로젝트

SNES(Super Famicom) 게임 「ミニ四駆 レッツ&ゴー!! POWER WGP2」의 한글 팬 번역 패치 프로젝트.
방법론은 `create-kr-patch` Agent Skill(레트로 게임 한글 패치 파이프라인)을 따른다.

## 원본 (roms/ — 비커밋)

| 항목 | 값 |
|------|-----|
| 파일 | `roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc` (헤더리스, 2MB) |
| 매퍼 | **HiROM + FastROM** |
| CRC32 / MD5 | `4459D4D0` / `acdeb2ee6ef7b460c5dfed6957f8581a` |
| 세이브 | 8KB SRAM + Battery / 국가: 일본(NTSC) |

**HiROM 주소 변환**: `PC = ((bank & 0x3F) << 16) | addr` — LoROM 공식 쓰지 말 것. 상세: [docs/01-media-survey.md](docs/01-media-survey.md)

## 파이프라인 상태

| 단계 | 상태 | 비고 |
|------|------|------|
| 매체 식별·무결성 | ✅ 완료 | HiROM 확정, 해시 고정, 헤더 유효 → [docs/01-media-survey.md](docs/01-media-survey.md) |
| round-trip 검증 | ✅ 완료(flat) | 전체 ROM 항등. 폰트/포인터 컨테이너 round-trip은 추후 property 테스트 |
| 텍스트 위치·인코딩 | ✅ 확정 | **메뉴/인명은 Shift-JIS 비압축**($C0–$C1). **본문 대사 인코딩 완전 역공학·검증**: 뱅크 $C7 스크립트, 1바이트 가변길이(글리프=byte−0x10, 2바이트 프리픽스 0x01–04, 종료 0x00, 제어 0x05 nl/0x06/0x07), 파서 $C1:9554·호출자 $C3:7899 → [docs/04-dialogue-encoding.md](docs/04-dialogue-encoding.md), [docs/02-text-survey.md](docs/02-text-survey.md) |
| 폰트 경로 | ✅ 확정 | **본문 폰트 = ROM 뱅크 $CA(`0x0A1137`), 16×16 1bpp(32B/글리프) 비압축, VWF.** 압축 아님(이전 가정 폐기). Mesen2 동적 트레이스+화면 실측으로 확정 → [docs/03-font-survey.md](docs/03-font-survey.md). ⚠️ 메뉴 폰트 경로는 미확인 |
| 훅 지점 | 🟡 후보확보 | 글리프 페치 `$C0:6827`/블리터 `$C0:68B2`/버퍼클리어 `$C0:6BC2`/폰트읽기 `$C0:686D`. 훅 확정은 인코딩 역공학 후 |
| 수용량·베이크드 비율 | ⬜ 미착수 | 빈 뱅크·프리픽스 인코딩 여지 |
| PoC (한글 화면 표시) | ✅ 통과 | **실기 화면에 한글 렌더 확인**("부천 레트로 흥해라"). 실제 경로(스크립트 $C7→파서 $C1:9554→글리프 페치→폰트 시트 $CA) 그대로. 폰트=`assets/fonts/x12y12pxMaruMinyaHangul.ttf`(OFL), 도구=`cargo run -- poc-font`(TTF 래스터+시트 주입+per-글리프 폭/공백). base03 인코더 검증됨 → [docs/05-poc-hangul-font.md](docs/05-poc-hangul-font.md) |
| 추출·완전성·포인터 | ✅ 완료 | 정적 대사 681, 어드벤처 메시지 **1,782**(엄격 VM 재감사 숨은 58런 복구), 월드맵 350문자열, 필드/NPC 텍스트런 1,411(고유 1,340) 카탈로그와 역검증 경로 확정. 상세는 [docs/07](docs/07-dialogue-completeness.md)·[docs/08](docs/08-adventure-text-engine.md)·[docs/19](docs/19-worldmap-quiz-text.md)·[docs/20](docs/20-field-npc-hidden-records.md) |
| 빌드·검증 | 🟡 v0.9 배포·실기 QA 진행 | `build_all.py`가 정적·그래픽·어드벤처·필드/NPC·월드맵·SJIS·소형 메뉴·Result·포메이션·능력치·개러지·경기 HUD·**VICTORYS 에피소드 인터미션 로고**·**챕터 인트로 2bpp 제목 10개**·**실제 엔딩 크레딧/베스트타임 45행과 현지화 메시지 12행**을 **원본과 동일한 2MB ROM 내부**에 통합한다. 정적 681, 어드벤처 **235씬·1,782메시지**, 필드 685레코드, 월드맵 350문자열, Result 선수 범위표 110/110·표시 이름 61종·물리 타일 공유 0, 인트로 그래픽 10/10, 경기 HUD와 엔딩 전용 글꼴·스트림 역검증 PASS. 완역–실삽입 조정문은 959건이며 원문·완역·삽입문을 분리 보존한다. v0.9 xdelta는 역적용 결과가 통합 ROM과 바이트 일치함을 검증했다. 메인스토리 전편 실기 완주 완료, 추가 동선·승인 그래픽 QA 진행 중 |

## 디렉토리 구조

```
roms/        원본·출력 이미지 (gitignore) — No-Intro 파일명 유지
docs/        역공학 결과 SSOT (단계별 파일 분리)
assets/
  fonts/         한글 TTF — x12y12pxMaruMinyaHangul.ttf(OFL, 주력) + README(귀속/라이선스)
  translations/  번역 JSON (진척 단계별 하위 디렉토리)
  translation_guide/  고유명사·용어 통일
scripts/     초기 탐색용 일회성 스크립트 격리 (빌드 경로에 넣지 않음)
qa_screenshot/  에뮬레이터 QA 스크린샷
out/         빌드 산출물 (gitignore)
```

## 핵심 불변식

- **원본 ROM·패치 적용 이미지는 절대 커밋하지 않는다.** 배포는 BPS/xdelta 차분 패치로.
- **round-trip 검증 우선** — 추출→재조립 바이트 일치 증명 후에만 수정 착수.
- **PoC 게이트 전 본 구현 금지** — 게임 실제 데이터 경로로 한글 글리프를 화면 표시하기 전엔 되돌리기 비싼 작업 시작 안 함.
- 오프셋 계산은 HiROM 변환 함수 SSOT 하나만 사용.

## 빌드·도구 (설치 완료·검증됨)

주 파이프라인 = **Rust**(clap/serde/fontdue/png/encoding_rs/crc32fast/md-5). 프로젝트 루트 단일 크레이트 `kr-patch-wgp2`, `src/commands/`에 서브커맨드.

```
cargo build                         # 전체 빌드
cargo run -- info --rom roms/<파일>  # ROM 헤더·해시 출력 (구현 완료·검증)
```

| 도구 | 버전 | 경로 / 호출 | 용도 |
|------|------|------------|------|
| Rust (GNU) | 1.97.0 | `C:\Program Files\Rust stable GNU 1.97\bin` (Machine PATH) | 주 파이프라인 (cargo/rustc) |
| mingw-w64 (WinLibs) | 16.1.0 (MSVCRT) | `...WinGet\Packages\BrechtSanders.WinLibs...\mingw64\bin` (PATH) | GNU 타깃 링크에 필요한 `dlltool`·binutils |
| Python | 3.14.3 | `python` (PATH) | 탐색 분석 스크립트 (`scripts/`) |
| Mesen2 | 2.1.1 | `...WinGet\Packages\SourMesen.Mesen2...\Mesen.exe` (별칭 `Mesen`) | 디버깅·Lua 스크립팅·QA |
| Flips | v198 | `C:\Users\namyunho\tools\flips\flips.exe` (User PATH) | BPS/IPS 패치 생성·적용 |
| xdelta3 | 3.2.0 | Homebrew `xdelta3` | v0.9 xdelta 생성·역적용 검증 |

- **GNU 툴체인 주의**: 독립형 Rust GNU는 `dlltool.exe`를 포함하지 않아 `windows-sys` 등 컴파일 시 mingw-w64 binutils가 PATH에 있어야 한다(설치 완료). PATH 미반영 셸에서는 `$env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")`로 재로딩.
- Mesen2는 GDB 서버 미지원 → **Lua 스크립팅이 주 디버깅 수단**. exec 브레이크포인트는 ROM(PC) 오프셋 기준, HiROM 변환 적용.
- **Mesen2 Lua 자동화(검증됨)**: CLI로 `Mesen.exe "<rom>" "<script.lua>"` → 스크립트 자동 로드·실행(설정 `AutoStartScriptOnLoad=true`). 파일 io 쓰려면 `~/Documents/Mesen2/settings.json`에서 `ScriptWindow.AllowIoOsAccess=true`, 긴 덤프 루프엔 `ScriptTimeout` 상향(현재 30) 필요(둘 다 반영 완료). `emu.stop(0)`은 **에뮬만 멈추고 GUI는 안 닫음** → PowerShell `Start-Process -PassThru` 후 `WaitForExit(timeout)`+`Stop-Process`로 종료. API: `emu.callbackType`(read/write/exec, `memCallbackType` 아님), `emu.getState()`는 **평면 테이블**(`st["dmaController.channel[N].srcBank"]`, `st["cpu.pc"]`, `st["ppu.vramAddress"]` 등). 트레이스 스크립트: `scripts/lua/`.
- 배포는 원본에서 패치 ROM 생성 후 **xdelta/BPS 차분**으로. 원본·패치 ROM은 비커밋.

### 역공학 MCP 도구 (macOS, 2026-07-20 셋업 → 상세 [docs/16](docs/16-reverse-engineering-mcp.md))

현재 작업 머신은 **macOS(arm64)**. 위 표의 Windows 경로는 이관 전 기록. 역공학은 아래 MCP 도구를 **적극 활용**한다(등록: 프로젝트 `.mcp.json`, **Claude Code 재시작 후** 활성·최초 승인 필요).

| MCP 서버 | 도구 | 용도 |
|----------|------|------|
| `ida-pro-mcp` | IDA Professional 9.4 (GUI 브리지, 13337) | IDA GUI에 ROM/DB 연 상태로 라이브 질의 |
| `idalib-mcp` | IDA headless (idalib) | GUI 없이 에이전트가 직접 바이너리 분석 — 자동화 우선 |
| `ghidra` | Ghidra 12.1.2 + GhidraMCP(11.3.2→12.1.2 패치, HTTP 8080) | 디컴파일러 크로스체크. 65816/SNES 로더 진입장벽 낮음 |

- 어셈블러 **asar 1.91**(`brew`, 65816) 설치 — 향후 폰트/VWF ASM 훅·패치 빌드용.
- **Ghidra JDK**: `openjdk@21` keg-only → `~/.zshrc`에 `JAVA_HOME` 영구 설정(반영 완료). 없으면 `ghidraRun`이 Java 못 찾음.
- **macOS Mesen2 설정 경로는 `~/Library/Application Support/Mesen2/settings.json`**(Windows의 `Documents/Mesen2` 아님). 스크립트 IO 플래그 설정 완료, `ScriptTimeout`=60, `Mesen.app` quarantine 제거 완료. OS 화면기록/자동화(TCC)는 사용자가 시스템 설정에서 허용 필요(자세히 docs/16 §5).
- 보류: bsnes-plus·aseprite(요청 시 설치, 근거 docs/16 §4).
