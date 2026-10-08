"""Edit-scope check: only game.py and solver.py may differ from the scaffold.

The pipeline wrote `.scaffold-manifest.json` at instantiation (SHA-256 of
every non-editable file). This script re-hashes the tree and fails loudly
on any modified/deleted non-editable file or any NEW file. Worker-local
runs are a convenience for the implementing agent; the pipeline re-verifies
against its own sibling copy of the manifest, so tampering with the
manifest or with this script is still caught upstream.

Run from the worker root: python tests/check_edit_scope.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_NAME = ".scaffold-manifest.json"
IGNORED_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache"}


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def walk_files(root: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if rel.name == MANIFEST_NAME or any(part in IGNORED_DIRS for part in rel.parts):
            continue
        files[rel.as_posix()] = path
    return files


def main() -> int:
    manifest_path = WORKER_ROOT / MANIFEST_NAME
    if not manifest_path.is_file():
        print(f"[scope] FAIL: {MANIFEST_NAME} missing — not an instantiated worker")
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    editable = set(manifest["editable"])
    expected: dict[str, str] = manifest["files"]

    present = walk_files(WORKER_ROOT)
    violations: list[str] = []

    for rel, expected_hash in sorted(expected.items()):
        if rel in editable:
            continue
        path = present.get(rel)
        if path is None:
            violations.append(f"deleted non-editable file: {rel}")
        elif sha256_of(path) != expected_hash:
            violations.append(f"modified non-editable file: {rel}")

    for rel in sorted(present):
        if rel not in expected and rel not in editable:
            violations.append(f"new file outside the edit scope: {rel}")

    if violations:
        print(f"[scope] FAIL: {len(violations)} edit-scope violation(s):")
        for line in violations:
            print(f"[scope]   {line}")
        print(f"[scope] allowed edits: {sorted(editable)} only")
        return 1

    print(f"[scope] OK: {len(expected) - len(editable)} scaffold files intact; "
          f"editable: {sorted(editable)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
