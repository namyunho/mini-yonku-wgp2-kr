# 15 · 축약 정책과 바이트 상한 원장 — 영구 기록

한글 번역이 게임 제약(바이트/슬롯)에 걸려 **의미 보존하며 축약**한 대사를 전부 기록한다.
**목적: 배포 시 "어떤 대사를 왜 축약했는지" 설명**. 축약 기록은 절대 유실하지 않는다(원 번역도 보존).

- **기계용 SSOT**: [`assets/translations/shortening_ledger.json`](../assets/translations/shortening_ledger.json)
  (`done`=완료 before→after 확정, `pending`=축약 대기·`before_kr` 스냅샷 보존, Codex가 `after_kr` 채움).
- 이 문서 = 사람이 읽는 뷰(완료 테이블) + 형식·워크플로 설명.
- **현재 전 시스템 통합 비교표 정본**:
  [22-shortened-translation-comparison.md](22-shortened-translation-comparison.md)
  — 어드벤처·정적·필드/NPC·소형 메뉴·월드맵의 완역문과 현재 실제 삽입문이 다른
  **959건 전량**을 나란히 수록한다.
- 아래 **452건**은 위치보존 도입 당시의 기계용 축약 원장 규모다. 현재 전체 비교 건수와
  같은 지표가 아니며, 후속 시스템과 표시 조정은 docs/22가 집계한다.

## 왜 축약하나 — 시스템별 제약

| 시스템 | 키 | 축약 이유 |
|--------|-----|-----------|
| **어드벤처**(`adventure_kr.json`) | `scene`(hex)·`at` | **위치보존**(docs/14): cmd0x20/0x21 런을 원본 바이트 이하로 축약해야 말미 공백 패딩으로 런 길이를 원본과 일치시켜 VM offset(조건분기·컨테이너)을 보존한다. 한글이 원본보다 길면 패딩 불가 → 축약 필수. |
| **정적 대사 681개**(`dialogue.json`) | `entry_id` | **결합(coupling) 축약**(docs/08): 폰트시트 $CA를 어드벤처와 공유. 어드벤처 음절 확대로 일부 in-place 대사가 글리프 슬롯을 초과하면 해당 대사를 최소 조정해 슬롯에 맞춘다. |
| **필드/NPC**(`field_kr.json`) | `entry_id` | **위치보존**(docs/21): 압축 레코드와 후속 데이터의 주소를 바꾸지 않도록 원본 슬롯 상한 안에 삽입한다. |
| **소형 메뉴 그래픽**(`menu_extra_labels.json`) | `id` | **고정 타일폭**: 원본 타일맵과 주변 그래픽을 건드리지 않고 지정된 8×8 타일 수 안에 픽셀을 패킹한다. |

바이트 카운트는 `adv_codec` 인코딩 기준(1바이트 슬롯 글리프=1B, 2바이트 슬롯=2B, 제어마커 `{wait}`/`{clear}`/`\n`=1B).

## ✅ 완료 축약 (452건)

전 452건의 정확한 전후 문구와 바이트 수는 기계용 SSOT에 보존한다. 아래 표는 크래시 해결과
직접 관련된 대표 사례이며, 2026-07-20 완료한 나머지 어드벤처 긴 런 443건도 원장에 전량 기록돼 있다.

### A. 어드벤처 위치보존 축약

| scene | at | before (원 번역) | after (축약) | byte |
|-------|-----|------------------|--------------|------|
| 0xB0 | 522 (0x020A) | 카이「아직도 이런 짓을/**계속할** 셈인가요！？ | 카이「아직도 이런 짓을/셈인가요！？(「계속」생략) | 31→27 (상한 27) |
| 0xB0 | 873 (0x0369) | 라「곧 **알게 된다** | 라「곧 **안다** | 14→9 (상한 11) |
| 0xB0 | 1091 (0x0443) | 카이「**그의** 눈은…/옛날의 저와 **같은 눈이었어요**… | 카이「**그** 눈은…/옛날의 저와 **같았어요**… | 36→30 (상한 31) |

> 0xB0 = 카이×라 승부 후 대화. 위치보존 프로토타입(docs/14)에서 긴 런 3개를 축약. 의미·말투(카이 `~요`, 라 오만·단정) 보존.

### B. cmd0x20 직접 본문 복구 축약

| scene | at | before (완역) | after (삽입문) | byte |
|-------|-----|---------------|----------------|------|
| 0x69 | 221 (0x00DD) | GP칩 레벨이 `{c7:0A}`가 됐다 | GP칩 레벨 `{c7:0A}`가 됐다 | 18→17 (상한 17) |
| 0x69 | 335 (0x014F) | 폭주 포인트가 `{c7:0A}` 올랐다 | 폭주 포인트가 `{c7:0A}` 상승 | 17→15 (상한 16) |
| 0x6F | 64 (0x0040) | 『`{c7:00}`』/을 손에 넣었다 | 『`{c7:00}`』/획득！ | 16→10 (상한 12) |

세 항목은 `adventure_kr.json`에도 `text_jp`(일본어 원문)·`text_kr_full`(축약 전 완역)·
`text_kr`(위치보존 삽입문)을 따로 보관한다.

### C. 정적 대사 결합축약

| entry_id | 화자 | before | after | 변경 |
|----------|------|--------|-------|------|
| 499 | 카이 | 「흥 **제법이군요** | 「흥 **잘하네요** | -1음절 |
| 392 | (고) | 용기가 **솟아난다**！ | 용기가 **솟는다**！ | -1음절 |
| 488 | 미하엘 | 「**뭐라고**！ | 「**뭐야**！ | -1음절 |

> before는 glossary·git 이력 기준 구절 단위 재구성(정확한 원문은 dialogue.json git 이력). 어드벤처 확대 시점(2026-07-16)에 슬롯 초과 해소용.

### D. 소형 메뉴 그래픽 고정폭 축약

| id | 원문 | 완역 | 실제 삽입문 | 제약 |
|---|---|---|---|---|
| `next_level` | 次のLVまで | 다음 레벨까지 | 다음LV까지 | 원본 5타일(40px) 위치 보존 |

원문·완역·실제 삽입문과 대상 자원 해시는 `assets/translations/menu_extra_labels.json`에 분리 보존한다.

## 대기 축약

없음. `pending_count=0`, 통합 빌드의 `out/retranslate_longer.json`도 0런이다.

## 워크플로 (축약 시 기록 규칙)

축약을 새로 할 때마다 **반드시 원장에 before→after를 남긴다**(before 유실 금지):

1. **before 확보**: 어드벤처는 축약 전 `adventure_kr.json`의 현재 `text_kr`(=`shortening_ledger.json` pending의 `before_kr`, 또는 `out/retranslate_longer.json`). 정적 대사는 `dialogue.json`의 `text_kr_full`, 소형 메뉴는 `menu_extra_labels.json:text_kr_full`에 보존한다.
2. **after 기입**: 축약안을 `after_kr`에 기록, `status`를 `done`으로. (Codex 배치 산출을 병합할 때 함께.)
3. **게이트**: after 바이트길이 ≤ `orig_bytes`(어드벤처)/정적 대사 슬롯 확인 후 `adventure_kr.json`·`dialogue.json`에 반영.
4. 이 문서의 완료 테이블도 갱신(사람용 뷰).

관련: [14-position-preserving-translation.md](14-position-preserving-translation.md)(왜 축약이 필요한가),
[13-adventure-reverted-scenes.md](13-adventure-reverted-scenes.md)(원본유지 씬),
[../assets/translation_guide/glossary.md](../assets/translation_guide/glossary.md)(용어·말투·줄길이 규칙).
