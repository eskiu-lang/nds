# Sound

SDAT archives, the sequence synthesizer, sound effects, streams and waves in `<nds/sdat>` and `<nds/wav>`. Every function and type is also in the [API reference](api.md).

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
noise, 32 voices with stealing. It mixes a span of samples at a time (up to the next
driver frame, where no setting changes), voice by voice, four PCM voices to a loop, and
each output sample still adds the voices in the same order with the same rounding. At
`-O2` on an Apple M-series Mac it renders the battle themes of the three games 1,050 to
1,250 times faster than real time; the Rust engine takes about 1.65 times as long
(`tools/bench_sdat.py`, see [Checks](checks.md#speed)).
