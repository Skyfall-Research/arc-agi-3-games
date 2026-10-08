"""C-5 acceptance: the CLICK verb + the duck-intake mirror.

Run: .venv/bin/python -m pytest gen/tests/test_c5_clickverb.py -q

Written FROM THE C-5 CONTRACT ONLY (`scratchpad/b003-c5-contract.md`, section
"Contract C-5-tests"), by the blind test writer. `gen/s6_package.py`'s C-5 diff
was NOT read: every expectation below is either one of the contract's four
numbered pins, a shape the EXISTING b10 pins already froze (read from
`gen/tests/test_b10_package.py`, which the contract names as the harness to
model), or measured ground truth in duckWM at the contract's pinned sha.

THE FOUR CONTRACT PINS and where they live:

  pin 1  `TSV_VERBS[6] == "CLICK"`; no value of `TSV_VERBS` is `"MOUSE"`.
         -> group 1.
  pin 2  the emitted TSV: action-6 rows spell CLICK with a dict payload
         carrying x and y; no cell in the action column contains MOUSE;
         header + terminal-row conventions unchanged from the b10 pins'
         shapes.  -> group 2.
  pin 3  the mirror: `duck-intake/<slug>_perfect/human_policy/
         unprocessed_game.tsv`, byte-identical to `tsv/level-set.tsv`;
         `manifest.paths.duck_intake` points at it; two packagings produce
         byte-identical trees.  -> group 3.
  pin 4  the ground-truth conformance leg (loud skip when unavailable): the
         control's verb set at duckWM sha 31f3a8b carries CLICK and never
         MOUSE.  -> group 4.

HARNESS (modelled on test_b10_package.py):
  * the b10 reference fixture `fixtures/s6_seeded` is staged into a pytest tmp
    dir and run through the REAL `run_s4` (seed 7, verdict `fit`), so
    `<worker>.s4/` lands in tmp and never in the repo's `out/`.
  * CLICK rows are produced the way b10 produces its mouse row: ACTION6 is a
    charged no-op on that board, so `{"id": 6, "data": {"x": .., "y": ..}}`
    splices into a replayed level line without breaking the win. Two splices
    (levels 1 and 3) so "action-6 rows" is pinned in the plural.
  * every write goes to a pytest tmp dir (`tmp_path` / `tmp_path_factory`); an
    autouse fixture fails any test that touches the repo's `out/play`.

CONTRACT AMBIGUITIES this file had to take a position on (reported to the lead,
never invented quietly):

  A. PIN 4'S CONTROL CARRIES NO CLICK. The contract names
     `ar25_perfect/human_policy/unprocessed_game.tsv` as the conformance
     control, but at the pinned sha ar25 is a KEYBOARD-ONLY trajectory: its
     verb set is {UP, DOWN, LEFT, RIGHT, INTERACT} — 259 action rows, not one
     mouse row. So "assert CLICK present" cannot pass on that control under
     ANY implementation. The contract is pinned as written
     (`test_the_pinned_control_spells_click`, EXPECTED TO FAIL — the lead
     adjudicates: re-point the control, or drop the CLICK-present half of the
     leg), and the substantive leg is pinned over all 24 officials, where the
     claim is true and measured: CLICK in 17 of 24, MOUSE in 0 of 24, every
     CLICK payload carrying exactly x and y.
  B. `manifest.paths.duck_intake` is worded "<relative path>" in the
     implementer half, but every existing `paths` entry is an ABSOLUTE path.
     The test half only says it "points at it", so the value is accepted
     either way: as-is when absolute, else resolved against the out dir. The
     inconsistency is the lead's to settle.
  C. The mirror's root is spelled `worker.s6/package/duck-intake/...` in the
     implementer half and `duck-intake/...` in the test half. The mirror is
     LOCATED by globbing the package output for `unprocessed_game.tsv` and the
     implementer half's full relative path is then asserted, so a mirror that
     lands somewhere else fails with its actual location in the message rather
     than with a bare "missing file".
  D. "two packagings => byte-identical trees" does not say whether the second
     packaging targets the same out dir. It is pinned BOTH ways: the whole
     tree in one out dir (the b10 determinism pin's shape), and TSV + mirror
     bytes across two different out dirs — the manifest is excluded from the
     cross-dir leg only because its existing `paths` entries are absolute
     (the b10 pins make the same exclusion).
  E. The officials' action column is csv-quoted (`"[""CLICK"", {}]"`) while
     b10's pins prove ours is bare JSON. `_action_pair` accepts both, so the
     pins are about the VERB, never about the quoting dialect.
  F. Pin 1 freezes only slot 6 and the absence of MOUSE. The other five slots
     and the absent slot 7 are asserted against the b10 pin's table as a
     regression guard ("unchanged" is the contract's own standard for the
     RESET/ACTION7 spelling).
"""

from __future__ import annotations

import csv
import io
import json
import shutil
import subprocess
import warnings
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

import pytest

from gen import s6_package as s6
from gen.config import REPO_ROOT, load_config
from gen.s4_baselines import OUT_SUFFIX as S4_SUFFIX
from gen.s4_baselines import run_s4

TESTS = Path(__file__).resolve().parent
FIXTURES = TESTS / "fixtures"
SEEDED = FIXTURES / "s6_seeded"
PILOT_CONFIG = "config/b001-pilot.yaml"
_CFG = load_config(PILOT_CONFIG)

# --- the b10 fixture's authored numbers (test_b10_package.py, verbatim) -----
S4_SEED = 7
AUTHORED_SEED = 13
LEVEL_COUNT = 6
SEEDED_SOLVER = (12, 11, 8, 7, 7, 10)
SEEDED_ACTIONS = 55

# --- the frozen TSV surface (b10 pins) -------------------------------------
EXPECTED_TSV_COLUMNS = (
    "step",
    "observation",
    "info",
    "level",
    "action_valid",
    "duration",
    "action",
    "reward",
    "terminated",
    "truncated",
    "explore_exploit",
    "world_model_path",
    "goal",
    "exploration_output",
)
#: the five keyboard slots b10 froze — C-5 renames slot 6 and nothing else.
KEYBOARD_VERBS = {1: "UP", 2: "DOWN", 3: "LEFT", 4: "RIGHT", 5: "INTERACT"}
CLICK_ID = 6
CLICK_VERB = "CLICK"
DEAD_VERB = "MOUSE"

MANIFEST_REL = Path("package") / "manifest.json"
TSV_REL = Path("package") / "tsv" / "level-set.tsv"
REPORT_NAME = "s6-report.json"

# --- the duck-intake mirror (contract §2 + the loader's literal path) -------
INTAKE_DIR = "duck-intake"
INTAKE_SUFFIX = "_perfect"
INTAKE_POLICY = "human_policy"
INTAKE_NAME = "unprocessed_game.tsv"
INTAKE_MANIFEST_KEY = "duck_intake"

#: (level, payload) splices — ACTION6 is a charged no-op on the b10 board.
CLICK_SPLICES = ((1, {"x": 11, "y": 29}), (3, {"x": 47, "y": 5}))

# --- pin 4: the ground truth, at the contract's pinned sha ------------------
PINNED_SHA = "31f3a8b"
SPRITE_LIB_TRAJECTORIES = (
    "src/ARC3-Inference/inference/sprite_lib/sample_trajectories"
)
# LEAD ADJUDICATION (ambiguity A): the contract named ar25 as the CLICK
# control, but at the pinned sha ar25 is keyboard-only — the contract
# defect this suite surfaced. Re-pointed at s5i5 (275/276 rows CLICK);
# the MOUSE-absence claim is carried by the all-24 sweep below either way.
CONTROL_SLUG = "s5i5_perfect"
CONTROL_REL = f"{SPRITE_LIB_TRAJECTORIES}/{CONTROL_SLUG}/{INTAKE_POLICY}/{INTAKE_NAME}"
#: the contract's own count: the 24 official trajectory TSVs (sprite_lib_v2).
OFFICIAL_TSV_COUNT = 24


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Clicked:
    """A staged worker, a CLICK-spliced `<worker>.s4/` copy, and its TSV."""

    worker: Path
    s4_dir: Path
    tsv: Path


def _write_worker(dest: Path, source: Path) -> Path:
    shutil.copytree(source, dest, ignore=shutil.ignore_patterns("__pycache__"))
    return dest


def _clone(worker: Path, s4_dir: Path, dest_root: Path) -> tuple[Path, Path]:
    """A private copy of a staged worker AND its `<worker>.s4/` sibling."""
    dest_root.mkdir(parents=True, exist_ok=True)
    worker_copy = dest_root / worker.name
    shutil.copytree(worker, worker_copy, ignore=shutil.ignore_patterns("__pycache__"))
    s4_copy = dest_root / s4_dir.name
    shutil.copytree(s4_dir, s4_copy)
    return worker_copy, s4_copy


def _splice_clicks(s4_dir: Path, dest: Path) -> Path:
    """Copy `<worker>.s4/` and put one action-6 row at the head of two levels."""
    shutil.copytree(s4_dir, dest)
    for level, payload in CLICK_SPLICES:
        path = dest / "actions" / f"level-{level}.json"
        records = json.loads(path.read_text(encoding="utf-8"))
        records.insert(0, {"id": CLICK_ID, "data": dict(payload)})
        path.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    return dest


def _read_tsv(path: Path) -> tuple[list[str], list[list[str]]]:
    """Header + raw cell lists (the b10 reader: `\\n` endings, tab separated)."""
    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n"), "the TSV must end with a newline"
    assert "\r" not in text, "the dialect writes \\n endings, never \\r\\n"
    lines = text.split("\n")[:-1]
    return lines[0].split("\t"), [line.split("\t") for line in lines[1:]]


def _rows(path: Path) -> list[dict]:
    header, cells = _read_tsv(path)
    return [dict(zip(header, row, strict=True)) for row in cells]


def _action_pair(cell: str) -> list:
    """One action cell -> `[verb, payload]`, bare-JSON or csv-quoted (amb. E)."""
    text = cell
    if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
        text = text[1:-1].replace('""', '"')
    pair = json.loads(text)
    assert isinstance(pair, list) and len(pair) == 2, f"not a verb pair: {cell!r}"
    return pair


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _intake_files(out_dir: Path) -> list[Path]:
    """Every `unprocessed_game.tsv` the package output holds (ambiguity C)."""
    return sorted(out_dir.rglob(INTAKE_NAME))


def _expected_intake_rel(slug: str) -> Path:
    """The implementer half's literal path, relative to the out dir."""
    return (
        Path("package")
        / INTAKE_DIR
        / f"{slug}{INTAKE_SUFFIX}"
        / INTAKE_POLICY
        / INTAKE_NAME
    )


def _the_intake_file(out_dir: Path, slug: str) -> Path:
    found = _intake_files(out_dir)
    assert len(found) == 1, (
        "the package must carry exactly one duck-intake mirror; found "
        f"{[str(path.relative_to(out_dir)) for path in found]}"
    )
    mirror = found[0]
    assert mirror.relative_to(out_dir) == _expected_intake_rel(slug), (
        "the mirror is not at the loader's literal path "
        f"{_expected_intake_rel(slug)} — it landed at {mirror.relative_to(out_dir)}"
    )
    return mirror


def _duckwm_root() -> Path | None:
    """The read-only duckWM checkout: config-derived first, `../duckWM` next."""
    candidates: list[Path] = []
    docs = _CFG.get("duckwm_docs")
    if docs:
        candidates.append(Path(docs).parent.parent)
    candidates.append(Path(REPO_ROOT).parent / "duckWM")
    for root in candidates:
        if (root / ".git").exists():
            return root
    return None


def _git_show(root: Path, ref: str, path: str) -> str | None:
    """`git -C <root> show <ref>:<path>`, or None when it is unavailable."""
    completed = subprocess.run(
        ["git", "-C", str(root), "show", f"{ref}:{path}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 or not completed.stdout:
        return None
    return completed.stdout


def _git_ls_tree(root: Path, ref: str, path: str) -> list[str] | None:
    completed = subprocess.run(
        ["git", "-C", str(root), "ls-tree", "-r", "--name-only", ref, "--", path],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return [line for line in completed.stdout.splitlines() if line.strip()]


def _loud_skip(reason: str) -> NoReturn:
    """The contract's "loud skip when unavailable" — never a silent pass."""
    message = f"C-5 GROUND-TRUTH CONFORMANCE LEG UNAVAILABLE: {reason}"
    warnings.warn(message, stacklevel=2)
    pytest.skip(message)


@contextmanager
def _big_csv_fields():
    """The officials' observation cells exceed csv's default 128k field cap."""
    previous = csv.field_size_limit(10**9)
    try:
        yield
    finally:
        csv.field_size_limit(previous)


def _official_action_cells(text: str) -> list[str]:
    with _big_csv_fields():
        reader = csv.DictReader(io.StringIO(text), delimiter="\t")
        assert reader.fieldnames is not None, "the official TSV has no header"
        assert tuple(reader.fieldnames) == EXPECTED_TSV_COLUMNS, reader.fieldnames
        return [row["action"] for row in reader]


def _official_verbs(text: str) -> tuple[set[str], dict[str, list[set[str]]]]:
    """(the control's verb set, per-verb payload key sets)."""
    verbs: set[str] = set()
    payloads: dict[str, list[set[str]]] = {}
    for cell in _official_action_cells(text):
        if not cell:  # the terminal row's blank action cell
            continue
        verb, payload = _action_pair(cell)
        verbs.add(verb)
        payloads.setdefault(verb, []).append(
            set(payload) if isinstance(payload, dict) else set()
        )
    return verbs, payloads


def _duckwm_control() -> str:
    root = _duckwm_root()
    if root is None:
        _loud_skip(
            "no duckWM git checkout found (config duckwm_docs' grandparent, "
            f"nor {Path(REPO_ROOT).parent / 'duckWM'})"
        )
    text = _git_show(root, PINNED_SHA, CONTROL_REL)
    if text is None:
        _loud_skip(f"`git -C {root} show {PINNED_SHA}:{CONTROL_REL}` produced nothing")
    return text


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _repo_play_root_untouched():
    """The b10 play-mirror rule: tests NEVER write into the repo's out/play."""
    root = Path(getattr(s6, "PLAY_ROOT", REPO_ROOT / "out" / "play"))

    def snapshot():
        if not root.exists():
            return None
        return sorted(str(path) for path in root.rglob("*"))

    before = snapshot()
    yield
    assert snapshot() == before, f"a test wrote into the repo play root {root}"


@pytest.fixture(scope="module")
def staged(tmp_path_factory) -> tuple[Path, Path]:
    """The b10 reference fixture + a REAL `<worker>.s4/`, both in tmp."""
    root = tmp_path_factory.mktemp("c5stage")
    worker = _write_worker(root / SEEDED.name, SEEDED)
    report = run_s4(worker, _CFG, seed=S4_SEED)
    assert report["verdict"] == "fit", f"S4 verdict {report['verdict']}"
    return worker, worker.parent / (worker.name + S4_SUFFIX)


@pytest.fixture(scope="module")
def clicked(staged, tmp_path_factory) -> Clicked:
    """ONE `emit_tsv` over a line with two spliced action-6 rows."""
    worker, s4_dir = staged
    root = tmp_path_factory.mktemp("c5click")
    spliced = _splice_clicks(s4_dir, root / "clicked.s4")
    tsv = root / "clicked.tsv"
    s6.emit_tsv(worker, spliced, tsv, layout_seed=AUTHORED_SEED)
    return Clicked(worker=worker, s4_dir=spliced, tsv=tsv)


@pytest.fixture(scope="module")
def packaged(staged, tmp_path_factory) -> tuple[dict, Path, dict]:
    """ONE real `run_s6` into tmp: (report, out_dir, manifest)."""
    worker, _s4_dir = staged
    root = tmp_path_factory.mktemp("c5pack")
    out_dir = root / "out"
    report = s6.run_s6(worker, _CFG, out_dir=out_dir, play_root=root / "play")
    assert report["verdict"] == s6.VERDICT_PACKAGED, report["verdict"]
    manifest = json.loads((out_dir / MANIFEST_REL).read_text(encoding="utf-8"))
    return report, out_dir, manifest


# --------------------------------------------------------------------------- #
# group 1 — pin 1: the verb table
# --------------------------------------------------------------------------- #


def test_tsv_verb_six_is_click():
    """Pin 1: the mouse slot spells the officials' verb."""
    verbs = dict(s6.TSV_VERBS)
    assert verbs[CLICK_ID] == CLICK_VERB, verbs


def test_no_tsv_verb_is_the_dead_mouse_spelling():
    """Pin 1: MOUSE is gone from the table, at any slot."""
    verbs = dict(s6.TSV_VERBS)
    offenders = {slot: verb for slot, verb in verbs.items() if verb == DEAD_VERB}
    assert not offenders, f"MOUSE still spelled at slot(s) {sorted(offenders)}"


def test_the_five_keyboard_slots_and_the_absent_seventh_are_unchanged():
    """Ambiguity F: C-5 renames slot 6 and touches nothing else in the table."""
    verbs = dict(s6.TSV_VERBS)
    assert {slot: verbs.get(slot) for slot in KEYBOARD_VERBS} == KEYBOARD_VERBS
    assert 7 not in verbs, "ACTION7/UNDO is not in the frozen table"
    assert set(verbs) == set(KEYBOARD_VERBS) | {CLICK_ID}, sorted(verbs)


# --------------------------------------------------------------------------- #
# group 2 — pin 2: the emitted TSV
# --------------------------------------------------------------------------- #


def _click_rows(tsv: Path) -> list[dict]:
    rows = _rows(tsv)
    return [row for row in rows[:-1] if _action_pair(row["action"])[0] == CLICK_VERB]


@pytest.mark.parametrize(
    ("level", "payload"), CLICK_SPLICES, ids=[f"level{lvl}" for lvl, _ in CLICK_SPLICES]
)
def test_an_action_six_row_spells_click_with_an_xy_payload(clicked, level, payload):
    """Pin 2: the verb is CLICK and the payload is a dict carrying x and y."""
    matches = [row for row in _click_rows(clicked.tsv) if int(row["level"]) == level]
    assert len(matches) == 1, f"level {level} has {len(matches)} CLICK rows"
    verb, emitted = _action_pair(matches[0]["action"])
    assert verb == CLICK_VERB == s6.TSV_VERBS[CLICK_ID]
    assert isinstance(emitted, dict), f"the CLICK payload must be a dict: {emitted!r}"
    assert set(emitted) == {"x", "y"}, emitted
    assert emitted == payload, emitted


def test_every_spliced_action_six_row_became_a_click_row(clicked):
    assert len(_click_rows(clicked.tsv)) == len(CLICK_SPLICES)


def test_no_action_cell_in_the_emitted_tsv_mentions_mouse(clicked):
    """Pin 2: "NO cell in the action column contains MOUSE"."""
    offenders = [
        (index, row["action"])
        for index, row in enumerate(_rows(clicked.tsv))
        if DEAD_VERB in row["action"]
    ]
    assert not offenders, offenders


def test_no_action_cell_in_the_packaged_level_set_mentions_mouse(packaged):
    _report, out_dir, _manifest = packaged
    offenders = [
        (index, row["action"])
        for index, row in enumerate(_rows(out_dir / TSV_REL))
        if DEAD_VERB in row["action"]
    ]
    assert not offenders, offenders


def test_the_keyboard_rows_still_carry_the_empty_payload(clicked):
    """The b10 shape: only the mouse verb carries a payload."""
    for row in _rows(clicked.tsv)[:-1]:
        verb, payload = _action_pair(row["action"])
        if verb == CLICK_VERB:
            continue
        assert verb in set(KEYBOARD_VERBS.values()), verb
        assert payload == {}, (verb, payload)


def test_the_header_is_the_frozen_fourteen_and_every_row_is_fourteen_cells(clicked):
    """Pin 2: "header ... unchanged from the existing b10 pins' shapes"."""
    header, cells = _read_tsv(clicked.tsv)
    assert header == list(EXPECTED_TSV_COLUMNS)
    assert header == list(s6.TSV_COLUMNS)
    assert {len(row) for row in cells} == {14}


def test_the_terminal_row_convention_is_unchanged(clicked):
    """Pin 2: the b10 terminal-row shape survives the rename."""
    rows = _rows(clicked.tsv)
    terminal = rows[-1]
    assert terminal["action"] == ""
    assert terminal["action_valid"] == ""
    assert terminal["duration"] == ""
    assert terminal["terminated"] == "True"
    assert terminal["truncated"] == "False"
    assert int(terminal["reward"]) == 1, "the terminal row echoes the win (b10 amb. L)"
    assert int(terminal["level"]) == LEVEL_COUNT + 1
    assert int(terminal["step"]) == int(rows[-2]["step"])
    # the b10 pin's exact shape: everything before the WINNING action row is
    # un-terminated, and the terminal row is terminated (the win action itself
    # is the one row b10 leaves unpinned).
    assert [row["terminated"] for row in rows[:-2]] == ["False"] * (len(rows) - 2)
    assert all(row["truncated"] == "False" for row in rows)


def test_the_click_rows_do_not_disturb_the_row_level_or_reward_conventions(clicked):
    """One row per replayed action + the terminal row; reward still sparse."""
    rows = _rows(clicked.tsv)
    assert len(rows) == SEEDED_ACTIONS + len(CLICK_SPLICES) + 1
    levels = [int(row["level"]) for row in rows]
    assert levels == sorted(levels), "levels must be non-decreasing"
    assert levels[0] == 1
    spliced_per_level = {level: 0 for level in range(1, LEVEL_COUNT + 1)}
    for level, _payload in CLICK_SPLICES:
        spliced_per_level[level] += 1
    expected = [
        SEEDED_SOLVER[index - 1] + spliced_per_level[index]
        for index in range(1, LEVEL_COUNT + 1)
    ]
    assert [levels.count(index) for index in range(1, LEVEL_COUNT + 1)] == expected
    action_rows = rows[:-1]
    rewards = [int(row["reward"]) for row in action_rows]
    assert set(rewards) <= {0, 1}
    assert sum(rewards) == LEVEL_COUNT
    assert [int(row["step"]) for row in action_rows] == list(
        range(1, len(action_rows) + 1)
    )


def test_a_click_row_is_action_valid_with_the_constant_duration(clicked):
    """The b10 action-row shape holds for the new verb too."""
    for row in _click_rows(clicked.tsv):
        assert row["action_valid"] == "True"
        assert row["duration"] == "0.0000"


def test_emitting_a_click_line_twice_is_byte_identical(clicked, tmp_path):
    """The rename must not cost determinism."""
    first = tmp_path / "first.tsv"
    second = tmp_path / "second.tsv"
    s6.emit_tsv(clicked.worker, clicked.s4_dir, first, layout_seed=AUTHORED_SEED)
    s6.emit_tsv(clicked.worker, clicked.s4_dir, second, layout_seed=AUTHORED_SEED)
    assert first.read_bytes() == second.read_bytes()
    assert first.read_bytes() == clicked.tsv.read_bytes()


# --------------------------------------------------------------------------- #
# group 3 — pin 3: the duck-intake mirror
# --------------------------------------------------------------------------- #


def test_the_package_carries_the_mirror_at_the_loaders_literal_path(packaged):
    """Pin 3 + the "Why" note: `<root>/<slug>_perfect/human_policy/
    unprocessed_game.tsv` — literals, so sprite_lib needs zero renaming."""
    _report, out_dir, manifest = packaged
    mirror = _the_intake_file(out_dir, manifest["slug"])
    assert mirror.is_file()
    assert mirror.parent.name == INTAKE_POLICY
    assert mirror.parent.parent.name == f"{manifest['slug']}{INTAKE_SUFFIX}"
    assert mirror.parent.parent.parent.name == INTAKE_DIR


def test_the_intake_root_is_a_zero_rename_sample_dir(packaged):
    """--sample-dir points AT the intake root: one `<slug>_perfect` child, and
    nothing inside it but `human_policy/unprocessed_game.tsv`."""
    _report, out_dir, manifest = packaged
    mirror = _the_intake_file(out_dir, manifest["slug"])
    intake_root = mirror.parent.parent.parent
    children = sorted(path.name for path in intake_root.iterdir())
    assert children == [f"{manifest['slug']}{INTAKE_SUFFIX}"], children
    game_dir = intake_root / children[0]
    assert sorted(path.name for path in game_dir.iterdir()) == [INTAKE_POLICY]
    assert sorted(path.name for path in (game_dir / INTAKE_POLICY).iterdir()) == [
        INTAKE_NAME
    ]


def test_the_mirror_is_byte_identical_to_the_canonical_level_set(packaged):
    """Pin 3: "byte-identical copy of the emitted level-set.tsv"."""
    _report, out_dir, manifest = packaged
    mirror = _the_intake_file(out_dir, manifest["slug"])
    assert mirror.read_bytes() == (out_dir / TSV_REL).read_bytes()


def test_the_canonical_corpus_artifacts_survive_beside_the_mirror(packaged):
    """Contract §2: "level-set.tsv stays the canonical corpus artifact"."""
    _report, out_dir, _manifest = packaged
    assert (out_dir / TSV_REL).is_file()
    assert (out_dir / MANIFEST_REL).is_file()
    assert (out_dir / REPORT_NAME).is_file()


def test_the_manifest_paths_point_at_the_mirror(packaged):
    """Pin 3: `manifest.paths.duck_intake` points at the mirror (amb. B)."""
    _report, out_dir, manifest = packaged
    paths = manifest["paths"]
    assert isinstance(paths, dict), type(paths).__name__
    assert INTAKE_MANIFEST_KEY in paths, sorted(paths)
    value = paths[INTAKE_MANIFEST_KEY]
    assert isinstance(value, str) and value, repr(value)
    assert INTAKE_DIR in value, value
    assert value.endswith(INTAKE_NAME), value
    mirror = _the_intake_file(out_dir, manifest["slug"]).resolve()
    # the contract words the value "<relative path>" but names no base, so all
    # three readings count as "points at it": absolute, out-dir-relative, and
    # relative to the manifest's own directory (ambiguity B).
    candidates = [Path(value), out_dir / value, (out_dir / MANIFEST_REL).parent / value]
    resolved = [path for path in candidates if path.is_file() and path.resolve() == mirror]
    assert resolved, (
        f"manifest.paths.{INTAKE_MANIFEST_KEY} = {value!r} does not resolve to the "
        f"mirror {mirror} (tried: {[str(path) for path in candidates]})"
    )


def test_two_packagings_produce_byte_identical_trees(staged, tmp_path):
    """Pin 3: determinism preserved — the whole package tree, one out dir."""
    worker, s4_dir = staged
    copy, _s4_copy = _clone(worker, s4_dir, tmp_path / "twice")
    out_dir = tmp_path / "twice" / "out"
    play_root = tmp_path / "twice" / "play"
    s6.run_s6(copy, _CFG, out_dir=out_dir, play_root=play_root)
    first = _tree_bytes(out_dir)
    s6.run_s6(copy, _CFG, out_dir=out_dir, play_root=play_root)
    second = _tree_bytes(out_dir)
    assert sorted(first) == sorted(second), "the package tree's file list moved"
    drifted = [rel for rel in first if first[rel] != second[rel]]
    assert not drifted, f"not byte-stable: {drifted}"
    slug = json.loads((out_dir / MANIFEST_REL).read_text(encoding="utf-8"))["slug"]
    assert str(_expected_intake_rel(slug)) in first, sorted(first)


def test_the_mirror_bytes_do_not_depend_on_where_the_package_is_written(
    packaged, staged, tmp_path
):
    """Ambiguity D: the mirror is a copy of a path-free TSV, so it cannot
    drift with the out dir (the b10 cross-out-dir pin's shape)."""
    _report, first_out, manifest = packaged
    worker, s4_dir = staged
    copy, _s4_copy = _clone(worker, s4_dir, tmp_path / "elsewhere")
    out_dir = tmp_path / "elsewhere" / "out"
    s6.run_s6(copy, _CFG, out_dir=out_dir, play_root=tmp_path / "elsewhere" / "play")
    other = json.loads((out_dir / MANIFEST_REL).read_text(encoding="utf-8"))
    assert other["slug"] == manifest["slug"]
    assert (out_dir / TSV_REL).read_bytes() == (first_out / TSV_REL).read_bytes()
    assert (
        _the_intake_file(out_dir, other["slug"]).read_bytes()
        == _the_intake_file(first_out, manifest["slug"]).read_bytes()
    )


# --------------------------------------------------------------------------- #
# group 4 — pin 4: the ground-truth conformance leg (duckWM @ 31f3a8b)
# --------------------------------------------------------------------------- #


def test_the_pinned_control_never_spells_mouse():
    """Pin 4, first half: MOUSE is absent from the officials' dialect."""
    verbs, _payloads = _official_verbs(_duckwm_control())
    assert DEAD_VERB not in verbs, sorted(verbs)


def test_the_pinned_control_spells_click():
    """Pin 4, second half — PINNED AS THE CONTRACT WORDS IT (ambiguity A).

    Lead-resolved (ambiguity A): the control is s5i5, a 100%-CLICK official;
    the contract's original ar25 was keyboard-only at the pinned sha and could
    never satisfy this half.
    """
    verbs, _payloads = _official_verbs(_duckwm_control())
    assert CLICK_VERB in verbs, (
        f"the contract's control {CONTROL_SLUG} has verb set {sorted(verbs)} at "
        f"{PINNED_SHA} — no mouse rows at all, so CLICK cannot be present"
    )


def test_the_twenty_four_officials_spell_click_and_never_mouse():
    """Ambiguity A's substantive leg: the same conformance claim over the 24
    TSVs the contract's "Why" cites, where it is measurable and true."""
    root = _duckwm_root()
    if root is None:
        _loud_skip("no duckWM git checkout found")
    names = _git_ls_tree(root, PINNED_SHA, SPRITE_LIB_TRAJECTORIES)
    if not names:
        _loud_skip(f"`git -C {root} ls-tree {PINNED_SHA}` listed no trajectories")
    tsvs = [name for name in names if name.endswith(INTAKE_NAME)]
    assert len(tsvs) == OFFICIAL_TSV_COUNT, len(tsvs)
    union: set[str] = set()
    click_games: list[str] = []
    mouse_games: list[str] = []
    click_payload_keys: set[frozenset[str]] = set()
    for name in tsvs:
        text = _git_show(root, PINNED_SHA, name)
        if text is None:
            _loud_skip(f"`git show {PINNED_SHA}:{name}` produced nothing")
        verbs, payloads = _official_verbs(text)
        union |= verbs
        slug = name.split("/")[-3]
        if CLICK_VERB in verbs:
            click_games.append(slug)
            click_payload_keys |= {frozenset(keys) for keys in payloads[CLICK_VERB]}
        if DEAD_VERB in verbs:
            mouse_games.append(slug)
    assert not mouse_games, f"MOUSE spelled in {mouse_games}"
    assert CLICK_VERB in union, sorted(union)
    assert click_games, "no official trajectory carries a mouse row"
    assert click_payload_keys == {frozenset({"x", "y"})}, sorted(
        sorted(keys) for keys in click_payload_keys
    )


def test_our_verb_table_is_a_subset_of_the_officials_vocabulary():
    """"the pin that our spelling matches theirs at the pinned sha"."""
    root = _duckwm_root()
    if root is None:
        _loud_skip("no duckWM git checkout found")
    names = _git_ls_tree(root, PINNED_SHA, SPRITE_LIB_TRAJECTORIES)
    if not names:
        _loud_skip(f"`git -C {root} ls-tree {PINNED_SHA}` listed no trajectories")
    union: set[str] = set()
    for name in [name for name in names if name.endswith(INTAKE_NAME)]:
        text = _git_show(root, PINNED_SHA, name)
        if text is None:
            _loud_skip(f"`git show {PINNED_SHA}:{name}` produced nothing")
        verbs, _payloads = _official_verbs(text)
        union |= verbs
    ours = set(dict(s6.TSV_VERBS).values())
    assert ours <= union, f"we spell verbs the officials never do: {sorted(ours - union)}"
