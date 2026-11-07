# Graphics and textures

2D graphics and animations in `<nds/graphics>`, textures and models in `<nds/model>`. Every function and type is also in the [API reference](api.md).

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
