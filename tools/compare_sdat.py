#!/usr/bin/env python3
"""Compares <nds/sdat> with the Tallgrass engine's synthesizer, sample by sample.

    python3 -I tools/compare_sdat.py --ref SDAT_WAV --esk SDAT_PLAY [--seconds 10]
        [--loop] [--names A,B,...] [--limit N] FILE.sdat ...

SDAT_WAV is the engine's example (engine/examples/sdat_wav.rs, built with
`cargo build --release --example sdat_wav`) and SDAT_PLAY this package's
examples/sdat_play.esk built with eskiuc. Both render each sequence (every named
one in the file, or those of --names) to a WAV; the script reports the sequences
whose output differs in length or in any sample, and the largest difference.
Nothing here is committed data: the SDAT files are read from where you have them.
"""
import argparse
import os
import struct
import subprocess
import sys
import tempfile


def seq_names(path):
    d = open(path, "rb").read()
    symb = struct.unpack_from("<I", d, 0x10)[0]
    if symb == 0:
        return []
    r = struct.unpack_from("<I", d, symb + 8)[0]
    n = struct.unpack_from("<I", d, symb + r)[0]
    out = []
    for i in range(n):
        o = struct.unpack_from("<I", d, symb + r + 4 + 4 * i)[0]
        if o:
            e = d.index(b"\0", symb + o)
            out.append(d[symb + o:e].decode("latin-1"))
    return out


def samples(path):
    d = open(path, "rb").read()
    if d[:4] != b"RIFF":
        return None
    n = struct.unpack_from("<I", d, 40)[0]
    return struct.unpack_from(f"<{n // 2}h", d, 44)


def render(cmd):
    p = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return p.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True)
    ap.add_argument("--esk", required=True)
    ap.add_argument("--seconds", default="10")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--names")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("sdat", nargs="+")
    a = ap.parse_args()
    tmp = tempfile.mkdtemp()
    ref_wav, esk_wav = os.path.join(tmp, "ref.wav"), os.path.join(tmp, "esk.wav")
    total = differ = skipped = 0
    worst = 0
    samples_total = 0
    for path in a.sdat:
        names = a.names.split(",") if a.names else seq_names(path)
        if a.limit:
            names = names[:a.limit]
        for name in names:
            extra = ["loop"] if a.loop else []
            for f in (ref_wav, esk_wav):
                if os.path.exists(f):
                    os.remove(f)
            rr = render([a.ref, path, name, a.seconds, ref_wav] + extra)
            re = render([a.esk, path, name, a.seconds, esk_wav] + extra)
            if rr != 0 or not os.path.exists(ref_wav):
                # the engine cannot open it (no bank, not an SSEQ): ours must fail too
                skipped += 1
                if re == 0:
                    print(f"{path} {name}: the engine refuses it, sdat_play renders it")
                    differ += 1
                continue
            total += 1
            if re != 0:
                print(f"{path} {name}: sdat_play failed")
                differ += 1
                continue
            r, e = samples(ref_wav), samples(esk_wav)
            samples_total += len(r)
            if len(r) != len(e):
                print(f"{path} {name}: length {len(e)} vs {len(r)}")
                differ += 1
                continue
            d = max((abs(x - y) for x, y in zip(r, e)), default=0)
            if d:
                n = sum(1 for x, y in zip(r, e) if x != y)
                print(f"{path} {name}: max difference {d}, {n} samples differ")
                differ += 1
                worst = max(worst, d)
        print(f"{path}: done", flush=True)
    print(f"{total} sequences rendered ({samples_total} samples), {differ} differ, "
          f"{skipped} refused by the engine, largest difference {worst}")
    return 1 if differ else 0


if __name__ == "__main__":
    sys.exit(main())
