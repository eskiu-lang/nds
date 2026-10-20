#!/usr/bin/env python3
"""Writes the synthetic test files in tests/data:

    python3 -I tools/gen_test_data.py [--ref SDAT_WAV]

Everything is built here from fixed seeds and known values; no file comes from a game.

- test.sdat: an SDAT with a wave archive (PCM8, PCM16 and IMA-ADPCM waves), a bank
  (single, drum set and key split instruments over PCM, PSG and noise) and three
  sequences. sdat.txt lists the names, the waves' expected PCM and the renders.
  With --ref (the Tallgrass engine's sdat_wav example), the renders are made by the
  engine and written as tests/data/*.wav: the tests compare <nds/sdat> with them.
- NARCs (named and unnamed), a small .nds ROM with a BLZ overlay, LZ10 and LZ11
  streams, NCLR/NCGR/NSCR/NCER files, an NSBTX with each of the seven texture formats
  and an NSBMD; each with the expected pixels, bytes or triangles next to it.
"""
import math
import os
import random
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "tests", "data")


def u16(v):
    return struct.pack("<H", v & 0xFFFF)


def u32(v):
    return struct.pack("<I", v & 0xFFFFFFFF)


def pad(b, n):
    return b + b"\0" * ((-len(b)) % n)


def write(name, data):
    with open(os.path.join(DATA, name), "wb") as f:
        f.write(data)


def nitro_header(magic, bom, size, nblocks, header=0x10):
    return magic + u16(bom) + u16(0x0100) + u32(size) + u16(header) + u16(nblocks)


def block(magic, body):
    return magic + u32(8 + len(body)) + body


def file_with_blocks(magic, blocks, bom=0xFEFF):
    body = b"".join(blocks)
    return nitro_header(magic, bom, 0x10 + len(body), len(blocks)) + body


# ---------------------------------------------------------------------------
# Sound: IMA-ADPCM, SWAR, SBNK, SSEQ, SDAT

STEP = [7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88,
        97, 107, 118, 130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658,
        724, 796, 876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660,
        4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899, 15289, 16818,
        18500, 20350, 22385, 24623, 27086, 29794, 32767]
INDEX = [-1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8]


def adpcm_step(pred, index, nib):
    step = STEP[index]
    diff = step >> 3
    if nib & 1:
        diff += step >> 2
    if nib & 2:
        diff += step >> 1
    if nib & 4:
        diff += step
    pred = max(pred - diff, -32768) if nib & 8 else min(pred + diff, 32767)
    index = min(max(index + INDEX[nib], 0), 88)
    return pred, index


def adpcm_encode(samples):
    """IMA-ADPCM as the DS stores it: a header (first predictor, step index), then two
    nibbles a byte, low first. Returns the bytes and the samples a decoder gives."""
    pred, index = samples[0], 20
    out = bytearray(struct.pack("<hH", pred, index))
    decoded = []
    nibs = []
    for s in samples:
        best = None
        for nib in range(16):
            p, i = adpcm_step(pred, index, nib)
            e = abs(p - s)
            if best is None or e < best[0]:
                best = (e, nib, p, i)
        _, nib, pred, index = best
        nibs.append(nib)
        decoded.append(pred)
    if len(nibs) % 2:
        nibs.append(0)
        decoded.append(adpcm_step(pred, index, 0)[0])
    for k in range(0, len(nibs), 2):
        out.append(nibs[k] | nibs[k + 1] << 4)
    return bytes(out), decoded


def swav(kind, looped, rate, loop_start, loop_len, data):
    return bytes([kind, 1 if looped else 0]) + u16(rate) + u16(16756991 // rate) + u16(loop_start) + u32(loop_len) + data


def make_waves():
    """Three waves and the PCM <nds/sdat> must decode from each (the whole data)."""
    # PCM8: one cycle of a soft square, looped from word 1
    p8 = [int(90 * math.sin(2 * math.pi * k / 32) + 20 * math.sin(6 * math.pi * k / 32)) for k in range(64)]
    w8 = swav(0, True, 16384, 2, 14, bytes(v & 0xFF for v in p8))
    pcm8 = [v << 8 for v in p8]
    # PCM16: a decaying chirp, not looped
    p16 = [int(26000 * math.exp(-k / 300) * math.sin(2 * math.pi * k * (0.02 + k / 40000))) for k in range(1200)]
    w16 = swav(1, False, 22050, 0, 600, b"".join(struct.pack("<h", v) for v in p16))
    # ADPCM: a sine with a harmonic, looped after the attack
    pa = [int(20000 * math.sin(2 * math.pi * k / 48) + 6000 * math.sin(2 * math.pi * k / 16)) for k in range(960)]
    data, dec = adpcm_encode(pa)
    # loop start 1 word into the samples (the header word counts), 120 words long
    wa = swav(2, True, 32000, 1 + 24, 120, data)
    adpcm = dec[:((25 + 120) * 4 - 4) * 2]
    return [w8, w16, wa], [(pcm8, 16384, True, 8), (p16, 22050, False, 0), (adpcm, 32000, True, 192)]


def make_swar(waves):
    n = len(waves)
    head = 0x3C + 4 * n
    offs, body = [], b""
    for w in waves:
        offs.append(head + len(body))
        body += pad(w, 4)
    data = b"DATA" + u32(8 + 32 + 4 + 4 * n + len(body)) + b"\0" * 32 + u32(n) + b"".join(u32(o) for o in offs) + body
    return nitro_header(b"SWAR", 0xFEFF, 0x10 + len(data), 1) + data


def note_rec(kind, wave, swar, root, atk, dec, sus, rel, panv):
    """A bank's note record: wave and archive (or PSG duty), root key, ADSR, pan."""
    return u16(wave) + u16(swar) + bytes([root, atk, dec, sus, rel, panv])


def make_sbnk():
    insts = []
    # 0: PCM8 wave across the keyboard
    insts.append((1, note_rec(1, 0, 0, 60, 127, 100, 110, 115, 64)))
    # 1: drum set, keys 36..39: PCM16, ADPCM, noise, PSG
    drums = [(1, note_rec(1, 1, 0, 36, 127, 127, 127, 120, 50)),
             (1, note_rec(1, 2, 0, 50, 125, 110, 100, 110, 80)),
             (3, note_rec(3, 0, 0, 60, 127, 90, 0, 100, 64)),
             (2, note_rec(2, 2, 0, 69, 115, 105, 90, 100, 30))]
    body16 = bytes([36, 39]) + b"".join(u16(k) + r for k, r in drums)
    insts.append((16, body16))
    # 2: key split: PSG below 60, ADPCM to 80, noise above
    splits = [59, 80, 127, 0, 0, 0, 0, 0]
    regs = [(2, note_rec(2, 3, 0, 57, 120, 108, 105, 112, 64)),
            (1, note_rec(1, 2, 0, 64, 110, 100, 120, 118, 64)),
            (3, note_rec(3, 0, 0, 72, 127, 115, 70, 110, 64))]
    body17 = bytes(splits) + b"".join(u16(k) + r for k, r in regs)
    insts.append((17, body17))
    # 3: PSG duty 5 alone, 4: noise alone, 5: PCM16 with a slow attack
    insts.append((2, note_rec(2, 5, 0, 69, 90, 110, 100, 100, 64)))
    insts.append((3, note_rec(3, 0, 0, 60, 127, 105, 60, 105, 64)))
    insts.append((1, note_rec(1, 1, 0, 60, 80, 120, 127, 110, 64)))
    n = len(insts)
    recs, body = b"", b""
    base = 0x3C + 4 * n
    for kind, b in insts:
        recs += bytes([kind]) + u16(base + len(body)) + b"\0"
        body += pad(b, 4)
    data = b"DATA" + u32(8 + 32 + 4 + len(recs) + len(body)) + b"\0" * 32 + u32(n) + recs + body
    return nitro_header(b"SBNK", 0xFEFF, 0x10 + len(data), 1) + data


class Seq:
    """A tiny SSEQ assembler with labels; offsets are relative to the data start."""

    def __init__(self):
        self.b = bytearray()
        self.labels = {}
        self.fix = []

    def raw(self, *v):
        self.b += bytes(v)

    def label(self, name):
        self.labels[name] = len(self.b)

    def ref(self, name):
        self.fix.append((len(self.b), name))
        self.b += b"\0\0\0"

    def vlq(self, v):
        out = [v & 0x7F]
        v >>= 7
        while v:
            out.append(0x80 | (v & 0x7F))
            v >>= 7
        self.b += bytes(reversed(out))

    def note(self, key, vel, dur):
        self.raw(key, vel)
        self.vlq(dur)

    def wait(self, n):
        self.raw(0x80)
        self.vlq(n)

    def prog(self, p):
        self.raw(0x81)
        self.vlq(p)

    def s16(self, v):
        self.b += struct.pack("<h", v)

    def done(self):
        for at, name in self.fix:
            o = self.labels[name]
            self.b[at:at + 3] = bytes([o & 0xFF, o >> 8 & 0xFF, o >> 16])
        return bytes(self.b)


def seq_main():
    """Four tracks over every instrument kind and most commands."""
    s = Seq()
    s.raw(0xFE, 0x0F, 0x00)
    for t in (1, 2, 3):
        s.raw(0x93, t)
        s.ref(f"t{t}")
    # track 0: PCM8 lead
    s.raw(0xE1)
    s.s16(150)
    s.raw(0xC2, 118)
    s.prog(0)
    s.raw(0xC1, 110)
    s.raw(0xC0, 40)
    s.raw(0xD5, 100)
    s.note(60, 100, 24)
    s.raw(0xC5, 4)
    s.raw(0xC4, 20)
    s.note(64, 90, 24)
    s.raw(0xC4, 0xEC)
    s.raw(0xC3, 2)
    s.note(62, 110, 24)
    s.raw(0xC3, 0)
    s.raw(0xC4, 0)
    s.raw(0xD0, 120, 0xD1, 100, 0xD2, 90, 0xD3, 110)
    s.raw(0xD4, 2)
    s.note(67, 100, 12)
    s.note(65, 80, 12)
    s.raw(0xFC)
    s.raw(0xD0, 0xFF, 0xD1, 0xFF, 0xD2, 0xFF, 0xD3, 0xFF)
    s.raw(0x95)
    s.ref("sub")
    s.raw(0xCA, 60, 0xCB, 30, 0xCC, 0, 0xCD, 2)
    s.raw(0xE0)
    s.s16(6)
    s.note(72, 100, 48)
    s.raw(0xCC, 1)
    s.note(69, 100, 48)
    s.raw(0xCC, 2, 0xCA, 120)
    s.note(67, 100, 48)
    s.raw(0xCA, 0)
    s.raw(0xC7, 0)
    s.note(60, 90, 30)
    s.note(64, 90, 30)
    s.raw(0xC7, 1)
    s.wait(30)
    s.raw(0xC8, 1)
    s.note(60, 100, 16)
    s.note(62, 100, 16)
    s.note(64, 100, 16)
    s.raw(0xC8, 0)
    s.raw(0xA0, 70, 100)
    s.s16(10)
    s.s16(30)
    s.raw(0xB0, 3)
    s.s16(5)
    s.raw(0xB1, 3)
    s.s16(7)
    s.raw(0xB8, 3)
    s.s16(12)
    s.raw(0xA2, 72, 100)
    s.vlq(20)
    s.raw(0xBD, 3)
    s.s16(12)
    s.raw(0xA2, 48, 100)
    s.vlq(20)
    s.raw(0xA1, 0x80, 3)
    s.raw(0xD6, 0)
    s.raw(0xE1)
    s.s16(90)
    s.note(55, 120, 40)
    s.raw(0xFF)
    s.label("sub")
    s.note(76, 70, 8)
    s.note(79, 70, 8)
    s.raw(0xFD)
    # track 1: drums
    s.label("t1")
    s.prog(1)
    s.raw(0xC1, 120)
    s.raw(0xD4, 6)
    s.note(36, 127, 12)
    s.note(38, 100, 6)
    s.note(37, 90, 6)
    s.note(39, 80, 12)
    s.raw(0xFC)
    s.raw(0xFF)
    # track 2: key split, pan sweep
    s.label("t2")
    s.prog(2)
    s.raw(0xC0, 100, 0xC1, 90)
    for k, v, d in ((48, 100, 24), (52, 90, 24), (70, 100, 24), (74, 100, 24), (90, 80, 12), (95, 80, 12), (55, 100, 48)):
        s.note(k, v, d)
        s.raw(0xC0, 128 - k)
    s.raw(0xFF)
    # track 3: PSG, noise and the slow PCM16 voice, ending at a jump back
    s.label("t3")
    s.prog(3)
    s.raw(0xC1, 70)
    s.label("again")
    s.note(81, 100, 18)
    s.prog(4)
    s.note(60, 80, 6)
    s.prog(5)
    s.note(64, 120, 60)
    s.prog(3)
    s.raw(0x94)
    s.ref("again")
    return s.done()


def seq_loop():
    """A short song with an endless loop and a jump back: plays forever when looping."""
    s = Seq()
    s.raw(0xFE, 0x03, 0x00, 0x93, 1)
    s.ref("t1")
    s.raw(0xE1)
    s.s16(200)
    s.prog(0)
    s.raw(0xD4, 0)
    s.note(60, 100, 12)
    s.note(67, 100, 12)
    s.raw(0xFC)
    s.raw(0xFF)
    s.label("t1")
    s.prog(2)
    s.label("top")
    s.note(50, 90, 24)
    s.note(75, 90, 24)
    s.raw(0x94)
    s.ref("top")
    return s.done()


def seq_bad_bank():
    """A sequence whose bank slot is empty: opening it must fail."""
    s = Seq()
    s.note(60, 100, 10)
    s.raw(0xFF)
    return s.done()


def make_sseq(code):
    data = b"DATA" + u32(8 + 4 + len(code)) + u32(0x1C) + code
    return pad(nitro_header(b"SSEQ", 0xFEFF, 0x10 + len(data), 1) + data, 4)


def make_sdat(files, seqs, banks, wavearcs, seq_names, wa_names):
    """files: FAT contents. seqs: (file, bank, vol) or None; banks: (file, [wa x4]) or
    None; wavearcs: file or None; names: list (None for a missing name)."""
    def symb_block():
        cats = [seq_names, [], [], wa_names, [], [], [], []]
        head = 8 + 8 * 4 + 24
        recs, strs = b"", b""
        offs = []
        rec_at = head
        tables = []
        for names in cats:
            tables.append(names)
        rec_bytes = [4 + 4 * len(n) for n in tables]
        strings_at = head + sum(rec_bytes)
        for names in tables:
            offs.append(head + len(recs))
            r = u32(len(names))
            for n in names:
                if n is None:
                    r += u32(0)
                else:
                    r += u32(strings_at + len(strs))
                    strs += n.encode() + b"\0"
            recs += r
        body = b"".join(u32(o) for o in offs) + b"\0" * 24 + recs + strs
        return pad(b"SYMB" + u32(8 + len(body)) + body, 4)

    def info_block():
        head = 8 + 8 * 4 + 24
        cats = [
            [None if s is None else u16(s[0]) + u16(0) + u16(s[1]) + bytes([s[2], 64, 64, 0]) + u16(0) for s in seqs],
            [],
            [None if b is None else u16(b[0]) + u16(0) + b"".join(u16(w) for w in b[1]) for b in banks],
            [None if w is None else u16(w) + u16(0) for w in wavearcs],
            [], [], [], [],
        ]
        tables_size = sum(4 + 4 * len(c) for c in cats)
        entries_at = head + tables_size
        recs, ents, offs = b"", b"", []
        for c in cats:
            offs.append(head + len(recs))
            r = u32(len(c))
            for e in c:
                if e is None:
                    r += u32(0)
                else:
                    r += u32(entries_at + len(ents))
                    ents += pad(e, 4)
            recs += r
        body = b"".join(u32(o) for o in offs) + b"\0" * 24 + recs + ents
        return pad(b"INFO" + u32(8 + len(body)) + body, 4)

    symb, info = symb_block(), info_block()
    fat_size = 12 + 16 * len(files)
    symb_at = 0x40
    info_at = symb_at + len(symb)
    fat_at = info_at + len(info)
    file_at = fat_at + fat_size
    body, offs = b"", []
    first = file_at + 16
    for f in files:
        body = pad(body, 0x20)
        offs.append(first + len(body))
        body += f
    file_blk = b"FILE" + u32(16 + len(body)) + u32(len(files)) + u32(0) + body
    fat = b"FAT " + u32(fat_size) + u32(len(files)) + b"".join(u32(o) + u32(len(f)) + b"\0" * 8 for o, f in zip(offs, files))
    total = file_at + len(file_blk)
    head = nitro_header(b"SDAT", 0xFEFF, total, 4, 0x40)
    head += u32(symb_at) + u32(len(symb)) + u32(info_at) + u32(len(info)) + u32(fat_at) + u32(fat_size) + u32(file_at) + u32(len(file_blk))
    head = head.ljust(0x40, b"\0")
    return head + symb + info + fat + file_blk


def gen_sdat(ref):
    waves, pcm = make_waves()
    swar = make_swar(waves)
    sbnk = make_sbnk()
    files = [make_sseq(seq_main()), make_sseq(seq_loop()), make_sseq(seq_bad_bank()), sbnk, swar]
    seqs = [(0, 0, 110), None, (1, 0, 127), (2, 3, 100)]
    banks = [(3, [0, 0xFFFF, 0xFFFF, 0xFFFF]), None, None, None]
    sdat = make_sdat(files, seqs, banks, [4], ["SEQ_TEST", None, "SEQ_LOOP", "SEQ_NO_BANK"], ["WAVE_ARC_TEST"])
    write("test.sdat", sdat)
    lines = ["# NAME index", "seq SEQ_TEST 0", "seq SEQ_LOOP 2", "seq SEQ_NO_BANK 3"]
    for k, (p, rate, looped, ls) in enumerate(pcm):
        write(f"wave{k}.pcm", b"".join(struct.pack("<h", v) for v in p))
        lines.append(f"wave {k} wave{k}.pcm {len(p)} {rate} {1 if looped else 0} {ls}")
    renders = [("SEQ_TEST", "8", "", "seq_test.wav"), ("SEQ_LOOP", "3", "loop", "seq_loop.wav")]
    for name, secs, loop, out in renders:
        lines.append(f"render {name} {secs} {loop or 'once'} {out}")
        if ref:
            args = [ref, os.path.join(DATA, "test.sdat"), name, secs, os.path.join(DATA, out)] + ([loop] if loop else [])
            subprocess.run(args, check=True, stdout=subprocess.DEVNULL)
    with open(os.path.join(DATA, "sdat.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Compression: LZ10, LZ11, BLZ

def lz_matches(data, i, max_len, max_dist, min_dist=1):
    best_len, best_dist = 0, 0
    for dist in range(min_dist, min(max_dist, i) + 1):
        n = 0
        while n < max_len and i + n < len(data) and data[i + n - dist] == data[i + n]:
            n += 1
        if n > best_len:
            best_len, best_dist = n, dist
    return best_len, best_dist


def lz10(data):
    out = bytearray([0x10]) + struct.pack("<I", len(data))[:3]
    i = 0
    while i < len(data):
        flags_at = len(out)
        out.append(0)
        for b in range(8):
            if i >= len(data):
                break
            n, d = lz_matches(data, i, 18, 4096)
            if n >= 3:
                out[flags_at] |= 0x80 >> b
                v = (n - 3) << 12 | (d - 1)
                out += bytes([v >> 8, v & 0xFF])
                i += n
            else:
                out.append(data[i])
                i += 1
    return bytes(out)


def lz11(data):
    """LZ11 with a 32-bit size field, using all three length forms."""
    out = bytearray([0x11, 0, 0, 0]) + struct.pack("<I", len(data))
    i = 0
    while i < len(data):
        flags_at = len(out)
        out.append(0)
        for b in range(8):
            if i >= len(data):
                break
            n, d = lz_matches(data, i, 0x10110, 4096)
            if n >= 3:
                out[flags_at] |= 0x80 >> b
                d -= 1
                if n <= 16:
                    out += bytes([(n - 1) << 4 | d >> 8, d & 0xFF])
                elif n <= 0x110:
                    m = n - 0x11
                    out += bytes([m >> 4, (m & 15) << 4 | d >> 8, d & 0xFF])
                else:
                    m = n - 0x111
                    out += bytes([0x10 | m >> 12, m >> 4 & 0xFF, (m & 15) << 4 | d >> 8, d & 0xFF])
                i += n + 0
            else:
                out.append(data[i])
                i += 1
    return bytes(out)


def blz(data):
    """Backward LZ: an LZ over the reversed data (distances of 3 or more), reversed."""
    r = data[::-1]
    s = bytearray()
    i = 0
    while i < len(r):
        flags_at = len(s)
        s.append(0)
        for b in range(8):
            if i >= len(r):
                break
            n, d = lz_matches(r, i, 18, 4098, 3)
            if n >= 3:
                s[flags_at] |= 0x80 >> b
                v = (n - 3) << 12 | (d - 3)
                s += bytes([v >> 8, v & 0xFF])
                i += n
            else:
                s.append(r[i])
                i += 1
    comp = bytes(s[::-1])
    hdr = 8
    body = comp
    total = len(body) + hdr
    inc = len(data) - total
    return body + u32(hdr << 24 | (len(body) + hdr)) + u32(inc)


def gen_lz():
    rnd = random.Random(5)
    text = b"".join(rnd.choice([b"pallet town ", b"route 1 ", b"oak's lab ", b"viridian "]) for _ in range(300))
    noise = bytes(rnd.randrange(256) for _ in range(300))
    long_run = b"\x07" * 5000 + b"abc" * 100
    plain = text + noise + long_run
    write("lz_plain.bin", plain)
    write("lz10.bin", lz10(plain))
    write("lz11.bin", lz11(plain))
    over = text * 2
    write("blz_plain.bin", over)
    write("blz.bin", blz(over))


# ---------------------------------------------------------------------------
# Archives: FNT, NARC, ROM

def fnt(tree, first_id):
    """tree: {name: subtree or None (a file)}. Returns the FNT bytes and the files in
    id order (paths)."""
    dirs = []

    def collect(t, prefix):
        idx = len(dirs)
        dirs.append((t, prefix))
        for name in sorted(t):
            if t[name] is not None:
                collect(t[name], prefix + name + "/")
        return idx

    collect(tree, "")
    ids = {}
    for k, (t, p) in enumerate(dirs):
        ids[p] = 0xF000 + k
    files = []
    subs = []
    firsts = []
    for t, prefix in dirs:
        firsts.append(first_id + len(files))
        b = bytearray()
        for name in sorted(t, key=lambda n: (t[n] is not None, n)):
            nm = name.encode()
            if t[name] is None:
                b += bytes([len(nm)]) + nm
                files.append(prefix + name)
            else:
                b += bytes([0x80 | len(nm)]) + nm + u16(ids[prefix + name + "/"])
        b.append(0)
        subs.append(bytes(b))
    main = b""
    off = 8 * len(dirs)
    parents = {}
    for t, prefix in dirs:
        for name in t:
            if t[name] is not None:
                parents[prefix + name + "/"] = ids[prefix]
    out_sub = b""
    for k, (t, prefix) in enumerate(dirs):
        parent = len(dirs) if k == 0 else parents[prefix]
        main += u32(off + len(out_sub)) + u16(firsts[k]) + u16(parent)
        out_sub += subs[k]
    return main + out_sub, files


def narc(contents, names=None):
    """contents: list of bytes. names: FNT tree in the same file order, or None."""
    fat, img = b"", b""
    for c in contents:
        img = pad(img, 4)
        fat += u32(len(img)) + u32(len(img) + len(c))
        img += c
    btaf = b"BTAF" + u32(12 + len(fat)) + u16(len(contents)) + u16(0) + fat
    if names is None:
        fntb_data = u32(4) + u16(0) + u16(1)
    else:
        fntb_data, order = fnt(names, 0)
    btnf = b"BTNF" + u32(8 + len(pad(fntb_data, 4))) + pad(fntb_data, 4)
    gmif = b"GMIF" + u32(8 + len(img)) + img
    body = btaf + btnf + gmif
    return nitro_header(b"NARC", 0xFFFE, 0x10 + len(body), 3) + body


def gen_archives():
    rnd = random.Random(9)
    files = [bytes(rnd.randrange(256) for _ in range(n)) for n in (0, 1, 7, 64, 300)]
    write("plain.narc", narc(files))
    lines = []
    for k, f in enumerate(files):
        write(f"narc_file{k}.bin", f)
        lines.append(f"plain {k} narc_file{k}.bin")
    tree = {"a": {"0": {"x.bin": None, "y.bin": None}, "z.dat": None}, "top.txt": None}
    _, order = fnt(tree, 0)
    contents = [("file " + p).encode() for p in order]
    write("named.narc", narc(contents, tree))
    for k, p in enumerate(order):
        lines.append(f"named {k} {p} {contents[k].decode().replace(' ', '_')}")
    with open(os.path.join(DATA, "narc.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")

    # A ROM: header, two ARM9 overlays (the first BLZ-compressed), named files, a NARC.
    over_plain = b"overlay zero " * 40
    over0 = blz(over_plain)
    over1 = b"overlay one, stored as it is"
    rom_tree = {"data": {"inner.narc": None, "hello.txt": None}, "readme": None}
    fnt_data, rom_order = fnt(rom_tree, 2)
    named = {"data/inner.narc": narc([b"first", b"second!"]), "data/hello.txt": b"hello from the rom", "readme": b"r"}
    file_list = [over0, over1] + [named[p] for p in rom_order]
    ovt = b""
    for oid, fid, comp, size in ((0, 0, True, len(over_plain)), (1, 1, False, len(over1))):
        ovt += u32(oid) + u32(0x02100000 + 0x1000 * oid) + u32(size) + u32(0) + u32(0) + u32(0) + u32(fid) + u32((0x01000000 if comp else 0) | len(file_list[fid]))
    arm9 = b"\0" * 64
    layout = bytearray(b"\0" * 0x200)
    pos = 0x200
    arm9_at = pos
    pos += len(arm9)
    ovt_at = pos
    pos += len(ovt)
    fnt_at = pad_to = pos
    pos += len(fnt_data)
    pos += (-pos) % 4
    fat_at = pos
    pos += 8 * len(file_list)
    starts = []
    blobs = b""
    for f in file_list:
        pos += (-pos) % 0x200
        starts.append(pos)
        blobs += b"\0" * (pos - (0x200 + len(blobs) + 0))
        pos += len(f)
    out = bytearray(layout)
    out[0:12] = b"TESTROM\0\0\0\0\0"
    out[0x0C:0x10] = b"ETST"
    out[0x10:0x12] = b"01"
    out[0x12] = 0
    out[0x1E] = 3
    struct.pack_into("<IIII", out, 0x20, arm9_at, 0x02000800, 0x02000000, len(arm9))
    struct.pack_into("<IIII", out, 0x30, 0, 0x02380000, 0x02380000, 0)
    struct.pack_into("<IIII", out, 0x40, fnt_at, len(fnt_data), fat_at, 8 * len(file_list))
    struct.pack_into("<II", out, 0x50, ovt_at, len(ovt))
    rom = bytearray(out)
    rom += arm9 + ovt + fnt_data
    rom = pad(bytes(rom), 4)
    fat = b"".join(u32(s) + u32(s + len(f)) for s, f in zip(starts, file_list))
    rom = bytearray(rom + fat)
    for s, f in zip(starts, file_list):
        rom += b"\0" * (s - len(rom))
        rom += f
    write("test.nds", bytes(rom))
    lines = [f"title TESTROM", f"code ETST", f"files {len(file_list)}"]
    for k, p in enumerate(rom_order):
        lines.append(f"file {k + 2} {p} {len(named[p])}")
    lines.append(f"overlay 0 {len(over_plain)}")
    lines.append(f"overlay 1 {len(over1)}")
    write("overlay0.bin", over_plain)
    write("overlay1.bin", over1)
    with open(os.path.join(DATA, "rom.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# 2D graphics: NCLR, NCGR, NSCR, NCER

def c5(v):
    return (v & 31) * 255 // 31


def rgb(c):
    return (c5(c), c5(c >> 5), c5(c >> 10))


def raw_image(w, h, px):
    """The expected-image format of the tests: width, height, then RGBA."""
    return u32(w) + u32(h) + bytes(v for p in px for v in p)


def nclr(colors, depth=3):
    data = b"".join(u16(c) for c in colors)
    ttlp = b"TTLP" + u32(0x18 + len(data)) + u32(depth) + u32(0) + u32(len(data)) + u32(0x10) + data
    return file_with_blocks(b"RLCN", [ttlp])


def ncgr(raw, bpp, tiles_w, tiles_h, linear):
    rahc = (b"RAHC" + u32(0x20 + len(raw)) + u16(tiles_h) + u16(tiles_w) + u32(3 if bpp == 4 else 4)
            + u16(0) + u16(0) + u32(1 if linear else 0) + u32(len(raw)) + u32(0x18) + raw)
    return file_with_blocks(b"RGCN", [rahc])


def pack_tiles(tiles, bpp):
    out = bytearray()
    for t in tiles:
        if bpp == 4:
            for k in range(0, 64, 2):
                out.append(t[k] | t[k + 1] << 4)
        else:
            out += bytes(t)
    return bytes(out)


def nscr(w, h, entries):
    data = b"".join(u16(e) for e in entries)
    nrcs = b"NRCS" + u32(0x14 + len(data)) + u16(w) + u16(h) + u32(0) + u32(len(data)) + data
    return file_with_blocks(b"RCSN", [nrcs])


def gen_graphics():
    rnd = random.Random(3)
    colors = [rnd.randrange(0x8000) for _ in range(64)]
    write("test.nclr", nclr(colors))
    pal = [rgb(c) for c in colors]
    # 4bpp tiles: 12 random tiles with some zeros (transparent)
    tiles = [[rnd.choice([0, 0] + list(range(1, 16))) for _ in range(64)] for _ in range(12)]
    write("tiles4.ncgr", ncgr(pack_tiles(tiles, 4), 4, 4, 3, False))
    # the sheet, 4 tiles wide (the file's width)
    w, h = 32, 24
    px = [(0, 0, 0, 0)] * (w * h)
    for i, t in enumerate(tiles):
        bx, by = (i % 4) * 8, (i // 4) * 8
        for y in range(8):
            for x in range(8):
                c = t[y * 8 + x]
                if c:
                    px[(by + y) * w + bx + x] = pal[c] + (255,)
    write("tiles4_sheet.rgba", raw_image(w, h, px))
    # 8bpp tiles, no dimensions in the file (sheet 32 tiles wide)
    tiles8 = [[rnd.choice([0] + list(range(1, 80))) for _ in range(64)] for _ in range(3)]
    write("tiles8.ncgr", ncgr(pack_tiles(tiles8, 8), 8, 0xFFFF, 0xFFFF, False))
    w, h = 256, 8
    px = [(0, 0, 0, 0)] * (w * h)
    for i, t in enumerate(tiles8):
        for y in range(8):
            for x in range(8):
                c = t[y * 8 + x]
                if c:
                    px[y * w + i * 8 + x] = (pal[c] if c < len(pal) else (255, 0, 255)) + (255,)
    write("tiles8_sheet.rgba", raw_image(w, h, px))
    # a linear 4bpp bitmap 16x8 (2 tiles wide, 1 high)
    lin = [rnd.choice([0] + list(range(1, 16))) for _ in range(16 * 8)]
    rawl = bytes(lin[k] | lin[k + 1] << 4 for k in range(0, len(lin), 2))
    write("linear.ncgr", ncgr(rawl, 4, 2, 1, True))
    px = [(pal[c] + (255,)) if c else (0, 0, 0, 0) for c in lin]
    write("linear_sheet.rgba", raw_image(16, 8, px))
    # a 32x24 screen over the 4bpp tiles, with flips, palettes 0..3 and a bad tile
    w, h = 32, 24
    entries = []
    for i in range(12):
        ti = rnd.randrange(12) if i != 5 else 1000
        entries.append(ti | rnd.randrange(2) << 10 | rnd.randrange(2) << 11 | rnd.randrange(4) << 12)
    write("screen.nscr", nscr(w, h, entries))
    for t0 in (False, True):
        px = [(0, 0, 0, 0)] * (w * h)
        for i, e in enumerate(entries):
            ti, hf, vf, pn = e & 0x3FF, e >> 10 & 1, e >> 11 & 1, e >> 12
            if ti >= len(tiles):
                continue
            bx, by = (i % 4) * 8, (i // 4) * 8
            for y in range(8):
                for x in range(8):
                    c = tiles[ti][y * 8 + x]
                    if c == 0 and t0:
                        continue
                    pi = pn * 16 + c
                    px[(by + (7 - y if vf else y)) * w + bx + (7 - x if hf else x)] = (pal[pi] if pi < len(pal) else (255, 0, 255)) + (255,)
        write(f"screen_t{int(t0)}.rgba", raw_image(w, h, px))
    # cells: two cells over the 4bpp tiles with 1D mapping (32K)
    sizes = {(0, 0): (8, 8), (0, 1): (16, 16), (1, 0): (16, 8), (2, 0): (8, 16)}
    cells = [[(-8, -8, 0, 1, 0, 0, 0, 1), (0, 4, 1, 0, 4, 1, 0, 2)],
             [(-4, -12, 2, 0, 6, 0, 1, 0), (2, -2, 0, 0, 11, 0, 0, 3)]]
    oams = b""
    tab = b""
    for objs in cells:
        tab += u16(len(objs)) + u16(0) + u32(len(oams))
        for x, y, shape, size, tile, hf, vf, palno in objs:
            a0 = (y & 0xFF) | shape << 14
            a1 = (x & 0x1FF) | hf << 12 | vf << 13 | size << 14
            a2 = tile | palno << 12
            oams += u16(a0) + u16(a1) + u16(a2)
    kbec_body = u16(len(cells)) + u16(0) + u32(0x18) + u32(0) + u32(0) + u32(0) + u32(0) + tab + oams
    write("cells.ncer", file_with_blocks(b"RECN", [b"KBEC" + u32(8 + len(kbec_body)) + kbec_body]))
    lines = []
    for ci, objs in enumerate(cells):
        x0 = min(o[0] for o in objs)
        y0 = min(o[1] for o in objs)
        x1 = max(o[0] + sizes[(o[2], o[3])][0] for o in objs)
        y1 = max(o[1] + sizes[(o[2], o[3])][1] for o in objs)
        w, h = x1 - x0, y1 - y0
        px = [(0, 0, 0, 0)] * (w * h)
        for x, y, shape, size, tile, hf, vf, palno in reversed(objs):
            ow, oh = sizes[(shape, size)]
            for yy in range(oh):
                for xx in range(ow):
                    t = tile + (yy // 8) * (ow // 8) + xx // 8
                    c = tiles[t][(yy % 8) * 8 + xx % 8] if t < len(tiles) else 0
                    if c == 0:
                        continue
                    dx = ow - 1 - xx if hf else xx
                    dy = oh - 1 - yy if vf else yy
                    pi = palno * 16 + c
                    px[(y - y0 + dy) * w + x - x0 + dx] = (pal[pi] if pi < len(pal) else (255, 0, 255)) + (255,)
        write(f"cell{ci}.rgba", raw_image(w, h, px))
        for x, y, shape, size, tile, hf, vf, palno in objs:
            ow, oh = sizes[(shape, size)]
            lines.append(f"oam {ci} {x} {y} {ow} {oh} {tile} {hf} {vf} {palno}")
    with open(os.path.join(DATA, "cells.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# 3D: NSBTX textures, NSBMD model

def nitro_dict(entries, unit):
    """entries: [(name, data bytes of `unit` length)]."""
    n = len(entries)
    tree = b"\0" * (4 * (n + 1))
    data_at = 8 + len(tree)
    body = u16(unit) + u16(4 + unit * n) + b"".join(d for _, d in entries) + b"".join(nm.encode().ljust(16, b"\0") for nm, _ in entries)
    size = data_at + len(body)
    return bytes([0, n]) + u16(size) + u16(8) + u16(data_at) + tree + body


def tex0(textures, palettes):
    """textures: [(name, fmt, w, h, color0, data, cmp_info or None)];
    palettes: [(name, colors)]. Returns a TEX0 block."""
    tex_data, cmp_data, cmp_info, pal_data = b"", b"", b"", b""
    tex_entries = []
    for name, fmt, w, h, c0, data, info in textures:
        if fmt == 5:
            off = len(cmp_data)
            cmp_data += pad(data, 8)
            cmp_info += pad(info, 4)
        else:
            off = len(tex_data)
            tex_data += pad(data, 8)
        p = (off >> 3) | (int(math.log2(w)) - 3) << 20 | (int(math.log2(h)) - 3) << 23 | fmt << 26 | (1 if c0 else 0) << 29
        tex_entries.append((name, u32(p) + u16(w) + u16(h)))
    pal_entries = []
    for name, cols in palettes:
        pal_entries.append((name, u16(len(pal_data) >> 3) + u16(0)))
        pal_data += pad(b"".join(u16(c) for c in cols), 8)
    tdict = nitro_dict(tex_entries, 8)
    pdict = nitro_dict(pal_entries, 4)
    head = 0x3C
    tdict_at = head
    pdict_at = tdict_at + len(pad(tdict, 4))
    tex_at = pdict_at + len(pad(pdict, 4))
    cmp_at = tex_at + len(tex_data)
    info_at = cmp_at + len(cmp_data)
    pal_at = info_at + len(cmp_info)
    h = bytearray(b"\0" * head)
    h[0:4] = b"TEX0"
    struct.pack_into("<I", h, 4, pal_at + len(pal_data))
    struct.pack_into("<HH", h, 0x0C, len(tex_data) >> 3, tdict_at)
    struct.pack_into("<I", h, 0x14, tex_at)
    struct.pack_into("<HH", h, 0x1C, len(cmp_data) >> 3, tdict_at)
    struct.pack_into("<II", h, 0x24, cmp_at, info_at)
    struct.pack_into("<III", h, 0x30, len(pal_data) >> 3, pdict_at, pal_at)
    return bytes(h) + pad(tdict, 4) + pad(pdict, 4) + tex_data + cmp_data + cmp_info + pal_data


def container(magic, blocks):
    n = len(blocks)
    head = 0x10 + 4 * n
    offs, body = [], b""
    for b in blocks:
        offs.append(head + len(body))
        body += pad(b, 4)
    return nitro_header(magic, 0xFEFF, head + len(body), n) + b"".join(u32(o) for o in offs) + body


def gen_textures():
    rnd = random.Random(11)
    textures, palettes, expected = [], [], []

    def pal(name, n):
        cols = [rnd.randrange(0x8000) for _ in range(n)]
        palettes.append((name, cols))
        return cols

    # 1 A3I5 8x8
    cols = pal("a3i5", 32)
    px = [rnd.randrange(256) for _ in range(64)]
    textures.append(("a3i5", 1, 8, 8, False, bytes(px), None))
    exp = []
    for v in px:
        a3 = v >> 5
        exp.append(rgb(cols[v & 31]) + (c5((a3 << 2) | (a3 >> 1)),))
    expected.append(("a3i5", 8, 8, exp))
    # 2 4-color 16x8, color 0 transparent
    cols = pal("four", 4)
    px = [rnd.randrange(4) for _ in range(128)]
    data = bytes(px[k] | px[k + 1] << 2 | px[k + 2] << 4 | px[k + 3] << 6 for k in range(0, 128, 4))
    textures.append(("four", 2, 16, 8, True, data, None))
    expected.append(("four", 16, 8, [(0, 0, 0, 0) if c == 0 else rgb(cols[c]) + (255,) for c in px]))
    # 3 16-color 8x16
    cols = pal("sixteen", 16)
    px = [rnd.randrange(16) for _ in range(128)]
    data = bytes(px[k] | px[k + 1] << 4 for k in range(0, 128, 2))
    textures.append(("sixteen", 3, 8, 16, False, data, None))
    expected.append(("sixteen", 8, 16, [rgb(cols[c]) + (255,) for c in px]))
    # 5 4x4 compressed 8x8: one block in each mode
    cols = pal("compressed", 16)
    words, infos = b"", b""
    exp = [None] * 64
    for blk in range(4):
        mode = blk
        base = blk * 2
        texels = [rnd.randrange(4) for _ in range(16)]
        word = 0
        for y in range(4):
            for x in range(4):
                word |= texels[y * 4 + x] << (y * 8 + x * 2)
        words += u32(word)
        infos += u16(base // 2 | mode << 14)
        c = [cols[base + k] for k in range(4)]
        five = [((v & 31), (v >> 5 & 31), (v >> 10 & 31)) for v in c]
        table = [five[0], five[1], five[2], five[3]]
        alpha = [255, 255, 255, 255]
        if mode == 0:
            alpha[3] = 0
        elif mode == 1:
            table[2] = tuple((five[0][k] + five[1][k]) // 2 for k in range(3))
            alpha[3] = 0
        elif mode == 3:
            table[2] = tuple((five[0][k] * 5 + five[1][k] * 3) // 8 for k in range(3))
            table[3] = tuple((five[0][k] * 3 + five[1][k] * 5) // 8 for k in range(3))
        bx, by = blk % 2, blk // 2
        for y in range(4):
            for x in range(4):
                k = texels[y * 4 + x]
                p = (by * 4 + y) * 8 + bx * 4 + x
                exp[p] = (0, 0, 0, 0) if alpha[k] == 0 else tuple(v * 255 // 31 for v in table[k]) + (255,)
    textures.append(("compressed", 5, 8, 8, False, words, infos))
    expected.append(("compressed", 8, 8, exp))
    # 6 A5I3 8x8
    cols = pal("a5i3", 8)
    px = [rnd.randrange(256) for _ in range(64)]
    textures.append(("a5i3", 6, 8, 8, False, bytes(px), None))
    expected.append(("a5i3", 8, 8, [rgb(cols[v & 7]) + (c5(v >> 3),) for v in px]))
    # 7 direct 8x8
    px = [rnd.randrange(0x10000) for _ in range(64)]
    textures.append(("direct", 7, 8, 8, False, b"".join(u16(v) for v in px), None))
    expected.append(("direct", 8, 8, [rgb(v) + (255 if v & 0x8000 else 0,) for v in px]))
    # 4 256-color 8x8 with a palette of 200 colors, the last: indices past it are magenta
    cols = pal("indexed", 200)
    px = [rnd.randrange(256) for _ in range(64)]
    textures.append(("indexed", 4, 8, 8, True, bytes(px), None))
    expected.append(("indexed", 8, 8, [(0, 0, 0, 0) if c == 0 else (rgb(cols[c]) if c < 200 else (255, 0, 255)) + (255,) for c in px]))
    t = tex0(textures, palettes)
    write("test.nsbtx", container(b"BTX0", [t]))
    lines = []
    for name, w, h, exp in expected:
        write(f"tex_{name}.rgba", raw_image(w, h, exp))
        fmt = next(x[1] for x in textures if x[0] == name)
        lines.append(f"tex {name} {fmt} {w} {h} tex_{name}.rgba")
    with open(os.path.join(DATA, "textures.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
    return t


def gpu_list(cmds):
    """cmds: [(op, [params])], packed four commands to a word."""
    out = b""
    for k in range(0, len(cmds), 4):
        group = cmds[k:k + 4]
        ops = [c[0] for c in group] + [0] * (4 - len(group))
        out += bytes(ops)
        for _, prm in group:
            out += b"".join(u32(p) for p in prm)
    return out


def fx(v, frac):
    return int(round(v * (1 << frac)))


def gen_model(tex_block):
    """An NSBMD: one model, two materials, two pieces (quads; a strip and triangles),
    with the expected triangles (positions times the scale)."""
    scale = 2.0
    q = [(-1, 0, -1), (1, 0, -1), (1, 0, 1), (-1, 0, 1)]
    c1 = []
    c1.append((0x40, [1]))
    c1.append((0x20, [0x7FFF]))
    for k, (x, y, z) in enumerate(q):
        c1.append((0x22, [(fx(k * 4, 4) & 0xFFFF) | (fx(8 - k * 2, 4) & 0xFFFF) << 16]))
        c1.append((0x21, [(fx(0.0, 9) & 0x3FF) | (fx(0.998, 9) & 0x3FF) << 10]))
        c1.append((0x23, [(fx(x, 12) & 0xFFFF) | (fx(y, 12) & 0xFFFF) << 16, fx(z, 12) & 0xFFFF]))
    c1.append((0x41, []))
    tris1 = [(q[0], q[1], q[2]), (q[0], q[2], q[3])]
    # strip with VTX_10, VTX_XY, VTX_DIFF, VTX_XZ; then a triangle with VTX_YZ
    c2 = [(0x40, [2])]
    v = (0.5, 0.25, -0.5)
    c2.append((0x24, [(fx(v[0], 6) & 0x3FF) | (fx(v[1], 6) & 0x3FF) << 10 | (fx(v[2], 6) & 0x3FF) << 20]))
    s = [v]
    v = (1.5, 2.0, v[2])
    c2.append((0x25, [(fx(1.5, 12) & 0xFFFF) | (fx(2.0, 12) & 0xFFFF) << 16]))
    s.append(v)
    d = (0.0625, -0.03125, 0.09375)
    c2.append((0x28, [(fx(d[0], 12) & 0x3FF) | (fx(d[1], 12) & 0x3FF) << 10 | (fx(d[2], 12) & 0x3FF) << 20]))
    v = (v[0] + d[0], v[1] + d[1], v[2] + d[2])
    s.append(v)
    c2.append((0x26, [(fx(-1.0, 12) & 0xFFFF) | (fx(3.0, 12) & 0xFFFF) << 16]))
    v = (-1.0, v[1], 3.0)
    s.append(v)
    tris2 = [(s[0], s[1], s[2]), (s[2], s[1], s[3])]
    c2.append((0x40, [0]))
    t = []
    c2.append((0x27, [(fx(1.0, 12) & 0xFFFF) | (fx(-2.0, 12) & 0xFFFF) << 16]))
    v = (v[0], 1.0, -2.0)
    t.append(v)
    c2.append((0x23, [(fx(4, 12) & 0xFFFF) | (fx(5, 12) & 0xFFFF) << 16, fx(6, 12) & 0xFFFF]))
    v = (4.0, 5.0, 6.0)
    t.append(v)
    c2.append((0x24, [(fx(-2, 6) & 0x3FF) | (fx(1, 6) & 0x3FF) << 10 | (fx(0.5, 6) & 0x3FF) << 20]))
    v = (-2.0, 1.0, 0.5)
    t.append(v)
    tris2.append(tuple(t))
    cmds = [gpu_list(c1), gpu_list(c2)]
    pieces_hdr_n = 2
    piece_dict = nitro_dict([("piece0", u32(0)), ("piece1", u32(0))], 4)
    piece_dict_len = len(pad(piece_dict, 4))
    piece_recs = b""
    rec_offs = []
    rec_size = 16
    bodies = b""
    for k, c in enumerate(cmds):
        rec_offs.append(piece_dict_len + rec_size * k)
    data_at = piece_dict_len + rec_size * len(cmds)
    for k, c in enumerate(cmds):
        here = rec_offs[k]
        piece_recs += u16(0) + u16(16) + u32(0) + u32(data_at + len(bodies) - here) + u32(len(c))
        bodies += pad(c, 4)
    piece_dict = nitro_dict([("piece0", u32(rec_offs[0])), ("piece1", u32(rec_offs[1]))], 4)
    pieces = pad(piece_dict, 4) + piece_recs + bodies
    # materials: dict of two (offsets unused here), pairing dicts for textures and palettes
    mat_dict = nitro_dict([("mat_floor", u32(0)), ("mat_wall", u32(0))], 4)
    head = 4
    md_at = head
    lists_at = md_at + len(pad(mat_dict, 4))
    lists = bytes([0, 1, 0, 0])
    tex_pair_at = lists_at + len(lists)
    tex_pair = nitro_dict([("sixteen", u16(lists_at) + bytes([1, 0])), ("four", u16(lists_at + 1) + bytes([1, 0]))], 4)
    pal_pair_at = tex_pair_at + len(pad(tex_pair, 4))
    pal_pair = nitro_dict([("sixteen", u16(lists_at) + bytes([1, 0])), ("four", u16(lists_at + 1) + bytes([1, 0]))], 4)
    mats = u16(tex_pair_at) + u16(pal_pair_at) + pad(mat_dict, 4) + lists + pad(tex_pair, 4) + pad(pal_pair, 4)
    render = bytes([0x04, 0, 0x05, 0, 0x0B, 0x44, 1, 0x05, 1, 0x01])
    model_head = 0x40
    render_at = model_head
    mats_at = render_at + len(pad(render, 4))
    pieces_at = mats_at + len(pad(mats, 4))
    m = bytearray(b"\0" * model_head)
    struct.pack_into("<IIII", m, 0, model_head + len(pad(render, 4)) + len(pad(mats, 4)) + len(pieces), render_at, mats_at, pieces_at)
    struct.pack_into("<I", m, 0x1C, fx(scale, 12))
    struct.pack_into("<I", m, 0x20, fx(1 / scale, 12))
    model = bytes(m) + pad(render, 4) + pad(mats, 4) + pieces
    mdl_dict = nitro_dict([("testmodel", u32(0))], 4)
    mdl_dict = nitro_dict([("testmodel", u32(8 + len(pad(mdl_dict, 4))))], 4)
    mdl0_body = pad(mdl_dict, 4) + model
    mdl0 = b"MDL0" + u32(8 + len(mdl0_body)) + mdl0_body
    write("test.nsbmd", container(b"BMD0", [mdl0, tex_block]))
    lines = ["model testmodel 2 2"]
    for mat, tex, tris in ((0, "sixteen", tris1), (1, "four", tris2)):
        for tri in tris:
            lines.append(f"tri {mat} {tex} " + " ".join(f"{c * scale:.6f}" for v in tri for c in v))
    with open(os.path.join(DATA, "model.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ref = None
    if "--ref" in sys.argv:
        ref = sys.argv[sys.argv.index("--ref") + 1]
    os.makedirs(DATA, exist_ok=True)
    gen_sdat(ref)
    gen_lz()
    gen_archives()
    gen_graphics()
    t = gen_textures()
    gen_model(t)


if __name__ == "__main__":
    main()
