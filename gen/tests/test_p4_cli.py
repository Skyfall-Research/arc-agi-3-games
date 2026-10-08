"""Contract P-4 — the implementer's own pins for `gen/cli.py`.

This is NOT the blind lane's file (`gen/tests/test_v2_cli.py`, written from the
contract alone and never read from here). It pins the things the implementer
decided and has to keep true:

  * the materialization is template + the autonomy overlay + the flags, and
    NOTHING else moves (pin 2), with the overlay equal to the live b005r2
    arming the contract points at (pin 3);
  * `config/template.yaml` is read-only to this CLI, byte for byte (pin 1 and
    the autouse guard);
  * id/seed allocation, the collision refusal, and the flag guards (pins 5-7);
  * the orchestrator is invoked on a config PATH, always the persisted one
    (pin 8) — the seam the whole "resume and reproducibility come free" claim
    rests on;
  * the narrator's vocabulary covers every §4 edge (pin 10), so a new edge in
    `gen/orchestrator.TRANSITIONS` turns this file red instead of going silently
    unnarrated.

HOUSE RULE, enforced by the autouse guard: no test here writes into the repo's
real `config/` or `out/`. Every id/seed scan and every written config in this
file lands in a tmp root.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
import yaml

from gen import cli, orchestrator

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_TEMPLATE = REPO_ROOT / "config" / "template.yaml"
REAL_CONFIG_DIR = REPO_ROOT / "config"
B005R2 = REPO_ROOT / "config" / "b005r2-auto.yaml"


# --- the guard ----------------------------------------------------------------


def _shape(root: Path) -> dict[str, int]:
    if not root.is_dir():
        return {}
    return {str(p.relative_to(root)): p.stat().st_size for p in sorted(root.rglob("*"))
            if p.is_file()}


@pytest.fixture(autouse=True)
def _repo_is_never_written():
    """`config/` and `out/batches/` come out exactly as they went in."""
    watched = {
        "config/": REAL_CONFIG_DIR,
        "out/batches/": orchestrator.BATCHES_ROOT,
    }
    before = {label: _shape(root) for label, root in watched.items()}
    yield
    for label, root in watched.items():
        assert _shape(root) == before[label], f"a test wrote into the repo's real {label}"


@pytest.fixture
def roots(tmp_path, monkeypatch):
    """A tmp `config/` + `out/batches/`, aimed at by every module-level scan."""
    config_dir = tmp_path / "config"
    batches = tmp_path / "out" / "batches"
    config_dir.mkdir(parents=True)
    batches.mkdir(parents=True)
    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(orchestrator, "BATCHES_ROOT", batches)
    return config_dir, batches


def _plant(config_dir: Path, batch_id: str, seed: int) -> None:
    (config_dir / f"{batch_id}.yaml").write_text(
        yaml.safe_dump({"duckwm_docs": "./canon", "batch": {"id": batch_id, "seed": seed}}),
        encoding="utf-8",
    )


def _flat(data, prefix: str = "") -> dict:
    out = {}
    for key, value in data.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(_flat(value, path + "."))
        else:
            out[path] = value
    return out


# --- pin 1: the template is read-only -----------------------------------------


def test_template_bytes_survive_a_full_materialization(roots):
    before = REAL_TEMPLATE.read_bytes()
    cfg = cli.build_config(driver="claude", games=2, tiers=["t1", "t2"], seed=99)
    cli.render_config(cfg)
    assert REAL_TEMPLATE.read_bytes() == before


# --- pins 2 + 3: the overlay, and nothing but the overlay ----------------------


EXPECTED_MOVED_KEYS = {
    # the overlay
    "verifier.reject_cap", "verifier.round_cap", "verifier.reconcile_early",
    "review.auto_accept", "tiers.knob_defaults_action", "tiers.goal_legible_cap",
    # the flags that actually differ from the template's own example values
    "batch.id", "batch.seed",
}


def test_materialization_moves_exactly_the_overlay_and_flag_keys(roots):
    raw = yaml.safe_load(REAL_TEMPLATE.read_text(encoding="utf-8"))
    # size 2 + tiers t1,t2 are the template's OWN example values, so the only
    # residue is the overlay plus id/seed: any other key that moves is a bug.
    cfg = cli.build_config(driver="claude", games=2, tiers=["t1", "t2"], seed=99)
    before, after = _flat(raw), _flat(cfg)
    moved = (set(before) ^ set(after)) | {
        key for key in set(before) & set(after) if before[key] != after[key]
    }
    assert moved == EXPECTED_MOVED_KEYS


#: Contract L-1 (2026-10-01), LEAD EDIT — the one overlay key that is NOT a
#: b005r2 arming: the knob was written after that batch ran, so b005r2 carries
#: no such key and never could. Pinned by VALUE and by its ABSENCE from b005r2 —
#: a stronger statement than dropping it from the loop.
#:
#: Contract E-2 (2026-10-05) adds its two on exactly the same footing and for
#: exactly the same reason — `orchestrator.stage_fail_park` and
#: `orchestrator.respec_feasibility` were written after b005r2 ran, so that
#: config carries neither and never could. The LICENSED edit E-2 §4 names.
#:
#: PIN UPDATE, 2026-10-06 (contract Q-1 §4, the same licensed edit): contract
#: Q-1 adds `verifier.term_dispute_action` on identical footing — written after
#: b005r2 ran, so that config carries no such key. It is `deception_action`'s
#: ruling for the TERM half: an `undeclared-term` finding the blind audit itself
#: grounded under two names is an attribution dispute, not a defect.
L1_OVERLAY_KEYS = {
    ("verifier", "deception_action"): "record",
    ("verifier", "term_dispute_action"): "record",
    ("orchestrator", "stage_fail_park"): True,
    ("orchestrator", "respec_feasibility"): True,
}


def test_overlay_is_the_b005r2_arming(roots):
    """The contract names `config/b005r2-auto.yaml` as the live example."""
    live = yaml.safe_load(B005R2.read_text(encoding="utf-8"))
    for block, keys in cli.AUTONOMY_OVERLAY.items():
        for key, value in keys.items():
            if (block, key) in L1_OVERLAY_KEYS:
                assert value == L1_OVERLAY_KEYS[(block, key)]
                # b005r2's ORIGINAL arming predates L-1 — a claim this pinned
                # as key-absence until the dated 2026-10-06 recorded operator
                # amendment (revival #3) armed the same value in the live
                # file. Absent or equal both keep the claim true; any OTHER
                # live value would mean the overlay no longer matches the
                # file the contract names.
                live_value = (live.get(block) or {}).get(key, value)
                assert live_value == value, (
                    f"{block}.{key}: the live config carries {live_value!r}, "
                    f"the overlay arms {value!r}")
                continue
            assert live[block][key] == value, f"{block}.{key} is not b005r2's arming"


def test_absent_tiers_removes_the_templates_example_sequence(roots):
    cfg = cli.build_config(driver="claude", games=3)
    assert "tier_sequence" not in cfg["batch"]
    assert cfg["batch"]["size"] == 3


@pytest.mark.parametrize(("flag", "driver"), [("claude", "localclaude"), ("openai", "codex")])
def test_driver_mapping(roots, flag, driver):
    assert cli.build_config(driver=flag, games=1)["backends"]["default_driver"] == driver


def test_render_config_parses_back_to_the_same_dict(roots):
    cfg = cli.build_config(driver="claude", games=1)
    assert yaml.safe_load(cli.render_config(cfg)) == cfg


# --- pin 5: ids and seeds ------------------------------------------------------


def test_id_increments_past_both_homes(roots):
    config_dir, batches = roots
    _plant(config_dir, "g20260101-1", 3)
    (batches / "g20260101-2").mkdir()
    made = cli.next_batch_id(today=__import__("datetime").date(2026, 1, 1))
    assert made == "g20260101-3"


def test_the_counter_is_reserved_whether_or_not_a_name_was_given(roots):
    config_dir, _batches = roots
    _plant(config_dir, "g20260101-1-alpha", 1)
    day = __import__("datetime").date(2026, 1, 1)
    assert cli.next_batch_id(today=day) == "g20260101-2"
    assert cli.next_batch_id("beta", today=day) == "g20260101-2-beta"


def test_seed_is_one_past_the_highest_written_anywhere(roots):
    config_dir, batches = roots
    _plant(config_dir, "b001", 4)
    (batches / "b002").mkdir()
    (batches / "b002" / cli.BATCH_CONFIG_NAME).write_text(
        yaml.safe_dump({"batch": {"id": "b002", "seed": 11}}), encoding="utf-8")
    assert cli.next_seed() == 12
    assert cli.build_config(driver="claude", games=1)["batch"]["seed"] == 12
    assert cli.build_config(driver="claude", games=1, seed=2)["batch"]["seed"] == 2


def test_an_explicit_colliding_id_is_refused(roots):
    config_dir, _batches = roots
    _plant(config_dir, "taken-one", 1)
    with pytest.raises(cli.CliError, match="already in use"):
        cli.build_config(driver="claude", games=1, batch_id="taken-one")


def test_the_template_placeholder_is_not_a_batch(roots):
    config_dir, _batches = roots
    (config_dir / cli.TEMPLATE_NAME).write_text(
        yaml.safe_dump({"batch": {"id": "bNNN-topic", "seed": 4}}), encoding="utf-8")
    assert "bNNN-topic" not in cli.known_batch_ids()
    assert cli.next_seed() == 5          # the seed still counts


# --- pins 6 + 7: the flag guards ----------------------------------------------


def test_tier_count_mismatch_names_both_numbers(roots, capsys):
    assert cli.main(["run", "--driver", "claude", "--games", "3",
                     "--tiers", "t1,t2", "--dry-run"]) == 1
    err = capsys.readouterr().err
    assert "2 tier(s)" in err and "3 game(s)" in err


def test_an_unknown_tier_falls_through_to_the_config_validator(roots, capsys):
    assert cli.main(["run", "--driver", "claude", "--games", "1",
                     "--tiers", "t9", "--dry-run"]) == 1
    out = capsys.readouterr().out
    assert "batch.tier_sequence names unknown tiers ['t9']" in out


def _dry_run_config(out: str) -> dict:
    """The resolved YAML a `--dry-run` printed between its own two markers."""
    return yaml.safe_load(out.split("--- the settings this batch would run under ---")[1]
                          .split("--- end of settings ---")[0])


def test_workers_forwards_the_arming(roots, capsys):
    """P-5 §Work 9 (this test is one of P-5's three licensed existing-test edits;
    it pinned P-4's placeholder refusal, which P-5 replaces with forwarding).

    `--workers N>1` writes BOTH keys — the count is decorative on its own, so
    `parallel_slots` is the sentence that arms it — and `--workers 1` writes
    neither, which is what keeps an unarmed run today's bytes.
    """
    assert cli.main(["run", "--driver", "claude", "--games", "2",
                     "--workers", "2", "--dry-run"]) == 0
    armed = _dry_run_config(capsys.readouterr().out)["orchestrator"]
    assert armed["parallel_slots"] is True and armed["workers"] == 2, armed

    assert cli.main(["run", "--driver", "claude", "--games", "2",
                     "--workers", "1", "--dry-run"]) == 0
    plain = _dry_run_config(capsys.readouterr().out)["orchestrator"]
    assert "parallel_slots" not in plain, (
        f"--workers 1 has nothing to arm and must write nothing: {plain}"
    )

    # More workers than games clamps, and says so rather than silently shrinking.
    assert cli.main(["run", "--driver", "claude", "--games", "1",
                     "--workers", "4", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert _dry_run_config(out)["orchestrator"].get("parallel_slots") is None, (
        "one game cannot be built by two workers, so there is nothing to arm"
    )
    assert "building 1 at once" in out, out


def test_dry_run_spends_nothing_and_writes_nothing(roots, capsys):
    _config_dir, batches = roots
    assert cli.main(["run", "--driver", "claude", "--games", "1", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "nothing was written and nothing was spent" in out
    assert yaml.safe_load(out.split("--- the settings this batch would run under ---")[1]
                          .split("--- end of settings ---")[0])["batch"]["size"] == 1
    assert list(batches.iterdir()) == []


# --- pin 8: the orchestrator is invoked on the PERSISTED path ------------------


@pytest.fixture
def captured(monkeypatch):
    calls: list[list[str]] = []

    def fake_main(argv):
        calls.append(list(argv))
        return 0

    monkeypatch.setattr(orchestrator, "main", fake_main)
    return calls


def test_run_writes_the_config_then_drives_that_file(roots, captured, capsys):
    _config_dir, batches = roots
    assert cli.main(["run", "--driver", "claude", "--games", "1", "--yes"]) == 0
    written = list(batches.glob(f"*/{cli.BATCH_CONFIG_NAME}"))
    assert len(written) == 1
    assert captured == [["--config", str(written[0])]]
    assert yaml.safe_load(written[0].read_text())["batch"]["id"] == written[0].parent.name


def _persist(batches: Path, batch_id: str, **extra) -> Path:
    batch = batches / batch_id
    batch.mkdir(parents=True, exist_ok=True)
    path = batch / cli.BATCH_CONFIG_NAME
    path.write_text(
        yaml.safe_dump({"batch": dict({"id": batch_id, "size": 1, "seed": 1}, **extra)}),
        encoding="utf-8")
    return path


def test_resume_drives_the_persisted_config(roots, captured):
    _config_dir, batches = roots
    path = _persist(batches, "g20260101-1")
    assert cli.main(["resume", "g20260101-1"]) == 0
    assert captured == [["--config", str(path)]]


def test_status_passes_through_to_the_same_file(roots, captured):
    _config_dir, batches = roots
    path = _persist(batches, "g20260101-1")
    assert cli.main(["status", "g20260101-1"]) == 0
    assert captured == [["--config", str(path), "--status"]]


def test_a_config_too_broken_to_narrate_still_reaches_the_orchestrator(roots, captured):
    """Narration is cosmetic: a bad `batch.seed` is the orchestrator's error to raise."""
    _config_dir, batches = roots
    batch = batches / "g20260101-1"
    batch.mkdir()
    path = batch / cli.BATCH_CONFIG_NAME
    path.write_text(yaml.safe_dump({"batch": {"id": "g20260101-1"}}), encoding="utf-8")
    assert cli.main(["resume", "g20260101-1"]) == 0
    assert captured == [["--config", str(path)]]


def test_a_handwritten_config_is_still_resumable(roots, captured):
    config_dir, _batches = roots
    _plant(config_dir, "b001-legacy", 1)
    assert cli.main(["status", "b001-legacy"]) == 0
    assert captured == [["--config", str(config_dir / "b001-legacy.yaml"), "--status"]]


def test_ctrl_c_hands_back_the_resume_command(roots, monkeypatch, capsys):
    _config_dir, batches = roots
    _persist(batches, "g20260101-1")

    def interrupted(_argv):
        raise KeyboardInterrupt

    monkeypatch.setattr(orchestrator, "main", interrupted)
    assert cli.main(["resume", "g20260101-1"]) == 130
    out = capsys.readouterr().out
    assert "NOTHING IS LOST" in out
    assert "arc-games resume g20260101-1" in out


def test_an_unknown_batch_is_loud_and_lists_what_it_knows(roots, captured, capsys):
    config_dir, _batches = roots
    _plant(config_dir, "b001-legacy", 1)
    assert cli.main(["status", "nope"]) == 1
    err = capsys.readouterr().err
    assert "no batch called 'nope'" in err and "b001-legacy" in err
    assert captured == []


def test_the_summary_never_tells_you_to_re_run_for_a_terminal_slot():
    report = {
        "slots": [{"slug": "b-s001", "state": "packaged", "paths": {"spec_dir": None}},
                  {"slug": "b-s002", "state": "parked", "paths": {}},
                  {"slug": "b-s003", "state": "gated", "paths": {}}],
        "parked": [{"slug": "b-s002", "reason": "a residual nobody could settle"}],
        "cost": {"total": {"usd": 1.5, "tokens_in": 1, "tokens_out": 2}},
        "cost_note": "note",
    }
    text = "\n".join(cli.summary_lines({"batch": {"id": "b"}}, report))
    carry_on = text.split("not finished yet")[1].split("stopped for good")[0]
    assert "b-s003" in carry_on and "b-s002" not in carry_on
    assert "b-s002 — parked" in text.split("stopped for good")[1]
    assert "a residual nobody could settle" in text
    assert "total cost: $1.50" in text


# --- the canon spot-check -----------------------------------------------------


def test_the_cli_does_not_import_the_maintainer_tool():
    """Contract P-2 §4's pin, restated where the temptation lives.

    `test_p2_vendoring.test_sync_canon_is_wired_into_nothing` AST-scans every
    `gen/*.py` for an import of `gen.tools`; the canon spot-check is exactly
    the code that would reach for `sync_canon.parse_provenance`, so this file
    says out loud that it must not.
    """
    import ast

    tree = ast.parse((REPO_ROOT / "gen" / "cli.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith(("gen.tools", "tools"))
        if isinstance(node, ast.Import):
            assert not any(alias.name.startswith("gen.tools") for alias in node.names)


def test_the_cli_reads_the_canon_stamp_exactly_as_the_tool_that_writes_it_does():
    """The duplication P-2's pin forces, held equal on the REAL stamp."""
    from gen.tools.sync_canon import CANON_ROOT, PROVENANCE_NAME, parse_provenance

    text = (CANON_ROOT / PROVENANCE_NAME).read_text(encoding="utf-8")
    assert cli.read_provenance_table(text) == parse_provenance(text)["files"]
    assert cli.PROVENANCE_NAME == PROVENANCE_NAME


def test_a_tampered_canon_file_is_caught(tmp_path):
    """The stamp is the only thing standing between a half-synced canon and bad prompts."""
    canon = tmp_path / "canon"
    (canon / "mechanics").mkdir(parents=True)
    (canon / "mechanics" / "objectives.csv").write_text("tampered", encoding="utf-8")
    (canon / cli.PROVENANCE_NAME).write_text(
        "- Source: /somewhere\n- duckWM commit: abc\n- Copied: 2026-01-01\n\n"
        "| path | bytes | sha256 |\n| --- | --- | --- |\n"
        "| mechanics/objectives.csv | 8 | " + "0" * 64 + " |\n",
        encoding="utf-8")
    check = cli.check_canon({"duckwm_docs": str(canon)}, canon_root=canon)
    assert check.failed
    assert "objectives.csv does not match its recorded sha256" in check.detail


def test_a_live_checkout_is_reported_not_failed(tmp_path):
    """`duckwm_docs` pointing somewhere else is legal; the stamp is the snapshot's."""
    check = cli.check_canon({"duckwm_docs": str(tmp_path)}, canon_root=tmp_path / "canon")
    assert not check.failed
    assert "not the vendored snapshot" in check.detail


def test_the_real_vendored_canon_passes_its_own_spot_check():
    check = cli.check_canon({"duckwm_docs": f"./{cli.CANON_DIRNAME}"})
    assert not check.failed, check.detail
    assert "all match" in check.detail


# --- the roots seam: the COMMAND layer, not just the library --------------------
#
# Lead ruling on the P-4 follow-up. The library seam was complete from the
# start; `run`/`resume`/`status`/`play` had no seam at all, because the batches
# half of it only existed as `gen.orchestrator.BATCHES_ROOT` and nothing looked
# for it there. These pin the fix from the OUTSIDE: one module constant moved,
# and the whole command layer follows it.


def test_batch_dir_is_the_orchestrators_own_derivation():
    """The config must land where the ledger will; this is why that is true."""
    cfg = {"batch": {"id": "b-demo", "size": 1, "seed": 1}}
    assert cli.batch_dir(cfg) == orchestrator.batch_dir(cfg)


def test_moving_only_gen_cli_BATCHES_ROOT_aims_the_whole_command_layer(
        tmp_path, monkeypatch, captured):
    """`gen.orchestrator.BATCHES_ROOT` untouched — the CLI still follows the CLI."""
    configs, batches = tmp_path / "config", tmp_path / "out" / "batches"
    configs.mkdir(parents=True)
    batches.mkdir(parents=True)
    monkeypatch.setattr(cli, "CONFIG_DIR", configs)
    monkeypatch.setattr(cli, "BATCHES_ROOT", batches)
    real_batches = _shape(orchestrator.BATCHES_ROOT)

    assert cli.main(["run", "--driver", "claude", "--games", "1", "--yes"]) == 0
    written = list(batches.glob(f"*/{cli.BATCH_CONFIG_NAME}"))
    assert len(written) == 1, "run did not write into the redirected root"
    assert captured == [["--config", str(written[0])]]

    batch_id = written[0].parent.name
    assert cli.main(["status", batch_id]) == 0
    assert cli.main(["resume", batch_id]) == 0
    assert captured[1:] == [["--config", str(written[0]), "--status"],
                            ["--config", str(written[0])]]
    assert _shape(orchestrator.BATCHES_ROOT) == real_batches


def test_write_config_takes_an_explicit_batches_root(tmp_path):
    """The parameter route, so a hermetic write pin needs no constant at all."""
    cfg = {"batch": {"id": "b-demo", "size": 1, "seed": 1}}
    path = cli.write_config(cfg, "duckwm_docs: ./canon\n", batches_root=tmp_path)
    assert path == tmp_path / "b-demo" / cli.BATCH_CONFIG_NAME
    assert path.read_text(encoding="utf-8") == "duckwm_docs: ./canon\n"


def test_play_follows_gen_cli_GAMES_ROOT(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "GAMES_ROOT", tmp_path / "elsewhere")
    monkeypatch.setattr(cli, "DUCKWM_SIBLING", tmp_path / "no-duckWM")
    assert cli.main(["play"]) == 1
    assert str(tmp_path / "elsewhere") in capsys.readouterr().err


# --- pin 9: play with NO server anywhere ---------------------------------------
#
# AMENDED BY CONTRACT L-2 (the queued P-4 §5 decision, now made). The player is
# vendored at `tools/play/server.py`, so "no server" is no longer the ordinary
# case — it needs BOTH the vendored copy and the duckWM sibling to be missing,
# and both are stubbed out here. Without the first stub this pin stopped being a
# pin and started LAUNCHING A REAL SERVER on PLAY_PORT. The behaviour under test
# is unchanged: exit 2, and say exactly what was looked for.


def test_play_without_any_server_says_what_it_wanted_and_exits_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "VENDORED_PLAY_SERVER", tmp_path / "no-tools" / "server.py")
    monkeypatch.setattr(cli, "DUCKWM_SIBLING", tmp_path / "no-duckWM")
    shelf = tmp_path / "games" / "demo" / "game"
    shelf.mkdir(parents=True)
    (shelf / "metadata.json").write_text("{}", encoding="utf-8")
    assert cli.main(["play", "--root", str(tmp_path / "games")]) == 2
    err = capsys.readouterr().err
    assert str(tmp_path / "no-tools" / "server.py") in err
    assert str(tmp_path / "no-duckWM" / cli.PLAY_SERVER_REL) in err


# --- pin 10: every §4 edge has a sentence --------------------------------------


def test_every_transition_the_state_machine_can_take_is_narrated():
    edges = {(src, dst) for src, outs in orchestrator.TRANSITIONS.items() for dst in outs}
    assert edges - set(cli.EDGE_NARRATION) == set()


def test_every_state_that_still_runs_something_says_what_it_is_doing():
    running = {state for state, stage in orchestrator.NEXT_STAGE.items()
               if stage is not None and state is not None}
    assert {state for state in running if cli.next_stage_line(state) is None} == set()
    for terminal in orchestrator.TERMINAL:
        assert cli.next_stage_line(terminal) is None


def test_the_narrator_counts_laps_and_names_the_slot(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text("", encoding="utf-8")

    class Sink:
        def __init__(self):
            self.text = ""

        def write(self, chunk):
            self.text += chunk

        def flush(self):
            pass

    sink = Sink()
    narrator = cli.LedgerNarrator(ledger, batch_id="b9", size=2, out=sink, interval=0.02)
    narrator.start()
    with ledger.open("a", encoding="utf-8") as fh:
        for frm, to in (("spec_ok", "implemented"), ("implemented", "spec_ok"),
                        ("spec_ok", "implemented")):
            fh.write(json.dumps({"slug": "b9-s001", "from": frm, "to": to}) + "\n")
            fh.flush()
            time.sleep(0.05)
    narrator.stop()
    assert "game 1 of 2: built the game and it passes its own checks (build 1)" in sink.text
    assert "game 1 of 2: built the game and it passes its own checks (build 2)" in sink.text


def test_a_packaged_line_is_matched_to_its_shelf_entry_by_content(tmp_path):
    """The ledger key is the SLOT; the shelf is the GAME. The game hash links them."""
    shelf = tmp_path / "games" / "some-game" / "game" / "package"
    shelf.mkdir(parents=True)
    (shelf / "manifest.json").write_text(json.dumps({"game_hash": "abc123"}), encoding="utf-8")
    narrator = cli.LedgerNarrator(tmp_path / "ledger.jsonl", batch_id="b", size=1,
                                  games_root=tmp_path / "games")
    assert narrator._shelf({"hashes": {"game": "abc123"}}) == "games/some-game/"
    assert narrator._shelf({"hashes": {"game": "nothing-like-it"}}) == "games/"


def test_the_narrator_starts_at_the_end_of_an_existing_ledger(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(json.dumps({"slug": "b9-s001", "from": None, "to": "ideated"}) + "\n",
                      encoding="utf-8")

    class Sink:
        text = ""

        def write(self, chunk):
            type(self).text += chunk

        def flush(self):
            pass

    narrator = cli.LedgerNarrator(ledger, batch_id="b9", size=1, out=Sink(), interval=0.02)
    narrator.start()
    narrator.stop()
    assert Sink.text == ""
