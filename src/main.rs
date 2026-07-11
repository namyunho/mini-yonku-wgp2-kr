use clap::{Parser, Subcommand};

mod commands;

/// Mini Yonku Let's & Go!! Power WGP2 (SNES) 한글 패치 파이프라인 도구
#[derive(Parser)]
#[command(name = "kr-patch-wgp2", version, about)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// ROM 메타데이터·해시·내부 헤더 출력
    Info {
        /// 원본 ROM 경로 (헤더리스)
        #[arg(long)]
        rom: std::path::PathBuf,
    },
    /// ROM 영역을 SNES 타일로 렌더링해 PNG 저장 (폰트/그래픽 조사용)
    RenderTiles {
        #[arg(long)]
        rom: std::path::PathBuf,
        /// 파일 오프셋 (예: 0x1B0000)
        #[arg(long, value_parser=parse_hex)]
        offset: usize,
        /// 렌더할 8×8 타일 수
        #[arg(long, default_value_t = 256)]
        tiles: usize,
        /// 비트뎁스 1/2/4
        #[arg(long, default_value_t = 2)]
        bpp: u8,
        /// 가로 타일 수
        #[arg(long, default_value_t = 16)]
        cols: usize,
        /// 확대 배율
        #[arg(long, default_value_t = 4)]
        scale: usize,
        /// 16×16 글리프 모드 (tiles=글리프 수, 각 글리프=4타일 TL/TR/BL/BR)
        #[arg(long, default_value_t = false)]
        glyph16: bool,
        #[arg(long)]
        output: std::path::PathBuf,
    },
    /// PoC: TTF에서 한글 글리프를 래스터화해 본문 폰트 시트($CA:1137)에 주입한 패치 ROM 생성
    PocFont {
        /// 원본 ROM (헤더리스)
        #[arg(long)]
        rom: std::path::PathBuf,
        /// 한글 TTF 경로 (예: C:\Windows\Fonts\malgun.ttf). --bin과 함께면 glyphmap에 없는 글자 폴백
        #[arg(long)]
        font: Option<std::path::PathBuf>,
        /// 사전 렌더 글리프 .bin (16×16 1bpp 32B/글리프). --glyphmap과 쌍으로
        #[arg(long)]
        bin: Option<std::path::PathBuf>,
        /// 문자→인덱스 glyphmap JSON (.bin 색인). --bin과 쌍으로
        #[arg(long)]
        glyphmap: Option<std::path::PathBuf>,
        /// 출력 패치 ROM 경로
        #[arg(long)]
        output: std::path::PathBuf,
        /// 매핑 "글리프인덱스(hex)=문자,..." 예: "2ED=안,15C=녕"
        #[arg(long)]
        map: String,
        /// 래스터 px 크기
        #[arg(long, default_value_t = 14.0)]
        px: f32,
        /// 이진화 임계값(coverage>=thr → 잉크)
        #[arg(long, default_value_t = 100)]
        thr: u8,
        /// VWF 폭 테이블 갱신값(생략 시 원본 유지)
        #[arg(long)]
        width: Option<u8>,
        /// 셀 내 좌측 여백(px)
        #[arg(long, default_value_t = 1)]
        xoff: usize,
        /// 셀 내 상단 여백(px)
        #[arg(long, default_value_t = 1)]
        yoff: usize,
        /// .bin 글리프 세로 시프트(음수=위로). MaruMinya .bin은 -2 필요(잉크 행2~12→0~10)
        #[arg(long, default_value_t = 0, allow_hyphen_values = true)]
        binyshift: i32,
    },
}

fn parse_hex(s: &str) -> Result<usize, String> {
    let s = s.trim();
    let r = if let Some(h) = s.strip_prefix("0x").or_else(|| s.strip_prefix("0X")) {
        usize::from_str_radix(h, 16)
    } else {
        s.parse::<usize>()
    };
    r.map_err(|e| format!("잘못된 오프셋 '{s}': {e}"))
}

fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();
    match cli.command {
        Command::Info { rom } => commands::info::run(&rom),
        Command::RenderTiles { rom, offset, tiles, bpp, cols, scale, glyph16, output } => {
            if glyph16 {
                commands::render::run_glyph16(&rom, offset, tiles, bpp, cols, scale, &output)
            } else {
                commands::render::run(&rom, offset, tiles, bpp, cols, scale, &output)
            }
        }
        Command::PocFont { rom, font, bin, glyphmap, output, map, px, thr, width, xoff, yoff, binyshift } => {
            commands::poc_font::run(
                &rom, font.as_deref(), bin.as_deref(), glyphmap.as_deref(),
                &output, &map, px, thr, width, xoff, yoff, binyshift,
            )
        }
    }
}
