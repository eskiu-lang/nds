<p align="center">
  <img src="https://raw.githubusercontent.com/eskiu-lang/eskiu/main/assets/logo.png" alt="Eskiu, a kitten with a ball of yarn" width="140">
</p>

<h2 align="center">nds</h2>
<p align="center">Nintendo DS file formats for Eskiu: ROMs, NARC archives, sound, 2D graphics and 3D textures.</p>
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
games.

- **ROMs and archives.** A `.nds` ROM's header, its file system by path or id and its
  ARM9 overlays; NARC archives by index or path; LZ10, LZ11 and the backward LZ of
  overlays.
- **Sound.** SDAT archives (names, sequences, banks, wave archives) and a synthesizer of
  the DS sound driver that renders a sequence to 48 kHz stereo, in blocks of any size.
  Its output is the Tallgrass engine's, sample for sample.
- **2D graphics.** NCLR palettes, NCGR tiles (4 and 8 bits, tiled or linear), NSCR
  screens and NCER cells to RGBA images.
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
buffer at a time (`render_f32` gives floats). `pitch`, `pan`, `mod_depth` and `mod_speed`
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

NdsTexSet ts = nds_texset(data, len)?;    // BTX0, or the TEX0 block of a BMD0
NdsImage tex = ts.image(0, ts.palette_for(0))?;
NdsModel m = nsbmd_read(data, len)?;      // materials and triangles
```

## Modules

| Module | Contents |
|---|---|
| `<nds>` | All of the below |
| `<nds/bin>` | `NdsData`, bounds-checked little-endian reads |
| `<nds/lz>` | `nds_lz_decompress` (LZ10, LZ11), `nds_unpack`, `nds_blz_decompress` |
| `<nds/narc>` | `Narc` (by index and path), `NdsNames` (FNT directory trees) |
| `<nds/rom>` | `NdsRom`: header, files, NARCs, ARM9 binary, overlays |
| `<nds/sdat>` | `Sdat`, `SdatPlayer`, `SdatWave`, `Sdat_render` |
| `<nds/wav>` | `Pcm16`, `wav_bytes` |
| `<nds/image>` | `NdsImage` (RGBA), PNG writer |
| `<nds/graphics>` | `NdsPalette`, `NdsTiles`, `NdsScreen`, `NdsCells` |
| `<nds/model>` | `NdsTexSet` (texture formats 1 to 7), `NdsModel` |

What is not supported: NSBMD node matrices, skinning and animations (the geometry is
right for single-node models such as map blocks), texture matrices, NANR/NMCR
animations, SPL particles, and SSAR/STRM sound files.

## How it was checked

On the ROMs and sound archives of three DS games:

- every sequence of the three SDATs (3775) rendered for 10 s, 116 background themes
  looping for 120 s and 800 more for 60 s: the 16-bit output is identical to the Tallgrass
  engine's, every sample (`tools/compare_sdat.py`);
- 4,100 screens, tile sheets and atlases and 1,650 cell files pixel-identical with
  Tallgrass's Python tools (`tools/compare_graphics.py`);
- 69,000 textures identical with its `btx.py`, the formats it skips within 1 of apicula,
  and 1,840 models' triangles equal to its `nsbmd.py` (`tools/compare_models.py`).

These scripts read the game files from paths you give them; nothing from a game is in
this repository. The tests use synthetic files from `tools/gen_test_data.py`; the
expected audio for them was rendered by the Tallgrass engine. On macOS the renders must
match exactly; elsewhere the C library's `exp2`, `powf`, `log10` and `sin` may round a
last bit differently, so the tests allow a difference of 2 in a 16-bit sample.

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
