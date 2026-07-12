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
| 대사 완전성 확정 | ✅ 완료 (정적 텍스트 뱅크 `$C7/$D0/$C1` 권위 열거) |
| 추출·라운드트립 | ✅ 완료 (**정적 대사 673개**, `encode(parse)==raw==ROM` 전량 무손실) |
| 전 블록 포인터 카탈로그 | ✅ 완료 (VM opcode·ROM 테이블·인라인 즉치 3경로) |
| 번역 | 🟡 진행 (`text_jp` → 한글; **c1_ui 37 완료**, 용어집 확립) |
| 재삽입·빌드·검증 | ⬜ 미착수 |

### 확정 대사 블록 (673)

| 블록 | 뱅크 | 개수 | 내용 |
|------|------|------|------|
| `c7_race` | `$C7:89E2` | 232 | 레이스 중계·조작 안내 |
| `d0_story` | `$D0:C80B` | 404 | 스토리/배틀 서사(캐릭터·마신명·필살기) |
| `c1_*` (4클러스터) | `$C1` | 37 | 세팅·마신명·개러지·포메이션 UI |

## 저장소 구조

```
docs/        역공학 결과 정본(SSOT) — 단계별 01~07
assets/
  fonts/            한글 TTF·비트맵 폰트 + 라이선스
  translations/     dialogue.json(673 대사) · pointer_catalog.json
  translation_guide/ glossary.md(용어집) · glyph_table.tsv(1008 글리프)
scripts/     Python 분석·추출·디코드 도구 + Mesen2 Lua
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
- [docs/07-dialogue-completeness](docs/07-dialogue-completeness.md) — 완전성 확정 + 포인터 카탈로그

## 번역 용어집 (고유명사·용어 통일)

번역 시 인명·마신명·팀명·UI 용어를 일관 적용하기 위한 정본 → **[assets/translation_guide/glossary.md](assets/translation_guide/glossary.md)**

- **명명 정책**: 1차 = **일본 원어 음차**(세이바 고 등). 한국 방영판(「우리는 챔피언」) 로컬명은 병기·학습만, 차후 별도 "한국명 버전"용. MAX(3기)·Return Racers 계열은 이 게임 범위 밖 → 미사용.
- **호칭 규칙**: 원문이 이름만 부르는 호격(`ゴー！`)은 성을 붙이지 않고 형태 유지 → 「고!」(❌「세이바 고!」).
- **TRF 빅토리즈 6종 머신·파일럿**: 비트 매그넘(세이바 고)·버스터 소닉(세이바 레츠)·네오 트라이대거 ZMC(타카바 료)·스핀 바이퍼(미쿠니 토우키치)·프로토 세이버 EVO(제이)·비크 스파이더(오키타 카이).
- **WGP 10개국 대표팀** 로스터·에이스 머신, **UI 용어**(머신·개러지·세팅·포메이션·파츠·그리드, 조작 안내 「A버튼 결정」) 수록.

## 시작하기

```bash
git clone https://github.com/namyunho/mini-yonku-wgp2-kr.git
cd mini-yonku-wgp2-kr
# roms/ 에 원본 ROM 배치 후 무결성 검증:
cargo run -- info --rom "roms/Mini Yonku Let's & Go!! - Power WGP 2 (J) (NP).smc"
# 라운드트립 회귀 게이트 (673 전량 무손실 확인):
python scripts/test_roundtrip.py
```

**도구 체인**: Rust(GNU 1.97, 주 파이프라인) · Python 3.14(`scripts/`) · Mesen2 2.1.1(Lua 디버깅·QA) · Flips v198(BPS).

## 기여·에이전트 협업

착수 전 **[CLAUDE.md](CLAUDE.md)** 또는 **[AGENTS.md](AGENTS.md)**(Codex 등)를 먼저 읽을 것.
핵심 불변식: **원본 ROM 비커밋 · 라운드트립 우선 · HiROM 변환 공식 하나만 사용.**
번역은 블록 단위(c7 → d0 → c1)로 나눠 진행하면 충돌이 적다.

## 라이선스

- 도구·문서·번역 데이터: 저장소 소유자 귀속.
- 한글 폰트: `assets/fonts/README.md`의 귀속·라이선스(SIL OFL 1.1) 참조.
- 원본 게임의 모든 권리는 저작권자(TAKARA/AKG 등)에 있다. 본 프로젝트는 비영리 팬 번역이다.
