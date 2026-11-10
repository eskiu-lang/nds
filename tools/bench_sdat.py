#!/usr/bin/env python3
"""Times <nds/sdat> against the Tallgrass engine's synthesizer on the same sequences.

    python3 -I tools/bench_sdat.py --ref RUST_BENCH --esk ESK_BENCH [--seconds 60]
        [--rounds 5] [--names A,B,...] FILE.sdat

RUST_BENCH is tools/sdat_bench.rs built against the engine (copy it to
engine/examples/ and run `cargo build --release --example sdat_bench`) and
ESK_BENCH is tools/sdat_bench.esk built with `eskiuc -O2`. Both render each
sequence looping for --seconds into a reused 4096-frame buffer and time only
the render calls. The two programs run in turn, --rounds times, and each
sequence keeps its fastest time on each side. Without --names the sequences
are the battle themes (names starting with SEQ_BA_, SEQ_BGM_VS_ or
SEQ_GS_VS_).

Each program also hashes its 16-bit output; the script reports the sequences
whose hash or length differs and exits 1 if any does. Nothing here is
committed data: the SDAT is read from where you have it.
"""
import argparse
import os
import subprocess
import sys

PREFIXES = ("SEQ_BA_", "SEQ_BGM_VS_", "SEQ_GS_VS_")


def seq_names(path):
    sys.dont_write_bytecode = True
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from compare_sdat import seq_names as names
    return names(path)


def run(cmd):
    """Runs one harness; returns {name: (frames, ms, hash)}."""
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    res = {}
    for line in out.splitlines():
        f = line.split()
        if len(f) == 7 and f[1] == "frames" and f[0] != "total":
            res[f[0]] = (int(f[2]), float(f[4]), f[6])
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True)
    ap.add_argument("--esk", required=True)
    ap.add_argument("--seconds", default="60")
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--names")
    ap.add_argument("sdat")
    a = ap.parse_args()
    if a.names:
        names = a.names.split(",")
    else:
        names = [n for n in seq_names(a.sdat) if n.startswith(PREFIXES)]
    if not names:
        print("no sequences to time (use --names)")
        return 1
    best = {"ref": {}, "esk": {}}
    first = {}
    differ = set()
    for _ in range(max(1, a.rounds)):
        for side, exe in (("ref", a.ref), ("esk", a.esk)):
            for name, (frames, ms, h) in run([exe, a.sdat, a.seconds, "1"] + names).items():
                b = best[side]
                b[name] = min(b.get(name, ms), ms)
                if name not in first:
                    first[name] = (frames, h)
                elif first[name] != (frames, h):
                    differ.add(name)
    rows = [n for n in names if n in best["ref"] and n in best["esk"]]
    print(f"{'sequence':32} {'frames':>9} {'engine ms':>10} {'eskiu ms':>10} {'ratio':>6}")
    tr = te = tf = 0
    for n in rows:
        r, e = best["ref"][n], best["esk"][n]
        tr, te, tf = tr + r, te + e, tf + first[n][0]
        ratio = f"{e / r:>6.2f}" if r > 0 else f"{'-':>6}"
        print(f"{n:32} {first[n][0]:>9} {r:>10.1f} {e:>10.1f} {ratio}")
    if rows and tr > 0 and tf > 0:
        print(f"{'total':32} {tf:>9} {tr:>10.1f} {te:>10.1f} {te / tr:>6.2f}")
        print(f"ns per frame: engine {tr * 1e6 / tf:.1f}, eskiu {te * 1e6 / tf:.1f}")
    for n in sorted(differ):
        print(f"{n}: output differs")
    missing = [n for n in names if n not in rows]
    if missing:
        print(f"{len(missing)} sequences not rendered by both: {', '.join(missing[:10])}")
    print(f"{len(rows)} sequences timed, {len(differ)} differ")
    return 1 if differ else 0


if __name__ == "__main__":
    sys.exit(main())
