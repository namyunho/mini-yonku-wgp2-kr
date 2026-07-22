#!/usr/bin/env python3
"""원본 Mesen 덤프의 Mode 1 BG 레이어를 독립 복원한다.

기존 메뉴 분석 주소·글꼴표를 사용하지 않고 PPU 상태와 VRAM만 입력으로 삼는다.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


def read_state(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k] = v
    return out


def tile_pixels(vram: bytes, word_addr: int, bpp: int) -> list[list[int]]:
    size = 16 if bpp == 2 else 32
    data = vram[word_addr * 2 : word_addr * 2 + size]
    if len(data) != size:
        return [[0] * 8 for _ in range(8)]
    px = [[0] * 8 for _ in range(8)]
    for y in range(8):
        for plane in range(bpp):
            group = plane // 2
            byte = data[group * 16 + y * 2 + (plane & 1)]
            for x in range(8):
                px[y][x] |= ((byte >> (7 - x)) & 1) << plane
    return px


def tilemap_entry(vram: bytes, base_word: int, x: int, y: int, wide: bool, tall: bool) -> int:
    screen_x, local_x = divmod(x, 32)
    screen_y, local_y = divmod(y, 32)
    screens_w = 2 if wide else 1
    if screen_x >= screens_w or screen_y >= (2 if tall else 1):
        return 0
    screen = screen_y * screens_w + screen_x
    word = base_word + screen * 0x400 + local_y * 32 + local_x
    off = word * 2
    return int.from_bytes(vram[off : off + 2], "little")


def render_layer(vram: bytes, state: dict[str, str], layer: int, out_dir: Path) -> None:
    prefix = f"ppu.layers[{layer}]"
    tm = int(state[f"{prefix}.tilemapAddress"])
    chr_base = int(state[f"{prefix}.chrAddress"])
    wide = state[f"{prefix}.doubleWidth"] == "true"
    tall = state[f"{prefix}.doubleHeight"] == "true"
    width, height = (64 if wide else 32), (64 if tall else 32)
    bpp = 2 if layer == 2 else 4
    max_color = (1 << bpp) - 1

    img = Image.new("L", (width * 8, height * 8))
    grid: list[str] = []
    for ty in range(height):
        row: list[str] = []
        for tx in range(width):
            entry = tilemap_entry(vram, tm, tx, ty, wide, tall)
            tile = entry & 0x03FF
            hflip = bool(entry & 0x4000)
            vflip = bool(entry & 0x8000)
            row.append(f"{entry:04X}")
            px = tile_pixels(vram, chr_base + tile * (bpp * 4), bpp)
            for y in range(8):
                sy = 7 - y if vflip else y
                for x in range(8):
                    sx = 7 - x if hflip else x
                    value = px[sy][sx]
                    img.putpixel((tx * 8 + x, ty * 8 + y), 255 * value // max_color)
        grid.append("\t".join(row))

    img.save(out_dir / f"bg{layer + 1}_full.png")
    (out_dir / f"bg{layer + 1}_map.tsv").write_text("\n".join(grid) + "\n", encoding="utf-8")

    hscroll = int(state[f"{prefix}.hscroll"]) % (width * 8)
    vscroll = int(state[f"{prefix}.vscroll"]) % (height * 8)
    tiled = Image.new("L", (width * 16, height * 16))
    for yy in range(2):
        for xx in range(2):
            tiled.paste(img, (xx * img.width, yy * img.height))
    tiled.crop((hscroll, vscroll, hscroll + 256, vscroll + 224)).save(
        out_dir / f"bg{layer + 1}_visible.png"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("state", type=Path)
    ap.add_argument("vram", type=Path)
    ap.add_argument("out", type=Path)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    state = read_state(args.state)
    vram = args.vram.read_bytes()
    if len(vram) != 0x10000:
        raise SystemExit(f"VRAM 크기 불일치: {len(vram)}")
    if int(state.get("ppu.bgMode", "-1")) != 1:
        raise SystemExit(f"Mode 1 아님: {state.get('ppu.bgMode')}")
    for layer in range(3):
        render_layer(vram, state, layer, args.out)


if __name__ == "__main__":
    main()
