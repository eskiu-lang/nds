#!/usr/bin/env python3
"""Compares <nds/spl> with the Tallgrass engine's particle converter on the SPL archives
of a ROM.

    python3 tools/compare_spl.py --tools TALLGRASS/tools --engine ENGINE \\
        --esk build/spl_json ROM.nds

ENGINE is the Tallgrass engine binary (engine/target/release/tallgrass-engine), run only
as a black box (`--spa-to-json DIR OUT`); build/spl_json is tools/spl_json.esk built with
eskiuc. Every file of the ROM, and every file of its NARCs, that starts with " APS" is
converted by both; each JSON file must be byte for byte the same and each PNG the same
pixels (Pillow). Nothing from the ROM is kept: files go to a temporary directory.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tools", required=True)
    ap.add_argument("--engine", required=True)
    ap.add_argument("--esk", required=True)
    ap.add_argument("rom")
    a = ap.parse_args()
    sys.path.insert(0, a.tools)
    from PIL import Image
    from nds.fs import NdsFs, narc_files

    fs = NdsFs(a.rom)
    tmp = tempfile.mkdtemp()
    src = os.path.join(tmp, "spa")
    os.makedirs(src)
    n = 0
    for path in sorted(fs.files):
        data = fs.read(path)
        items = [(path, data)]
        if data[:4] == b"NARC":
            try:
                items = [(f"{path}_{i:04d}", x) for i, x in enumerate(narc_files(data))]
            except Exception:
                items = []
        for name, x in items:
            if x[:4] == b" APS":
                open(os.path.join(src, name.replace("/", "_") + ".spa"), "wb").write(x)
                n += 1
    ref, mine = os.path.join(tmp, "ref"), os.path.join(tmp, "esk")
    subprocess.run([a.engine, "--spa-to-json", src, ref], check=True, capture_output=True)
    r = subprocess.run([a.esk, src, mine], capture_output=True, text=True)
    print(r.stdout.strip().split("\n")[-1])
    same_json = differ_json = same_png = differ_png = 0
    for f in sorted(os.listdir(ref)):
        p, q = os.path.join(ref, f), os.path.join(mine, f)
        if f.endswith(".json"):
            if os.path.exists(q) and open(p, "rb").read() == open(q, "rb").read():
                same_json += 1
            else:
                differ_json += 1
                print(f"{f}: JSON differs")
        elif f.endswith(".png"):
            ok = os.path.exists(q)
            if ok:
                x, y = Image.open(p).convert("RGBA"), Image.open(q).convert("RGBA")
                ok = x.size == y.size and x.tobytes() == y.tobytes()
            if ok:
                same_png += 1
            else:
                differ_png += 1
                print(f"{f}: image differs")
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"archives: {n}")
    print(f"JSON identical: {same_json}, different: {differ_json}")
    print(f"PNG identical: {same_png}, different: {differ_png}")
    return 1 if differ_json or differ_png else 0


if __name__ == "__main__":
    sys.exit(main())
