# 10 · 그래픽 에셋 (오프닝 크레딧·로고 등) — 🟡 조사 시작

텍스트가 아니라 **타일 그래픽**으로 그려지는 화면들(저작권/상표 크레딧, 로고 등)의 편집·재삽입.

## 판별: 텍스트 아님 = 그래픽
오프닝 크레딧(`©1998 Nintendo・JUPITER CORP.` / `©こしたてつひろ・小学館・テレビ東京` / `©タミヤ` / `ミニ四駆は、田宮模型の登録商標です。`)의 문자열을 ROM에서 SJIS·ASCII로 검색 → **0건**(심지어 "1998","Nintendo"도 없음). → **그래픽(2bpp 타일)로 렌더**되는 화면 확정.

## 압축 여부 (DMA 트레이스 `scripts/lua/dma_trace.lua`)
| 에셋 | 소스 | 압축? | 편집 |
|---|---|---|---|
| 인트로·크레딧 타일 (vmadd $0000/$3000/$4000/$7000, tilemap $5C00) | **WRAM $7F:1000 / $7E:6000** | **압축**(ROM→해제→WRAM→DMA) | 해제→편집→재압축 필요 |
| f492 타일 (vmadd $7A00-7F60) | **ROM $CE:8D38-969E 직접** | **비압축** | 툴로 직접 편집 가능 |

→ 압축 에셋은 **디컴프레서·코덱 역공학** 후에야 편집 가능. 비압축 에셋은 ROM 오프셋만 알면 바로 편집.

## VRAM 덤프·렌더 (확인용)
- `scripts/lua/trace_credits.lua` : 크레딧 화면(부팅 ~f420)에서 VRAM(64KB)·CGRAM·PPU 레지스터·스크린샷 덤프 → `tmp/trace/credits/`.
- `scripts/render_credits.py` : BG 레이어별 PNG 렌더(BG mode1: BG1/2=4bpp, BG3=2bpp).
- 전체 VRAM 타일시트(2bpp/4bpp, 이진) 렌더로 글리프 위치 확인 가능. 크레딧 글자 = **2bpp 타일**(팔레트 pal0: 색1=흰색 텍스트).
- CGRAM: pal0 = [검정, 흰(248), 회(136), 암(32)] — 텍스트는 색1(흰).

## 도구 (그래픽 편집)
- **Mesen2(설치됨)**: Debug ▸ Tile Viewer / Tilemap Viewer / Sprite Viewer(라이브 VRAM 확인, PNG Export). 위치 파악·비압축 확인에 최적. Memory Tools로 VRAM/CGRAM 덤프.
- **YY-CHR(.NET)**: SNES 2bpp/4bpp 타일 직접 편집(비압축 ROM 오프셋 지정). Windows 무료. 번역씬 표준.
- **Tile Molester(모던 포크)**: Java, 코덱 유연·팔레트 임포트.
- **Crystaltile2**: 고급(타일맵·폰트·일부 압축 지원), 번역 프로젝트에서 많이 씀.
- **압축 에셋**: Lunar Compress(다수 SNES 코덱) 또는 코덱 식별 후 커스텀 해제/재압축 파이프라인.

## ✅ 오프닝 그래픽 코덱 = 표준 LZSS (완전 해독)
디컴프레서 **`$C0:0D91~0E1x`** 정밀 디스어셈블 → **표준 LZSS(4KB 링버퍼)**:
- 링버퍼 4096B(`$7F:0000`), 시작 위치 `r=0xFEE`, 초기값 0(부팅 WRAM 클리어).
- 플래그 비트 **LSB first**: `1`=리터럴(소스1B 출력+링기록), `0`=매치(소스 2B LE word →
  `pos=word>>4`(12bit 링위치)·`len=(word&0xF)+3`, 링에서 len바이트 복사).
- `$05`=출력길이. 소스 롱포인터 `$11-$13`.
- 출력은 VRAM 타일(2bpp/4bpp)로 DMA.

### 압축 소스 목록 (전부 뱅크 $C7, 트레이스 `trace_lzsrc.lua` 확정)
| 소스 | 해제크기 | VRAM | 내용 |
|---|---|---|---|
| `$C7:1574` | 12800 | $0000 | 4bpp 그래픽(로고/아트, 타일맵 배치) |
| `$C7:347C` | 2048 | $3000 | |
| `$C7:382F` | 4096 | $4000 | |
| **`$C7:3A3F`** | **8192** | **$7000** | **★크레딧 문자 글리프(2bpp)** — ©1998 Nintendo·JUPITER/こしたてつひろ·小学館·テレビ東京/タミヤ/ミニ四駆は田宮模型の登録商標です |
| `$C7:1218` | 4096 | — | |
| `$C7:1148` | 640 | — | |
| `$C7:0D11` | 2048 | — | |

### 도구 `scripts/lzss.py`
- `decompress(rom, foff(bank,addr), out_len)` — 검증됨(정확). 전 블롭 `tmp/gfx/*.bin` 산출.
- `compress()` — 매치 기반 재압축은 **오버랩 버그로 왕복 실패(대형 블롭)**. 재삽입엔 **전량 리터럴 모드(항상 정확)** 사용 예정 or 컴프레서 수정. 리터럴은 ~9/8배라 원본 슬롯 초과→자유공간 재배치+소스포인터($11-$13 셋업) 패치 필요.
- 타일시트 렌더: `tmp/gfx/*_2bpp.png`(크레딧=vram_7000), `*_4bpp.png`.

## 편집→재삽입 워크플로 (그래픽)
1. `tmp/gfx/<blob>.bin` = 해제된 원본 타일(YY-CHR/Tile Molester로 열어 편집; 2bpp 또는 4bpp).
2. 편집본 → `lzss.compress`(리터럴 안전모드)로 재압축.
3. 원본 슬롯($C7:xxxx)에 맞으면 in-place, 초과면 자유공간 재배치 + **소스포인터 패치**(디컴프 호출자가 $11-$13에 넣는 값).
4. Mesen 확인.

## ✅ 재삽입 파이프라인 완성·실기 검증 (`scripts/build_gfx.py`)
- `lzss.compress()` **오버랩 정확 수정** → 전 블롭 왕복 OK, **원본과 동일 크기**(게임 인코더와 동급) 재현.
- **핵심**: 편집해도 **해제 길이 불변**(타일 수 동일) → 디컴프 호출자의 길이/포인터 **패치 불필요**. 재압축본을 **원래 $C7 슬롯에 in-place** 기록(재압축 ≤ 원본 압축 크기면 다음 블롭 침범 없음). 초과 시만 재배치 필요(드묾; 디컴프 = 범용 루틴 **`$C0:0D52`**, 파라미터는 레지스터/스택 전달).
- **검증**: vram_7000 반전 편집 → 재압축(2851/2851B) → in-place → 실기 크레딧 화면에 반영 확인(상단 3줄 변화). 역검증(ROM 재해제==편집본) 통과.
- **판명**: `vram_7000` = 크레딧 **상단 3줄**(©1998 Nintendo·JUPITER / こしたてつひろ·小学館·テレビ東京 / タミヤ). 하단 「ミニ四駆は…登録商標です」줄은 **다른 블롭**(미식별 — main_0000 등 확인 필요).

### 편집 워크플로 (확정)
1. `tmp/gfx/<name>.bin` = 해제된 원본 타일 → YY-CHR/Tile Molester로 편집(2bpp/4bpp).
2. 편집본을 `tmp/gfx_edit/<name>.bin` 에 저장(크기=해제크기 유지).
3. `python scripts/build_gfx.py --rom out/wgp2_kr.smc --out out/wgp2_kr.smc` → 재압축·in-place·역검증.
4. Mesen 확인.

## ✅ 크레딧 화면 = 스프라이트(OBJ) 렌더 — 완전 규명·한글화 완료 (2026-07-15)
⚠️ 이전 "크레딧 텍스트 = 2bpp BG" 및 "하단 상표줄 = 다른 블롭 미식별"은 **오식별·정정**.
라이브 VRAM 실측(Mesen `dump_credit_mid.lua`, 크레딧 중앙 프레임 450)으로 확정:
- **`ppu.mainScreenLayers=16`(bit4=OBJ만 표시)** → 크레딧 텍스트는 BG 아니라 **전부 스프라이트**. BG 타일맵(0x5000/0x5C00 등)은 무관 잔여값.
- **Mesen getState의 PPU VRAM 주소·DMA vmadd는 word 주소** → byte = ×2. (이 혼동이 그간 오독의 근본원인. vmadd $7000 → byte 0xE000.)
- 스프라이트 33개, **각 16×16 4bpp**(글자 하나가 아니라 텍스트 비트맵을 16×16 조각으로 슬라이스). OBJ chr base word 0x6000 = **byte 0xC000**. 팔레트 pal2(1·2줄·타미야줄)·pal0(하단줄), 공통 인덱스 1=흰(255)·3=진회(57)·0=투명.
- **글리프 소스 = `vram_7000` 블롭**(LZSS, $C7:3A3F, 해제 8192B=**256타일 4bpp**). 상단 대형 Nintendo 로고 + 크레딧 소형 글리프 아틀라스(하단 상표줄 「ミニ四駆は…登録商標」포함 — 다 여기 있음). 렌더 `tmp/gfx/vram_7000_4bpp.png`.
- **매핑: OAM 타일번호 T → 블롭 타일 인덱스 = T − 0x100**. 16×16 = 블롭 타일 {b, b+1, b+16, b+17}(아틀라스 16타일폭). OAM은 런타임 조립($7E:0563, DMA src $00:0563).

### 줄 구성 (frame 450 OAM)
| 줄 | Y | 스프라이트 | pal | 내용 |
|---|---|---|---|---|
| 1 | 39 | 10 | 2 | ©1998 Nintendo·JUPITER CORP. (**영어, 유지**) |
| 2 | 55 | 10 | 2 | ©こしたてつひろ·小学館·テレビ東京 → **한글** |
| 3 | 71 | 3 | 2 | ©タミヤ → **한글** |
| 하단 | 183 | 10 | 0 | ミニ四駆は…登録商標です → **한글** |
- 각 줄 첫 스프라이트(타일 0x15F=블롭 95)=공유 「©」 기호(한글화 시 유지).

### ✅ 한글화 워크플로 (`scripts/build_credit_kr.py`, 실기 검증)
1. **목표 이미지 `img_tile/screen.bmp`**(256×224, 사용자가 게임 정확 팔레트로 한글 크레딧 디자인: 검정0·흰255·진회57).
2. `build_credit_kr.py`: OAM 파싱 → **전 줄(Y=39/55/71/183)** 각 스프라이트 위치의 screen.bmp 16×16을 4bpp(0/1/3, 검정→투명 인덱스0)로 변환 → `vram_7000.bin` 해당 타일블록에 기록(© 타일 95만 유지). 산출 `tmp/gfx_edit/vram_7000.bin`(해제길이 불변) + 프리뷰 `tmp/gfx_edit/credit_preview.png`. `--dry`=ROM 미기록.
   - ⚠️ **1줄(영어)도 반드시 screen.bmp에서 베이킹**: 1줄 원본 유지 시 영어 글자 맨 아랫줄 픽셀(y=53,54)이 2줄 위에 **잉여 점**으로 남아 깨져 보임(사용자 발견). 전 줄을 screen.bmp로 베이킹하면 검정=투명으로 전체 정합.
3. `python scripts/build_gfx.py --rom out/wgp2_kr.smc --out out/wgp2_kr.smc` → LZSS 재압축(2844/2851B) in-place·역검증.
4. Mesen 확인(`shot_seq.lua` 크레딧 구간 연속캡처): **실기 화면 vs screen.bmp 인덱스 불일치 0/57344(0.000%) = 픽셀 단위 완전 일치**(잡점·누락 0).
- 도구: `dump_credit_mid.lua`(크레딧 프레임 전체덤프+getState 전체키), `find_credit_frame.lua`, 오프라인 스프라이트 렌더(`build_credit_kr.py` 내장).

## ✅ 범용 타일 그래픽 편집 도구 `scripts/gfx_io.py` (2026-07-15)
사용자 픽셀아트 편집(포토샵/OptFix ImageStudio) 왕복 파이프라인. 편집대상 타일을 (편집용 PNG + 팔레트 + 매니페스트)로 뽑아주고, 편집본 PNG를 받아 타일로 역변환해 해제 블롭에 재기록 → `build_gfx.py`로 재압축.

**교환 포맷** `work/<asset>/`:
- `edit.png` — RGBA, 게임 정확 색상, **투명=알파0**(팔레트 인덱스0). 포토샵 편집·투명 확인.
- `palette.act`(Adobe Color Table)·`palette.pal`(JASC)·`palette.png`(스와치) — 색상감소(4bpp=16색)용.
- `manifest.json` — 각 편집셀(x,y,w,h)→블롭 타일 인덱스. import가 이걸로 역삽입.

**두 모드** (사용자 워크플로):
- **모드 A(타깃 타일 편집) = `--mode grid`**: 편집할 타일을 겹침 없는 격자로 팩 → 각 타일 분리 편집. **왕복 무손실(라운드트립 0 bytes 검증)**. 스프라이트 겹침 영향 없음.
- **모드 B(풀 이미지) = `--mode screen` + 완성 이미지 제공**: 큰 이미지(타이틀 로고 등)는 사용자가 정사이즈 완성 PNG(또는 알파없는 검정배경 이미지, `black_transparent`로 검정→투명)를 주면 매니페스트대로 슬라이스·삽입. 크레딧 screen.bmp import = build_credit_kr 산출과 0 bytes 일치 검증.
  - ⚠️ **screen 모드 export 캔버스는 참조용**: 스프라이트가 화면에서 겹치면(예 크레딧 © X52가 다음 X60과 8px 겹침) 캔버스 컴포짓에서 겹침영역 정보 손실 → 그 캔버스를 편집·재import하면 겹친 타일 깨짐. 편집은 **모드A(grid)** 쓰거나 **모드B(완성 이미지 직접 제공)**로.

**사용:**
```
python scripts/gfx_io.py export credit --mode grid    # 타깃 편집용 격자 뽑기
# (work/credit/edit.png 편집)
python scripts/gfx_io.py import credit                # 편집본 → tmp/gfx_edit/<blob>.bin
python scripts/gfx_io.py import credit --png <완성이미지.png>   # 모드B: 풀이미지 직접
python scripts/build_gfx.py --rom out/wgp2_kr.smc --out out/wgp2_kr.smc
```
**에셋 레지스트리**(`ASSETS`): 블롭·bpp·팔레트·셀유도(`cells_from`)·keep_tiles·black_transparent. 현재 `credit`(OAM 스프라이트 셀). 신규 에셋은 셀유도 방식 추가(BG는 tilemap 기반 — BG 타일은 겹침없어 screen 모드 무손실).

## ✅ 타이틀 화면(PUSH START) — 코덱 RE 완료 (2026-07-15)
타이틀 = 겹친 BG 레이어(라이브 덤프 frame3428, bgMode1). 번역대상 2개(공통 **하늘색 74,107,255=투명**, 사용자 제공 `img_tile/`):
- **BG1(4bpp)** = 로고 「미니사구 렛츠&고 WGP2」+Nintendo아치. `credit_logo.png`(원본)/`credit_logo.bmp`(번역).
- **BG3(2bpp)** = PUSH START(영어유지)+하단 크레딧줄. `credit.png`/`credit.bmp`.
- BG2=구름·스프라이트96=TRF캐릭터: 번역 불필요.

### ✅ 타이틀 압축 코덱 = LZSS + **2바이트 길이 헤더**
- 래퍼 **`$C3:53C7`** = JSL 다음 인라인 3바이트(소스 롱포인터) 읽어 `JSL $C0:0D52`(LZSS) 호출. **`$C3:53EE`** = 인라인 8바이트로 DMA 실행.
- **소스에 2바이트 길이 헤더**: 스트림은 `addr+2` 시작, 길이=addr의 LE 워드. 해제 `lzss.decompress(rom, foff(bank,addr)+2, hdr)`.
- 로더 클러스터 `$C3:5A00~5EAF` 순차파싱(LDA#;STA$2116=VMADD / JSL$C353C7=LZSS / JSL$C353EE=DMA)으로 **각 DMA의 (VMADD, LZSS소스, size) 전량 확정**.

### ✅ 로고 소스 확정·검증
| 요소 | 소스 | 해제 | 원본압축 |
|---|---|---|---|
| **로고 chr** | `$C3:0E2F` | 12800B(400타일 4bpp) | 7047B(+2헤더) |
| **로고 타일맵** | `$C7:5BF8` | 2048B(32×32) | 1107B(+2헤더) |
- **검증**: $C3:0E2F chr + $C7:5BF8 타일맵 렌더 = `credit_logo.png` **diff 0/28757 완전일치**. 타일번호 1-384(전부<512, chr byte0), 팔레트 0,2,3,4,6,7(로고텍스트=6·7).
- **재압축 in-place OK**: 무편집 재압축 chr 7045≤7047·타일맵 1107≤1107B.
- 로더 전체 매핑: word$0000←$C3:0E2F(로고chr), $2000←$C7:4562, $4000←$C7:593D, $5000←$C7:5BF8(로고타일맵), $5800←$C7:604D, $6000←$C3:29B8(스프라이트).

### ⚠️ 마스킹 필요 (사용자 지적: 번역은 원본 타일배치와 1:1 아님)
번역이 원래 빈칸(타일0)에 새 잉크 추가/기존 잉크 제거 → 단순 타일 repaint 불가. 로고 진단: 263셀 변경, **25셀이 원래 타일0(빈칸)에 새 잉크**. → **이미지에서 chr+타일맵 통째 재빌드**(빈칸→타일0, 새잉크→새타일)로 마스킹 자동 해결.

### 🔲 남은 구현 (다음)
마스킹 인식 인코더: `credit_logo.bmp` 32×32 슬라이스→셀별 팔레트선택(최소오차)→타일 디듀프(+flip)→새 chr(≤400타일)+새 타일맵(2048B)→LZSS 재압축 in-place($C3:0E2F/$C7:5BF8 헤더유지, 초과시 재배치)→Mesen 검증. `scripts/build_title.py`=현재 diff/충돌 진단 단계(repaint 방식은 타일0 충돌로 미완, 재빌드로 전환 예정).

### RE 도구
`scripts/lua/`: `trace_title_dma`(타이틀 VRAM DMA), `trace_titlefill2`(벌크필러 PC), `trace_chrsrc2`(소스포인터, write콜백 우회), `trace_lzsrc750`(디컴프소스). ⚠️Mesen exec콜백 불안정($C0:0DC1 등 미발화)→write콜백/로더 정적파싱으로 우회. 로더 정적파싱이 가장 확실.

## 다음
1. **타이틀 로고 마스킹 인코더 구현**(위) → 실기 검증 → 커밋.
2. BG3 크레딧줄(`credit.bmp`) 동일 방식.
3. 크레딧 문구 미세조정: screen.bmp 수정 후 재빌드.
