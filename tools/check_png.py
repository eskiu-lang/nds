#!/usr/bin/env python3
"""Reads the PNGs examples/nds_textures.esk wrote for tests/data/test.nsbtx with Python's
zlib and compares their pixels with the expected tests/data/tex_*.rgba:

    eskiuc examples/nds_textures.esk -o build/nds_textures
    mkdir -p build/png && build/nds_textures tests/data/test.nsbtx build/png
    python3 -I tools/check_png.py build/png
"""
import os
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "tests", "data")


def read_png(path):
    d = open(path, "rb").read()
    assert d[:8] == b"\x89PNG\r\n\x1a\n", "signature"
    at, idat, w, h = 8, b"", 0, 0
    while at < len(d):
        n = struct.unpack_from(">I", d, at)[0]
        kind = d[at + 4:at + 8]
        body = d[at + 8:at + 8 + n]
        assert zlib.crc32(kind + body) == struct.unpack_from(">I", d, at + 8 + n)[0], "chunk CRC"
        if kind == b"IHDR":
            w, h, depth, color = struct.unpack_from(">IIBB", body)
            assert (depth, color) == (8, 6), "RGBA8"
        elif kind == b"IDAT":
            idat += body
        at += 12 + n
    raw = zlib.decompress(idat)
    row = w * 4 + 1
    assert len(raw) == row * h, "size"
    assert all(raw[y * row] == 0 for y in range(h)), "filter"
    return w, h, b"".join(raw[y * row + 1:(y + 1) * row] for y in range(h))


def main():
    out = sys.argv[1]
    bad = 0
    names = [f for f in os.listdir(DATA) if f.startswith("tex_") and f.endswith(".rgba")]
    for f in sorted(names):
        name = f[4:-5]
        e = open(os.path.join(DATA, f), "rb").read()
        ew, eh = struct.unpack_from("<II", e, 0)
        try:
            w, h, px = read_png(os.path.join(out, name + ".png"))
        except Exception as ex:
            print(f"{name}: {ex}")
            bad += 1
            continue
        if (w, h, px) != (ew, eh, e[8:]):
            print(f"{name}: pixels differ")
            bad += 1
    print(f"{len(names)} PNGs checked, {bad} bad")
    return 1 if bad or not names else 0


if __name__ == "__main__":
    sys.exit(main())
