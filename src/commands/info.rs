use anyhow::{Context, Result, bail};
use md5::{Digest, Md5};
use std::path::Path;

/// HiROM 내부 헤더 시작 오프셋 (헤더리스 기준)
const HIROM_HEADER: usize = 0xFFC0;

pub fn run(rom_path: &Path) -> Result<()> {
    let data = std::fs::read(rom_path)
        .with_context(|| format!("ROM 읽기 실패: {}", rom_path.display()))?;

    println!("파일:   {}", rom_path.display());
    println!("크기:   {} B ({} KB, {} Mbit)", data.len(), data.len() / 1024, data.len() * 8 / 1024 / 1024);
    println!("카피어 헤더: {}", if data.len() % 1024 == 512 { "있음 (512B)" } else { "없음 (헤더리스)" });

    // 해시
    let crc = crc32fast::hash(&data);
    let md5 = Md5::digest(&data);
    println!("CRC32:  {crc:08X}");
    print!("MD5:    ");
    for b in md5 { print!("{b:02x}"); }
    println!();

    // HiROM 내부 헤더
    if data.len() < HIROM_HEADER + 0x30 {
        bail!("ROM이 너무 작아 HiROM 헤더를 읽을 수 없음");
    }
    let title: String = data[HIROM_HEADER..HIROM_HEADER + 21]
        .iter()
        .map(|&b| if b.is_ascii_graphic() || b == b' ' { b as char } else { '.' })
        .collect();
    let mapper = data[HIROM_HEADER + 0x15];
    let romsize = data[HIROM_HEADER + 0x17];
    let sramsize = data[HIROM_HEADER + 0x18];
    let country = data[HIROM_HEADER + 0x19];
    let chk_comp = u16::from_le_bytes([data[HIROM_HEADER + 0x1C], data[HIROM_HEADER + 0x1D]]);
    let chk = u16::from_le_bytes([data[HIROM_HEADER + 0x1E], data[HIROM_HEADER + 0x1F]]);

    println!("--- 내부 헤더 @ 0x{HIROM_HEADER:04X} (HiROM) ---");
    println!("타이틀:  \"{}\"", title.trim_end());
    println!("매핑:    0x{mapper:02X} ({}{})",
        if mapper & 1 == 1 { "HiROM" } else { "LoROM" },
        if mapper & 0x10 != 0 { " + FastROM" } else { "" });
    println!("ROM크기: 0x{romsize:02X} ({} KB)", 1u32 << romsize);
    println!("SRAM:    0x{sramsize:02X} ({} KB)", if sramsize == 0 { 0 } else { 1u32 << sramsize });
    println!("국가:    0x{country:02X} ({})", if country == 0 { "일본/NTSC" } else { "기타" });
    let sum = chk.wrapping_add(chk_comp);
    println!("체크섬:  0x{chk:04X} + 보수 0x{chk_comp:04X} = 0x{sum:04X} ({})",
        if sum == 0xFFFF { "유효" } else { "무효" });

    Ok(())
}
