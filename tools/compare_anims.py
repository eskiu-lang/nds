#!/usr/bin/env python3
"""Compares <nds/graphics>'s NANR and NMAR reader with the Tallgrass extraction tools
(tools/nds/g2d.py's cell_anims), sequence by sequence and frame by frame, over every
cell animation in a ROM's NARCs; reads every NMCR (no reference tool reads them) and
renders every frame of each NANR with the nearest NCER, NCGR and NCLR of its NARC.

    python3 tools/compare_anims.py --tools TALLGRASS/tools --esk build/anim_dump ROM.nds

build/anim_dump is tools/anim_dump.esk built with eskiuc. Needs Pillow and numpy (the
tools import them). The tools are run as a black box: only their output is used.
Nothing is committed from the ROM: files go to a temporary directory.
"""
import argparse
import os
import subprocess
import sys
import tempfile


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tools", required=True)
    ap.add_argument("--esk", required=True)
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("rom")
    a = ap.parse_args()
    sys.path.insert(0, a.tools)
    from nds import g2d
    from nds.fs import NdsFs, narc_files
    import bw_sprites as bw

    tmp = tempfile.mkdtemp()
    fs = NdsFs(a.rom)
    st = {"anims": [0, 0], "frames": 0, "nmcr": [0, 0], "render": [0, 0], "rendered": 0}

    def run(args):
        return subprocess.run([a.esk] + args, capture_output=True, text=True)

    for narc in sorted(fs.files):
        d = fs.read(narc)
        if d[:4] != b"NARC":
            continue
        try:
            raw = narc_files(d)
        except Exception:
            continue
        files = []
        for x in raw:
            if x[:1] in (b"\x10", b"\x11"):
                try:
                    x = bw.unpack(x)
                except Exception:
                    pass
            files.append(x)
        kinds = {m: [i for i, f in enumerate(files) if f[:4] == m] for m in (b"RNAN", b"RAMN", b"RCMN", b"RECN", b"RGCN", b"RLCN")}
        if not (kinds[b"RNAN"] or kinds[b"RAMN"] or kinds[b"RCMN"]):
            continue

        def path(i):
            p = os.path.join(tmp, f"{i}.bin")
            open(p, "wb").write(files[i])
            return p

        def near(i, m):
            c = kinds[m]
            return min(c, key=lambda k: abs(k - i)) if c else None

        for i in kinds[b"RNAN"] + kinds[b"RAMN"]:
            st["anims"][0] += 1
            try:
                ref = g2d.cell_anims(files[i])
            except Exception as e:
                ref = None
            r = run(["nanr", path(i)])
            got = []
            for line in r.stdout.splitlines():
                v = line.split()
                if v[0] == "seq":
                    got.append({"type": int(v[2]) | (int(v[3]) << 16), "mode": int(v[4]), "frames": []})
                else:
                    dur, cell, rot, sx, sy, tx, ty = map(int, v)
                    got[-1]["frames"].append((dur, cell, rot, sx / 4096, sy / 4096, tx, ty))
            if r.returncode != 0 or ref is None or got != ref:
                st["anims"][1] += 1
                print(f"{narc}/{i}: differs ({r.stdout.strip()[:80]}; reference {'ok' if ref is not None else 'failed'})")
                continue
            st["frames"] += sum(len(s["frames"]) for s in got)
            if a.no_render or kinds[b"RNAN"] == [] or files[i][:4] != b"RNAN":
                continue
            c, g, p = near(i, b"RECN"), near(i, b"RGCN"), near(i, b"RLCN")
            if c is None or g is None or p is None:
                continue
            st["render"][0] += 1
            r = run(["render", path(i), path(c), path(g), path(p)])
            if r.returncode != 0:
                st["render"][1] += 1
                print(f"{narc}/{i}: render failed: {r.stdout.strip()}")
            else:
                st["rendered"] += int(r.stdout.split()[0])
        for i in kinds[b"RCMN"]:
            st["nmcr"][0] += 1
            r = run(["nmcr", path(i)])
            if r.returncode != 0:
                st["nmcr"][1] += 1
                print(f"{narc}/{i}: nmcr failed: {r.stdout.strip()}")
    print(f"animations: {st['anims'][0]} compared ({st['frames']} frames), {st['anims'][1]} differ")
    print(f"multi-cells: {st['nmcr'][0]} read, {st['nmcr'][1]} failed")
    print(f"renders: {st['render'][0]} files ({st['rendered']} frames), {st['render'][1]} failed")
    return 1 if st["anims"][1] or st["nmcr"][1] or st["render"][1] else 0


if __name__ == "__main__":
    sys.exit(main())
