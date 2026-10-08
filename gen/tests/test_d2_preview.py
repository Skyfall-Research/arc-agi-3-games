"""Blind pins for contract D-2 — the playable preview at the review stop.

Run: .venv/bin/python -m pytest gen/tests/test_d2_preview.py -v

Written from the frozen D-2 contract ALONE (blind test writer). No in-progress
D-2 diff was read: at the moment this file was written the working tree carried
`gen/s6_package.py` UNMODIFIED and no `write_play_preview` /
`withdraw_play_preview` / `play_preview_error` / "review pending" byte anywhere
under `gen/` — that clean tree (D-3's landed orchestrator changes included) is
the pre-state every pin below is built against. What it is allowed to know, and
does: the b10 play-mirror surface it is told to reuse (`write_play_mirror` and
its `<slug>/<hash8>/` layout, `_clear_play_mirror`, `play_command`, `PLAY_ROOT`,
`PLAY_TAGS`, `PLAY_DEFAULT_FPS`, `game_hash`), the orchestrator's §4 machinery
(`default_runners`, `NOTE_ARTIFACTS`, `_check_artifacts`, `_apply_review`,
`run_batch`, the `REVIEW REQUIRED` stop print), the visual-card precedent this
contract is told to follow (contract V-C: a recorder that can never fail an
edge), and the b11 fake-runner harness. These pins therefore describe the
CONTRACT, not the implementation, and are expected to fail until D-2 lands.

WHY THE PREVIEW EXISTS (the contract's own "Why", restated)

Every slot halts at `played` for a human verdict, but the play mirror is written
one edge LATER (`reviewed -> packaged`) — so the reviewer has never once been
handed a playable build by the machine, and every review so far ran on a
hand-built preview copy. D-2 moves a playable copy one edge earlier and pulls it
back if the human says no. STANDING behavior, no config knob (operator ruling):
the pins below drive the shipped `config/b001-pilot.yaml` with nothing added, so
a knob-gated, default-off implementation fails pin 4 rather than passing quietly.

THE PINS, in the contract's order

0. Surface: `write_play_preview(worker_dir, s4_dir, cfg, play_root=None)` and
   `withdraw_play_preview(worker_dir, game_hash8, play_root=None)` exist with
   those parameter names and that `play_root` default.
1. `write_play_preview` creates `<slug>/<hash8>/` holding the game file + the
   metadata, whose `title` ENDS WITH " (review pending)"; the layout is
   otherwise `write_play_mirror`'s (same file names, same metadata keys, same
   values), the dir is what the play server's own discovery glob finds, and the
   baselines come from the S4 metadata at `s4_dir`.
2. Packaging overwrites: preview, then `write_play_mirror` into the SAME
   `play_root` ⇒ the same dir, the title without the suffix, the game file bytes
   unchanged, and a metadata file byte-identical to a clean mirror's.
3. `withdraw_play_preview` removes the dir's two files with
   `_clear_play_mirror`'s exact semantics: those files and nothing else, the
   directory itself left standing, a missing dir a silent no-op, idempotent.
4. Runner integration: the `baselined -> played` edge writes the preview; an
   unwritable play root yields the `play_preview_error` NOTE artifact and the
   edge still lands; `play_preview_error` is in `NOTE_ARTIFACTS`.
5. Pull integration: `run_batch(review=(slug, "pull"))` withdraws the preview
   and records what it withdrew.
6. The review-stop print names the play recipe from `play_command`.

AMBIGUITIES RESOLVED (each is quoted in the failure message that depends on it)

  a. "layout otherwise byte-compatible … (same keys)" is pinned as key-SET
     equality with `write_play_mirror`'s metadata (hard) plus a SEPARATE test
     for key ORDER, so an order-only divergence — which the play server cannot
     see — moves exactly one line.
  b. `withdraw_play_preview`'s return type: the contract spells no `->`, while
     the `_clear_play_mirror` it wraps returns `list[str]`. Pinned tolerantly
     (`None` accepted; anything else must be the list of removed paths) in
     `test_pin3_the_return_value_if_any_lists_what_it_removed`.
  c. "`_clear_play_mirror`'s exact removal semantics" read off the pre-state:
     `unlink` on exactly `<slug>.py` and `metadata.json`, never `rmtree`, a file
     that is not there is skipped silently. Pinned as three separate behaviors
     (dir survives, an unrelated file survives, a second call is a no-op).
  d. Which seam owns the write — "the s5_battery runner's success return, or the
     transition site if cleaner" — is left open by the contract, so pin 4's
     success and failure legs drive the WHOLE `baselined -> played` edge through
     `run_batch` and pass either way. The note-artifact pin necessarily reads the
     RUNNER's result: a transition-site write has no artifacts dict to put a note
     in, so "ANY failure is a note artifact (`play_preview_error`)" is itself the
     contract's constraint on the seam, not this file's invention. The seam's
     source pin reads the TOPIC WORD ("preview") in the runner or `_work_slot`
     rather than the function name, because V-C resolved the same ambiguity that
     way — a runner calling a module-level helper is a legitimate seam; the NAME
     is pinned at file level instead.
  e. "printed ONCE per stop (not per slot) if that reads better; your call" is
     pinned at batch size 1, where BOTH readings coincide at exactly one recipe
     line. A multi-slot count is deliberately not pinned.
  f. The preview's root: with no knob, the preview can only go to the root the
     packaged mirror uses, `s6_package.PLAY_ROOT`. The tests patch that module
     attribute (and `orchestrator.PLAY_ROOT` if D-2 adds one) rather than
     passing a knob.
  g. The suffix is pinned as "the mirror's title PLUS " (review pending)"", so
     the title ALGORITHM (`slug.replace(…).title()`) is never restated here and
     stays owned by `write_play_mirror`.
  h. A `played` reached through a battery CRASH is not a "success return", so no
     preview is expected there. Pinned through a DIRECT runner call (the
     test_b003_confirm runner-driving pattern), because through `run_batch` a
     permanent crash cycles the slot instead of settling. If the implementer put
     the write at the transition site, this pin passes vacuously. RECORDED GAP.
  i. What the pull RECORDS — "the review's ledger reason or artifacts" — is
     pinned tolerantly: the withdrawn path, or the word "preview"/"withdraw",
     must appear in the pull's own ledger lines or in the batch report's review
     block.
  j. Whether `write_play_preview` REFUSES a missing or non-`fit` S4 metadata is
     not pinned: the contract says nothing about it. RECORDED GAP.
  k. Not pinned at all: the contract's comment obligations ("verify and state in
     a comment rather than re-arguing"), "ruff clean", "full suite green", and
     the implementer's end-to-end proof on a tmp copy of conduit-watch. Those are
     the implementer's half.

This file writes only inside `tmp_path`. `out/`, the configs, the canon and
every source file are read-only here; two autouse guards fail the test that
writes into the repo's own `out/batches` or `out/play`.
"""

from __future__ import annotations

import inspect
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest

from gen import orchestrator as orch
from gen import s5_battery as battery_module
from gen import s6_package as s6
from gen.config import load_config
from gen.s4_baselines import METADATA_NAME as S4_METADATA_NAME
from gen.s4_baselines import OUT_SUFFIX as S4_OUT_SUFFIX
from gen.s4_baselines import VERDICT_FIT

# b11's standing guards and batch harness (imported, never copied — the
# test_r2_hotfix3 / test_b003_confirm precedent). pytest resolves a fixture by
# looking its name up in the REQUESTING module, so each one is re-bound here.
from gen.tests import test_b11_pipeline as b11

_no_network_no_agent = b11._no_network_no_agent
_repo_batches_untouched = b11._repo_batches_untouched
batch_home = b11.batch_home
make_cfg = b11.make_cfg

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = Path(__file__).resolve().parent
TOY_WORKER = TESTS_DIR / "toy_worker"
ORCHESTRATOR_SOURCE = REPO_ROOT / "gen" / "orchestrator.py"
S6_SOURCE = REPO_ROOT / "gen" / "s6_package.py"

# The frozen pilot config: it supplies `duckwm_docs` (which `play_command`
# resolves the recipe from), `batch` and `package`. Nothing here adds a knob.
CONFIG = "config/b001-pilot.yaml"
_CFG = load_config(CONFIG)

BATCH_ID = "d2-preview-synthetic"
GAME_SLUG = "d2-preview-watch"     # the corpus dir name = the play mirror slug
BASELINES = [11, 22, 33]           # distinct, so a mixed-up level list shows

# Contract wording, not code names.
SUFFIX = " (review pending)"
NOTE_KEY = "play_preview_error"
PREVIEW_FN = "write_play_preview"
WITHDRAW_FN = "withdraw_play_preview"

# The play server's own discovery glob (`arc-agi-3-games/tools/play/server.py`,
# quoted in `write_play_mirror`'s docstring): what makes a dir PLAYABLE.
PLAY_GLOB = "*/*/metadata.json"
# PIN UPDATE, 2026-10-06 (contract H-1 item 4), deliberate and justified. This
# was `"PLAY_GAMES_DIR="`, the head of the duckWM one-liner `play_command` built
# before L-2 vendored the player into `tools/play/` and P-4 gave it
# `arc-games play`. Every pin that reads it is about the review stop CARRYING
# the recipe, which is unchanged; only the recipe's own head moved.
RECIPE_HEAD = "arc-games play"

# The one metadata payload spelling in s6_package.py ("refactor-shared, never
# duplicated"): the dict KEY, so the docstring's prose mention does not count.
PAYLOAD_CANARY = '"default_fps":'


# --------------------------------------------------------------------------
# helpers — the D-2 surface, located rather than assumed
# --------------------------------------------------------------------------


def _fn(name: str):
    """`gen.s6_package.<name>`, with the contract's own words on absence."""
    found = getattr(s6, name, None)
    assert callable(found), (
        f"gen/s6_package.py exposes no callable {name}(…). Contract D-2 §gen/s6_package.py "
        f"names it: the review stop has no playable build without it"
    )
    return found


def _write_s4_metadata(worker: Path, baselines=BASELINES, *, verdict: str = VERDICT_FIT) -> Path:
    """`<worker>.s4/metadata.json` in S4's own shape (the preview's input)."""
    s4_dir = Path(worker).with_name(Path(worker).name + S4_OUT_SUFFIX)
    s4_dir.mkdir(parents=True, exist_ok=True)
    path = s4_dir / S4_METADATA_NAME
    path.write_text(
        json.dumps(
            {
                "schema_version": "b8.1-synthetic",
                "game_id": GAME_SLUG,
                "baseline_actions": list(baselines),
                "g": 1.5,
                "solver_actions": [max(1, value // 2) for value in baselines],
                "caps": list(baselines),
                "rng_seed": 7,
                "verdict": verdict,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _metadata(play_dir: Path) -> dict:
    path = Path(play_dir) / S4_METADATA_NAME
    assert path.is_file(), (
        f"no {S4_METADATA_NAME} in {play_dir} — the play server discovers games with "
        f"glob({PLAY_GLOB!r}) and reads title/baseline_actions/default_fps out of it, so a "
        "mirror without one is not a playable build"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def _play_files(play_dir: Path) -> tuple[Path, Path]:
    """The two files a mirror dir holds: `<slug>.py` and the metadata."""
    slug = Path(play_dir).parent.name
    return Path(play_dir) / f"{slug}.py", Path(play_dir) / S4_METADATA_NAME


def _playable_dirs(play_root: Path) -> list[Path]:
    """Every dir the play server's own discovery glob would find under a root."""
    return sorted(path.parent for path in Path(play_root).glob(PLAY_GLOB))


def _preview_dir(play_root: Path, worker: Path) -> Path:
    """Where `<slug>/<hash8>/` lands for this worker (§2 ⊕ hash, b10 layout)."""
    worker = Path(worker)
    return Path(play_root) / worker.parent.name / s6.game_hash(worker)[:8]


def _plant_preview(worker: Path, play_root: Path) -> Path:
    """A preview-SHAPED dir built from PRE-EXISTING surface only.

    Pin 5 is about the withdrawal, so the dir it clears is written by b10's
    `write_play_mirror` (untouched by D-2) and its title suffixed by hand. A
    broken `write_play_preview` therefore cannot make the pull pins fail.
    """
    worker = Path(worker)
    s4_path = worker.with_name(worker.name + S4_OUT_SUFFIX) / S4_METADATA_NAME
    metadata = json.loads(s4_path.read_text(encoding="utf-8"))
    play_dir = s6.write_play_mirror(
        worker, metadata, game_hash8=s6.game_hash(worker)[:8], play_root=play_root
    )
    path = play_dir / S4_METADATA_NAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["title"] = f"{payload['title']}{SUFFIX}"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return play_dir


def _body(source: str, pattern: str) -> str:
    """One `def` block, sliced out of a module as TEXT (the V-C precedent)."""
    lines = source.splitlines(keepends=True)
    starts = [index for index, line in enumerate(lines) if re.match(pattern, line)]
    assert len(starts) == 1, (
        f"expected exactly one definition matching {pattern!r}; found {len(starts)}"
    )
    start = starts[0]
    indent = len(lines[start]) - len(lines[start].lstrip())
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if not line.strip():
            continue
        here = len(line) - len(line.lstrip())
        if here <= indent and re.match(r"^\s*(def |class |@)", line):
            end = index
            break
    return "".join(lines[start:end])


# --------------------------------------------------------------------------
# helpers — driving the §4 machine (b11 fakes; one real runner where pinned)
# --------------------------------------------------------------------------


class _Recorder:
    """The REAL `s5_battery` runner, with its result kept for inspection."""

    def __init__(self) -> None:
        self.real = orch.default_runners()["s5_battery"]
        self.results: list[dict] = []

    def __call__(self, ctx) -> dict:
        result = self.real(ctx)
        self.results.append(dict(result))
        return result

    @property
    def last(self) -> dict:
        assert self.results, (
            "the real s5_battery runner was never invoked — the fake table did not reach "
            "`baselined`, so pin 4 measured nothing"
        )
        return self.results[-1]


def _fake_runners(cfg) -> tuple[dict, object]:
    """b11's fake stage table with ONE addition.

    Its `s4_baselines` fake also lands the REAL S4 sibling
    (`<worker>.s4/metadata.json`), because that file — not the fake's
    slot-root `metadata.json` — is what the preview reads its level list from.
    """
    journal = b11._Journal()
    runners = b11._Runners(journal, cfg)
    inner = runners["s4_baselines"]

    def s4_baselines(ctx) -> dict:
        result = dict(inner(ctx))
        worker = ctx.worker_dir
        assert worker is not None, f"no worker dir on the s4 context: {ctx}"
        path = _write_s4_metadata(Path(worker))
        result["artifacts"] = {**(result.get("artifacts") or {}), "metadata": str(path)}
        return result

    runners["s4_baselines"] = s4_baselines
    return runners, journal


def _run_to_played(cfg, *, real_battery: bool) -> tuple[dict, _Recorder | None, dict]:
    """Drive one slot to the review stop. Returns (report, recorder, runners)."""
    runners, _journal = _fake_runners(cfg)
    recorder = None
    if real_battery:
        recorder = _Recorder()
        runners["s5_battery"] = recorder
    report = orch.run_batch(cfg, runners=runners)
    return report, recorder, runners


def _slot_row(report: dict) -> dict:
    rows = report["slots"]
    assert len(rows) == 1, f"these pins assume a one-slot batch; the report has {len(rows)}"
    return rows[0]


def _worker_of(report: dict) -> Path:
    row = _slot_row(report)
    worker = row["paths"]["worker"]
    assert worker, f"the slot never got a worker dir: {row}"
    return Path(worker)


def _ctx(cfg, *, spec_dir: Path, tmp_path: Path, state: str = "baselined",
         stage: str = "s5_battery") -> orch.SlotContext:
    """The context §4 hands a stage, built under tmp_path (confirm-suite shape)."""
    ideas = Path(tmp_path) / "ideas" / BATCH_ID
    ideas.mkdir(parents=True, exist_ok=True)
    return orch.SlotContext(
        cfg=cfg,
        batch_id=BATCH_ID,
        slug=orch.slot_id(BATCH_ID, 1),
        index=1,
        state=state,
        stage=stage,
        attempt=1,
        batch_dir=Path(tmp_path) / "batches" / BATCH_ID,
        ideas_dir=ideas,
        idea_path=ideas / "idea-001.json",
        corpus_dir=Path(spec_dir).parent,
        spec_dir=Path(spec_dir),
        respec_count=0,
        verifier_rejects=0,
        green_failures=0,
        history=(),
    )


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _repo_play_root_untouched():
    """A test that wrote into the repo's own play root fails here.

    Deliberately NOT imported from test_b10_package: this file patches
    `s6.PLAY_ROOT` inside its own fixtures, so the guard has to name the repo
    path directly rather than read the attribute it may already have replaced.
    """
    root = REPO_ROOT / "out" / "play"

    def snapshot():
        return sorted(str(path) for path in root.rglob("*")) if root.exists() else None

    before = snapshot()
    yield
    assert snapshot() == before, f"a D-2 test wrote into the repo play root {root}"


@pytest.fixture
def play_root(tmp_path, monkeypatch) -> Path:
    """The standing play root, redirected into tmp_path.

    D-2 adds no knob, so the preview lands wherever the packaged mirror lands:
    `s6_package.PLAY_ROOT`. The path mirrors the repo's own `out/play` tail so it
    agrees with b11's `batch_home`, which redirects every repo-rooted Path in the
    orchestrator the same way.
    """
    root = tmp_path / "out" / "play"
    monkeypatch.setattr(s6, "PLAY_ROOT", root)
    if isinstance(getattr(orch, "PLAY_ROOT", None), Path):
        monkeypatch.setattr(orch, "PLAY_ROOT", root)
    return root


@pytest.fixture
def blocked_play_root(tmp_path, monkeypatch) -> Path:
    """A play root that CANNOT be created: its parent is a regular file."""
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("this file stands where a play root would go\n", encoding="utf-8")
    root = blocker / "play"
    monkeypatch.setattr(s6, "PLAY_ROOT", root)
    if isinstance(getattr(orch, "PLAY_ROOT", None), Path):
        monkeypatch.setattr(orch, "PLAY_ROOT", root)
    return root


@dataclass(frozen=True)
class _Planted:
    """One worker on disk with its S4 metadata beside it, under tmp_path."""

    spec_dir: Path
    worker: Path
    s4_dir: Path
    s4_metadata: Path
    play_root: Path

    @property
    def slug(self) -> str:
        return self.worker.parent.name

    @property
    def hash8(self) -> str:
        return s6.game_hash(self.worker)[:8]

    @property
    def metadata(self) -> dict:
        return json.loads(self.s4_metadata.read_text(encoding="utf-8"))


@pytest.fixture
def planted(tmp_path) -> _Planted:
    spec_dir = tmp_path / "corpus" / BATCH_ID / GAME_SLUG
    worker = spec_dir / orch.WORKER_DIRNAME
    shutil.copytree(TOY_WORKER, worker, ignore=shutil.ignore_patterns("__pycache__"))
    (spec_dir / "spec.yaml").write_text("# synthetic spec (D-2 blind pins)\n", encoding="utf-8")
    s4_metadata = _write_s4_metadata(worker)
    return _Planted(
        spec_dir=spec_dir,
        worker=worker,
        s4_dir=s4_metadata.parent,
        s4_metadata=s4_metadata,
        play_root=tmp_path / "play",
    )


@pytest.fixture
def preview(planted) -> Path:
    """`write_play_preview` on the planted worker, into its own tmp root."""
    return _fn(PREVIEW_FN)(planted.worker, planted.s4_dir, _CFG, play_root=planted.play_root)


@pytest.fixture
def mirror(planted, tmp_path) -> Path:
    """`write_play_mirror` on the SAME worker, into a SEPARATE tmp root.

    The reference the preview is compared against: same machinery, same S4
    metadata, no suffix.
    """
    return s6.write_play_mirror(
        planted.worker,
        planted.metadata,
        game_hash8=planted.hash8,
        play_root=tmp_path / "mirror-reference",
    )


@pytest.fixture
def stub_battery(monkeypatch):
    """Replace `s5_battery.run_battery` (the confirm/patchbaseline pattern).

    The battery is an agent stage; these pins are about the edge it lands on, so
    it is scripted. The stub still writes `battery-report.json`, because the
    runner declares it as an artifact and §4 checks every declared artifact is
    on disk before a transition is appended.
    """

    def _install(status: str = battery_module.STATUS_COMPLETE, *, crash: dict | None = None):
        calls: list[Path] = []

        def run_battery(worker_dir, cfg, *args, **kwargs) -> dict:
            worker_dir = Path(worker_dir)
            calls.append(worker_dir)
            out_dir = worker_dir.with_name(worker_dir.name + battery_module.OUT_SUFFIX)
            out_dir.mkdir(parents=True, exist_ok=True)
            report = {
                "stage": "s3d",
                "status": status,
                "passes": 1,
                "levels": [],
                "usd_total": 0.0123,
                "tokens": {"tokens_in": 321, "tokens_out": 21},
                "crash": crash,
                "note": "synthetic battery report (D-2 blind pins)",
            }
            (out_dir / battery_module.REPORT_NAME).write_text(
                json.dumps(report, indent=2) + "\n", encoding="utf-8"
            )
            return report

        monkeypatch.setattr(battery_module, "run_battery", run_battery)
        return calls

    return _install


@pytest.fixture(scope="session")
def orchestrator_source() -> str:
    assert ORCHESTRATOR_SOURCE.is_file(), f"{ORCHESTRATOR_SOURCE} does not exist"
    return ORCHESTRATOR_SOURCE.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def s6_source() -> str:
    assert S6_SOURCE.is_file(), f"{S6_SOURCE} does not exist"
    return S6_SOURCE.read_text(encoding="utf-8")


# ==========================================================================
# PIN 0 — the surface the contract spells out
# ==========================================================================


def test_pin0_write_play_preview_has_the_contract_signature():
    params = inspect.signature(_fn(PREVIEW_FN)).parameters
    names = list(params)
    assert names[:3] == ["worker_dir", "s4_dir", "cfg"], (
        f"{PREVIEW_FN} takes {names}; contract D-2 spells it "
        "`write_play_preview(worker_dir, s4_dir, cfg, play_root=None) -> Path`"
    )
    assert "play_root" in params, f"{PREVIEW_FN} has no `play_root` parameter: {names}"
    assert params["play_root"].default is None, (
        f"{PREVIEW_FN}'s `play_root` defaults to {params['play_root'].default!r}; the contract "
        "defaults it to None (the standing out/play root)"
    )


def test_pin0_withdraw_play_preview_has_the_contract_signature():
    params = inspect.signature(_fn(WITHDRAW_FN)).parameters
    names = list(params)
    assert names[:2] == ["worker_dir", "game_hash8"], (
        f"{WITHDRAW_FN} takes {names}; contract D-2 spells it "
        "`withdraw_play_preview(worker_dir, game_hash8, play_root=None)`"
    )
    assert "play_root" in params, f"{WITHDRAW_FN} has no `play_root` parameter: {names}"
    assert params["play_root"].default is None, (
        f"{WITHDRAW_FN}'s `play_root` defaults to {params['play_root'].default!r}; the contract "
        "defaults it to None"
    )


# ==========================================================================
# PIN 1 — the preview's layout, title and metadata
# ==========================================================================


def test_pin1_the_preview_is_the_slug_hash8_dir(planted, preview):
    expected = planted.play_root / planted.slug / planted.hash8
    assert Path(preview) == expected, (
        f"write_play_preview returned {preview}; contract D-2 reuses write_play_mirror's "
        f"`<slug>/<hash8>/` layout, which is {expected}"
    )
    assert Path(preview).is_dir(), f"{preview} is not a directory on disk"


def test_pin1_the_preview_holds_the_game_file_and_the_metadata(planted, preview):
    game_file, metadata_file = _play_files(preview)
    on_disk = sorted(path.name for path in Path(preview).iterdir())
    assert on_disk == sorted([game_file.name, metadata_file.name]), (
        f"{preview} holds {on_disk}; the b10 layout is exactly "
        f"[{game_file.name!r}, {metadata_file.name!r}] — the play server loads the first `*.py` "
        "beside the metadata it finds"
    )
    assert game_file.read_bytes() == s6.game_source_path(planted.worker).read_bytes(), (
        "the preview's game file must be the worker's game.py bytes — a preview that is not "
        "the reviewed build is worse than no preview"
    )


def test_pin1_the_preview_is_what_the_play_servers_glob_finds(planted, preview):
    assert _playable_dirs(planted.play_root) == [Path(preview)], (
        f"the play server discovers games with glob({PLAY_GLOB!r}); under {planted.play_root} it "
        f"finds {_playable_dirs(planted.play_root)} instead of just {preview}. The point of D-2 "
        "is a PLAYABLE build at the review stop"
    )


def test_pin1_the_title_ends_with_the_review_pending_suffix(preview):
    title = _metadata(preview).get("title")
    assert isinstance(title, str) and title.endswith(SUFFIX), (
        f"the preview's metadata title is {title!r}; contract D-2 suffixes it {SUFFIX!r} so the "
        "play menu says out loud that this build has not been accepted yet"
    )


def test_pin1_the_title_is_the_mirrors_title_plus_the_suffix(preview, mirror):
    preview_title = _metadata(preview)["title"]
    mirror_title = _metadata(mirror)["title"]
    assert preview_title == f"{mirror_title}{SUFFIX}", (
        f"the preview title {preview_title!r} is not the mirror title {mirror_title!r} plus "
        f"{SUFFIX!r} — the suffix is an ADDITION to write_play_mirror's title, not a "
        "replacement for it (the title algorithm stays owned by the mirror writer)"
    )


def test_pin1_the_metadata_keys_are_the_mirrors_keys(preview, mirror):
    preview_keys = set(_metadata(preview))
    mirror_keys = set(_metadata(mirror))
    assert preview_keys == mirror_keys, (
        f"the preview metadata carries {sorted(preview_keys)} against the mirror's "
        f"{sorted(mirror_keys)}. Contract D-2 test-pin 1: the layout is otherwise "
        "byte-compatible with write_play_mirror's output (same keys) — the preview must not "
        "invent a field the play server does not read, nor drop one it does"
    )


def test_pin1_the_metadata_key_order_is_the_mirrors_key_order(preview, mirror):
    """AMBIGUITY (a): pinned on its own line — the play server reads by key."""
    assert list(_metadata(preview)) == list(_metadata(mirror)), (
        f"the preview writes its metadata keys in {list(_metadata(preview))} and the mirror in "
        f"{list(_metadata(mirror))}. 'byte-compatible' reads as the SAME writer emitting the "
        "same order; an order-only divergence means the payload was re-spelled instead of "
        "shared (contract D-2: refactor-shared, never duplicated)"
    )


def test_pin1_every_value_but_the_title_is_the_mirrors_value(preview, mirror):
    preview_meta, mirror_meta = _metadata(preview), _metadata(mirror)
    differing = {
        key: (preview_meta.get(key), mirror_meta.get(key))
        for key in set(preview_meta) | set(mirror_meta)
        if preview_meta.get(key) != mirror_meta.get(key)
    }
    assert set(differing) == {"title"}, (
        f"preview and mirror metadata differ on {sorted(differing)} ({differing}); the ONLY "
        "difference contract D-2 authorizes is the suffixed title"
    )


def test_pin1_the_level_list_comes_from_the_s4_metadata(planted):
    """The `s4_dir` parameter is the metadata SOURCE, not decoration."""
    other = [4, 5]
    _write_s4_metadata(planted.worker, other)
    play_dir = _fn(PREVIEW_FN)(
        planted.worker, planted.s4_dir, _CFG, play_root=planted.play_root / "again"
    )
    assert _metadata(play_dir)["baseline_actions"] == other, (
        f"the preview's baseline_actions are {_metadata(play_dir)['baseline_actions']}, not the "
        f"{other} standing in {planted.s4_metadata}. The play server reads that list as the "
        "game's level count, so it has to be S4's own"
    )


def test_pin1_two_writes_are_byte_identical(planted, preview):
    """Same worker, same config ⇒ same bytes: the mirror is overwritten in place."""
    before = {path.name: path.read_bytes() for path in Path(preview).iterdir()}
    again = _fn(PREVIEW_FN)(planted.worker, planted.s4_dir, _CFG, play_root=planted.play_root)
    assert Path(again) == Path(preview), f"the second write went to {again}, not {preview}"
    after = {path.name: path.read_bytes() for path in Path(again).iterdir()}
    assert after == before, (
        "a second preview write changed the bytes on disk. write_play_mirror overwrites a "
        "same-slug+hash mirror with the SAME bytes, and D-2 reuses its machinery"
    )


# ==========================================================================
# PIN 2 — the packaging pass overwrites the preview in place
# ==========================================================================


def test_pin2_packaging_overwrites_the_same_dir_without_the_suffix(planted, preview):
    game_before = _play_files(preview)[0].read_bytes()
    packaged = s6.write_play_mirror(
        planted.worker,
        planted.metadata,
        game_hash8=planted.hash8,
        play_root=planted.play_root,
    )
    assert Path(packaged) == Path(preview), (
        f"the packaging pass wrote {packaged} while the preview sits at {preview}; contract D-2 "
        "test-pin 2 has the real packaging pass OVERWRITE the same dir"
    )
    assert _playable_dirs(planted.play_root) == [Path(preview)], (
        "the preview and the packaged mirror must be ONE dir under the play root, not two — "
        f"found {_playable_dirs(planted.play_root)}"
    )
    title = _metadata(packaged)["title"]
    assert not title.endswith(SUFFIX), (
        f"after packaging the title is still {title!r}; the accepted build must lose the "
        f"{SUFFIX!r} marker (existing write_play_mirror behavior, which D-2 leans on)"
    )
    assert _play_files(packaged)[0].read_bytes() == game_before, (
        "packaging changed the game file bytes the reviewer played — the preview and the "
        "packaged mirror are the same build"
    )


def test_pin2_the_packaged_metadata_is_byte_identical_to_a_clean_mirror(planted, preview, mirror):
    """A preview leaves NO residue: the overwritten file equals a fresh mirror's."""
    packaged = s6.write_play_mirror(
        planted.worker,
        planted.metadata,
        game_hash8=planted.hash8,
        play_root=planted.play_root,
    )
    assert (packaged / S4_METADATA_NAME).read_bytes() == (mirror / S4_METADATA_NAME).read_bytes(), (
        "the metadata left by preview-then-package differs byte-for-byte from a mirror written "
        "into a clean root. The preview must not be able to leave anything behind in the "
        "artifact the corpus ships"
    )


# ==========================================================================
# PIN 3 — the withdrawal (`_clear_play_mirror`'s exact semantics)
# ==========================================================================


def test_pin3_withdraw_removes_both_files(planted, preview):
    game_file, metadata_file = _play_files(preview)
    _fn(WITHDRAW_FN)(planted.worker, planted.hash8, play_root=planted.play_root)
    assert not game_file.exists() and not metadata_file.exists(), (
        f"{WITHDRAW_FN} left {[str(p) for p in (game_file, metadata_file) if p.exists()]} on "
        "disk. `_clear_play_mirror` unlinks both of a mirror's files, and the pull path reuses it"
    )
    assert _playable_dirs(planted.play_root) == [], (
        "the play server's discovery glob still finds a pulled game: "
        f"{_playable_dirs(planted.play_root)}"
    )


def test_pin3_withdraw_never_removes_the_directory_itself(planted, preview):
    _fn(WITHDRAW_FN)(planted.worker, planted.hash8, play_root=planted.play_root)
    assert Path(preview).is_dir(), (
        f"{WITHDRAW_FN} removed the directory {preview}. `_clear_play_mirror` is documented "
        '"Never creates, never rmtree" — it unlinks two files and nothing else'
    )


def test_pin3_withdraw_leaves_an_unrelated_file_alone(planted, preview):
    stray = Path(preview) / "reviewer-notes.txt"
    stray.write_text("a human put this here\n", encoding="utf-8")
    _fn(WITHDRAW_FN)(planted.worker, planted.hash8, play_root=planted.play_root)
    assert stray.is_file(), (
        f"{WITHDRAW_FN} deleted {stray}, which it never wrote. `_clear_play_mirror` removes "
        "exactly `<slug>.py` and metadata.json — never a tree"
    )


def test_pin3_a_second_withdraw_is_a_no_op(planted, preview):
    _fn(WITHDRAW_FN)(planted.worker, planted.hash8, play_root=planted.play_root)
    _fn(WITHDRAW_FN)(planted.worker, planted.hash8, play_root=planted.play_root)   # must not raise
    for path in _play_files(preview):
        assert not path.exists(), f"{WITHDRAW_FN} re-created {path} on a second call"


def test_pin3_withdraw_on_a_dir_that_was_never_written_creates_nothing(planted):
    root = planted.play_root / "never-written"
    _fn(WITHDRAW_FN)(planted.worker, planted.hash8, play_root=root)   # must not raise
    assert not root.exists(), (
        f"{WITHDRAW_FN} created {root} while withdrawing a preview that was never written. "
        '`_clear_play_mirror` is "Never creates": a pull of a slot whose preview failed to '
        "build must be a silent no-op, not a new empty tree"
    )


def test_pin3_the_return_value_if_any_lists_what_it_removed(planted, preview):
    """AMBIGUITY (b): the contract spells no return type for the withdrawal."""
    expected = sorted(str(path) for path in _play_files(preview))
    returned = _fn(WITHDRAW_FN)(planted.worker, planted.hash8, play_root=planted.play_root)
    if returned is None:
        return
    assert isinstance(returned, list), (
        f"{WITHDRAW_FN} returned {type(returned).__name__}; `_clear_play_mirror`, the function "
        "it wraps, returns list[str] of the paths it removed (or None, if D-2 returns nothing)"
    )
    assert sorted(str(item) for item in returned) == expected, (
        f"{WITHDRAW_FN} reported {sorted(str(item) for item in returned)} as removed; the files "
        f"it cleared are {expected}"
    )


# ==========================================================================
# PIN 4 — the `baselined -> played` edge writes the preview
# ==========================================================================


def test_pin4_the_s5_success_path_writes_the_preview(make_cfg, play_root, stub_battery):
    stub_battery()
    cfg, _path = make_cfg("d2-runner-success")
    report, _recorder, _runners = _run_to_played(cfg, real_battery=True)

    assert report["stop_reason"] == "review", (
        f"the run stopped for {report['stop_reason']!r}, not the review checkpoint: {report}"
    )
    spine = b11._spine(b11._ledger_lines(cfg))
    assert ("baselined", "played") in spine, f"the battery edge never landed: {spine}"

    play_dir = _preview_dir(play_root, _worker_of(report))
    assert play_dir.is_dir(), (
        f"no preview at {play_dir} after the slot reached `played`. Contract D-2: every slot "
        "halts at `played` for a human verdict, and the reviewer must be handed a playable "
        "build BY THE MACHINE — with no knob to turn it on"
    )
    assert _metadata(play_dir)["title"].endswith(SUFFIX), (
        f"the preview written on the s5 edge is titled {_metadata(play_dir)['title']!r}; at the "
        f"review stop the build is titled {SUFFIX!r}"
    )
    assert _playable_dirs(play_root) == [play_dir], (
        f"the play server would find {_playable_dirs(play_root)} under the standing root; the "
        f"review stop offers exactly one playable build, {play_dir}"
    )


def test_pin4_the_preview_path_joins_the_stage_artifacts(make_cfg, play_root, stub_battery):
    stub_battery()
    cfg, _path = make_cfg("d2-runner-artifacts")
    report, recorder, _runners = _run_to_played(cfg, real_battery=True)
    play_dir = _preview_dir(play_root, _worker_of(report))

    artifacts = recorder.last.get("artifacts") or {}
    values = {str(value) for value in artifacts.values()}
    assert str(play_dir) in values, (
        f"the s5 result declares artifacts {artifacts}; contract D-2 has the preview's path "
        f"JOIN them ({play_dir}), so the record of the stop names the build the human played"
    )


def test_pin4_every_declared_artifact_is_on_disk(make_cfg, play_root, stub_battery):
    """§4's own rule, re-asked with the new artifact in the dict."""
    stub_battery()
    cfg, _path = make_cfg("d2-runner-ondisk")
    _report, recorder, _runners = _run_to_played(cfg, real_battery=True)
    orch._check_artifacts("s5_battery", recorder.last)   # must not raise


def test_pin4_an_unwritable_play_root_still_lands_the_edge(
    make_cfg, blocked_play_root, stub_battery
):
    stub_battery()
    cfg, _path = make_cfg("d2-runner-broken-root")
    report, _recorder, _runners = _run_to_played(cfg, real_battery=True)

    spine = b11._spine(b11._ledger_lines(cfg))
    assert ("baselined", "played") in spine, (
        f"a preview that could not be written under {blocked_play_root} stopped the edge: "
        f"{spine}. Contract D-2: ANY failure is a note artifact and NEVER blocks the edge — "
        "the visual-card precedent. Measurement machinery must never fail a game"
    )
    assert report["stop_reason"] == "review", (
        f"the run stopped for {report['stop_reason']!r} instead of reaching the human: {report}"
    )
    assert _slot_row(report)["blocked"] is None, (
        f"the slot was BLOCKED by a failed preview: {_slot_row(report)['blocked']}"
    )


def test_pin4_an_unwritable_play_root_yields_the_note_artifact(
    make_cfg, blocked_play_root, stub_battery
):
    stub_battery()
    cfg, _path = make_cfg("d2-runner-note")
    _report, recorder, _runners = _run_to_played(cfg, real_battery=True)

    artifacts = recorder.last.get("artifacts") or {}
    assert NOTE_KEY in artifacts, (
        f"the s5 result carries {sorted(artifacts)} after the preview failed under "
        f"{blocked_play_root}; contract D-2 records the failure as the note artifact "
        f"{NOTE_KEY!r} — a failure that leaves no trace is a preview that silently stops "
        "being written"
    )
    note = artifacts[NOTE_KEY]
    assert str(note).strip(), f"the {NOTE_KEY!r} note is empty ({note!r}): it carries the reason"
    assert not Path(str(note)).exists(), (
        f"the {NOTE_KEY!r} artifact points at an existing path ({note!r}); it is a NOTE — it "
        "exists precisely because a file could not be written (the visual_card_error precedent)"
    )


def test_pin4_the_note_key_is_registered_as_a_note_artifact():
    assert NOTE_KEY in orch.NOTE_ARTIFACTS, (
        f"orchestrator.NOTE_ARTIFACTS is {orch.NOTE_ARTIFACTS} and does not carry {NOTE_KEY!r}. "
        "Contract D-2 extends that list: the rule beside it is 'every declared artifact is on "
        "disk', so an unregistered note turns a failed preview into a run-killing RuntimeError"
    )


def test_pin4_a_battery_crash_writes_no_preview(planted, play_root, stub_battery, tmp_path):
    """AMBIGUITY (h): a crash's `played` is not the runner's success return.

    Driven by calling the runner DIRECTLY (the test_b003_confirm pattern),
    because through `run_batch` a permanent crash cycles the slot rather than
    settling anywhere this pin could read.
    """
    stub_battery(battery_module.STATUS_CRASH, crash={"pass": 1, "level": 1, "error": "synthetic"})
    runner = orch.default_runners()["s5_battery"]
    result = runner(_ctx(_CFG, spec_dir=planted.spec_dir, tmp_path=tmp_path))

    assert result["ok"] is False and result["to_state"] == "implemented", (
        f"the crash leg returned {result['ok']!r}/{result['to_state']!r}; §4 routes a battery "
        "crash back to `implemented`"
    )
    assert _playable_dirs(play_root) == [], (
        f"a CRASHED battery left a playable build at {_playable_dirs(play_root)}. The preview "
        "belongs to the s5 runner's SUCCESS return: a crash leaves `played` immediately, and "
        "the human is never asked to review it"
    )


# ==========================================================================
# PIN 5 — the pull withdraws it
# ==========================================================================


def test_pin5_a_pull_withdraws_the_preview(make_cfg, play_root, stub_battery):
    stub_battery()
    cfg, _path = make_cfg("d2-pull", max_attrition=1.0)
    report, _recorder, runners = _run_to_played(cfg, real_battery=False)
    worker = _worker_of(report)
    play_dir = _plant_preview(worker, play_root)
    assert _playable_dirs(play_root) == [play_dir], "fixture wall: the planted preview is not there"

    slug = _slot_row(report)["slug"]
    pulled = orch.run_batch(cfg, runners=runners, review=(slug, "pull"))

    assert b11._table(cfg)[slug] == "pulled", f"the pull did not terminalize the slot: {pulled}"
    left = [str(path) for path in _play_files(play_dir) if path.exists()]
    assert not left, (
        f"the pull left {left} on disk. Contract D-2: on `reviewed -> pulled` the preview is "
        "WITHDRAWN — a game the human rejected must not stay playable in the menu"
    )
    assert _playable_dirs(play_root) == [], (
        f"the play server still finds {_playable_dirs(play_root)} after a pull"
    )


def test_pin5_the_pull_records_what_it_withdrew(make_cfg, play_root, stub_battery):
    """AMBIGUITY (i): 'the review's ledger reason or artifacts' — either place."""
    stub_battery()
    cfg, _path = make_cfg("d2-pull-record", max_attrition=1.0)
    report, _recorder, runners = _run_to_played(cfg, real_battery=False)
    play_dir = _plant_preview(_worker_of(report), play_root)
    slug = _slot_row(report)["slug"]

    pulled = orch.run_batch(cfg, runners=runners, review=(slug, "pull"))
    lines = [line for line in b11._ledger_lines(cfg) if line.get("slug") == slug]
    haystack = json.dumps(lines) + json.dumps(pulled["review"], default=str)
    tokens = (str(play_dir), play_dir.name, "preview", "withdraw", "withdrew")
    assert any(token in haystack for token in tokens), (
        f"nothing in the pull's ledger lines or the report's review block mentions the "
        f"withdrawal (looked for {tokens}). Contract D-2: record what was withdrawn in the "
        f"review's ledger reason or artifacts. Lines:\n{json.dumps(lines, indent=2)}"
    )


def test_pin5_an_accept_leaves_the_preview_in_place(make_cfg, play_root, stub_battery):
    stub_battery()
    cfg, _path = make_cfg("d2-accept")
    report, _recorder, runners = _run_to_played(cfg, real_battery=False)
    play_dir = _plant_preview(_worker_of(report), play_root)
    slug = _slot_row(report)["slug"]

    orch.run_batch(cfg, runners=runners, review=(slug, "accept"))
    left = [str(path) for path in _play_files(play_dir) if path.exists()]
    assert len(left) == 2, (
        f"an ACCEPT withdrew the preview (only {left} survive). D-2 withdraws on the PULL leg "
        "only: the accepted build is the one the packaging pass overwrites in place"
    )


# ==========================================================================
# PIN 6 — the review-stop print names the play recipe
# ==========================================================================


def _stop_output(cfg, cfg_path, capsys) -> tuple[int, str]:
    """The CLI's stop print for a slot already parked at `played`.

    No stage runs here (the b11 CLI-group precedent): every recorded stage's
    inputs are unchanged, and `played` itself has no runner edge — so `main`
    re-walks the ledger, prints the stop and exits 2.
    """
    capsys.readouterr()
    code, out, err = b11._cli(["--config", str(cfg_path)], capsys)
    return code, out + err


def test_pin6_the_review_stop_names_the_play_recipe(make_cfg, play_root, stub_battery, capsys):
    stub_battery()
    cfg, cfg_path = make_cfg("d2-stop-recipe")
    _run_to_played(cfg, real_battery=True)

    code, text = _stop_output(cfg, cfg_path, capsys)
    assert code == 2, f"a run stopped at the review checkpoint exits 2; got {code}:\n{text}"
    assert RECIPE_HEAD in text, (
        f"the review stop never prints {RECIPE_HEAD!r}. Contract D-2: the REVIEW REQUIRED block "
        "gains one line — the play recipe from play_command — because a playable build the "
        f"reviewer cannot launch is not a review.\n{text}"
    )


def test_pin6_the_recipe_is_play_commands_own_line(make_cfg, play_root, stub_battery, capsys):
    stub_battery()
    cfg, cfg_path = make_cfg("d2-stop-command")
    _run_to_played(cfg, real_battery=True)

    _code, text = _stop_output(cfg, cfg_path, capsys)
    # Built from the config `main` itself loads, and the play root the machine
    # writes previews to: the recipe is a fact about this run, not a template.
    expected = s6.play_command(load_config(str(cfg_path)), s6.PLAY_ROOT)["command"]
    assert expected in text, (
        f"the stop print does not carry play_command's own line:\n  expected: {expected}\n"
        f"printed:\n{text}"
    )


def test_pin6_the_recipe_is_printed_once(make_cfg, play_root, stub_battery, capsys):
    """AMBIGUITY (e): at batch size 1, once-per-stop and once-per-slot agree."""
    stub_battery()
    cfg, cfg_path = make_cfg("d2-stop-once")
    assert cfg["batch"]["size"] == 1, "fixture wall: this pin needs the one-slot batch"
    _run_to_played(cfg, real_battery=True)

    _code, text = _stop_output(cfg, cfg_path, capsys)
    assert text.count(RECIPE_HEAD) == 1, (
        f"the recipe is printed {text.count(RECIPE_HEAD)} times for ONE stopped slot; the "
        f"contract asks for one line, once.\n{text}"
    )


def test_pin6_the_recipe_sits_with_the_review_block(make_cfg, play_root, stub_battery, capsys):
    stub_battery()
    cfg, cfg_path = make_cfg("d2-stop-block")
    report, _recorder, _runners = _run_to_played(cfg, real_battery=True)
    slug = _slot_row(report)["slug"]

    _code, text = _stop_output(cfg, cfg_path, capsys)
    for needle in ("REVIEW REQUIRED", slug, "--review", RECIPE_HEAD):
        assert needle in text, (
            f"the stop output is missing {needle!r}: the recipe belongs in the REVIEW REQUIRED "
            f"block, beside the accept/pull commands.\n{text}"
        )


# ==========================================================================
# SEAMS — source-level pins (the contract V-C precedent)
# ==========================================================================


@pytest.mark.parametrize("name", [PREVIEW_FN, WITHDRAW_FN, NOTE_KEY])
def test_the_orchestrator_names_the_preview_seam(name: str, orchestrator_source: str):
    assert name in orchestrator_source, (
        f"gen/orchestrator.py never mentions {name!r}. The preview is written on the pipeline's "
        "own path or it is written nowhere: a helper nothing calls is a helper that silently "
        "stops being called the first time the pipeline changes shape"
    )


def test_the_preview_seam_sits_on_the_baselined_to_played_path(orchestrator_source: str):
    """AMBIGUITY (d): the runner OR the transition site — both accepted.

    Pinned on the TOPIC WORD, not on `write_play_preview` itself: contract V-C
    resolved the identical ambiguity that way ("a runner that calls a
    module-level helper is a legitimate implementation", and its own seam pin
    asserts `"visual" in body`). The function NAME is pinned at file level by
    `test_the_orchestrator_names_the_preview_seam`.
    """
    runner = _body(orchestrator_source, r"^\s*def s5_battery\(")
    edge = _body(orchestrator_source, r"^\s*def _work_slot\(")
    assert "preview" in runner or "preview" in edge, (
        "neither the s5_battery runner nor _work_slot mentions a preview. Contract D-2 puts "
        "the write on the `baselined -> played` edge — the runner's success return, or the "
        f"transition site. s5_battery body:\n{runner}"
    )


def test_the_s5_runner_still_returns_only_its_own_two_states(orchestrator_source: str):
    """The recorder rule: the preview adds an artifact, never an edge."""
    runner = _body(orchestrator_source, r"^\s*def s5_battery\(")
    for state in ("played", "implemented"):
        assert f'"{state}"' in runner, (
            f"the s5_battery runner no longer returns {state!r}. The preview is a recorder: it "
            f"must leave the battery's verdict surface exactly where it was.\n{runner}"
        )


def test_the_pull_leg_withdraws_the_preview(orchestrator_source: str):
    body = _body(orchestrator_source, r"^\s*def _apply_review\(")
    assert WITHDRAW_FN in body or "withdraw" in body, (
        "_apply_review never withdraws anything. Contract D-2: on `reviewed -> pulled` the "
        f"preview is pulled back, in the same place the decision is recorded.\n{body}"
    )


def test_the_metadata_payload_is_spelled_in_exactly_one_place(s6_source: str):
    """"reuses write_play_mirror's machinery … refactor-shared, never duplicated"."""
    assert s6_source.count(PAYLOAD_CANARY) == 1, (
        f"gen/s6_package.py spells the metadata key {PAYLOAD_CANARY} "
        f"{s6_source.count(PAYLOAD_CANARY)} times. The preview and the mirror write ONE payload "
        "through ONE writer: a second copy is the drift D-2 forbids in its own words"
    )
