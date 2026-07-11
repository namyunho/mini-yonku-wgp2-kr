use anyhow::{Context, Result, bail};
use fontdue::{Font, FontSettings};
use std::collections::HashMap;
use std::path::Path;

/// 본문 폰트 시트 base (파일 오프셋). $CA:1137, HiROM.
const FONT_BASE: usize = 0x0A1137;
/// VWF 폭 테이블 base ($CA:9137). 글리프 인덱스 1바이트 색인.
const WIDTH_BASE: usize = 0x0A9137;
/// 글리프 인덱스 유효 상한 (1024 글리프: 0x000..0x3FF).
const MAX_GLYPH: usize = 0x400;
/// 사전 렌더 .bin 글리프당 바이트 (16×16 1bpp = 16행 × 2B).
const BIN_GLYPH_BYTES: usize = 32;

/// 글리프 인덱스 n → 폰트 시트 내 바이트 오프셋(상단블록 시작). render_font.py base03와 동일.
fn base03(n: usize) -> usize {
    16 * (((n & !7) * 2) + (n & 7))
}

/// 16×16 1bpp 비트맵(px[R][C] 0/1)을 폰트 시트에 인코딩해 기록.
/// render_font.py decode_glyph의 정확한 역: 상단8행=base 블록, 하단8행=base+0x80 블록.
/// 각 행 = 좌8px→(block+2r+1), 우8px→(block+2r), bit7=좌측 픽셀.
fn encode_glyph(rom: &mut [u8], n: usize, px: &[[u8; 16]; 16]) {
    let base = FONT_BASE + base03(n);
    for r_full in 0..16usize {
        let block = if r_full < 8 { base } else { base + 0x80 };
        let r = r_full & 7;
        let mut left = 0u8;
        let mut right = 0u8;
        for c in 0..8usize {
            if px[r_full][c] & 1 != 0 {
                left |= 1 << (7 - c);
            }
            if px[r_full][8 + c] & 1 != 0 {
                right |= 1 << (7 - c);
            }
        }
        rom[block + 2 * r + 1] = left;
        rom[block + 2 * r] = right;
    }
}

/// 사전 렌더 .bin의 글리프 인덱스 → 16×16 픽셀 배열.
/// 포맷(실측): 선형 행우선 16행×2B. byte[2r]=좌8px, byte[2r+1]=우8px, MSB=최좌측, 1bpp.
/// yshift: 세로 시프트(음수=위로). MaruMinya .bin은 잉크가 일률적으로 행2~12라
///         게임 원본 규약(상단 정렬, 잉크 행0~10)에 맞추려면 -2가 필요.
fn decode_bin_glyph(bin: &[u8], bin_idx: usize, yshift: i32) -> Result<[[u8; 16]; 16]> {
    let off = bin_idx * BIN_GLYPH_BYTES;
    if off + BIN_GLYPH_BYTES > bin.len() {
        bail!(".bin 글리프 인덱스 {bin_idx} 범위 초과");
    }
    let g = &bin[off..off + BIN_GLYPH_BYTES];
    let mut out = [[0u8; 16]; 16];
    for r in 0..16usize {
        let tr = r as i32 + yshift;
        if !(0..16).contains(&tr) {
            continue; // 시프트로 셀 밖으로 나간 행은 버림
        }
        let (left, right) = (g[2 * r], g[2 * r + 1]);
        for c in 0..8usize {
            out[tr as usize][c] = (left >> (7 - c)) & 1;
            out[tr as usize][8 + c] = (right >> (7 - c)) & 1;
        }
    }
    Ok(out)
}

/// 한 문자를 TTF로 래스터화해 16×16 1bpp (좌상단 정렬, 임계값 이진화).
fn rasterize_glyph(font: &Font, ch: char, px_size: f32, thr: u8, xoff: usize, yoff: usize) -> [[u8; 16]; 16] {
    let mut out = [[0u8; 16]; 16];
    let (m, bitmap) = font.rasterize(ch, px_size);
    for gy in 0..m.height {
        for gx in 0..m.width {
            if bitmap[gy * m.width + gx] >= thr {
                let (x, y) = (gx + xoff, gy + yoff);
                if x < 16 && y < 16 {
                    out[y][x] = 1;
                }
            }
        }
    }
    out
}

/// 매핑 문자열 "2ED=부,028=:6,03B=:0,..." 파싱 → Vec<(glyph_index, Option<char>, Option<width>)>
/// 항목 형식: "idx=char" | "idx=char:width" | "idx=:width"(빈 글리프=공백) | "idx=:0"(숨김)
fn parse_map(s: &str) -> Result<Vec<(usize, Option<char>, Option<u8>)>> {
    let mut v = Vec::new();
    for pair in s.split(',') {
        let pair = pair.trim();
        if pair.is_empty() {
            continue;
        }
        let (k, val) = pair.split_once('=').with_context(|| format!("잘못된 매핑 항목: {pair}"))?;
        let idx = usize::from_str_radix(k.trim(), 16).with_context(|| format!("잘못된 글리프 인덱스(hex): {k}"))?;
        if idx >= MAX_GLYPH {
            bail!("글리프 인덱스 0x{idx:03X} 범위 초과(>=0x{MAX_GLYPH:X})");
        }
        let (cpart, wpart) = match val.split_once(':') {
            Some((c, w)) => (c, Some(w)),
            None => (val, None),
        };
        let ch = cpart.chars().next(); // 비어 있으면 None → 공백 글리프
        let width = match wpart {
            Some(w) => Some(w.trim().parse::<u8>().with_context(|| format!("잘못된 폭: {pair}"))?),
            None => None,
        };
        v.push((idx, ch, width));
    }
    Ok(v)
}

/// glyphmap JSON {"가":0,...} → HashMap<char, usize>. 다중 코드포인트 키는 무시.
fn load_glyphmap(path: &Path) -> Result<HashMap<char, usize>> {
    let text = std::fs::read_to_string(path)
        .with_context(|| format!("glyphmap 읽기 실패: {}", path.display()))?;
    let raw: HashMap<String, usize> = serde_json::from_str(&text)
        .with_context(|| "glyphmap JSON 파싱 실패")?;
    let mut m = HashMap::new();
    for (k, idx) in raw {
        let mut it = k.chars();
        if let (Some(c), None) = (it.next(), it.next()) {
            m.insert(c, idx);
        }
    }
    Ok(m)
}

#[allow(clippy::too_many_arguments)]
pub fn run(
    rom_path: &Path,
    font_path: Option<&Path>,
    bin_path: Option<&Path>,
    glyphmap_path: Option<&Path>,
    out_path: &Path,
    map_str: &str,
    px_size: f32,
    thr: u8,
    width: Option<u8>,
    xoff: usize,
    yoff: usize,
    binyshift: i32,
) -> Result<()> {
    let mut rom = std::fs::read(rom_path)
        .with_context(|| format!("ROM 읽기 실패: {}", rom_path.display()))?;

    // TTF (선택)
    let font_bytes = font_path.map(std::fs::read).transpose()?;
    let font = match &font_bytes {
        Some(b) => Some(
            Font::from_bytes(b.as_slice(), FontSettings::default())
                .map_err(|e| anyhow::anyhow!("fontdue 폰트 로드 실패: {e}"))?,
        ),
        None => None,
    };

    // 사전 렌더 .bin + glyphmap (선택, 쌍으로만 유효)
    let bin = bin_path.map(std::fs::read).transpose()?;
    let glyphmap = glyphmap_path.map(load_glyphmap).transpose()?;
    if bin.is_some() != glyphmap.is_some() {
        bail!("--bin 과 --glyphmap 은 함께 지정해야 합니다");
    }
    if font.is_none() && bin.is_none() {
        bail!("글리프 소스가 없습니다: --font 또는 --bin/--glyphmap 중 하나는 필요");
    }

    let map = parse_map(map_str)?;
    if map.is_empty() {
        bail!("매핑이 비었습니다 (--map)");
    }

    for &(idx, ch, entry_w) in &map {
        let (px, src) = build_glyph(ch, &bin, &glyphmap, &font, px_size, thr, xoff, yoff, binyshift)?;
        encode_glyph(&mut rom, idx, &px);
        // 폭: 항목별 지정 > 전역 --width > 원본 유지
        let w = entry_w.or(width);
        if let Some(w) = w {
            rom[WIDTH_BASE + idx] = w;
        }
        let ink: usize = px.iter().flatten().map(|&b| b as usize).sum();
        let chdisp = ch.map(|c| c.to_string()).unwrap_or_else(|| "공백".into());
        let wdisp = w.map(|w| format!(", width {w}")).unwrap_or_default();
        println!("  glyph 0x{idx:03X} <- '{chdisp}' [{src}] (ink {ink}px{wdisp})");
    }

    std::fs::write(out_path, &rom)
        .with_context(|| format!("출력 ROM 쓰기 실패: {}", out_path.display()))?;
    println!("wrote {} ({} glyphs injected @ font $CA:1137)", out_path.display(), map.len());
    Ok(())
}

/// 문자 하나의 16×16 비트맵을 만든다. 우선순위: 공백(None) → .bin(glyphmap 조회) → TTF.
#[allow(clippy::too_many_arguments)]
fn build_glyph(
    ch: Option<char>,
    bin: &Option<Vec<u8>>,
    glyphmap: &Option<HashMap<char, usize>>,
    font: &Option<Font>,
    px_size: f32,
    thr: u8,
    xoff: usize,
    yoff: usize,
    binyshift: i32,
) -> Result<([[u8; 16]; 16], &'static str)> {
    let ch = match ch {
        None => return Ok(([[0u8; 16]; 16], "blank")),
        Some(c) => c,
    };
    // .bin 우선
    if let (Some(bin), Some(gm)) = (bin, glyphmap) {
        if let Some(&bin_idx) = gm.get(&ch) {
            return Ok((decode_bin_glyph(bin, bin_idx, binyshift)?, "bin"));
        }
    }
    // TTF 폴백
    if let Some(font) = font {
        return Ok((rasterize_glyph(font, ch, px_size, thr, xoff, yoff), "ttf"));
    }
    bail!("'{ch}' 글리프를 만들 소스가 없음(.bin glyphmap에 없고 --font도 없음)");
}
