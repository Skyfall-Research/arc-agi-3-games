# worker-template — the isolated implementer sandbox (B1)

Each S2 implementation job runs in a fresh copy of this template
(instantiated by `gen/worker.py`, which writes `worker.mk` with the
pinned python and `.scaffold-manifest.json` with the scaffold hashes).

- **Editable by the agent: `game.py` + `solver.py`. Nothing else** —
  `make validate` re-hashes the scaffold and fails on any out-of-scope
  change (and the pipeline re-verifies against its own manifest copy).
- `make validate` = edit-scope check → ruff on the two editable files →
  `pytest tests/` (game loads · solver reaches WIN ≤1200 actions with
  every level credited via `next_level()` · frames 64x64/0-15 throughout
  · solver deterministic across runs · THE SEED SWEEP: every seed in the
  pipeline's `<worker>.seeds.json` sidecar won under explicit
  `layout_seed=` construction within S6's 600-action bound, skipped when
  there is no sidecar or no `build_layout`).
- `AGENTS.md` carries the agent-facing contract (score contract,
  `complete_action()`, engine gotchas).

Deliberate deviations from the upstream re-arc-3 worker shape:
- **No `metadata.json` in the edit scope** — `game_id` comes from the game
  class; `baseline_actions` is the PIPELINE's output (D7 g-sampler, S4),
  never an implementer claim.
- **Edit scope is enforced by hash manifest** (upstream is prose-only).
- Workers reuse the arc-agi-games venv via `worker.mk` (pilot is fully
  local); `pyproject.toml` documents the pins for a self-venv lane later.

B2 extends `tests/` with the full engine-conformance + REQUIRED-gate
battery calibrated on the 25 officials.
