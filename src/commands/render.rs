use anyhow::{Context, Result, bail};
use std::path::Path;

/// 8×8 타일 하나를 디코드해 픽셀값(0..maxval)을 콜백으로 흘려보낸다.
fn decode_tile(data: &[u8], tbase: usize, bpp: u8, mut put: impl FnMut(usize, usize, u16)) {
    for row in 0..8 {
        let mut planes = [0u8; 4];
        for p in 0..bpp as usize {
            let byte_index = if bpp == 4 {
                if p < 2 { row * 2 + p } else { 16 + row * 2 + (p - 2) }
            } else {
                row * (bpp as usize) + p
            };
            planes[p] = data[tbase + byte_index];
        }
        for col in 0..8 {
            let bit = 7 - col;
            let mut v = 0u16;
            for p in 0..bpp as usize {
                v |= (((planes[p] >> bit) & 1) as u16) << p;
            }
            put(col, row, v);
        }
    }
}

/// 16×16 글리프 모드: 각 글리프 = 4개 8×8 타일(TL,TR,BL,BR 선형). glyph를 grid 배열.
pub fn run_glyph16(
    rom_path: &Path,
    offset: usize,
    glyphs: usize,
    bpp: u8,
    cols: usize,
    scale: usize,
    out: &Path,
) -> Result<()> {
    let data = std::fs::read(rom_path)
        .with_context(|| format!("ROM 읽기 실패: {}", rom_path.display()))?;
    let bpt = match bpp { 1 => 8, 2 => 16, 4 => 32, _ => bail!("bpp 1/2/4") };
    let glyph_bytes = bpt * 4;
    if offset + glyphs * glyph_bytes > data.len() {
        bail!("범위 초과");
    }
    let maxval = (1u16 << bpp) - 1;
    let rows = glyphs.div_ceil(cols);
    // 글리프 사이 1px 간격
    let cell = 17;
    let px_w = cols * cell + 1;
    let px_h = rows * cell + 1;
    let mut img = vec![64u8; px_w * px_h]; // 회색 배경(간격선 구분)
    for g in 0..glyphs {
        let gx = (g % cols) * cell + 1;
        let gy = (g / cols) * cell + 1;
        // TL,TR,BL,BR
        let sub = [(0usize, 0usize), (8, 0), (0, 8), (8, 8)];
        for (ti, (ox, oy)) in sub.iter().enumerate() {
            let tbase = offset + g * glyph_bytes + ti * bpt;
            decode_tile(&data, tbase, bpp, |c, r, v| {
                let gray = (v * 255 / maxval) as u8;
                let x = gx + ox + c;
                let y = gy + oy + r;
                img[y * px_w + x] = gray;
            });
        }
    }
    write_png(&img, px_w, px_h, scale, out)?;
    println!("wrote {} (glyph16, {} glyphs @ {}bpp, offset 0x{:06X})", out.display(), glyphs, bpp, offset);
    Ok(())
}

fn write_png(img: &[u8], w: usize, h: usize, scale: usize, out: &Path) -> Result<()> {
    let (ow, oh) = (w * scale, h * scale);
    let mut scaled = vec![0u8; ow * oh];
    for y in 0..oh {
        for x in 0..ow {
            scaled[y * ow + x] = img[(y / scale) * w + (x / scale)];
        }
    }
    let file = std::fs::File::create(out)?;
    let bw = std::io::BufWriter::new(file);
    let mut enc = png::Encoder::new(bw, ow as u32, oh as u32);
    enc.set_color(png::ColorType::Grayscale);
    enc.set_depth(png::BitDepth::Eight);
    enc.write_header()?.write_image_data(&scaled)?;
    Ok(())
}

/// SNES 타일(planar) → 그레이스케일 PNG.
/// bpp: 1 / 2 / 4. 8×8 타일을 `cols`개씩 가로로 배열.
pub fn run(
    rom_path: &Path,
    offset: usize,
    tiles: usize,
    bpp: u8,
    cols: usize,
    scale: usize,
    out: &Path,
) -> Result<()> {
    let data = std::fs::read(rom_path)
        .with_context(|| format!("ROM 읽기 실패: {}", rom_path.display()))?;
    let bytes_per_tile = match bpp {
        1 => 8,
        2 => 16,
        4 => 32,
        _ => bail!("bpp는 1/2/4만 지원"),
    };
    if offset + tiles * bytes_per_tile > data.len() {
        bail!("범위가 ROM 끝을 초과: offset=0x{offset:06X} tiles={tiles}");
    }
    let rows = tiles.div_ceil(cols);
    let px_w = cols * 8;
    let px_h = rows * 8;
    let mut img = vec![0u8; px_w * px_h]; // grayscale

    let maxval = (1u16 << bpp) - 1;
    for t in 0..tiles {
        let tbase = offset + t * bytes_per_tile;
        let tx = (t % cols) * 8;
        let ty = (t / cols) * 8;
        for row in 0..8 {
            // 각 플레인 비트를 모아 픽셀값 구성
            let mut planes = [0u8; 4];
            for p in 0..bpp as usize {
                // SNES: bp0/bp1 인터리브(행당 2바이트), 4bpp는 bp0/bp1 16B 뒤 bp2/bp3 16B
                let byte_index = if bpp == 4 {
                    if p < 2 { row * 2 + p } else { 16 + row * 2 + (p - 2) }
                } else {
                    row * (bpp as usize) + p
                };
                planes[p] = data[tbase + byte_index];
            }
            for col in 0..8 {
                let bit = 7 - col;
                let mut v = 0u16;
                for p in 0..bpp as usize {
                    v |= (((planes[p] >> bit) & 1) as u16) << p;
                }
                // 픽셀값 → 그레이(0=검정 배경, 큰 값=밝게)
                let gray = (v * 255 / maxval) as u8;
                let x = tx + col;
                let y = ty + row;
                img[y * px_w + x] = gray;
            }
        }
    }

    // scale
    let (ow, oh) = (px_w * scale, px_h * scale);
    let mut scaled = vec![0u8; ow * oh];
    for y in 0..oh {
        for x in 0..ow {
            scaled[y * ow + x] = img[(y / scale) * px_w + (x / scale)];
        }
    }

    let file = std::fs::File::create(out)?;
    let w = std::io::BufWriter::new(file);
    let mut enc = png::Encoder::new(w, ow as u32, oh as u32);
    enc.set_color(png::ColorType::Grayscale);
    enc.set_depth(png::BitDepth::Eight);
    enc.write_header()?.write_image_data(&scaled)?;
    println!(
        "wrote {} ({}×{}px, {} tiles @ {}bpp, offset 0x{:06X})",
        out.display(), ow, oh, tiles, bpp, offset
    );
    Ok(())
}
