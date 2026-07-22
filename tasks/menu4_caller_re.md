# System ④ `$C0:1B4B` caller RE and menu4 label handoff

SSOT: `tasks/codex-brief-menu4.md`, `docs/17-menu-tile-font-labels.md`,
`docs/11-sjis-menu.md`, `docs/12-sjis-ui-hangul.md`.

Analysis input was the isolated Codex copy only:
`roms/re_codex.smc` + `roms/re_codex.smc.i64` (MD5
`acdeb2ee6ef7b460c5dfed6957f8581a`).  The main ROM IDB was not opened.

## Renderer calling convention

`$C0:1B4B` starts with `PHP; REP #$30; PHD; PHY; PHA x3; TSC; TCD`.
Consequently its direct-page operands are a temporary stack frame, not
persistent zero-page/WRAM globals.  The fetch at `$C0:1B5C`, `LDA [$0F],Y`,
resolves the caller-supplied 24-bit string pointer.  IDA renders this stack
alias using `$7E:000E/$000F` symbols, which is why the path is commonly
described as the `$7E:000E` pointer path even though fixed callers do not first
store a pointer to literal WRAM.

Fixed callers pass the pointer as:

```asm
PEA #$00BB       ; bank word (low byte is bank)
PEA #$AAAA       ; address
LDA #base
JSL $C01B4B
PLA              ; caller discards the two PEA words
PLA
```

`X` is the tilemap-buffer byte offset.  `A` is the complete tilemap base
(tile base plus palette/priority attributes).  The renderer saves it in its
stack DP frame and performs `tile_byte + base` before writing `$7E:0000,X`.

The generic `$C3:8B81` path avoids the two PEA instructions because its own
stack locals line up with the nested renderer frame.  It constructs the
24-bit pointer in caller locals `$01..$03`, loads `X` from `$13`, and loads the
base from `$05` immediately before the JSL.

## All ten callers

| JSL site | pointer source | base source | destination / traversal |
|---|---|---|---|
| `$C0:719A` | fixed `$C0:720B` (`PEA #$00C0; PEA #$720B`) | immediate `$2E00` | `X` returned by `$C0:1B11` for input `$2202`; static multirun tile program |
| `$C0:778C` | fixed `$C0:7841` | immediate `$2100` | `X` returned by `$C0:1B11` for input `$0C10`; program decodes as `よろしいですか？ / はい / いいえ` |
| `$C0:79F9` | fixed `$C0:7A5A` | immediate `$2200` | `X=$7370`; selected when `$7E:C2F5 == $FFFF` |
| `$C0:7A0D` | fixed `$C0:7A6C` | immediate `$2200` | `X=$7370`; alternate branch when `$7E:C2F5 != $FFFF` |
| `$C0:7A31` | computed `$C0:(7A75 + 5*n)` | immediate `$2200` | `X=$7370+$44`; `n=$7E:C2F7`, computed as `4*n+n`; outer loop starts at 3 and decrements, destination decreases `$0E` per iteration |
| `$C0:7C00` | fixed `$C0:7C5C` | immediate `$2E00` | destination `word[$C0:7C50,index]+$4840`; the surrounding object loop decrements its index twice per pass |
| `$C0:8D6F` | fixed `$C0:8D8A` | immediate `$2100` | `X=$0484+$054D`; one-shot results/status layout |
| `$C3:8B81` | descriptor-driven 24-bit pointer copied to stack locals `$01..$03` | descriptor byte 5 becomes `$xx00`; optionally OR `$0400` | generic label walker; destination in `$13`; script-record offset in `$0F`; nested row/column loops advance destination and descriptor offsets |
| `$C3:95A4` | fixed `$C3:95BE` | immediate `$2100` | fixed `X=$5A4C`; X-menu program containing `セッティング / グリッドへんこう / アイテム` |
| `$C3:99B8` | fixed `$C3:99C0` | immediate `$2100` | fixed `X=$5A62`; `イージー / マニュアル`, explicitly excluded from this batch |

The byte signature `22 4B 1B C0` occurs exactly ten times in the isolated ROM;
there are no additional static JSL sites.

## Generic descriptor and script traversal

The `$C3:8B04` walker receives a base pointer in its incoming stack arguments,
then repeatedly parses six-byte descriptors from `[local $15],Y`:

```text
+0  record/op selector
+1  string address low
+2  string address high
+3  string bank
+4  auxiliary/overlay-row selector
+5  base high byte (masked with $FF00)
```

At `$C3:8B48` it increments past byte 0, copies bytes 1..3 into the nested
renderer's effective pointer, splits bytes 4..5 into `$07` and `$05`, advances
the descriptor cursor by six, and calls `$C0:1B4B`.  Object state can add
`$0400` to `$05` for a palette variant.  The cursor and destination are then
advanced in the surrounding row/column loops.

The `$C7:B180..B460` label data reached through this path uses
length-prefixed tile payloads.  A normal label is `length + body[length]`.
Parameter rows retain a three-byte prefix (`SP/CN/PW/DF/WT/DP/BP` plus blank)
inside the same payload, so only the following description subspan is a patch
target.  Separate length-prefixed overlay payloads and all page/control data
remain outside the emitted patch spans.

X-menu strings use the renderer's native inline program instead.  A voiced
tile is encoded as `00 94 body` (dakuten) or `00 95 body` (handakuten), and
`00 01/02` changes row while `00 00` returns.  This is why simple byte-count
fit is insufficient: a marker pair may not be split across an immutable
inline overlay escape.

## Table survey results

- `$C7:B180..B460`: 42 SSOT-target occurrences extracted from length-prefixed
  payloads.  The count includes the explicitly listed duplicate labels.
- `$C1:C6D0..C7A0`: boxed direct-tile data with `$E0..$E7` frame parts was
  inspected.  It contains no standalone SSOT translation row after excluding
  Easy/Manual setting; substrings inside longer setting labels were not
  patched.
- The remaining six X-menu targets are actual renderer programs at
  `$C3:9201/$9208/$9212` and `$C3:95BE/$95CA/$95DA`.
- `$CE:46xx` did not validate as a direct-tile script table: it is repeating
  bitplane-looking graphic data, and apparent `0F 03 0B` matches recur at
  regular graphic-block intervals.  No unsafe span was emitted from this
  region.  This conflicts with the briefing's `$CE:46xx` location claim and
  needs Claude/runtime confirmation before any write there.

## Base-swap conclusion

**General per-label base swap is not available.**  The C3 generic descriptor
stores only the base high byte and masks it with `$FF00`; it cannot express
the required `+$0220`.  The C7 page also mixes labels, preserved Latin stat
tiles, blanks, and overlays, so changing one shared draw base would corrupt
non-Hangul cells.

The fixed `$C3:95A4` call is the one conditional exception: its immediate
`$2100` can mechanically become `$2320`, and its three visible X-menu labels
are intended to become pure Hangul.  However, the base applies to the entire
multiline `$C3:95BE` program.  It therefore requires a group re-encode, cannot
be mixed with FE-marker labels in that same program, and needs an explicit
blank rule because the original renderer maps `$FF` to tile zero *before*
adding the base (under `$2320`, that is no longer the original blank tile).
`アイテム -> 아이템` is flagged `mode=baseswap` as this caller-group
candidate; it is not a standalone ready-to-write patch.

All other oversize labels remain `mode=overflow`; no semantic abbreviation or
arbitrary truncation was introduced.

## Output gates

`scripts/menu4_labels.py` generated
`assets/translations/menu4_labels.json` and asserted:

1. all 48 emitted encodings decode to their locked `kr` value;
2. every `inplace` span retains its size, and direct-program overlay escapes
   retain exact byte offsets; non-fitting plans are explicitly flagged;
3. no oversize label is silently written or truncated;
4. added syllables are exactly 24, so `200 + 24 = 224` (VRAM cap 224);
5. every required Hangul syllable exists in the 8pt glyph map;
6. all 40 SSOT translation rows are covered, with 48 physical occurrences
   after duplicates (missing 0).

Current mode distribution: `inplace=22`, `overflow=25`, `baseswap=1`,
`abbrev=0`.
