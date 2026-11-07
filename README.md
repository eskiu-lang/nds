<p align="center">
  <img src="https://raw.githubusercontent.com/eskiu-lang/eskiu/main/assets/logo.png" alt="Eskiu, a kitten with a ball of yarn" width="140">
</p>

<h2 align="center">nds</h2>
<p align="center">Nintendo DS file formats for Eskiu: ROMs, NARC archives, sound, 2D graphics, 3D textures and game text.</p>
<p align="center"><sub>Part of the <a href="https://github.com/eskiu-lang">Eskiu</a> project</sub></p>
<p align="center">
  <a href="https://eskiu-lang.org">eskiu-lang.org</a> &nbsp;&middot;&nbsp;
  <a href="#modules">Modules</a> &nbsp;&middot;&nbsp;
  <a href="examples/">Examples</a> &nbsp;&middot;&nbsp;
  <a href="https://github.com/eskiu-lang/eskiu">The language</a>
</p>

<p align="center">
  <a href="https://github.com/eskiu-lang/nds/actions/workflows/ci.yml"><img src="https://github.com/eskiu-lang/nds/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/version-0.1.0-6448d4" alt="Version 0.1.0">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="License: MIT"></a>
</p>

---

`nds` reads the files of Nintendo DS games, written in Eskiu with no dependencies beyond
the standard library. It was ported from the tools and engine of Tallgrass, a game maker
that loads the assets of DS games, and checked against them on the files of three
games. The cell animation, sequence archive, stream and text readers were written later
from public format descriptions (see [Sources](#sources)) and checked against the same
tools as black boxes.

- **ROMs and archives.** A `.nds` ROM's header, its file system by path or id and its
  ARM9 overlays; NARC archives by index or path; LZ10, LZ11 and the backward LZ of
  overlays.
- **Sound.** SDAT archives (names, sequences, sequence archives, banks, wave archives,
  streams) and a synthesizer of the DS sound driver that renders a sequence or a sound
  effect of an SSAR to 48 kHz stereo, in blocks of any size. Its output is the Tallgrass
  engine's, sample for sample. STRM streams (PCM8, PCM16, IMA-ADPCM) decode to PCM.
- **2D graphics.** NCLR palettes, NCGR tiles (4 and 8 bits, tiled or linear), NSCR
  screens and NCER cells to RGBA images; NANR and NMAR cell animations (frames with
  durations, translation, rotation and scale) and NMCR multi-cells, drawn frame by frame.
- **Text.** The message files of the Gen 4 and Gen 5 Pokémon games, decrypted, with
  their control codes kept as tagged items.
- **3D.** NSBTX and NSBMD textures in all seven DS formats, and the triangles of NSBMD
  models grouped by material.
- **PNG and WAV writers**, so the examples need nothing else.
- **Errors as `Result`.** Every read is bounds checked; truncated or corrupt files give an
  error, never a crash (the parsers run under AddressSanitizer with mutated inputs).

## Sound

```eskiu
import <nds/sdat>;
import <nds/wav>;

Result<int, string> run() {
    Sdat s = Sdat_open("sound_data.sdat")?;
    defer s.close();
    Pcm16 pcm;
    s.render_name("SEQ_BGM_FIELD", 30.0, &pcm)?;   // stops at the song's loop point
    defer pcm.free();
    pcm.write_wav("field.wav")?;
    return Ok<int, string>(0);
}
```

For a player, `SdatPlayer_open(&s, index, looping)` and `p.render(out, frames)` fill a
buffer at a time (`render_f32` gives floats). Sound effects stored in a sequence archive
play the same way: `SdatPlayer_open_ssar(&s, archive, entry, looping)` starts at the
entry's offset in the archive's shared bytecode with its own bank and volume
(`s.ssar_entry(archive, entry)` gives the record, `s.ssar_find` and
`s.ssar_entry_find` look names up, `s.render_ssar` renders one). `s.stream(i)` decodes a
STRM to a `SdatStream`: its `Pcm16` (channels interleaved, at the stream's rate), loop
flag and loop start; `sdat_strm(data)` does the same for a STRM file outside an SDAT. `pitch`, `pan`, `mod_depth` and `mod_speed`
are the player's settings, `set_volume` its volume. `s.wave(archive, index)` decodes one
wave (a cry is wave 0 of its archive) to 16-bit PCM.

The synthesizer models the driver: a 192 Hz frame clock with a tempo accumulator,
volumes summed in tenths of a dB, the driver's ADSR rate tables, pitch in 1/64 semitone
with bend and LFO, PCM8, PCM16 and IMA-ADPCM samples with loops, PSG square waves and
noise, 32 voices with stealing. It renders a busy battle theme 550 to 640 times faster
than real time at `-O2` on an Apple M-series Mac (the Rust engine is 12 to 18% faster).

## Archives and ROMs

```eskiu
NdsRom rom = NdsRom_open("game.nds")?;
defer rom.close();
printf("%s (%s), %d files\n", rom.title, rom.code, rom.count());
Narc n = rom.narc("a/0/0/4")?;            // views into the ROM
defer n.close();
Bytes f = nds_unpack(n.file(12).data, n.file(12).len)?;   // LZ data decompressed
Bytes ov = rom.overlay(12)?;              // decompressed when compressed
```

## Graphics and textures

```eskiu
NdsPalette pal = nclr_read(nclr.data, nclr.len)?;
NdsTiles tiles = ncgr_read(ncgr.data, ncgr.len)?;
NdsScreen scr = nscr_read(nscr.data, nscr.len)?;
NdsImage img = nds_render_screen(&scr, &tiles, &pal, true);
img.write_png("bg.png")?;

NdsAnims an = nanr_read(nanr.data, nanr.len)?;   // RNAN (or an NMAR, RAMN)
NdsCells cells = ncer_read(ncer.data, ncer.len)?;
List<NdsImage> frames;
frames.init(8);
an.render(0, &cells, &tiles, &pal, &frames);     // every frame of sequence 0
NdsAnimFrame* f = an.frame(0, an.frame_at(0, ticks));   // the frame at a 60 Hz tick
cells.draw_frame(f, &tiles, &pal, &img, ox, oy);
NdsMultiCells mc = nmcr_read(nmcr.data, nmcr.len)?;
mc.draw(0, &an, ticks, &cells, &tiles, &pal, &img, ox, oy);

NdsTexSet ts = nds_texset(data, len)?;    // BTX0, or the TEX0 block of a BMD0
NdsImage tex = ts.image(0, ts.palette_for(0))?;
NdsModel m = nsbmd_read(data, len)?;      // materials and triangles
```

A NANR sequence is a list of `NdsAnimFrame`s: a cell, a duration in 60 Hz ticks and the
frame's transform (translation, and for the affine kind a rotation in 1/65536 turn and
two scales in 1/4096). `frame_at` follows the sequence's loop mode (stop, repeat, back
and forth once or forever). `draw_frame` moves the cell, and turns and scales it around
its origin by sampling the cell at each drawn pixel's center, with the inverse matrix
the hardware uses for affine objects; an identity frame draws exactly as
`NdsCells_draw`. An NMCR multi-cell is a set of nodes, each playing a NANR sequence at a
position; an NMAR animates multi-cells as a NANR animates cells.

## Text

```eskiu
NdsCharmap map = nds_charmap_load("charmap.txt")?;   // the Gen 4 character table
defer map.free();
NdsText t = nds_text_read(f.data, f.len, &map)?;      // Gen 4 or Gen 5, detected
defer t.free();
for (i in 0..t.count) {
    string s = t.text(i, NDS_TEXT_CONTROLS);  // "Hi {STRVAR_1 1, 2, 0}!\nBye"
    printf("%d %s\n", i, s);
    free((*void)s);
}
```

`gen4_text_read` and `gen5_text_read` read one generation. Each message is a list of
`NdsTextItem`s: characters (Unicode code points), line breaks, the scroll and clear
codes of Gen 4, control codes with their command and arguments (text variables, colors,
sizes, waits) and codes with no character, so a tool can turn the codes into its own
markup. `t.text(i, mode)` writes a message as UTF-8, line breaks as `\n` (and `\r`, `\f`),
control codes in braces with `NDS_TEXT_CONTROLS` or left out with `NDS_TEXT_PLAIN`.
Gen 5 codes are Unicode. Gen 4 codes are game characters, turned into Unicode by a
character table you load: the package ships none, because no public source for the
games' table carries a license. `nds_charmap_load(path)` and `nds_charmap_read(data,
len)` read the format of the pret decompilation projects' `charmap.txt` (one `HHHH=c`
line per code), for example the one in github.com/pret/pokeheartgold under
`tools/msgenc/`. Without a table (`null`), Gen 4 characters come out as unknown codes
with their game code as the value, which `t.text` writes as `\xHHHH`.

## Modules

| Module | Contents |
|---|---|
| `<nds>` | All of the below |
| `<nds/bin>` | `NdsData`, bounds-checked little-endian reads |
| `<nds/lz>` | `nds_lz_decompress` (LZ10, LZ11), `nds_unpack`, `nds_blz_decompress` |
| `<nds/narc>` | `Narc` (by index and path), `NdsNames` (FNT directory trees) |
| `<nds/rom>` | `NdsRom`: header, files, NARCs, ARM9 binary, overlays |
| `<nds/sdat>` | `Sdat`, `SdatPlayer`, `SdatWave`, `SdatSsarEntry`, `SdatStream`, `Sdat_render` |
| `<nds/wav>` | `Pcm16`, `wav_bytes` |
| `<nds/image>` | `NdsImage` (RGBA), PNG writer |
| `<nds/graphics>` | `NdsPalette`, `NdsTiles`, `NdsScreen`, `NdsCells`, `NdsAnims`, `NdsMultiCells` |
| `<nds/model>` | `NdsTexSet` (texture formats 1 to 7), `NdsModel` |
| `<nds/text>` | `NdsText`: Gen 4 and Gen 5 message files |

What is not supported: NSBMD node matrices, skinning and animations (the geometry is
right for single-node models such as map blocks), texture matrices, SPL particles, and
writing any format. Within the newer readers: a cell's affine objects are drawn without
their own rotation (a frame's rotation and scale turn the whole cell); a multi-cell
frame of an NMAR moves the multi-cell but its rotation and scale are not applied; the
NMCR play flags are read but not acted on (`NdsMultiCells_draw` plays every node from
the tick it is given); text control codes have names only for the Gen 4 commands the
pret table names (others are written `{CMD_XXXX ...}`); the font glyphs Gen 5 keeps in
Unicode's enclosed alphanumerics block (the PK and MN glyphs at U+2486 and U+2487, for
example) come out as those code points; and SSAR playback was checked on synthetic
files only, as no game at hand has a sequence archive (see below).

## How it was checked

On the ROMs and sound archives of three DS games:

- every sequence of the three SDATs (3775) rendered for 10 s, 116 background themes
  looping for 120 s and 800 more for 60 s: the 16-bit output is identical to the Tallgrass
  engine's, every sample (`tools/compare_sdat.py`);
- 4,100 screens, tile sheets and atlases and 1,650 cell files pixel-identical with
  Tallgrass's Python tools (`tools/compare_graphics.py`);
- 69,000 textures identical with its `btx.py`, the formats it skips within 1 of apicula,
  and 1,840 models' triangles equal to its `nsbmd.py` (`tools/compare_models.py`).

- every NANR and NMAR in the ROMs of Platinum (796), HeartGold (988) and Black 2 (6,824):
  sequences and frames equal to the output of Tallgrass's `g2d.py`, every NANR's frames
  drawn with the nearest cells of its NARC, and Black 2's 3,181 NMCRs read
  (`tools/compare_anims.py`; Tallgrass has no NMCR reader to compare with);
- every message of Platinum (46,053), HeartGold (49,984) and Black 2 (80,095 in its two
  message NARCs) identical to Tallgrass's `text4.py` and `text5.py`, which stop a Gen 4
  message at its first control code and leave Gen 5 control codes out
  (`tools/compare_text.py`);
- Black 2's stream (PCM16 stereo, 112 s) decoded to its channels' samples exactly
  (`tools/sdat_check.esk`). None of the three games has a sequence archive, and the
  Gen 4 games have no streams, so SSAR playback is checked on synthetic files only: each
  sound effect of the test archive renders sample for sample as the same bytecode stored
  as an SSEQ.

These scripts read the game files from paths you give them; nothing from a game is in
this repository. The tests use synthetic files from `tools/gen_test_data.py`; the
expected audio for them was rendered by the Tallgrass engine. On macOS the renders must
match exactly; elsewhere the C library's `exp2`, `powf`, `log10` and `sin` may round a
last bit differently, so the tests allow a difference of 2 in a 16-bit sample.

## Sources

The cell animation, sequence archive, stream and text readers follow these public
descriptions; the Tallgrass tools were only run, never read.

- **NANR, NMAR, NMCR:** the DS Pokémon Hacking documentation, "NANR", "ABNK section",
  "NMCR" and "MCBK section" (ds-pokemon-hacking.github.io, Nitro graphics 2D). Checked on
  the files of the ROMs: a multi-cell's node offset counts from the node table, not from
  its record; byte 6 of a node holds the play flags (0x20 or 0x21) and byte 7 the
  animation slot.
- **Affine drawing:** GBATEK (problemkaputt.de), "LCD OBJ - OAM Rotation/Scaling
  Parameters", for the inverse matrix.
- **SSAR, STRM:** the "Nitro Composer File (*.sdat) Specification" (the SDAT document
  mirrored at feshrine.net and romhacking.net): the SSAR DATA block and its 12-byte
  records, the two-level SEQARC names of SYMB, the STRM HEAD block and the interleaving
  of the channels' blocks; ndspy's documentation of `soundStream` (an ADPCM block starts
  with its own header).
- **Gen 4 text:** Project Pokémon's RawDB, "msg" format (projectpokemon.org/rawdb/diamond/
  formats/msg.php): the table and string keys and the 9-bit form. Two points were found
  on the games' files: a 9-bit message packs 15 bits per word (the description implies
  16), and a control code is 0xFFFE, its command, its argument count and the arguments.
  Character table: checked with pret's `charmap.txt` (github.com/pret/pokeheartgold,
  `tools/msgenc/charmap.txt`, version 2021.08.17), loaded at run time and not shipped;
  the Gen 4 games share one character set.
- **Gen 5 text:** Project Pokémon's RawDB, Black "msg" format (projectpokemon.org/rawdb/
  black/formats/msg.php): blocks, entries and the decryption from the end with a key
  turned 3 bits per character, characters as Unicode, 0xFFFE as a line break and 0xF000
  as a control code. Found on Black 2's files: the 9-bit form there packs 16 bits per
  word.

## Platforms

The package is plain Eskiu with no native library, so it builds for every target Eskiu has:
macOS, Linux and Windows, iOS and Android, WebAssembly, and freestanding builds. Its tests
pass on macOS, Linux and Windows in CI, under node as WebAssembly (emscripten) and on an
Android arm64 emulator.

## Install

```toml
[deps]
nds = { git = "https://github.com/eskiu-lang/nds", rev = "v0.1.0" }
```

```
eskiuc test
```

## License

MIT
