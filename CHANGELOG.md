# Changelog

All notable changes to this package are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed

- `<nds/sdat>`: the synthesizer mixes a span of samples at a time (the samples up to
  the next driver frame), voice by voice, with up to four PCM voices in one loop and
  no per-sample end-of-wave checks where a voice cannot reach its end. The output is
  unchanged, sample for sample, in any block size; rendering takes about 30% less time
  (19.6 against 27.5 ns a frame on Black 2's battle themes on an Apple M-series Mac).
- `<nds/model>`: `nsbmd_read` reads the model's nodes, inverse bind matrices and the
  drawing state of its materials (colors, alpha, culling, texture flags and matrix)
  along with the triangles it gave before; `NdsMaterial` and `NdsModel` have new
  fields. The test model has three nodes, a skinning blend and full material records.

### Added

- `<nds/model>`: `nsbmd_open` and `nsbmd_count` for every model of a file;
  `NdsModel_mesh`, the model posed as the DS draws it (node matrices, the matrix stack,
  skinning, scale commands) with a joint tree built from the matrix chains and up to
  four joints and weights a vertex (`NdsMesh`, `NdsJoint`, `NdsMeshVertex`,
  `NdsPrim`); `NdsNode`, `NdsMat` and the matrix helpers (`nds_mat_*`,
  `nds_pivot_matrix`, `nds_basis_matrix`).
- `<nds/anim>`: BCA joint, BTA texture SRT, BTP texture pattern and BMA material color
  animations (`nds_anim_read`, `NdsAnimFile`), as curves sampled every 1, 2 or 4 frames
  and read at any frame (`NdsCurve`).
- `<nds/gltf>`: `nds_gltf_write`, a model to glTF 2.0 with its skin, unlit materials,
  PNG textures and joint animations; texture SRT and color animations as
  `KHR_animation_pointer` channels and, with pattern animations, in the JSON side files
  the Tallgrass engine reads (`.uvanims.json`, `.patterns.json`, `.matanims.json`).
- `<nds/spl>`: SPL particle archives (`spl_read`, `NdsSpl`): emitters, scale, color,
  alpha and texture animations, child particles, fields and textures; `NdsSpl_json` and
  `NdsSpl_write_json` write the Tallgrass engine's open particle format.
- Tools: `nitro_gltf.esk` with `compare_gltf.py` (against apicula), `spl_json.esk`
  with `compare_spl.py` (against the Tallgrass engine's converter).
- Tests: `anim3d`, `gltf` and `spl`, with synthetic BCA, BTA, BTP, BMA and SPA files;
  the new readers in the `corrupt` test.
- Docs: `models.md`.
- Tools: `bench_sdat.py` with `sdat_bench.esk` and `sdat_bench.rs`, which time the
  synthesizer against the Tallgrass engine's on the same sequences and compare a hash
  of both outputs.
- Tests: a synthetic sequence of five and six voice chords (`SEQ_CHORD` in
  `test.sdat`, rendered by the engine), checked whole and in blocks of 1 to 9 frames.

## [0.2.0] - 2026-11-07

### Added

- `<nds/graphics>`: NANR and NMAR cell animations (`nanr_read`, `NdsAnims`,
  `NdsAnimFrame` with duration, translation, rotation and scale; `frame_at` by loop
  mode; `render` for every frame of a sequence), `NdsCells_draw_frame` and
  `NdsCells_frame_bounds`, and NMCR multi-cells (`nmcr_read`, `NdsMultiCells`,
  `draw` and `bounds` at a tick).
- `<nds/sdat>`: SSAR sequence archives (`Sdat_ssar_count`, `_name`, `_find`,
  `_entries`, `_entry`, `_entry_name`, `_entry_find`, `SdatPlayer_open_ssar`,
  `Sdat_render_ssar`) with the two-level SYMB names, and STRM streams (`sdat_strm`,
  `Sdat_stream`, `Sdat_strm_count`, `_name`, `_find`, `SdatStream`) in PCM8, PCM16
  and IMA-ADPCM blocks.
- `<nds/text>`: Gen 4 and Gen 5 message files (`gen4_text_read`, `gen5_text_read`,
  `nds_text_read`), the 9-bit form of both, control codes kept as tagged items, UTF-8
  output (`NdsText_text`). Gen 4 characters go through a character table the caller
  loads (`NdsCharmap`, `nds_charmap_load`, `nds_charmap_read`, in the pret projects'
  `charmap.txt` format); the package ships none.
- Tools: `compare_anims.py` with `anim_dump.esk`, `compare_text.py` with
  `text_dump.esk`, `sdat_check.esk`; `gen_test_data.py --only` and synthetic SSAR,
  STRM, NANR, NMAR, NMCR and message files with their tests (`anims`, `sdat_arc`,
  `text`), and the new readers in the `corrupt` test.
- README: a Sources section naming the public descriptions each new reader follows.
