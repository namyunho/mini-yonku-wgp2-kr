<p align="center">
  <img src="intro.png" alt="미니사구 렛츠&고!! POWER WGP2 — 타이틀 화면(한글)" width="512">
  <br>
  <sub>타이틀 화면 (SFC 네이티브 256×224, 2× 표시)</sub>
</p>

# ミニ四駆 レッツ&ゴー!! POWER WGP2 — 한글 패치 프로젝트

SNES(Super Famicom) 게임 **「ミニ四駆 レッツ&ゴー!! POWER WGP2」**(미니욘쿠 렛츠&고!! 파워 WGP2)의
한글 팬 번역 패치 프로젝트. 레트로 게임 한글화 파이프라인(ROM 분석 → 역공학 → 폰트 → 추출·번역 → 재삽입 → 빌드)을 따른다.

> ⚠️ **법적 고지**: 이 저장소에는 **원본 ROM이 포함되지 않는다.** 도구·역공학 문서·번역 데이터만 둔다.
> 배포는 완성 시 **BPS 차분 패치**(원본 소지자가 직접 적용)로만 이뤄진다. 원본 ROM은 각자 합법적으로 확보할 것.

## 대상 ROM

| 항목 | 값 |
|------|-----|
| 매퍼 | HiROM + FastROM (헤더리스 2MB) |
| CRC32 / MD5 | `4459D4D0` / `acdeb2ee6ef7b460c5dfed6957f8581a` |
| HiROM 주소 변환 | `PC = ((bank & 0x3F) << 16) \| addr` |

## 진행 상태

| 단계 | 상태 |
|------|------|
| 매체 식별·무결성 | ✅ 완료 (HiROM 확정) |
| 텍스트 위치·인코딩 역공학 | ✅ 완료 (파서 `$C1:9554`, 1바이트 가변길이, 글리프=byte−0x10) |
| 폰트 경로 | ✅ 완료 (본문 폰트 뱅크 `$CA`, 16×16 1bpp VWF 비압축) |
| PoC (한글 화면 표시) | ✅ 통과 (실기 Mesen2 렌더 확인) |
| **정적 대사 673** 추출·번역·재삽입 | ✅ 완료 (681/681 무손실, `build_patch.py` — 포메이션 안내 `$C1:CFAF` + 세팅 프리셋·평가문 등 `$C1:C501` 테이블 미캡처 고아 문자열 8건 발굴 복구 포함) |
| **어드벤처 스토리 엔진** 역공학 | ✅ 완료 (씬 VM·압축 코덱·씬표 `$C6:9C57` — [docs/08](docs/08-adventure-text-engine.md)) |
| **어드벤처 스토리 번역·재삽입** | ✅ 번역 완료 + **위치보존 크래시 원천차단** (런 단위 패딩 → 디컴프 스크립트 길이 불변 → VM offset 보존, [docs/14](docs/14-position-preserving-translation.md)). 긴 런 Codex 3라운드 축약, cmd0x20 메뉴/선택지 한글화 진행 |
| **그래픽 한글화**(크레딧·타이틀 로고·타이틀 크레딧줄) | ✅ 완료 (LZSS·스프라이트 재삽입, [docs/10](docs/10-graphics-assets.md)) |
| **시작 저장메뉴**(SJIS) | ✅ 완료 (처음부터/이어하기/복사/삭제, `build_menu.py`) |
| **SJIS 메뉴/UI 텍스트**(레이서명·팀명·파츠명·버튼 프롬프트·저장다이얼로그) | 🟡 **미번역** (조사 완료·착수 전 — [아래 참조](#남은-작업)) |
| 인게임 QA·BPS 배포 | 🟡 진행 (메인스토리 **스테이지8까지 실기 크래시 없음** 확인, BPS는 flips 필요) |

> **번역 현황 요약**: 게임의 **두 텍스트 시스템** 중 ①압축 글리프 시스템(어드벤처 스토리 + 정적 대사 673)은 **전량 한글화 완료**. ②비압축 **SJIS 메뉴/UI 시스템**은 시작 저장메뉴만 처리됐고 **레이서·팀·파츠명, 버튼 프롬프트, 저장/불러오기 다이얼로그 등은 아직 일본어**다.

### 완료 블록

| 시스템 | 규모 | 내용 |
|------|------|------|
| 정적 대사 681 | `c7_race` 232 · `d0_story` 404 · `c1_ui` 45 | 레이스 중계·스토리/배틀 서사·세팅/개러지/포메이션 UI(세팅 프리셋·완성도 평가문 포함) |
| 어드벤처 스토리 | **씬 232 / 텍스트런 1725** | 오프닝·각국팀 대진·세이바가 일상·인격교환·후일담·백과사전 등 전 스토리 |
| 그래픽 | 크레딧 화면·타이틀 로고·하단 상표줄 | 타일/스프라이트 재삽입 |

### 남은 작업

미번역 SJIS 텍스트 영역(현재 ROM `survey.py` 실측):

| 주소 | 내용 |
|------|------|
| `$C0:F4A0` | 레이서 이름 전체(세이바 레츠·고, 타카바 료 …) |
| `$C0:F260` | 팀명 전체(TRF 빅토리즈·NA 아스트로 레인저스 …) |
| `$C0:EB60` | 파츠/모터명(행성명 모터 등) + 카테고리(머신·모터·기어·타이어) |
| `$C1:C540/570` | 버튼 프롬프트(X로 메뉴/A로 결정/B로 뒤로)·저장/불러오기 다이얼로그 |

이 SJIS 시스템은 [docs/02](docs/02-text-survey.md)에서 조사됐고 `build_menu.py`가 SJIS 한글화 경로를 갖고 있어 같은 방식으로 확장 가능(폰트 슬롯·타일 수용량 제약 유의). 그래픽에 구워진 그 외 화면 라벨은 인게임 QA로 추가 확인 예정.

## 저장소 구조

```
docs/        역공학 결과 정본(SSOT) — 단계별 01~10
assets/
  fonts/            한글 TTF·비트맵 폰트 + 라이선스
  translations/     dialogue.json(673) · adventure_kr.json(어드벤처) · pointer_catalog.json
  translation_guide/ glossary.md(용어집) · glyph_table.tsv(글리프표)
scripts/     Python 분석·추출·디코드·빌드 도구(build_all.py 통합) + Mesen2 Lua
src/         Rust 파이프라인(kr-patch-wgp2 크레이트)
roms/ out/ tmp/   비커밋 (원본 ROM·산출물·임시 파일)
```

## 문서 (정본)

- [docs/01-media-survey](docs/01-media-survey.md) — 매체 식별·무결성
- [docs/02-text-survey](docs/02-text-survey.md) — 텍스트 위치(SJIS 메뉴/인명 포함)
- [docs/03-font-survey](docs/03-font-survey.md) — 폰트 트레이싱
- [docs/04-dialogue-encoding](docs/04-dialogue-encoding.md) — 대사 인코딩 역공학
- [docs/05-poc-hangul-font](docs/05-poc-hangul-font.md) — PoC(한글 렌더)
- [docs/06-dialogue-extraction](docs/06-dialogue-extraction.md) — 추출·라운드트립
- [docs/07-dialogue-completeness](docs/07-dialogue-completeness.md) — 파서 대사 완전성 + 포인터 카탈로그
- [docs/08-adventure-text-engine](docs/08-adventure-text-engine.md) — 어드벤처/스토리 텍스트 엔진(씬 VM·코덱) 완전 해독 + 번역·재삽입
- [docs/09-textbox-clip-investigation](docs/09-textbox-clip-investigation.md) — 대화창 클리핑·줄폭 조사
- [docs/10-graphics-assets](docs/10-graphics-assets.md) — 그래픽 에셋(크레딧·로고) 한글화
- [docs/13-adventure-reverted-scenes](docs/13-adventure-reverted-scenes.md) — 원본유지/재번역 추적(cmd0x20·desync)
- [docs/14-position-preserving-translation](docs/14-position-preserving-translation.md) — 위치보존 번역(VM 크래시 원천차단)
- [docs/15-shortening-ledger](docs/15-shortening-ledger.md) — 축약 원장(before→after, 배포 설명용)
- [docs/16-reverse-engineering-mcp](docs/16-reverse-engineering-mcp.md) — 역공학 MCP(IDA·Ghidra) 셋업

## 번역 용어집 (고유명사·용어 통일)

번역 시 인명·마신명·팀명·UI 용어·**캐릭터 말투**를 일관 적용하기 위한 정본 → **[assets/translation_guide/glossary.md](assets/translation_guide/glossary.md)**

- **명명 정책**: 1차 = **일본 원어 음차**(세이바 고 등). 한국 방영판(「우리는 챔피언」) 로컬명은 병기·학습만, 차후 별도 "한국명 버전"용. MAX(3기)·Return Racers 계열은 이 게임 범위 밖 → 미사용.
- **호칭 규칙**: 원문이 이름만 부르는 호격(`ゴー！`)은 성을 붙이지 않고 형태 유지 → 「고!」(❌「세이바 고!」).
- **말투 가이드(§1.5)**: 츠치야「이 아이」↔오오가미「머신」, 토우키치 `~옵쇼`, 지로마루 충청 `~유`, 텟신 사극풍, 카를로 빈정, 파이터 하이텐션 등 어미로 화자 식별.
- **WGP 10개국 대표팀** 로스터·에이스 머신, **UI 용어**·경기장명, 어드벤처 조연·단역 표기 수록.

## 빌드·검증

```bash
git clone https://github.com/namyunho/mini-yonku-wgp2-kr.git
cd mini-yonku-wgp2-kr
# ⚠️ 빌드에 필요하나 gitignore된 파일(폰트 .bin 2종·원본 ROM)은 별도 배치 필요.

# ROM 무결성:
cargo run -- info --rom "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"

# 통합 빌드(전 파이프라인 → out/wgp2_kr.smc):
python3 scripts/build_all.py

# 검증:
python3 scripts/build_patch.py --adv-json assets/translations/adventure_kr.json --out out/wgp2_kr.smc  # 673/673
python3 scripts/build_adv.py         # 어드벤처 재삽입 역검증(round-trip·렌더일치)
python3 scripts/test_roundtrip.py    # 673 무손실
```

**도구 체인**: Python 3(주 파이프라인, `scripts/`, 표준 라이브러리 + Pillow) · Rust(정보/무결성) · Mesen2(arm64 macOS/Windows, Lua QA) · Flips(BPS 배포, 선택).

## 기여·에이전트 협업

착수 전 **[CLAUDE.md](CLAUDE.md)** 또는 **[AGENTS.md](AGENTS.md)**(Codex 등)를 먼저 읽을 것.
핵심 불변식: **원본 ROM 비커밋 · 라운드트립 우선 · HiROM 변환 공식 하나만 사용.**

- **어드벤처 번역**은 서사 클러스터 단위로 나눠 Claude+Codex 두 AI가 분담, 4중 게이트(마커·줄수·전각공백·줄폭≤16)로 교차 검수하는 방식으로 진행됐다.
- **결합(coupling) 주의**: 어드벤처 음절이 늘면 폰트시트 `$CA` 공유로 673 대사가 슬롯을 초과할 수 있다. `build_patch`가 초과 id를 출력하면 해당 673 대사를 1음절 축약한다.
- **문장부호**는 전각만 사용(`！？〜…。「」『』・`). 반각 `! ? ~ , . ; :` 는 게임 폰트에 없다.

## 라이선스

- 도구·문서·번역 데이터: 저장소 소유자 귀속.
- 한글 폰트: `assets/fonts/README.md`의 귀속·라이선스(SIL OFL 1.1) 참조.
- 원본 게임의 모든 권리는 저작권자(TAKARA/AKG 등)에 있다. 본 프로젝트는 비영리 팬 번역이다.
