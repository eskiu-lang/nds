#!/usr/bin/env python3
"""Compares <nds/text> with the Tallgrass extraction tools (tools/nds/text4.py and
text5.py), message by message, over every file of a ROM's message NARC:

    python3 tools/compare_text.py --tools TALLGRASS/tools --esk build/text_dump \\
        --gen 4 --charmap charmap.txt ROM.nds msgdata/pl_msg.narc

build/text_dump is tools/text_dump.esk built with eskiuc. The tools are run as a black
box (python3 -m nds.text4 ROM NARC INDEX), one file at a time; text4.py needs its
character table (TALLGRASS_DSPRE_CHARMAP), and text_dump the one --charmap names (a
charmap.txt in the pret projects' format; the package ships none). The reference writes line breaks as \\n, \\r
and \\f, as text_dump does, and ends a message at its first control code: the
messages of text_dump -c are cut at the first "{" before comparing, and the number
of messages the cut shortens is reported. text5.py (--gen 5)
leaves control codes out and prints each message as a Python literal; it is compared
with text_dump without -c, its \\n turned into line breaks. Where the two
character tables spell a character differently (--same A=B: the reference writes A
where text_dump writes B, e.g. the PK and MN glyphs), B is replaced by A in text_dump's
output before comparing. Nothing is committed from the ROM:
files go to a temporary directory.
"""
import argparse
import ast
import os
import subprocess
import sys
import tempfile


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tools", required=True)
    ap.add_argument("--esk", required=True)
    ap.add_argument("--gen", default="4")
    ap.add_argument("--same", action="append", default=[])
    ap.add_argument("--charmap")
    ap.add_argument("rom")
    ap.add_argument("narc")
    a = ap.parse_args()
    sys.path.insert(0, a.tools)
    from nds.fs import NdsFs, narc_files

    tmp = tempfile.mkdtemp()
    files = narc_files(NdsFs(a.rom).read(a.narc))
    paths = []
    for i, f in enumerate(files):
        p = os.path.join(tmp, f"{i}.bin")
        open(p, "wb").write(f)
        paths.append(p)
    opts = (["-c"] if a.gen == "4" else []) + (["-m", a.charmap] if a.charmap else [])
    r = subprocess.run([a.esk] + opts + paths, capture_output=True)
    mine = {}
    cur = None
    for line in r.stdout.decode("utf-8").split("\n"):
        if line.startswith("== "):
            cur = paths.index(line[3:])
            mine[cur] = []
        elif line:
            mine[cur].append(line)
    cut = 0
    for k, lines in mine.items():
        for j, line in enumerate(lines):
            if "{" in line:
                lines[j] = line[:line.index("{")]
                cut += 1
    subs = [s.split("=", 1) for s in a.same]
    bad_files, msgs, bad_msgs = 0, 0, 0
    for i in range(len(files)):
        ref = subprocess.run([sys.executable, "-m", f"nds.text{a.gen}", a.rom, a.narc, str(i)],
                             capture_output=True, cwd=a.tools)
        out = ref.stdout.decode("utf-8")
        want = [l for l in out.split("\n") if l]
        if a.gen == "5":
            want = []
            for l in out.split("\n"):
                if l:
                    k, _, lit = l.partition(" ")
                    want.append(k + " " + ast.literal_eval(lit))
            got = [g.replace("\\n", "\n") for g in mine.get(i, [])]
        else:
            got = mine.get(i, [])
        for x, y in subs:
            got = [g.replace(y, x) for g in got]
        msgs += len(want)
        if ref.returncode != 0:
            print(f"{a.narc}/{i}: the reference failed")
            bad_files += 1
            continue
        if got != want:
            bad_files += 1
            diff = [(w, g) for w, g in zip(want, got) if w != g]
            bad_msgs += len(diff) + abs(len(want) - len(got))
            print(f"{a.narc}/{i}: {len(diff)} messages differ, {len(got)} vs {len(want)} lines")
            for w, g in diff[:3]:
                print(f"   ref  {w!r}\n   mine {g!r}")
    print(f"{len(files)} files, {msgs} messages ({cut} with control codes, cut): {bad_files} files and {bad_msgs} messages differ")
    return 1 if bad_files else 0


if __name__ == "__main__":
    sys.exit(main())
