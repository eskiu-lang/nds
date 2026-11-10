# nds documentation

Guides and reference for nds. The [README](../README.md) has the overview.

<!-- pages -->
- [Archives and ROMs](archives.md)
- [Checks and sources](checks.md)
- [Graphics and textures](graphics.md)
- [Models, animations and particles](models.md)
- [Sound](sound.md)
- [Text](text.md)
- [API reference](api.md): every public function and type
<!-- /pages -->

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
| `<nds/model>` | `NdsTexSet` (texture formats 1 to 7), `NdsModel`, `NdsMesh` (posed and skinned) |
| `<nds/anim>` | `NdsAnimFile`: BCA, BTA, BTP and BMA animations as `NdsCurve`s |
| `<nds/gltf>` | `nds_gltf_write`: glTF 2.0 with skins, materials, textures, animations |
| `<nds/spl>` | `NdsSpl`: SPL particle archives, the Tallgrass particle JSON |
| `<nds/text>` | `NdsText`: Gen 4 and Gen 5 message files |

What is not supported: writing any DS format, simulating particles, and BVA (visibility)
animations; see [Models](models.md#limits) for the limits of the 3D readers. Within the
newer readers: a cell's affine objects are drawn without their own rotation (a frame's
rotation and scale turn the whole cell); a multi-cell frame of an NMAR moves the
multi-cell but its rotation and scale are not applied; the NMCR play flags are read but
not acted on (`NdsMultiCells_draw` plays every node from the tick it is given); text
control codes have names only for the Gen 4 commands the pret table names (others are
written `{CMD_XXXX ...}`); the font glyphs Gen 5 keeps in Unicode's enclosed
alphanumerics block (the PK and MN glyphs at U+2486 and U+2487, for example) come out as
those code points; and SSAR playback was checked on synthetic files only, as no game at
hand has a sequence archive (see below).

## Platforms

The package is plain Eskiu with no native library, so it builds for every target Eskiu has:
macOS, Linux and Windows, iOS and Android, WebAssembly, and freestanding builds. Its tests
pass on macOS, Linux and Windows in CI, under node as WebAssembly (emscripten) and on an
Android arm64 emulator.
