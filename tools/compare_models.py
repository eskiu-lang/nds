#!/usr/bin/env python3
"""Compares <nds/model> with the Tallgrass tools (tools/nds/btx.py, tools/nds/nsbmd.py)
and, for the texture formats those tools skip, with apicula's PNGs.

    python3 tools/compare_models.py --tools TALLGRASS/tools --esk build/nitro_dump \
        [--apicula apicula] ROM.nds NARC_PATH ...

build/nitro_dump is tools/nitro_dump.esk built with eskiuc. For each BTX0/BMD0 file in
the NARCs: every texture btx.py decodes (formats 2, 3, 4, 7) must match pixel for pixel;
with --apicula, every texture apicula writes is compared with a tolerance (apicula
widens 5-bit colors and alphas in its own way), and the formats are counted; every
NSBMD's triangles must match nsbmd.read's, per texture, to 1/1000. Needs Pillow.
Nothing is committed from the ROM: files go to a temporary directory.
"""
import argparse
import collections
import os
import shutil
import struct
import subprocess
import sys
import tempfile


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tools", required=True)
    ap.add_argument("--esk", required=True)
    ap.add_argument("--apicula")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("rom")
    ap.add_argument("narcs", nargs="+")
    a = ap.parse_args()
    sys.path.insert(0, a.tools)
    sys.path.insert(0, os.path.join(a.tools, "nds"))
    from PIL import Image
    from nds import btx, nsbmd
    from nds.fs import NdsFs, narc_files
    import inspect
    import textwrap

    # nsbmd.py's BEGIN_VTXS (0x40) falls through to emit the previous vertex, which
    # adds a stray vertex at the start of every primitive list. Compare against a copy
    # with that fixed (one `continue`); <nds/model> follows the GPU.
    src = textwrap.dedent(inspect.getsource(nsbmd._triangles))
    fixed = src.replace("prim, strip = p[0] & 3, []", "prim, strip = p[0] & 3, []\n            continue")
    assert fixed != src
    exec(compile(fixed, "nsbmd_fixed", "exec"), nsbmd.__dict__)

    tmp = tempfile.mkdtemp()
    fs = NdsFs(a.rom)
    st = collections.Counter()
    worst = collections.Counter()

    for narc in a.narcs:
        files = narc_files(fs.read(narc))
        if a.limit:
            files = files[:a.limit]
        for i, f in enumerate(files):
            if f[:4] not in (b"BTX0", b"BMD0"):
                continue
            src = os.path.join(tmp, "in.nsbtx" if f[:4] == b"BTX0" else "in.nsbmd")
            for p in ("in.nsbtx", "in.nsbmd"):
                if os.path.exists(os.path.join(tmp, p)):
                    os.remove(os.path.join(tmp, p))
            open(src, "wb").write(f)
            out = os.path.join(tmp, "esk")
            shutil.rmtree(out, ignore_errors=True)
            os.makedirs(out)
            r = subprocess.run([a.esk, "textures", src, out], capture_output=True, text=True)
            out_btx = os.path.join(tmp, "esk_btx")
            shutil.rmtree(out_btx, ignore_errors=True)
            os.makedirs(out_btx)
            subprocess.run([a.esk, "textures", src, out_btx, "btx"], capture_output=True)
            label = f"{narc}/{i}"
            if r.returncode != 0:
                print(f"{label}: nitro_dump failed: {r.stdout.strip()}")
                st["fail"] += 1
                continue
            fmts = {}
            for line in r.stdout.split("\n"):
                if line.strip():
                    name, fmt, _w, _h = line.rsplit(" ", 3)
                    fmts[name] = int(fmt)

            def mine(name, where=out):
                d = open(os.path.join(where, name + ".raw"), "rb").read()
                w, h = struct.unpack_from("<II", d, 0)
                return w, h, d[8:]

            try:
                ref = btx.read(f, 0, True)
            except Exception:
                ref = []
            for name, img in ref:
                w, h, px = mine(name, out_btx)
                st["btx"] += 1
                if (w, h) != img.size or px != img.tobytes():
                    st["btx differ"] += 1
                    print(f"{label} {name}: differs from btx.py")
            if a.apicula:
                ad = os.path.join(tmp, "ap")
                shutil.rmtree(ad, ignore_errors=True)
                subprocess.run([a.apicula, "convert", src, "--more-textures", "-o", ad],
                               capture_output=True)
                for png in sorted(os.listdir(ad)) if os.path.isdir(ad) else []:
                    name = png[:-4]
                    if not png.endswith(".png") or name not in fmts:
                        continue
                    img = Image.open(os.path.join(ad, png)).convert("RGBA")
                    w, h, px = mine(name)
                    fmt = fmts[name]
                    st[f"apicula format {fmt}"] += 1
                    if (w, h) != img.size:
                        st["apicula differ"] += 1
                        print(f"{label} {name}: size differs from apicula")
                        continue
                    ref_px = img.tobytes()
                    d = 0
                    for k in range(0, len(px), 4):
                        if ref_px[k + 3] == 0 and px[k + 3] == 0:
                            continue
                        d = max(d, max(abs(px[k + c] - ref_px[k + c]) for c in range(4)))
                    worst[fmt] = max(worst[fmt], d)
                    if d > 8:
                        st["apicula differ"] += 1
                        print(f"{label} {name} (format {fmt}): differs from apicula by {d}")
            if f[:4] == b"BMD0":
                try:
                    geo = nsbmd.read(f)
                except Exception:
                    continue
                r = subprocess.run([a.esk, "model", src], capture_output=True, text=True)
                st["models"] += 1
                got = collections.defaultdict(list)
                for line in r.stdout.split("\n"):
                    p = line.split(" ")
                    if len(p) < 10:
                        continue
                    got[p[0]].append(tuple(round(float(x), 2) for x in p[1:10]))
                bad = r.returncode != 0
                for tex, tris in geo.items():
                    want = sorted(tuple(round(c, 2) for v in t for c in v) for t in tris)
                    have = sorted(got.get(tex, []))
                    if len(want) != len(have) or any(max(abs(x - y) for x, y in zip(p, q)) > 0.011 for p, q in zip(want, have)):
                        bad = True
                if len(got) != len(geo):
                    bad = True
                if bad:
                    st["models differ"] += 1
                    print(f"{label}: model differs from nsbmd.py")
        print(f"{narc}: done", flush=True)
    for k in sorted(st):
        print(f"{k}: {st[k]}")
    for k in sorted(worst):
        print(f"largest difference from apicula, format {k}: {worst[k]}")
    return 1 if st["btx differ"] or st["models differ"] or st["fail"] or st["apicula differ"] else 0


if __name__ == "__main__":
    sys.exit(main())
