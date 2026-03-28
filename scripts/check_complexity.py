#!/usr/bin/env python3
"""Fail when a function exceeds the cyclomatic complexity threshold."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Iterable


def iter_blocks(
    blocks: Iterable[dict[str, object]],
) -> Iterable[dict[str, object]]:
    """Yield function-like Radon blocks with nested closures and methods."""

    for block in blocks:
        block_type = block.get("type")
        if block_type in {"function", "method"}:
            yield block
        yield from iter_blocks(block.get("closures", []))
        yield from iter_blocks(block.get("methods", []))


def main() -> int:
    """Run the Radon JSON report and validate the threshold."""

    parser = argparse.ArgumentParser()
    parser.add_argument("target", nargs="?", default="src/")
    parser.add_argument("--max", type=int, default=9, dest="maximum")
    args = parser.parse_args()

    output = subprocess.check_output(
        [sys.executable, "-m", "radon", "cc", "-j", args.target],
        text=True,
    )
    report = json.loads(output)
    violations: list[str] = []
    for path, blocks in sorted(report.items()):
        for block in iter_blocks(blocks):
            complexity = int(block["complexity"])
            if complexity > args.maximum:
                violations.append(
                    (
                        f"{path}:{block['lineno']} "
                        f"{block['name']} has complexity {complexity}"
                    )
                )

    if violations:
        print("Cyclomatic complexity threshold exceeded:", file=sys.stderr)
        for violation in violations:
            print(violation, file=sys.stderr)
        return 1

    print(
        f"All functions are within the complexity threshold <= {args.maximum}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
