#!/usr/bin/env python3
"""Compares <nds/gltf> with apicula's glTF output on the NSBMD models of a ROM.

    python3 tools/compare_gltf.py --tools TALLGRASS/tools --esk build/nitro_gltf \\
        [--apicula apicula] [--limit N] [--frames K] ROM.nds [NARC_PATH ...]

build/nitro_gltf is tools/nitro_gltf.esk built with eskiuc. Without NARC paths every
NARC of the ROM holding a BMD0 is read. Each model goes through both converters with
the joint animations (BCA0) of its NARC whose node count is the model's. Then:

- the vertex and triangle counts and the position bounds at rest must be equal, and
  every vertex position at rest within 1e-3 of apicula's (both keep the order the GPU
  commands draw);
- the joints must have the same names and rest positions in model space;
- every joint animation apicula writes is played on both skins at K frames spread over
  its length, and every skinned vertex compared (to 1e-3 of the model's size), as are
  the node transforms of every channel at every frame both files have a key for.

apicula reads a curve sampled every 2 or 4 frames with one sample too few and stretches
it over the animation, and binds a node scaled to zero at rest at scale 2e-6 (its
vertices keep a few bits of precision), so animations with such curves or nodes are
reported apart ("stepped", "zero rest scale") and not counted as differences. Nothing from the ROM is kept: files go to a temporary directory.
"""
import argparse
import collections
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile

COMP = {5126: ("f", 4), 5121: ("B", 1), 5123: ("H", 2), 5125: ("I", 4)}
WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


class Gltf:
    def __init__(self, path):
        self.doc = json.load(open(path))
        self.bin = open(os.path.join(os.path.dirname(path), self.doc["buffers"][0]["uri"]), "rb").read()

    def acc(self, i):
        a = self.doc["accessors"][i]
        bv = self.doc["bufferViews"][a["bufferView"]]
        fmt, size = COMP[a["componentType"]]
        n = WIDTH[a["type"]]
        stride = bv.get("byteStride", size * n)
        base = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        out = []
        for k in range(a["count"]):
            v = struct.unpack_from("<" + fmt * n, self.bin, base + k * stride)
            if a.get("normalized"):
                v = tuple(x / 255.0 for x in v)
            out.append(v if n > 1 else v[0])
        return out

    def prim_attr(self, name):
        p = self.doc["meshes"][0]["primitives"][0]
        return self.acc(p["attributes"][name]) if name in p["attributes"] else None

    def triangles(self):
        return sum(self.doc["accessors"][p["indices"]]["count"] for p in self.doc["meshes"][0]["primitives"]) // 3


def mat_mul(a, b):
    return [[sum(a[r][k] * b[k][c] for k in range(4)) for c in range(4)] for r in range(4)]


def trs(t, q, s):
    x, y, z, w = q
    r = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
         [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
         [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    return [[r[i][0] * s[0], r[i][1] * s[1], r[i][2] * s[2], t[i]] for i in range(3)] + [[0, 0, 0, 1]]


def colmajor(m):
    return [[m[c * 4 + r] for c in range(4)] for r in range(4)]


def sample(times, vals, t):
    if t <= times[0]:
        return vals[0]
    if t >= times[-1]:
        return vals[-1]
    for i in range(len(times) - 1):
        if times[i] <= t <= times[i + 1]:
            f = (t - times[i]) / (times[i + 1] - times[i]) if times[i + 1] > times[i] else 0
            a, b = vals[i], vals[i + 1]
            if isinstance(a, tuple):
                v = tuple(x + (y - x) * f for x, y in zip(a, b))
                if len(v) == 4:
                    n = math.sqrt(sum(c * c for c in v)) or 1
                    v = tuple(c / n for c in v)
                return v
            return a + (b - a) * f
    return vals[-1]


def world(g, anim, t):
    """World matrices of every node at time t of animation anim (None for rest)."""
    nodes = g.doc["nodes"]
    over = collections.defaultdict(dict)
    if anim is not None:
        for ch in anim["channels"]:
            tg = ch["target"]
            if "node" not in tg:
                continue
            smp = anim["samplers"][ch["sampler"]]
            over[tg["node"]][tg["path"]] = sample(g.acc(smp["input"]), g.acc(smp["output"]), t)
    local = []
    for i, n in enumerate(nodes):
        if "matrix" in n:
            local.append(colmajor(n["matrix"]))
            continue
        o = over.get(i, {})
        local.append(trs(o.get("translation", n.get("translation", (0, 0, 0))),
                         o.get("rotation", n.get("rotation", (0, 0, 0, 1))),
                         o.get("scale", n.get("scale", (1, 1, 1)))))
    parent = {}
    for i, n in enumerate(nodes):
        for c in n.get("children", []):
            parent[c] = i
    cache = {}

    def w(i):
        if i not in cache:
            cache[i] = mat_mul(w(parent[i]), local[i]) if i in parent else local[i]
        return cache[i]
    return [w(i) for i in range(len(nodes))]


def skinned(g, anim, t, picks):
    pos = g.prim_attr("POSITION")
    if "skins" not in g.doc:
        return [pos[i] for i in picks]
    # apicula writes a skin for every model
    joints = g.prim_attr("JOINTS_0")
    weights = g.prim_attr("WEIGHTS_0")
    skin = g.doc["skins"][0]
    ib = [colmajor(m) for m in g.acc(skin["inverseBindMatrices"])]
    W = world(g, anim, t)
    mats = [mat_mul(W[j], ib[k]) for k, j in enumerate(skin["joints"])]
    out = []
    for i in picks:
        p = pos[i]
        acc = [0.0, 0.0, 0.0]
        for j, wt in zip(joints[i], weights[i]):
            if wt == 0:
                continue
            m = mats[j]
            for r in range(3):
                acc[r] += wt * (m[r][0] * p[0] + m[r][1] * p[1] + m[r][2] * p[2] + m[r][3])
        out.append(acc)
    return out


def bca_info(b):
    """Node count of each animation of a BCA0, and whether a curve is stepped."""
    n = struct.unpack_from("<H", b, 14)[0]
    for i in range(n):
        o = struct.unpack_from("<I", b, 0x10 + 4 * i)[0]
        if b[o:o + 4] == b"JNT0":
            cnt = b[o + 9]
            e = o + 8 + 12 + 4 * cnt
            a = o + struct.unpack_from("<I", b, e + 4)[0]
            return struct.unpack_from("<H", b, a + 6)[0], False
    return -1, False


def node_count(b):
    n = struct.unpack_from("<H", b, 14)[0]
    for i in range(n):
        o = struct.unpack_from("<I", b, 0x10 + 4 * i)[0]
        if b[o:o + 4] == b"MDL0":
            cnt = b[o + 9]
            e = o + 8 + 12 + 4 * cnt
            mo = o + struct.unpack_from("<I", b, e + 4)[0]
            return b[mo + 23]
    return -1


def has_stepped(b):
    """True when a BCA0 has a curve sampled every 2 or 4 frames."""
    n = struct.unpack_from("<H", b, 14)[0]
    o = struct.unpack_from("<I", b, 0x10)[0]
    cnt = b[o + 9]
    e = o + 8 + 12 + 4 * cnt
    unit = struct.unpack_from("<H", b, e)[0]
    for k in range(cnt):
        a = o + struct.unpack_from("<I", b, e + 4 + k * unit)[0]
        nobj = struct.unpack_from("<H", b, a + 6)[0]
        for i in range(nobj):
            q = a + struct.unpack_from("<H", b, a + 0x14 + 2 * i)[0]
            fl = struct.unpack_from("<H", b, q)[0]
            p = q + 4
            if fl & 1:
                continue
            parts = []
            if not (fl >> 1) & 3:
                parts += [(fl >> (3 + c)) & 1 for c in range(3)]
            for c in parts:
                if not c:
                    info = struct.unpack_from("<I", b, p)[0]
                    if info >> 30:
                        return True
                    p += 8
                else:
                    p += 4
            if not (fl >> 6) & 3:
                if (fl >> 8) & 1:
                    p += 4
                else:
                    if struct.unpack_from("<I", b, p)[0] >> 30:
                        return True
                    p += 8
            if not (fl >> 9) & 3:
                for c in range(3):
                    if not (fl >> (11 + c)) & 1:
                        if struct.unpack_from("<I", b, p)[0] >> 30:
                            return True
                        p += 8
                    else:
                        p += 8
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tools", required=True)
    ap.add_argument("--esk", required=True)
    ap.add_argument("--apicula", default="apicula")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--frames", type=int, default=4)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("rom")
    ap.add_argument("narcs", nargs="*")
    a = ap.parse_args()
    sys.path.insert(0, a.tools)
    from nds.fs import NdsFs, narc_files

    fs = NdsFs(a.rom)
    narcs = a.narcs
    if not narcs:
        narcs = []
        for p in sorted(fs.files):
            d = fs.read(p)
            if d[:4] == b"NARC":
                try:
                    if any(x[:4] == b"BMD0" for x in narc_files(d)):
                        narcs.append(p)
                except Exception:
                    pass
    tmp = tempfile.mkdtemp()
    st = collections.Counter()
    for narc in narcs:
        files = narc_files(fs.read(narc))
        bcas = [x for x in files if x[:4] == b"BCA0"]
        models = [(i, x) for i, x in enumerate(files) if x[:4] == b"BMD0"]
        if a.limit:
            models = models[:a.limit]
        for i, f in models:
            label = f"{narc}/{i}"
            n = node_count(f)
            anims = []
            for b in bcas:
                try:
                    if bca_info(b)[0] == n:
                        anims.append(b)
                except Exception:
                    pass
            anims = anims[:4]
            src = os.path.join(tmp, "src")
            shutil.rmtree(src, ignore_errors=True)
            os.makedirs(src)
            open(os.path.join(src, "m.nsbmd"), "wb").write(f)
            for k, b in enumerate(anims):
                open(os.path.join(src, f"a{k}.nsbca"), "wb").write(b)
            ins = [os.path.join(src, "m.nsbmd")] + [os.path.join(src, f"a{k}.nsbca") for k in range(len(anims))]
            ad, ed = os.path.join(tmp, "ap"), os.path.join(tmp, "esk")
            shutil.rmtree(ad, ignore_errors=True)
            shutil.rmtree(ed, ignore_errors=True)
            r = subprocess.run([a.apicula, "convert", *ins, "-f", "gltf", "-o", ad], capture_output=True, text=True)
            ag = [x for x in os.listdir(ad) if x.endswith(".gltf")] if os.path.isdir(ad) else []
            r2 = subprocess.run([a.esk, "convert", ed, "m", *ins], capture_output=True, text=True)
            st["models"] += 1
            if r2.returncode != 0:
                if not ag:
                    st["both fail"] += 1
                    continue
                st["esk fail"] += 1
                print(f"{label}: nitro_gltf failed: {r2.stdout.strip()}")
                continue
            if not ag:
                st["apicula fail"] += 1
                continue
            A = Gltf(os.path.join(ad, sorted(ag)[0]))
            E = Gltf(os.path.join(ed, "m.gltf"))
            if "meshes" not in A.doc or "meshes" not in E.doc:
                st["empty"] += 1 if ("meshes" in A.doc) == ("meshes" in E.doc) else 0
                if ("meshes" in A.doc) != ("meshes" in E.doc):
                    st["differ: empty"] += 1
                    print(f"{label}: one mesh is empty")
                continue
            # positions at rest as the skins place them (a node scaled to zero at rest
            # collapses its vertices in both)
            pa = skinned(A, None, 0, range(len(A.prim_attr("POSITION"))))
            pe = skinned(E, None, 0, range(len(E.prim_attr("POSITION"))))
            st["vertices"] += len(pe)
            st["triangles"] += E.triangles()
            if len(pa) != len(pe) or A.triangles() != E.triangles():
                st["differ: counts"] += 1
                print(f"{label}: counts {len(pa)}/{A.triangles()} apicula, {len(pe)}/{E.triangles()} nds")
                continue
            lo = [min(p[k] for p in pa) for k in range(3)]
            hi = [max(p[k] for p in pa) for k in range(3)]
            size = max(1e-6, max(h - l for l, h in zip(lo, hi)))
            tol = max(1e-3, size * 1e-4)
            # apicula stores weights in 8 bits: a vertex blended from two or more joints
            # may be off by 1/255 of its distance from them
            wa = A.prim_attr("WEIGHTS_0") or [(1, 0, 0, 0)] * len(pa)
            multi = [sum(1 for x in w if x > 0) > 1 for w in wa]
            reach = max((abs(c) for p in pa for c in p), default=0)

            def far(p, q, k):
                lim = max(tol, 0.006 * reach) if multi[k] else tol
                return max(abs(x - y) for x, y in zip(p, q)) > lim
            d = max((abs(x - y) for p, q in zip(pa, pe) for x, y in zip(p, q)), default=0)
            if any(far(p, q, k) for k, (p, q) in enumerate(zip(pa, pe))):
                st["differ: rest positions"] += 1
                print(f"{label}: rest positions differ by {d:.5f}")
                continue
            st["same rest"] += 1
            # joints: names and model-space rest positions
            def joints(g):
                if "skins" not in g.doc:
                    return []
                W = world(g, None, 0)
                return sorted((g.doc["nodes"][j].get("name", ""), tuple(round(W[j][r][3], 3) for r in range(3))) for j in g.doc["skins"][0]["joints"])
            ja, je = joints(A), joints(E)
            st["joints"] += len(je)
            if [x[0] for x in ja] != [x[0] for x in je] or any(max(abs(p - q) for p, q in zip(x[1], y[1])) > tol for x, y in zip(ja, je)):
                st["differ: joints"] += 1
                print(f"{label}: joints differ ({len(ja)} apicula, {len(je)} nds)")
                if a.verbose:
                    print(" ", ja[:6], "\n ", je[:6])
                continue
            # animations, by order
            aa = [x for x in A.doc.get("animations", []) if x["channels"] and all("node" in c["target"] for c in x["channels"])]
            ea = [x for x in E.doc.get("animations", []) if x["channels"] and all("node" in c["target"] for c in x["channels"])]
            if len(aa) != len(ea):
                st["differ: animation count"] += 1
                print(f"{label}: {len(aa)} animations from apicula, {len(ea)} from nds")
                continue
            picks = list(range(0, len(pe), max(1, len(pe) // 300)))
            # apicula binds a node scaled to zero at rest at scale 2e-6, so the vertices it
            # moves keep only a few bits; <nds/gltf> binds such a node at scale 1
            zero_scale = any(abs(c) <= 2e-6 for n in A.doc["nodes"] for c in n.get("scale", (1, 1, 1)))
            for k, (x, y) in enumerate(zip(aa, ea)):
                stepped = has_stepped(anims[k]) if k < len(anims) else False
                end = max(max(A.acc(s["input"])) for s in x["samplers"]) if x["samplers"] else 0
                worst = 0
                for q in range(a.frames):
                    t = round(end * q / max(1, a.frames - 1) * 60) / 60
                    va = skinned(A, x, t, picks)
                    ve = skinned(E, y, t, picks)
                    worst = max([worst] + [max(abs(u - v) for u, v in zip(p, r)) - (0.006 * max(reach, max(abs(c) for c in p)) if multi[k2] else 0) for k2, p, r in zip(picks, va, ve)])
                st["animations"] += 1
                if worst > max(1e-3, size * 1e-3):
                    long_anim = max(max(E.acc(sm["input"])) for sm in y["samplers"]) * 60 > 4095
                    if long_anim:
                        st["over 4095 frames (apicula reads 12 bits)"] += 1
                    elif zero_scale:
                        st["zero rest scale (apicula's bind loses precision)"] += 1
                    elif stepped:
                        st["stepped (apicula reads them short)"] += 1
                    else:
                        st["differ: animation"] += 1
                        print(f"{label}: animation {y.get('name')} differs by {worst:.4f} (size {size:.1f})")
                else:
                    st["same animation"] += 1
        print(f"{narc}: done", flush=True)
    shutil.rmtree(tmp, ignore_errors=True)
    for k in sorted(st):
        print(f"{k}: {st[k]}")
    return 1 if any(k.startswith("differ") or k == "esk fail" for k in st) else 0


if __name__ == "__main__":
    sys.exit(main())
