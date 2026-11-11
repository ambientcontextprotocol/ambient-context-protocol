#!/usr/bin/env python3
"""Print the Requirements of docs/pm.md that hold in one protocol version.

Usage: python3 tools/requirements.py <version> [file]
Prints one line per Requirement: its id and statement.
"""
import re
import sys


def key(version):
    parts = [int(p) for p in version.split(".")]
    return tuple(parts + [0] * (3 - len(parts)))


def requirements(text, version):
    rows = []
    for line in text.splitlines():
        if not re.match(r"\| \*\*PR-\d{3}\*\* ", line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        ident = re.match(r"\*\*(PR-\d{3})\*\*", cells[0]).group(1)
        # A file from before the columns existed holds 0.1 only.
        since, until = (cells[5], cells[6]) if len(cells) >= 8 else ("0.1", "—")
        if key(since) <= key(version) and (until == "—" or key(version) <= key(until)):
            rows.append((ident, cells[1]))
    return sorted(rows)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    path = sys.argv[2] if len(sys.argv) > 2 else "docs/pm.md"
    for ident, statement in requirements(open(path).read(), sys.argv[1]):
        print(ident, statement)
