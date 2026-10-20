#!/usr/bin/env python3
"""Compares <nds/graphics> with the Tallgrass extraction tools (tools/nds/g2d.py and
tools/bw_sprites.py), pixel by pixel, over the 2D files of a ROM's NARCs.

    python3 tools/compare_graphics.py --tools TALLGRASS/tools --esk build/g2d_render \
        ROM.nds NARC_PATH ...

build/g2d_render is tools/g2d_render.esk built with eskiuc. In each NARC, every NSCR is
drawn with the nearest NCGR and NCLR (by file index), every tiled NCGR as a tile sheet,
every linear NCGR as a bitmap atlas (as bw_sprites.atlas), and every NCER's objects
are compared with bw_sprites.cells. Needs Pillow and numpy (the tools import them).
Nothing is committed from the ROM: files go to a temporary directory.
"""
import argparse
import os
import struct
import subprocess
import sys
import tempfile


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tools", required=True)
    ap.add_argument("--esk", required=True)
    ap.add_argument("rom")
    ap.add_argument("narcs", nargs="+")
    a = ap.parse_args()
    sys.path.insert(0, a.tools)
    from nds import g2d
    from nds.fs import NdsFs, narc_files
    import bw_sprites as bw

    tmp = tempfile.mkdtemp()
    fs = NdsFs(a.rom)
    stats = {"screen": [0, 0], "sheet": [0, 0], "atlas": [0, 0], "cells": [0, 0]}

    def run_esk(args):
        out = os.path.join(tmp, "out.raw")
        if os.path.exists(out):
            os.remove(out)
        p = subprocess.run([a.esk] + args + ([] if args[0] == "cells" else []), capture_output=True, text=True)
        return p

    def load_raw():
        d = open(os.path.join(tmp, "out.raw"), "rb").read()
        w, h = struct.unpack_from("<II", d, 0)
        return w, h, d[8:]

    def same(img, kind, label):
        w, h, px = load_raw()
        ok = (w, h) == img.size and px == img.convert("RGBA").tobytes()
        stats[kind][0] += 1
        if not ok:
            stats[kind][1] += 1
            print(f"{label}: differs ({w}x{h} vs {img.size[0]}x{img.size[1]})")

    for narc in a.narcs:
        files = []
        for x in narc_files(fs.read(narc)):
            try:
                files.append(bw.unpack(x))
            except Exception:
                files.append(x)
        paths = []
        for i, f in enumerate(files):
            p = os.path.join(tmp, f"{i}.bin")
            open(p, "wb").write(f)
            paths.append(p)
        kinds = {m: [i for i, f in enumerate(files) if f[:4] == m] for m in (b"RCSN", b"RGCN", b"RLCN", b"RECN")}

        def near(i, m):
            c = kinds[m]
            return min(c, key=lambda k: abs(k - i)) if c else None

        out = os.path.join(tmp, "out.raw")
        for i in kinds[b"RCSN"]:
            g, p = near(i, b"RGCN"), near(i, b"RLCN")
            if g is None or p is None:
                continue
            for t0 in (False, True):
                try:
                    img = g2d.render_screen(g2d.screen(files[i]), g2d.tiles(files[g]), g2d.palette(files[p]), t0)
                except Exception:
                    continue
                r = run_esk(["screen", paths[i], paths[g], paths[p], out] + (["t"] if t0 else []))
                if r.returncode != 0:
                    print(f"{narc}/{i}: g2d_render failed: {r.stdout.strip()}")
                    stats["screen"][1] += 1
                    continue
                same(img, "screen", f"{narc}/{i} screen")
        for i in kinds[b"RGCN"]:
            p = near(i, b"RLCN")
            if p is None:
                continue
            d = files[i]
            off = d.index(b"RAHC")
            linear = struct.unpack_from("<I", d, off + 20)[0] & 1
            try:
                if linear:
                    if struct.unpack_from("<I", d, off + 12)[0] != 3:
                        continue
                    img = bw.atlas(d, bw.palette(files[p]))
                    kind = "atlas"
                else:
                    img = g2d.render_tiles(g2d.tiles(d), g2d.palette(files[p]))
                    kind = "sheet"
            except Exception:
                continue
            r = run_esk(["sheet", paths[i], paths[p], out])
            if r.returncode != 0:
                print(f"{narc}/{i}: g2d_render failed: {r.stdout.strip()}")
                stats[kind][1] += 1
                continue
            same(img, kind, f"{narc}/{i} {kind}")
        for i in kinds[b"RECN"]:
            try:
                ref = bw.cells(files[i])
            except Exception:
                continue
            r = run_esk(["cells", paths[i]])
            stats["cells"][0] += 1
            got = {}
            for line in r.stdout.split("\n"):
                if line.strip():
                    v = list(map(int, line.split()))
                    got.setdefault(v[0], []).append(v[1:])
            bad = r.returncode != 0 or len(got) > len(ref)
            for c, objs in enumerate(ref):
                mine = got.get(c, [])
                if len(mine) != len(objs):
                    bad = True
                    break
                for o, m in zip(objs, mine):
                    x, y, w, h, tile, hf, vf, mode, _pal = m
                    want = (o["x"], o["y"], o["w"], o["h"], o["u"], o["v"], o["hf"], o["vf"], o["eye"])
                    have = (x, y, w, h, (tile % 32) * 8, (tile // 32) * 8, bool(hf), bool(vf), mode == 1)
                    if want != have:
                        bad = True
            if bad:
                stats["cells"][1] += 1
                print(f"{narc}/{i}: cells differ")
        print(f"{narc}: done", flush=True)
    bad = 0
    for k, (n, d) in stats.items():
        print(f"{k}: {n} compared, {d} differ")
        bad += d
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
