# Archives and ROMs

ROMs, NARC archives and compression in `<nds/rom>`, `<nds/narc>` and `<nds/lz>`. Every function and type is also in the [API reference](api.md).

```eskiu
NdsRom rom = NdsRom_open("game.nds")?;
defer rom.close();
printf("%s (%s), %d files\n", rom.title, rom.code, rom.count());
Narc n = rom.narc("a/0/0/4")?;            // views into the ROM
defer n.close();
Bytes f = nds_unpack(n.file(12).data, n.file(12).len)?;   // LZ data decompressed
Bytes ov = rom.overlay(12)?;              // decompressed when compressed
```
