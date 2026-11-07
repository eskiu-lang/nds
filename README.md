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
  <img src="https://img.shields.io/badge/version-0.2.0-6448d4" alt="Version 0.2.0">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="License: MIT"></a>
</p>

---

`nds` reads the files of Nintendo DS games, written in Eskiu with no dependencies beyond
the standard library. It was ported from the tools and engine of Tallgrass, a game maker
that loads the assets of DS games, and checked against them on the files of three
games. The cell animation, sequence archive, stream and text readers were written later
from public format descriptions (see [Sources](docs/checks.md#sources)) and checked against the same
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

## Example

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

## Documentation

- [Sound](docs/sound.md): rendering sequences, players, sound effects of sequence archives,
- [Archives and ROMs](docs/archives.md): ROM files and overlays, NARCs, LZ
- [Graphics and textures](docs/graphics.md): palettes, tiles, screens, cells, animations,
- [Text](docs/text.md): Gen 4 and Gen 5 message files and character tables
- [How it was checked](docs/checks.md): the comparisons on three games' files, and the
- [API reference](docs/api.md): every public function and type
- [Modules](docs/README.md#modules)
- [Platforms](docs/README.md#platforms)
- [API reference](docs/api.md): every public function and type

## Install

```toml
[deps]
nds = { git = "https://github.com/eskiu-lang/nds", rev = "v0.2.0" }
```

```
eskiuc test
```

## License

MIT
