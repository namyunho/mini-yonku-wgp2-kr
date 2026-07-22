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
| **정적 대사 681** 추출·번역·재삽입 | ✅ 완료 (681/681 무손실, `build_patch.py` — 포메이션 안내 `$C1:CFAF` + 세팅 프리셋·평가문 등 `$C1:C501` 테이블 미캡처 고아 문자열 8건 발굴 복구 포함) |
| **어드벤처 스토리 엔진** 역공학 | ✅ 완료 (씬 VM·압축 코덱·씬표 `$C6:9C57` — [docs/08](docs/08-adventure-text-engine.md)) |
| **어드벤처 스토리 번역·재삽입** | ✅ **완료** — **231씬·1,724메시지 전량 반영** + 위치보존 크래시 원천차단(런 단위 패딩 → 디컴프 스크립트 길이·VM offset 불변, [docs/14](docs/14-position-preserving-translation.md)). cmd0x20은 2바이트 오퍼랜드를 보존하고 본문만 같은 길이로 치환. **오프닝~엔딩 전편 실기 완주(크래시 0) 확인** |
| **월드맵 퀴즈·정보 DB** | ✅ 70문항·350문자열 추출/번역/재삽입 완료 (`$C6:A08D` 포인터표, 350/350 왕복·역디코드 — [docs/19](docs/19-worldmap-quiz-text.md)) |
| **장소별 필드/NPC 숨은 레코드** | ✅ 전수 발굴·번역·**위치보존 재삽입 완료** (**1,207레코드**, C2 참조 1,290개+패턴 오탐 10개 제외, 텍스트런 1,411/고유 **1,340 전량 번역**; 텍스트 레코드 685개 역검증·타일/OBJ 실기 정상, [docs/20](docs/20-field-npc-hidden-records.md)·[docs/21](docs/21-field-position-preserving-translation.md)) |
| **그래픽 한글화**(크레딧·타이틀 로고·타이틀 크레딧줄) | ✅ 완료 (LZSS·스프라이트 재삽입, [docs/10](docs/10-graphics-assets.md)) |
| **시작 저장메뉴**(SJIS) | ✅ 완료 (처음부터/이어하기/복사/삭제, `build_menu.py`) |
| **SJIS 메뉴/UI 텍스트**(레이서명·팀명·머신/파츠명·행성·옵션부품·시작/저장메뉴) | ✅ **완료** (비압축 SJIS 한글화 + 슬롯 `0x86` 확장 189→224, `build_sjis.py`) |
| **소형 타일폰트 메뉴**(월드맵 X메뉴·조작방법 튜토리얼·용어집·지도·수동 세팅 X메뉴 — System④) | ✅ **완료** — 원본 소형폰트 자원(`$D9`)을 문맥별 한글 글꼴로 재압축·포인터 리다이렉트(코드 훅/NMI 없음). 수동 세팅 X메뉴는 공유폰트 미사용 타일 재사용(`build_setbox.py`) |
| 인게임 QA·BPS 배포 | 🟡 진행 (메인스토리 **오프닝~엔딩 전편 실기 완주·크래시 0** 확인, 통합 빌드에서 Flips 감지 시 BPS 자동 생성) |

> **번역 현황 요약**: 정적 대사·어드벤처 스토리(오프닝~엔딩 전편)·월드맵 퀴즈/정보 DB·**장소별 필드/NPC 대사 1,340종**·비압축 **SJIS 메뉴/UI**(레이서·팀·머신/파츠·행성·옵션·저장메뉴)·**소형 타일폰트 메뉴**(월드맵 X메뉴·조작방법·용어집·지도·수동 세팅)의 번역과 통합 재삽입이 완료됐다. 필드/NPC 대표 장소 실기 QA와 타일에 구워진 일부 그래픽 텍스트가 아래 [남은 작업](#남은-작업)과 같이 남아 있다.

통합 빌드는 번역 카탈로그와 실제 치환 항목을 대조한다. 어드벤처 미반영 항목, 정적 대사 미커버 초과,
필드 위치보존 상한 초과가 하나라도 생기면 ROM 생성을 실패시켜 번역문이 조용히 원문으로 되돌아가지 않게 한다.

### 완료 블록

| 시스템 | 규모 | 내용 |
|------|------|------|
| 정적 대사 681 | `c7_race` 232 · `d0_story` 404 · `c1_ui` 45 | 레이스 중계·스토리/배틀 서사·세팅/개러지/포메이션 UI(세팅 프리셋·완성도 평가문 포함) |
| 어드벤처 스토리 | **씬 232 / 텍스트런 1725** | 오프닝·각국팀 대진·세이바가 일상·인격교환·후일담·백과사전 등 전 스토리 |
| 월드맵 퀴즈·정보 | **70문항 / 350문자열** | 산수 40문항 + 정보 30문항, 질문 1 + 선택지 4 구조 보존 |
| 장소별 필드/NPC | **텍스트런 1,411 / 고유 1,340** | `text_kr_full` 완역본과 `text_kr` 삽입본(축약 280) 분리 보존, 685개 압축 레코드 재삽입·위치/렌더 역검증 통과 |
| 그래픽 | 크레딧 화면·타이틀 로고·하단 상표줄 | 타일/스프라이트 재삽입 |
| SJIS UI(전체) | 레이서 57·팀 10·머신 22·행성 11·옵션 15 + 시작/저장메뉴 | 비압축 SJIS 한글화 + 슬롯 **0x86 확장(189→224)** — [docs/12](docs/12-sjis-ui-hangul.md) |
| 소형 타일폰트 메뉴(System④) | 월드맵 X메뉴·조작방법 튜토리얼·용어집·지도·수동 세팅 X메뉴 | 원본 `$D9` 소형폰트를 문맥별 한글 글꼴로 재압축·포인터 리다이렉트(코드 훅/NMI 없음) |

### 남은 작업

> 정적 대사·어드벤처 스토리(전편)·월드맵 퀴즈·필드/NPC·SJIS 메뉴/UI·소형 타일폰트 메뉴는 번역과 통합 재삽입이 끝났다.
> 남은 항목은 아래와 같으며, 진행하며 추가로 발견될 수 있다.

**텍스트 번역**
- **장소별 필드/NPC 대표 장소 실기 QA** — C4/C5/C6 씬간 압축 팩의 **1,340 고유문자열**은 `build_field.py`로 통합됐다. 연구소·학교·미쿠니가·각 팀 숙소 등에서 동선·분기·선택지를 확인할 것([docs/21](docs/21-field-position-preserving-translation.md)).
- **경기 후 Result 화면** — 순위별 선수명 표기.
- **경기 중 일시정지 메뉴** — 계속하다 / 리타이어.

**그래픽·이미지 폰트** (타일에 구워진 텍스트 — LZSS/스프라이트 재삽입 필요, [docs/10](docs/10-graphics-assets.md) 방식)
- **엔딩 크레딧** 롤 번역.
- **챕터별 타이틀** 이미지 번역.
- 챕터 중 캐릭터 씬 하단 **게임 타이틀 이미지(소형) 삽입**.
- **개러지 파츠명 이미지 폰트**(모터·기어 등).
- **포메이션 셋팅 이미지 폰트**(セッティング / イージーセッティング / テストそうこう / コースチェック).
- **경기 중 데미지·폭주 이미지 폰트**.

## 저장소 구조

```
docs/        역공학 결과 정본(SSOT) — 단계별 01~20
assets/
  fonts/            한글 TTF·비트맵 폰트 + 라이선스
  translations/     dialogue.json(681) · adventure_kr.json · worldmap_{kr,text}.json · field_text.json
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
- [docs/19-worldmap-quiz-text](docs/19-worldmap-quiz-text.md) — 월드맵 퀴즈/정보 DB 70문항 추출·번역·재삽입
- [docs/20-field-npc-hidden-records](docs/20-field-npc-hidden-records.md) — 장소별 필드/NPC 숨은 압축 레코드 전수 조사
- [docs/21-field-position-preserving-translation](docs/21-field-position-preserving-translation.md) — 필드/NPC 위치보존 번역·재삽입 설계
- [docs/22-shortened-translation-comparison](docs/22-shortened-translation-comparison.md) — 완역문과 실제 ROM 삽입 축약문 751건 전수 비교

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

# 통합 빌드(원본과 동일한 2MB → out/wgp2_kr.smc + out/wgp2_kr.bps):
python3 scripts/build_all.py

# 추출·카탈로그 회귀:
python3 scripts/extract_worldmap_text.py  # 월드맵 350/350 왕복
python3 scripts/extract_field_text.py     # 필드/NPC 1,207레코드·C2 참조 1,290개(+오탐 10개 제외)

# 재삽입·검증:
python3 scripts/build_patch.py --adv-json assets/translations/adventure_kr.json --worldmap-json assets/translations/worldmap_text.json --field-json assets/translations/field_kr.json --out out/wgp2_kr.smc
python3 scripts/build_adv.py         # 어드벤처 재삽입 역검증(round-trip·렌더일치)
python3 scripts/build_field.py       # 필드/NPC 위치보존 재삽입·685/685 역검증
python3 scripts/validate_field_translation.py
python3 scripts/audit_field_position.py
python3 scripts/test_roundtrip.py    # 정적 대사 681/681 무손실
```

**도구 체인**:
- **Python 3** — 주 파이프라인(`scripts/`, 표준 라이브러리 + Pillow): 추출·디코드·재삽입·빌드.
- **Rust**(kr-patch-wgp2) — ROM 정보/무결성.
- **역공학**: **IDA Pro 9.4**(`ida-pro-mcp` GUI 브리지 + `idalib-mcp` 헤드리스) · **Ghidra 12.1.2**(GhidraMCP, 디컴파일 크로스체크) · **asar 1.91**(65816 어셈블러, ASM 훅·패치) — 셋업 [docs/16](docs/16-reverse-engineering-mcp.md).
- **Mesen2**(arm64 macOS/Windows) — Lua 스크립팅 QA·트레이싱.
- **Flips** — BPS 차분 배포(선택, 통합 빌드가 감지 시 자동 생성).

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
