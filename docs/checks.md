# Checks and sources

How the readers were checked against other tools, and the public descriptions they follow.

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

## Speed

`tools/bench_sdat.py` times the synthesizer against the Tallgrass engine's on the same
sequences: `tools/sdat_bench.esk` (built with `eskiuc -O2`) and `tools/sdat_bench.rs`
(built as an example of the engine crate) render each sequence looping into a reused
4096-frame buffer, time only the render calls and hash the 16-bit output. The script runs
the two in turn, keeps each side's fastest time and fails if a hash differs.

On an Apple M-series Mac, 60 s of each battle theme, best of 5:

| SDAT | Sequences | Engine (ns a frame) | `nds` (ns a frame) |
|---|---|---|---|
| Black 2 | 41 | 33.3 | 19.6 |
| HeartGold | 15 | 30.9 | 18.7 |
| Platinum | 14 | 27.4 | 16.6 |

Before the synthesizer mixed a span at a time (0.2.0), the same runs took 27.5, 26.7 and
23.4 ns a frame. After the change all 3775 sequences of the three SDATs rendered for 10 s
are still identical to the engine's (`tools/compare_sdat.py`).

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
