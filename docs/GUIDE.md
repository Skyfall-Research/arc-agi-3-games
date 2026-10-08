# The Game Generator — Team Guide

This repository generates original, playable puzzle games in the
ARC-AGI-3 style, end to end and without human intervention: an idea is
drawn from the official games' own design vocabulary, written into a
formal specification, implemented as working code, audited blind
against its spec, checked for structure and visual quality, play-tested
by an agent, and packaged. Accepted games land in the tracked
[`games/`](../games) directory — the shelf — ready to play, share, or
feed downstream.

This guide is the front door. It covers installing, generating games,
playing them, and understanding what the pipeline did. For deep
operational detail (every knob, every failure mode), see
[`docs/RUNBOOK.md`](RUNBOOK.md); for the packaged-output format,
[`docs/OUTPUT-FORMAT.md`](OUTPUT-FORMAT.md).

---

## 1. What you need

- **Python 3.12+**
- **One agent CLI, authenticated:**
  - the `claude` CLI (run `claude` once and sign in), **or**
  - the `codex` CLI, authenticated either with an OpenAI API key
    (`printenv OPENAI_API_KEY | codex login --with-api-key`) or with a
    ChatGPT subscription (`codex login` — the browser sign-in; Plus,
    Pro and Team plans work). The pipeline is credential-agnostic: it
    checks that a codex login exists and never reads the credential
- **`OPENROUTER_API_KEY`** in your environment — used only by the
  play-test stage. Without it a batch fails at that stage, not before;
  the preflight warns you up front.

That is all. The design canon the generator reads is vendored into this
repository (`canon/`, provenance-stamped), and the game player ships in
`tools/play/` — a fresh clone needs **no sibling repositories**.

## 2. Install

```bash
git clone <this-repo> && cd arc-agi-games
python3.12 -m venv .venv
.venv/bin/pip install -e .
```

This installs the `arc-games` command into the venv.

## 3. Generate games

```bash
.venv/bin/arc-games run --driver claude --games 2
```

That is the whole manual for the common case. The command:

1. materializes a complete batch configuration from the maintained
   template (no YAML to write — the resolved config is saved under
   `out/batches/<batch>/` as the batch's reproducible record),
2. runs **preflights before any spend** — driver installed and
   authenticated, canon integrity, play-test key present,
3. runs the pipeline, narrating each stage in plain language,
4. puts every accepted game on the shelf.

Useful variants:

```bash
arc-games run --driver openai --games 1          # generate with the OpenAI lane
arc-games run --driver claude --games 2 --workers 2   # build games in parallel
arc-games run --driver claude --games 1 --tiers t1    # pin the difficulty tier
arc-games run --driver claude --games 1 --dry-run     # show config + preflights, spend nothing
arc-games resume <batch>                         # continue an interrupted batch
arc-games status <batch>                         # what has happened (reads the record, runs nothing)
```

**Difficulty tiers**: `t1` (small, few mechanics), `t2`, `t3` (rich).
Left unspecified, tiers are drawn from a weighted mix. A game that
outgrows its tier during refinement is promoted, never trimmed.

**Interrupting is safe.** Ctrl-C (or a closed laptop) loses nothing:
every completed step is in an append-only record, and
`arc-games resume <batch>` picks up exactly where it stopped.

### What to expect

Measured on real batches, per game at tier t1: roughly **$15–50** of
agent spend and **2–6 hours** wall-clock, most of it in the build and
audit sessions. `--workers N` runs up to N games concurrently, which
cuts wall-clock time, not cost. Two notes on the cost report:

- Reported dollars cover the priced stages (build, audit, play-test);
  spec-writing and the checking stages are unpriced by the agent CLIs.
- The OpenAI lane reports **no per-session dollars at all** (its CLI
  does not expose them); the batch report says so explicitly rather
  than printing a false zero.

## 4. Play games

```bash
.venv/bin/arc-games play
```

This starts the bundled player on the shelf and prints the local URL
(default port 8009; `PLAY_PORT` overrides). Pick a game from the menu.
Each game offers a **seed picker**: the canonical build as packaged,
the five seeds the packager validated (labeled with their verified
results), or any seed you type. The seed in play is shown on screen and
recorded in the play log, so sessions are never conflated.

Play logs are written to `play-logs-games/` — the folder is tracked,
your logs stay local.

One quirk: the player snapshots its game list at startup. If a batch
packages a new game while the server is running, restart the server to
see it.

## 5. The shelf

Every accepted game lives at `games/<slug>/game/`:

| file | what it is |
|---|---|
| `game.py` | the playable game (one self-contained module) |
| `spec.yaml` | the formal specification the game was audited against |
| `metadata.json` | player metadata (title, levels, per-level baselines) |
| `package/` | the full package: solver trajectory TSV, ingestion mirror, manifest |

The manifest records everything the pipeline verified: the audit
verdict, validated seeds with results, content hashes, and provenance
(which batch, which contract). All paths are relative — the shelf works
identically on every machine, and **sharing games is just git**: pull
the repo, play the games.

## 6. How the pipeline works

Seven stages, driven by a state machine whose single source of truth is
an append-only ledger (`out/batches/<batch>/ledger.jsonl`):

1. **Sample** — an idea is drawn from the official corpus's own design
   vocabulary and term statistics: an objective, an interaction style,
   and a small set of mechanics, weighted the way the official games
   actually use them. A dedupe history keeps batches from redrawing
   the same idea.
2. **Specify** — an agent writes the idea into a formal spec (levels,
   mechanics, palette, rendering rules) and a linter enforces the
   signed spec contract — tier budgets, goal visibility, palette
   discipline — before anything is built.
3. **Build** — an agent implements the game in a sandboxed worker and
   must pass the game's own validation loop before leaving the stage.
   That loop includes the packager's own seed list (stage 7): a solver
   that only solves its authored layout is caught here, not at the end.
4. **Blind audit** — a *separate* agent session, with no access to the
   builder's reasoning, plays and reads the game and files exactly
   what disagrees with the spec. Small declaration mismatches are
   reconciled mechanically (the spec is amended to match the audited
   truth, within tier budgets); real defects send the game back to the
   builder with the findings. A passing verdict requires a second,
   independent confirming audit. Deception-pattern observations are
   recorded as **advisories** on the report rather than grounds for
   rejection.
5. **Gate** — mechanical structure and visual checks: declared roles
   must be drawn at legible size, the win state must be visibly
   rendered, level counts and layout contracts must hold.
6. **Play-test** — baseline action budgets are measured per level,
   then an agent plays the game end to end under a budget cap.
7. **Package** — the packager replays the game on multiple seeds and
   refuses any seed that cannot be completed; survivors are packaged
   and promoted to the shelf.

A game that fails a stage is routed back with its findings — never
silently dropped. A game that exhausts its retry budget is **parked**
with all work intact (nothing is ever deleted), and a resume after a
fix can revive it. The batch report (`batch-report.json`) summarizes
every slot: state, audit rounds, spend, and what was reconciled or
recorded along the way.

## 7. Configuration beyond the flags

The CLI covers normal use. Power users can copy
`config/template.yaml` — every knob is documented in place, and the
template's values are the maintained, batch-proven arming — and run the
orchestrator on it directly:

```bash
.venv/bin/python -m gen.orchestrator --config config/<your-batch>.yaml
```

The RUNBOOK documents every knob, state, and failure mode. Two defaults
worth knowing: agent sessions run under a 2-hour ceiling (raised from
1 hour after real builds were measured brushing it), and audits treat
deception-pattern sightings as recorded advisories rather than
rejections (both are template armings; the code defaults are stricter).

## 8. When something goes wrong

| symptom | what it means | what to do |
|---|---|---|
| preflight fails | missing/unauthenticated driver, bad key, canon drift | fix what it names; nothing was spent |
| a session times out | one agent turn hit the 2-hour ceiling | nothing to do — the attempt is retried automatically |
| `BLOCKED (driver unavailable)` | the agent CLI had an outage | re-run `arc-games resume <batch>` when the lane is back; no attempt was consumed |
| a game is `parked` | it exhausted its refinement budget | its work is intact under `out/corpus/`; resume after a fix, or leave it |
| a batch stopped at `review` | the config asked for human review | `arc-games status <batch>` shows the pending game; the player serves it for inspection |
| the player doesn't show a new game | the server predates the game | restart the player |

The ledger never lies and never loses work: `arc-games status <batch>`
is always safe to run and shows exactly where everything stands.

## 9. Further reading

- [`docs/RUNBOOK.md`](RUNBOOK.md) — operating batches in depth: every
  knob, every state, cost accounting, failure forensics.
- [`docs/OUTPUT-FORMAT.md`](OUTPUT-FORMAT.md) — the packaged-game
  format for downstream consumers (TSV conventions, manifest fields,
  ingestion mirror).
