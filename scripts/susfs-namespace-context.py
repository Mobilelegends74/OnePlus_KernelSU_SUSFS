#!/usr/bin/env python3
"""Adapt an optional context-only include in SUSFS patches to vendor sources.

No added/removed functional lines are dropped. Unknown patch layouts fail closed.
The adapted patch is still applied by patch(1), which must succeed completely.
"""
import argparse
import re
from pathlib import Path


def adapt(patch: str, source: str) -> str:
    context = " #include <trace/hooks/blk.h>\n"
    if "#include <trace/hooks/blk.h>" in source.splitlines():
        return patch
    sections = patch.split("diff --git ")
    for index, section in enumerate(sections):
        if not section.startswith("a/fs/namespace.c b/fs/namespace.c\n"):
            continue
        lines = section.splitlines(keepends=True)
        for start, line in enumerate(lines):
            match = re.fullmatch(r"@@ -(\d+),(\d+) \+(\d+),(\d+) @@(.*)\n", line)
            if not match:
                continue
            end = start + 1
            while end < len(lines) and lines[end][:1] in (" ", "+", "-", "\\"):
                end += 1
            body = lines[start + 1:end]
            if context not in body:
                continue
            if body.count(context) != 1:
                raise ValueError("Ambiguous namespace include context")
            body.remove(context)
            old_count = sum(x.startswith((" ", "-")) for x in body)
            new_count = sum(x.startswith((" ", "+")) for x in body)
            if old_count != int(match[2]) - 1 or new_count != int(match[4]) - 1:
                raise ValueError("Unexpected SUSFS hunk lengths")
            header = f"@@ -{match[1]},{old_count} +{match[3]},{new_count} @@{match[5]}\n"
            lines[start:end] = [header, *body]
            sections[index] = "".join(lines)
            return "diff --git ".join(sections)
    return patch


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("patch", type=Path)
    parser.add_argument("namespace", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    original = args.patch.read_text()
    result = adapt(original, args.namespace.read_text())
    args.output.write_text(result)
    print("SUSFS: adapted missing context-only trace/hooks/blk.h include"
          if result != original else "SUSFS: original patch context retained")
