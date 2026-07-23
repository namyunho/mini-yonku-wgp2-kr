#!/usr/bin/env python3
"""System ④ direct-tile label extractor/encoder.

SSOT: docs/worklogs/codex-brief-menu4.md and docs/18-menu-tile-font-labels.md.

The tutorial table at $C7:B180 is a sequence of length-prefixed tile
payloads mixed with page/control data.  The X-menu strings at $C3:9201 and
$C3:95BE are programs consumed directly by $C0:1B4B; dakuten/handakuten are
inline ``00 94``/``00 95`` escapes there.  This tool asserts every original
span against the ROM, appends only the newly required Hangul syllables to the
stable build_sjis.py pool, classifies byte fit without truncation, and writes
assets/translations/menu4_labels.json.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROM = ROOT / "roms" / "re_codex.smc"
DEFAULT_OUT = ROOT / "assets" / "translations" / "menu4_labels.json"
TBL = 0x01D1C3
MARKER = 0xFE
VRAM_CAP = 224
SLOT1 = 189


# Translation order is locked to docs/worklogs/codex-brief-menu4.md.
C7_SPECS = [
    ("toc_title", "もくじ", "목차"),
    ("toc_p2", "マップ モード", "맵 모드"),
    ("toc_p3", "セッティング モード", "세팅 모드"),
    ("toc_p4", "パラメータについて", "파라미터"),
    ("toc_p5", "グリッドへんこう モード", "그리드변경 모드"),
    ("toc_p6", "レース モード", "레이스 모드"),
    ("toc_p7", "WGPエントリー モード", "WGP출전 모드"),
    ("map_button", "アクション", "액션"),
    ("map_button", "いどう", "이동"),
    ("map_button", "マニュアル", "매뉴얼"),
    ("map_button", "ウィンドウ", "윈도우"),
    ("map_button", "ダッシュ", "대시"),
    ("map_button", "セッティング", "세팅"),
    ("setting_button", "マシンきりかえ", "머신전환"),
    ("setting_button", "パーツせんたく", "파츠선택"),
    ("setting_button", "けってい", "결정"),
    ("setting_button", "キャンセル", "취소"),
    ("parameter", "スピードせいのう", "스피드성능"),
    ("parameter", "コーナリングせいのう", "코너링성능"),
    ("parameter", "パワーせいのう", "파워성능"),
    ("parameter", "ダウンフォースせいのう", "다운포스성능"),
    ("parameter", "おもさ", "무게"),
    ("parameter", "たいきゅうりょく", "내구력"),
    ("parameter", "ばくそうポイント", "폭주포인트"),
    ("grid_button", "マシンせんたく", "머신선택"),
    ("grid_button", "しゅうりょう", "종료"),
    ("race_button", "チェンジ", "체인지"),
    ("race_button", "ステアリング", "스티어링"),
    ("race_button", "ポーズ", "포즈"),
    ("race_button", "トップチェンジ", "톱체인지"),
    ("race_button", "BPかいふく", "BP회복"),
    ("race_button", "ばくそう", "폭주"),
    ("race_button", "レースアイテム", "레이스아이템"),
    ("wgp_entry", "せんたく", "선택"),
]

# Exact direct-render label spans.  Row controls following each span are not
# part of the patch span.  Inline overlay escapes inside a span are immutable
# for an inplace result.
XMENU_SPECS = [
    ("xmenu", 0x0395BE, "セッティング", "세팅"),
    ("xmenu", 0x0395CA, "グリッドへんこう", "그리드변경"),
    ("xmenu", 0x0395DA, "アイテム", "아이템"),
    ("xmenu", 0x039201, "マップ", "지도"),
    ("xmenu", 0x039208, "そうさマニュアル", "조작방법"),
    ("xmenu", 0x039212, "ようごしゅう", "용어집"),
]


def r16(rom: bytes, off: int) -> int:
    return rom[off] | (rom[off + 1] << 8)


def tile_value(rom: bytes, ch: str) -> int:
    # Direct font has fullwidth Latin/number tiles.  The brief writes WGP/BP
    # in ASCII, so map them to their visually identical fullwidth source tile.
    if ch == " ":
        return 0
    if ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
        ch = chr(ord("Ａ") + ord(ch) - ord("A")) if ch.isalpha() else chr(ord("０") + ord(ch) - ord("0"))
    sj = ch.encode("cp932")
    if len(sj) != 2:
        raise ValueError(f"direct-tile character is not 2-byte cp932: {ch!r}")
    hi, lo = sj
    row = r16(rom, TBL + (hi & 0x7F) * 2)
    return r16(rom, TBL + row + (lo - 0x40) * 2)


def body_bytes(rom: bytes, text: str) -> bytes:
    return bytes(tile_value(rom, ch) & 0xFF for ch in text)


def direct_bytes(rom: bytes, text: str) -> bytes:
    out = bytearray()
    for ch in text:
        value = tile_value(rom, ch)
        overlay, body = value >> 8, value & 0xFF
        if overlay:
            out += bytes((0, overlay))
        out.append(body)
    return bytes(out)


def existing_syllables() -> list[str]:
    # Mirror build_sjis.py's stable collection order without importing/running
    # the build module or touching an output ROM.
    menus = [
        ["처음부터", "이어하기", "복사", "삭제"],
        ["저장", "뒤로", "복사", "삭제"],
    ]
    corpus = json.loads((ROOT / "assets/translations/sjis_ui.json").read_text(encoding="utf-8"))
    syllables: list[str] = []

    def add(text: str) -> None:
        for ch in text:
            if "가" <= ch <= "힣" and ch not in syllables:
                syllables.append(ch)

    for row in menus:
        for text in row:
            add(text)
    for items in corpus.values():
        if isinstance(items, list):
            for item in items:
                add(item["kr"])
    return syllables


def all_translation_rows() -> list[tuple[str, str]]:
    rows = [(jp, kr) for _, jp, kr in C7_SPECS]
    rows += [(jp, kr) for _, _, jp, kr in XMENU_SPECS]
    return rows


def marker_tokens(rom: bytes, text: str, kmap: dict[str, int]) -> list[bytes]:
    tokens = []
    for ch in text:
        if "가" <= ch <= "힣":
            tokens.append(bytes((MARKER, kmap[ch])))
        else:
            tokens.append(bytes((tile_value(rom, ch) & 0xFF,)))
    return tokens


def marker_bytes(rom: bytes, text: str, kmap: dict[str, int]) -> bytes:
    return b"".join(marker_tokens(rom, text, kmap))


def pc_to_snes(pc: int) -> str:
    return f"${0xC0 + (pc >> 16):02X}:{pc & 0xFFFF:04X}"


def containing_len_record(rom: bytes, pos: int, n: int) -> tuple[int, int] | None:
    """Find the nearest C7 length-prefixed payload containing [pos,pos+n)."""
    for start in range(pos - 1, max(0x07B17F, pos - 0x21), -1):
        size = rom[start]
        if 1 <= size <= 0x20 and start + 1 <= pos and pos + n <= start + 1 + size:
            return start, size
    return None


def find_c7_occurrences(rom: bytes, section: str, jp: str) -> list[tuple[int, tuple[int, int]]]:
    needle = body_bytes(rom, jp)
    found = []
    start, end = 0x07B180, 0x07B461
    pos = start
    while True:
        pos = rom.find(needle, pos, end)
        if pos < 0:
            break
        rec = containing_len_record(rom, pos, len(needle))
        # Most labels occupy the complete payload.  Parameter rows retain a
        # two-letter stat tile plus one blank byte (SP/CN/PW/DF/WT/DP/BP), so
        # their translated description begins three bytes into the payload.
        # Reject ordinary substring hits such as チェンジ inside
        # トップチェンジ and せんたく inside マシンせんたく.
        if rec is not None:
            record_start, record_size = rec
            exact_payload = pos == record_start + 1 and len(needle) == record_size
            parameter_suffix = (
                section == "parameter"
                and pos == record_start + 4
                and len(needle) + 3 == record_size
            )
            if not (exact_payload or parameter_suffix):
                pos += 1
                continue
            found.append((pos, rec))
        pos += 1
    return found


def immutable_overlay_pairs(orig: bytes) -> list[tuple[int, int]]:
    pairs = []
    i = 0
    while i + 1 < len(orig):
        if orig[i] == 0 and orig[i + 1] >= 3:
            pairs.append((i, orig[i + 1]))
            i += 2
        else:
            i += 1
    return pairs


def structured_direct_reencode(orig: bytes, tokens: list[bytes]) -> bytes | None:
    """Place whole marker tokens in body runs, preserving overlay pairs exactly."""
    fixed = {i: bytes((0, value)) for i, value in immutable_overlay_pairs(orig)}
    runs: list[tuple[int, int]] = []
    i = 0
    while i < len(orig):
        if i in fixed:
            i += 2
            continue
        start = i
        while i < len(orig) and i not in fixed:
            i += 1
        runs.append((start, i))

    out = bytearray(orig)
    token_i = 0
    for start, end in runs:
        p = start
        while token_i < len(tokens) and p + len(tokens[token_i]) <= end:
            tok = tokens[token_i]
            out[p:p + len(tok)] = tok
            p += len(tok)
            token_i += 1
        out[p:end] = bytes((0xFF,)) * (end - p)
    if token_i != len(tokens):
        return None
    for i, value in fixed.items():
        assert out[i:i + 2] == value
    return bytes(out)


def decode_marker_payload(data: bytes, syllables: list[str], direct: bool) -> str:
    out = []
    i = 0
    while i < len(data):
        b = data[i]
        if b == MARKER:
            if i + 1 >= len(data):
                raise AssertionError("dangling FE marker")
            out.append(syllables[data[i + 1]])
            i += 2
        elif direct and b == 0 and i + 1 < len(data) and data[i + 1] >= 3:
            i += 2  # immutable dakuten/handakuten escape
        elif b == 0xFF:
            i += 1  # padding
        elif b == 0:
            out.append(" ")
            i += 1
        else:
            # Only WGP/BP are retained non-Hangul in this batch.
            out.append(f"<{b:02X}>")
            i += 1
    return "".join(out)


def decode_for_expected(data: bytes, expected: str, syllables: list[str], rom: bytes, direct: bool) -> str:
    # Replace retained direct Latin tiles with their locked text spelling.
    decoded = decode_marker_payload(data, syllables, direct)
    for ch in "WGPB":
        tile = tile_value(rom, ch) & 0xFF
        decoded = decoded.replace(f"<{tile:02X}>", ch)
    return decoded.rstrip(" ")


def build(rom_path: Path, out_path: Path) -> dict:
    rom = rom_path.read_bytes()
    if len(rom) != 0x200000:
        raise SystemExit(f"expected headerless 2 MiB ROM, got {len(rom)} bytes")

    old_syllables = existing_syllables()
    assert len(old_syllables) == 200, f"SJIS pool drifted: {len(old_syllables)} != 200"
    additions: list[str] = []
    for _, kr in all_translation_rows():
        for ch in kr:
            if "가" <= ch <= "힣" and ch not in old_syllables and ch not in additions:
                additions.append(ch)
    syllables = old_syllables + additions
    assert len(syllables) <= VRAM_CAP
    kmap = {ch: i for i, ch in enumerate(syllables)}

    glyph_map = json.loads((ROOT / "assets/fonts/small/font-007242d37349daf3_glyph_map.json").read_text(encoding="utf-8"))
    needed_hangul = {ch for _, kr in all_translation_rows() for ch in kr if "가" <= ch <= "힣"}
    missing_glyphs = sorted(needed_hangul - glyph_map.keys())
    assert not missing_glyphs, f"8pt font coverage missing: {missing_glyphs}"

    labels = []
    covered_rows: set[tuple[str, str]] = set()

    # C7 length-prefixed payloads.  Duplicate labels intentionally produce
    # one output row per ROM occurrence.
    for section, jp, kr in C7_SPECS:
        occurrences = find_c7_occurrences(rom, section, jp)
        assert occurrences, f"C7 label not found: {jp}"
        covered_rows.add((jp, kr))
        orig = body_bytes(rom, jp)
        encoded = marker_bytes(rom, kr, kmap)
        for pos, (record_start, record_size) in occurrences:
            assert rom[pos:pos + len(orig)] == orig
            if len(encoded) <= len(orig):
                mode = "inplace"
                new = encoded + bytes((0xFF,)) * (len(orig) - len(encoded))
                note = (
                    f"C7 length record {pc_to_snes(record_start)} size={record_size}; "
                    "main-tile subspan only; length/opcodes/coordinates/overlay records unchanged"
                )
            else:
                mode = "overflow"
                new = encoded
                note = (
                    f"marker {len(encoded)}B > main span {len(orig)}B by {len(encoded)-len(orig)}B; "
                    "no truncation; C38B descriptor exposes only base high byte, so per-label +0x0220 base swap is unavailable"
                )
            labels.append({
                "table": f"c7_tutorial:{section}",
                "addr": pc_to_snes(pos),
                "jp": jp,
                "kr": kr,
                "orig_span_hex": orig.hex().upper(),
                "new_bytes_hex": new.hex().upper(),
                "mode": mode,
                "note": note,
            })

    # X-menu direct-render programs discovered through the C38B dynamic path
    # and the fixed C395A4 caller.  Preserve inline overlay escapes for an
    # inplace classification; otherwise emit the canonical untruncated marker
    # stream and flag the required integration strategy.
    for table, pos, jp, kr in XMENU_SPECS:
        orig = direct_bytes(rom, jp)
        assert rom[pos:pos + len(orig)] == orig, (
            f"direct span mismatch {pc_to_snes(pos)} {jp}: "
            f"{rom[pos:pos+len(orig)].hex()} != {orig.hex()}"
        )
        covered_rows.add((jp, kr))
        tokens = marker_tokens(rom, kr, kmap)
        canonical = b"".join(tokens)
        structured = structured_direct_reencode(orig, tokens)
        if structured is not None:
            mode = "inplace"
            new = structured
            overlays = immutable_overlay_pairs(orig)
            note = (
                f"direct-render span; preserved {len(overlays)} inline overlay escape(s) at exact offsets; "
                "row terminator/control bytes immediately after span unchanged"
            )
        elif jp == "アイテム":
            # This pure-Hangul label is in the fixed $C3:95BE program rendered
            # by $C3:95A4 with immediate base #$2100.  It is the sole useful
            # base-swap candidate, but the entire multiline program and blank
            # handling must be switched coherently by the integration owner.
            mode = "baseswap"
            raw_idx = bytes(kmap[ch] for ch in kr)
            new = raw_idx + bytes((0xFF,)) * (len(orig) - len(raw_idx))
            note = (
                "marker 6B > 4B; fixed caller $C3:95A4 can change base $2100->$2320 only for the entire "
                "$C3:95BE program; requires group re-encode and FF blank special-case"
            )
        else:
            mode = "overflow"
            new = canonical
            body_slots = len(orig) - 2 * len(immutable_overlay_pairs(orig))
            note = (
                f"canonical marker {len(canonical)}B cannot fit immutable direct-render runs "
                f"({body_slots} body bytes split by overlay escapes); no truncation"
            )
        labels.append({
            "table": table,
            "addr": pc_to_snes(pos),
            "jp": jp,
            "kr": kr,
            "orig_span_hex": orig.hex().upper(),
            "new_bytes_hex": new.hex().upper(),
            "mode": mode,
            "note": note,
        })

    # Gate 1: every emitted representation decodes to the locked translation.
    # Overflow rows carry the canonical marker stream; baseswap carries direct
    # one-byte pool indices; inplace rows carry padded/structured bytes.
    for item in labels:
        data = bytes.fromhex(item["new_bytes_hex"])
        if item["mode"] == "baseswap":
            decoded = "".join(syllables[b] for b in data if b != 0xFF)
        else:
            decoded = decode_for_expected(data, item["kr"], syllables, rom, item["table"] == "xmenu")
        assert decoded == item["kr"], f"decode mismatch {item['addr']}: {decoded!r} != {item['kr']!r}"

    expected_rows = set(all_translation_rows())
    assert covered_rows == expected_rows, f"translation rows missing: {sorted(expected_rows-covered_rows)}"
    assert len(labels) == 48, f"occurrence inventory drifted: {len(labels)} != 48"

    modes = Counter(item["mode"] for item in labels)
    result = {
        "_meta": {
            "ssot": "docs/worklogs/codex-brief-menu4.md",
            "rom": str(rom_path.relative_to(ROOT)),
            "format": "addr identifies the first byte of the exact contiguous orig_span_hex patch span",
            "existing_syllable_count": len(old_syllables),
            "added_syllables": additions,
            "added_syllable_count": len(additions),
            "total_syllable_count": len(syllables),
            "vram_cap": VRAM_CAP,
            "mode_counts": dict(sorted(modes.items())),
            "source_inventory": {
                "c7_length_payload_occurrences": 42,
                "c3_xmenu_direct_spans": 6,
                "c1_c6d0_c7a0": "boxed direct-tile data inspected; no standalone SSOT target row (Easy/Manual setting excluded)",
                "ce_46xx": "no parseable direct-tile label table; bytes are repeating 2bpp-looking graphics data, so no patch span emitted",
            },
            "gates": {
                "decode_match": "PASS (48/48)",
                "structure_preserved": "PASS for inplace spans; overflow/baseswap rows are explicitly non-applied plans",
                "byte_fit_flagged": "PASS (no truncation)",
                "syllable_cap": f"PASS ({len(old_syllables)}+{len(additions)}={len(syllables)} <= {VRAM_CAP})",
                "font_coverage": "PASS",
                "missing_translation_rows": "PASS (0)",
            },
        },
        "labels": labels,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rom", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    result = build(args.rom.resolve(), args.out.resolve())
    meta = result["_meta"]
    print(f"wrote {args.out}: {len(result['labels'])} labels")
    print(f"modes: {meta['mode_counts']}")
    print(
        f"syllables: {meta['existing_syllable_count']}+{meta['added_syllable_count']}="
        f"{meta['total_syllable_count']} <= {meta['vram_cap']}"
    )


if __name__ == "__main__":
    main()
