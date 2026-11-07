# Text

Gen 4 and Gen 5 message files in `<nds/text>`. Every function and type is also in the [API reference](api.md).

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
