"""B1 acceptance: a hand-written toy game passes `make validate` in a fresh
scaffold copy; edit-scope violations are detected.

Run: .venv/bin/python -m pytest gen/tests/test_b1_acceptance.py -v
Each case instantiates a REAL worker via gen.worker and shells out to the
real `make validate`, exactly as the S2 agent will.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from gen.worker import build_manifest, instantiate_worker, verify_worker

TOY = Path(__file__).resolve().parent / "toy_worker"


def _validate(worker: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["make", "validate"], cwd=worker, capture_output=True, text=True, timeout=300,
        check=False,
    )


def _worker_with_toy(dest: Path) -> Path:
    instantiate_worker(dest)
    shutil.copy2(TOY / "game.py", dest / "game.py")
    shutil.copy2(TOY / "solver.py", dest / "solver.py")
    return dest


def test_fresh_scaffold_fails_before_implementation(tmp_path):
    worker = tmp_path / "w-fresh"
    instantiate_worker(worker)
    proc = _validate(worker)
    assert proc.returncode != 0, "placeholder scaffold must not validate green"
    assert "ARCBaseGame subclass" in proc.stdout + proc.stderr


def test_toy_game_validates_green(tmp_path):
    worker = _worker_with_toy(tmp_path / "w-toy")
    proc = _validate(worker)
    assert proc.returncode == 0, f"expected green validate:\n{proc.stdout}\n{proc.stderr}"
    assert "validate: GREEN" in proc.stdout
    assert "[scope] OK" in proc.stdout
    assert verify_worker(worker) == [], "pipeline-side verify must agree with worker-local"


def test_modified_scaffold_file_is_detected(tmp_path):
    worker = _worker_with_toy(tmp_path / "w-tamper")
    target = worker / "tests/test_scaffold.py"
    target.write_text(target.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")
    proc = _validate(worker)
    assert proc.returncode != 0
    assert "modified non-editable file: tests/test_scaffold.py" in proc.stdout
    assert "modified non-editable file: tests/test_scaffold.py" in verify_worker(worker)


def test_new_file_is_detected(tmp_path):
    worker = _worker_with_toy(tmp_path / "w-stray")
    (worker / "helpers.py").write_text("# stray\n", encoding="utf-8")
    proc = _validate(worker)
    assert proc.returncode != 0
    assert "new file outside the edit scope: helpers.py" in proc.stdout
    assert "new file outside the edit scope: helpers.py" in verify_worker(worker)


def test_deleted_scaffold_file_is_detected(tmp_path):
    worker = _worker_with_toy(tmp_path / "w-delete")
    (worker / "AGENTS.md").unlink()
    proc = _validate(worker)
    assert proc.returncode != 0
    assert "deleted non-editable file: AGENTS.md" in proc.stdout


def test_restore_after_violation_goes_green(tmp_path):
    worker = _worker_with_toy(tmp_path / "w-restore")
    stray = worker / "helpers.py"
    stray.write_text("# stray\n", encoding="utf-8")
    assert _validate(worker).returncode != 0
    stray.unlink()
    proc = _validate(worker)
    assert proc.returncode == 0, f"restore should validate green:\n{proc.stdout}\n{proc.stderr}"


def test_editable_files_may_change_freely(tmp_path):
    worker = _worker_with_toy(tmp_path / "w-edit")
    game = worker / "game.py"
    game.write_text(game.read_text(encoding="utf-8") + "\n# implementer note\n", encoding="utf-8")
    scope = subprocess.run(
        ["make", "scope"], cwd=worker, capture_output=True, text=True, timeout=60,
        check=False,
    )
    assert scope.returncode == 0, scope.stdout + scope.stderr


def test_two_instantiations_hash_identically(tmp_path):
    a = instantiate_worker(tmp_path / "w-a")
    b = instantiate_worker(tmp_path / "w-b")
    assert a == b, "template instantiation must be deterministic"
    rebuilt = build_manifest(tmp_path / "w-a")
    assert rebuilt == a, "manifest must reproduce from the tree"


def test_instantiate_refuses_existing_dir_without_force(tmp_path):
    dest = tmp_path / "w-exists"
    instantiate_worker(dest)
    with pytest.raises(FileExistsError):
        instantiate_worker(dest)
    instantiate_worker(dest, force=True)
