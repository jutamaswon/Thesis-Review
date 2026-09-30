#!/usr/bin/env python3
"""Map every line of full_text.txt to its PDF page number.

The ingest stage writes `--- PAGE N ---` markers into full_text.txt. This helper
reads those markers and prints (or writes) a line->page lookup so the reviewer
can cite concrete PDF page numbers for every issue.

Usage:
    python page_map.py <full_text.txt>            # print summary
    python page_map.py <full_text.txt> --line 1234 # what page is line 1234 on?
    python page_map.py <full_text.txt> --range 320:536  # page coverage for a span
"""
import re
import sys
from pathlib import Path

PAGE_RE = re.compile(r"^--- PAGE (\d+) ---")


def build_map(path: Path):
    lines = path.read_text(encoding="utf-8").splitlines()
    page_of = []          # page_of[i] = page number for source line i
    cur = 0
    for ln in lines:
        m = PAGE_RE.match(ln)
        if m:
            cur = int(m.group(1))
        page_of.append(cur)
    return page_of


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    path = Path(sys.argv[1])
    page_of = build_map(path)
    # summary
    pages = sorted(set(page_of))
    print(f"total lines: {len(page_of)} | pages: {min(pages)}-{max(pages)} ({len(pages)} markers)")
    args = sys.argv[2:]
    if args and args[0] == "--line":
        i = int(args[1])
        print(f"line {i} -> page {page_of[i] if i < len(page_of) else '?'}")
    elif args and args[0] == "--range":
        a, b = (int(x) for x in args[1].split(":"))
        pa, pb = page_of[a], page_of[b - 1] if b <= len(page_of) else page_of[-1]
        print(f"lines {a}-{b} -> pages {pa}-{pb}")


if __name__ == "__main__":
    main()
