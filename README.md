# arc-agi-games — an ARC-AGI-3-style game generator

This repository generates original, playable puzzle games in the style of
[ARC-AGI-3](https://arcprize.org) — interactive grid games where a player has
to discover the rules by acting — end to end and without a human in the loop:

1. **idea** — a premise drawn from the official games' own design vocabulary;
2. **spec** — written into a formal, machine-checked specification;
3. **build** — implemented as working game code by an agent in a sandbox;
4. **audit** — re-read *blind* by a second agent and diffed against the spec;
5. **gates** — structural, visual and seed checks;
6. **budget + play-test** — an action budget per level, and an agent plays it;
7. **package** — a solver trajectory, a manifest of everything verified, and
   the game itself.

What survives lands on **the shelf**, [`games/`](games/): **11 games** today,
tracked in git, playable in the bundled browser player.

## Quickstart

You need **Python 3.12+**, **one agent CLI, signed in** — the `claude` CLI
(Claude Code) or the `codex` CLI — and an **OpenRouter key** for the
play-test stage.

```bash
git clone <repository-url> arc-agi-games && cd arc-agi-games
python3.12 -m venv .venv
.venv/bin/pip install -e .
export OPENROUTER_API_KEY=...                       # used by the play-test stage only
.venv/bin/arc-games run --driver claude --games 1   # or: --driver openai (the codex CLI)
```

`arc-games run` works out a batch name and seed, writes the settings it will
use to `out/batches/<batch>/config.yaml`, checks your machine (CLI installed
and signed in, canon intact, settings valid) **before spending anything**, asks
you to confirm, and then builds each game while narrating what it is doing.
Every accepted game is promoted to `games/<name>/`.

A game takes a while — it is written, built, blind-audited, gated, budgeted
and play-tested. Ctrl-C is safe at any point: the on-disk ledger is the state,
and `arc-games resume <batch>` carries on exactly where it stopped. Agent
spend is real (the [guide](docs/GUIDE.md#what-to-expect) has measured
figures); `--dry-run` shows the settings and runs the checks without spending
anything.

```bash
arc-games run --driver claude --games 2 --dry-run    # settings + machine checks, no spend
arc-games run --driver openai --games 1 --tiers t1   # pin the difficulty tier (t1 .. t3)
arc-games run --driver claude --games 4 --workers 2  # build two games at a time
arc-games resume <batch>                             # carry on
arc-games status <batch>                             # what has happened (reads the ledger)
arc-games play                                       # play the shelf in the browser
```

`python -m gen <command>` is the same program, for a checkout you have not
installed.

## Play the shelf

```bash
.venv/bin/arc-games play
```

starts the bundled player ([`tools/play/`](tools/play/), nothing else to
install) on `http://127.0.0.1:8009/` (`PLAY_PORT` overrides). Pick a game; it
loads the build that was packaged. The **seed picker** beside it also offers
every layout seed the packager validated for that game — each labelled with
the win and level count it measured — and a box for any seed you like. The
seed in play stays on screen and is recorded in the play log
(`play-logs-games/`, which stays local).

| game | title | levels |
|---|---|---|
| `conduit-watch` | Conduit Watch | 8 |
| `convoy-in-the-fog` | Convoy In The Fog | 8 |
| `core-ward-phase-gates` | Core Ward Phase Gates | 8 |
| `echo-quilt` | Echo Quilt | 7 |
| `key-strip-rover` | Key Strip Rover | 8 |
| `lantern-path-parity-trace` | Lantern Path Parity Trace | 8 |
| `pump-flow-match-glow` | Pump Flow Match Glow | 8 |
| `pump-phase-time-echo` | Pump Phase Time Echo | 8 |
| `seamlock` | Seamlock | 7 |
| `tidegate-mosaic` | Tidegate Mosaic | 7 |
| `twin-signal-rendezvous` | Twin Signal Rendezvous | 8 |

Each lives at `games/<name>/game/`: `game.py` (the game, one self-contained
module), `spec.yaml` (what it was audited against), `metadata.json`, and
`package/` (solver trajectory TSV, an ingestion mirror, and a manifest of the
audit verdict, validated seeds and content hashes). All paths are relative,
so sharing games is just git. The package format is documented in
[`docs/OUTPUT-FORMAT.md`](docs/OUTPUT-FORMAT.md).

## Read next

| you want to… | read |
|---|---|
| install, generate, play, understand a run | [`docs/GUIDE.md`](docs/GUIDE.md) |
| operate batches in detail (every knob, every failure mode) | [`docs/RUNBOOK.md`](docs/RUNBOOK.md) |
| consume the packaged games | [`docs/OUTPUT-FORMAT.md`](docs/OUTPUT-FORMAT.md) |
| change something the flags do not cover | [`config/template.yaml`](config/template.yaml) — every key commented |
| contribute | [`CONTRIBUTING.md`](CONTRIBUTING.md) |

For anything the flags do not cover — a different model per stage, an armed or
disarmed check — copy `config/template.yaml`, edit it, and run
`.venv/bin/python -m gen.orchestrator --config <your file>`. The CLI reads the
same template and never modifies it. `config/b*.yaml` are the hand-written
configurations of the earliest batches, kept as records (they name the
optional `../duckWM` checkout and will not load without it).

## The canon, and third-party material

Every prompt is built from a design **canon**: the spec, the mechanics
vocabulary, the object playbook and bestiary, and the term and objective
tables the sampler and linter consume. It ships here as
[`canon/`](canon/) — a snapshot maintained upstream by the authors and
vendored with a per-file sha256 table in
[`canon/PROVENANCE.md`](canon/PROVENANCE.md), which `arc-games` spot-checks
before every batch. A fresh clone needs nothing else. (Historical configs and
a few comments name the upstream checkout, `../duckWM`; it is optional, and
nothing in a normal run needs it.)

- **Tufalabs re-arc-3.** Two prompts from Tufalabs' re-arc-3 v0.1.2 are
  vendored verbatim under `canon/third-party/re-arc-3/` and used as reference
  doctrine. They are MIT-licensed; the license text and attribution are in
  `canon/third-party/re-arc-3/LICENSE-MIT.md`.
- **The official ARC-AGI-3 games** belong to the ARC Prize Foundation and are
  not redistributed here. The canon's analyses of them carry derived numbers
  and brief quotations for analysis only. See [`NOTICE`](NOTICE).

## Tests

```bash
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest gen/tests -q
.venv/bin/ruff check gen/
```

The suite — about 4,700 tests (2026-10-08) — runs offline and spends nothing.
On a fresh clone about 300 of them **skip**, each with its reason: they measure
evidence this public tree does not carry (the maintainers' private run corpus,
the official-games corpus, the upstream canon checkout).
`gen/tests/conftest.py` lists every one; a failure is never expected.

## Layout

```
games/             the shelf: finished games, tracked in git
gen/               the pipeline: CLI, stages S0–S6, backends, orchestrator, tests
config/            template.yaml (every knob) + the early batches' configs
canon/             the vendored, sha256-stamped design canon (+ third-party/)
tools/play/        the browser player `arc-games play` runs
worker-template/   the sandbox an agent implements each game in
docs/              GUIDE · RUNBOOK · OUTPUT-FORMAT
out/               your runs: ledgers, worker repos, packages (gitignored)
```

## License

Apache License 2.0 — see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).
Copyright 2026 Skyfall AI.
