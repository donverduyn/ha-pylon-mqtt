#!/usr/bin/env python3
"""Validate external GitHub Action pins across workflows and composites."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
USES_RE = re.compile(r"""^\s*(?:-\s+)?uses:\s+["']?([^"'#\s]+)""")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def action_files() -> list[Path]:
    workflows = (ROOT / ".github" / "workflows").glob("*.y*ml")
    composites = (ROOT / ".github" / "actions").glob("**/action.y*ml")
    return sorted({*workflows, *composites})


def main() -> int:
    errors: list[str] = []
    pins: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))

    for path in action_files():
        for line_number, line in enumerate(path.read_text().splitlines(), start=1):
            match = USES_RE.match(line)
            if not match:
                continue
            value = match.group(1)
            if value.startswith("./") or value.startswith("docker://"):
                continue
            if "@" not in value:
                errors.append(f"{path.relative_to(ROOT)}:{line_number}: missing @ref")
                continue

            target, ref = value.rsplit("@", 1)
            if not SHA_RE.fullmatch(ref):
                errors.append(
                    f"{path.relative_to(ROOT)}:{line_number}: "
                    f"{value} is not pinned to a full commit SHA"
                )
                continue

            parts = target.split("/")
            if len(parts) < 2:
                errors.append(
                    f"{path.relative_to(ROOT)}:{line_number}: invalid action {target}"
                )
                continue
            repository = "/".join(parts[:2])
            pins[repository][ref].append(f"{path.relative_to(ROOT)}:{line_number}")

    for repository, refs in sorted(pins.items()):
        if len(refs) <= 1:
            continue
        locations = "; ".join(
            f"{ref}: {', '.join(paths)}" for ref, paths in sorted(refs.items())
        )
        errors.append(
            f"{repository} uses inconsistent commit pins across the repository: "
            f"{locations}"
        )

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print(f"Validated external action pins in {len(action_files())} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
