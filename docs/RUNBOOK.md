# RUNBOOK — running a batch

You are about to drive the generator: sample game ideas, write specs,
implement them, audit them, gate them, and package the ones a human accepts.
This is the **operator** half of the docs. If you only want to *use* games
that already exist, you do not need this file — read
[`OUTPUT-FORMAT.md`](OUTPUT-FORMAT.md) instead and stop there.

Every command below was executed against this tree on 2026-09-27 unless the
line says otherwise. Run all of them from the repo root:

```bash
cd arc-agi-games        # the root of your clone
```

One thing to know before anything else: **a batch is not a command that
finishes.** It stops at a human review checkpoint for every game it builds,
and it stops on failures. Stopping is normal. You re-run the same command to
continue; the ledger on disk is the state.

---

## 0. If this is your first batch, you do not need this file yet

Everything below is the long way round: it explains each stage, each config
key and each failure mode, and it assumes you are going to author a YAML file
per batch. That is still the power-user path and it still works exactly as
written.

**But you no longer have to start there.** Contract P-4 added a command line
that materializes the config for you:

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/arc-games run --driver claude --games 2
```

That does the whole of §1–§5 below for you: it picks a batch name and an
unused seed, writes the settings to `out/batches/<batch>/config.yaml`, checks
the machine before it spends anything (driver installed, canon stamp intact,
settings valid), and then narrates the batch in plain sentences while the
orchestrator drives it. `arc-games resume <batch>` continues a stopped one,
`arc-games status <batch>` prints the replayed ledger, and `arc-games run …
--dry-run` shows you the settings and the machine check without spending.
`arc-games run … --workers 2` builds two games at the same time, each in its
own process, with its own progress in `out/batches/<batch>/<slot>.slot.log`
(contract P-5; one worker, or no flag, is one game at a time as before).

Read the rest of this file when you want to change something the flags do not
cover, when a stage fails and you need to know what it was doing, or when you
are the one deciding what a batch should be armed with. The config the CLI
wrote is an ordinary config: edit `out/batches/<batch>/config.yaml` and
`resume` it, or copy `config/template.yaml` and drive it directly as §2
describes. The CLI reads `config/template.yaml` as its starting point and
never modifies it, so the two paths cannot drift apart.

---

## 1. Prerequisites

### The venv

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Check it:

```bash
.venv/bin/python -c "import arcengine, gen; print('env OK')"
.venv/bin/python -c "from importlib.metadata import version; print('arcengine', version('arcengine'))"
```

The second command must print `arcengine 0.9.3` — the version the 25 official
games run under. Do not trust `arcengine.__version__`: that attribute is a
stale `0.1.0` literal inside the package. Everything in this repo reads the
distribution version (`importlib.metadata.version("arcengine")`, in
`gen/s6_package.py`), which is the real pin.

If PyPI does not have it, copy the package from
`../duckWM/.venv/lib/python3.12/site-packages/arcengine/`.

### The canon (vendored — no sibling checkout needed)

The design canon the pipeline reads ships **inside this repo** at
`canon/` — a tracked, byte-identical snapshot with a per-file sha256
table in `canon/PROVENANCE.md`. The template's default
(`duckwm_docs: ./canon`) points at it, so a fresh clone runs with no
other repository present. Verify any config's canon resolves:

```bash
.venv/bin/python -c "from gen.config import load_config, matrix_row_count; \
  cfg = load_config('config/template.yaml'); \
  print('canon      :', cfg['duckwm_docs']); \
  print('matrix rows:', matrix_row_count(cfg))"
```

Expected: the absolute path of this repo's `canon/` and `matrix rows:
190` (25 officials + 165 tufa rows — a *signed* count; if it drifts,
the sampler's vocabulary is no longer the one every earlier batch drew
from). A wrong path raises at load and names the missing canon file;
paths resolve against **this repo's root**, never your CWD.

Maintainers editing the canon itself can point `duckwm_docs` at a live
source checkout instead and re-stamp the snapshot with
`.venv/bin/python -m gen.tools.sync_canon` (it refuses divergence
without `--force`). The optional `duckwm_games` key (the signed
officials corpus, used only by calibration features and the
conformance battery's official controls) stays commented out unless
you have that checkout; normal batches never need it.

### The two agent lanes

Agent stages (S1 spec writer, S2 implementer, S2b verifier) go through one
driver interface with two drivers:

- **`localclaude`** — the locally installed `claude` CLI on *your own* login.
  This repo handles no API key for it. Every batch that has ever run used this
  lane, on the operator's own subscription. If the session has expired, the driver says so and
  prints its own remediation (`claude auth login`).
- **`codex`** — the `codex` CLI, authenticated with an OpenAI API key
  (`printenv OPENAI_API_KEY | codex login --with-api-key` — recent codex
  versions ignore a bare environment variable) or with a ChatGPT
  subscription (`codex login`, the browser sign-in). Either way the
  credential lives in `~/.codex/auth.json`; the preflight checks
  presence only and this repo never reads the value. Subscription plans
  meter by usage windows rather than dollars — a long batch can hit a
  plan ceiling mid-run, which surfaces as the blocked-not-killed driver
  outage path, not as a kill. Live since 2026-10-01
  (first green smoke and first full game batch); previously auth-blocked
  since B0 as AUTH-2. Note its sessions report no per-call dollars — the
  batch report's cost note says so.

The backend smoke:

```bash
.venv/bin/python -m gen.smoke --driver localclaude
```

That spends one cheap haiku call and appends to `out/smoke/smoke.jsonl`. It was
*not* executed for this document (it spends a real driver call), so the
expected output is quoted from the B0 record, not measured today: `canon OK …`
then `ok    localclaude | … | $0.0679 | tokens 10/166`.

**Do not run bare `.venv/bin/python -m gen.smoke`.** Its default is
`--driver all`, and `all` now includes the OpenRouter driver, which has no
entry in that module's model table and no `complete()` method — so it runs the
two CLI lanes, spends their calls, and then dies on an unhandled `KeyError:
'openrouter'`. Verified by reading `gen/smoke.py:23-26` against
`gen/backends.py:614,940` (`'openrouter' in SMOKE_MODELS` is `False`;
`hasattr(OpenRouterDriver, 'complete')` is `False`). `--driver localclaude` is
the lane that matters and it is unaffected.

### OPENROUTER_API_KEY — only for the battery

Stage S5 (the smoke battery) plays the game over OpenRouter, and the key is
presence-checked before a single engine action:

```
[openrouter] no OPENROUTER_API_KEY in the environment — the battery plays
through OpenRouter (D12). Fix: export OPENROUTER_API_KEY=<your key>
```

```bash
export OPENROUTER_API_KEY=<your key>
```

**Export it before you start.** Nothing earlier in the pipeline needs it, so a
batch without it will spend S0 through S4 on a slot — the expensive part — and
then die at the battery. And it *dies* rather than blocking: that refusal is a
`DriverError`, which the CLI's error handler does not catch, so you get a raw
traceback rather than a `[b11] ERROR …` line. Nothing is lost — the ledger is
intact through `baselined` and a resume picks up at the battery — but it is an
ugly way to find out. (Verified by calling the resolver with the variable
unset: the message above is verbatim, and `DriverError` is a `RuntimeError`,
which is outside the CLI's caught set.)

---

## 2. Start a batch

### Write the config

> **Refinement waves 1-3 (2026-09-28).** The comparative audit's 22
> active refinement contracts are landed and `config/template.yaml` now
> ARMS the whole set — the visual gates (`field_index`,
> `role_footprint`, `win_render`, `declared_vs_painted`,
> `chrome_extent` at `fail`; `danger_visible` at `record`), the S1
> fidelity warns, the officials-shaped sampler (`corpus_share`,
> `secondary_rate`, `term_bias` t1+t2), the caps rebase
> (`caps.basis: official-band`, `g.cap_fit: reject`) and the step
> trace (`frames.trace: on`). Every knob's comment in the template
> says what it does and which evidence armed it; the live status board
> is the Generator Readiness page §6. A batch run from this template
> is HELD TO STRICTER GATES than every shipped game was — rejects at
> S1 and gate-time visual fails are the machinery working, and the
> first such batch (b004-validation) is the before/after parity
> measurement.

> **Deception findings are record-only (2026-10-01, contract L-1).**
> `config/template.yaml` now arms `verifier.deception_action: record`,
> and so does the `arc-games run` overlay. An `undeclared-deception`
> finding the blind audit raises is written to the verifier report's
> `deception_advisories` and printed at the stop as `… deception
> advisories (recorded, not rejecting): …`; it never rejects, never
> counts toward `verifier.reject_cap` and never reaches
> reconciliation. Every other reject code is unchanged, and so is the
> S1 lint rule on levers a spec DECLARES. The ruling came out of
> g20261001-1, where a `t1` game's tier table allows no declared
> lever, so an audit lever sighting could be neither declared nor
> repaired and the slot could only ride the ladder to
> `verifier.round_cap` and park. The CODE default is still `reject`:
> a config with no `deception_action` key behaves exactly as it did.

> **The ladder now has a top, and the re-spec reads before it spends
> (2026-10-05, contract E-2).** `config/template.yaml` and the
> `arc-games run` overlay arm two new `orchestrator:` bools. Both are
> answers to g20261001-5, whose ledger is on disk at
> `out/batches/g20261001-5/ledger.jsonl` and is worth reading once:
>
> * `orchestrator.stage_fail_park: true` — a gate / S4 / S6 failure
>   whose count EXCEEDS `verifier.reject_cap` now PARKS the slot from
>   the state it failed at (`verified`, `gated` or `reviewed`) instead
>   of re-speccing it again. Unarmed, that ladder had no terminal at
>   all: lines 7, 10, 21 and 28 of that ledger read "gate fail 1/1",
>   "gate fail 2/1", "package fail 3/1" and "package fail 4/1" — three
>   of them past a cap of 1 — because over the cap the reason merely
>   gains the escalation mark. `verifier.round_cap` cannot bite there
>   (it counts only the verify lane's `implemented --> spec_ok` edges)
>   and `orchestrator.respec_cap` bounds only the S1 lint-kill loop, so
>   the sole remaining bound was the 64-step livelock guard, which
>   CRASHES. Armed, that same ledger stops at line 10 and lines 11-28
>   never happen.
> * `orchestrator.respec_feasibility: true` — the escalated re-spec
>   READS the findings it would answer and skips the S1 session
>   entirely when no spec amendment could answer them. The same
>   ledger's line 7 paid for a re-spec that left the spec hash
>   byte-identical (bd7b492e before and after); the payload still on
>   disk at `out/corpus/g20261001-5/lantern-path-parity-trace/
>   worker.stage-findings.json` is five `s6.seed-reject` rows, none of
>   which any declaration can make untrue. The slot parks at `spec_ok`
>   with the codes and `no S1 session was spent` in the ledger reason.
>   The classifier is deliberately one-sided: `solver-quality`,
>   `forbidden-static`, the gate's visual checks and `s6.seed-reject`
>   are futile, and EVERY other code — known or not — spends the
>   session. Wrongly spending one re-spec is a bill; wrongly parking is
>   a game nobody can finish.
>
> A park is NOT a death: the artifacts stand, nothing is deleted, it is
> outside the attrition fraction and it never aborts a batch (operator
> ruling, 2026-09-29, "We should never kill"). `--status` counts them, the
> batch report carries the reason under `parked`, and the run log
> prints `[b11] PARKED <slug>: …`.
>
> THE WAY BACK (contract E-5): `arc-games unpark <batch> <slug>
> --reason '<why>'` appends ONE recorded lift line restoring the slot
> to the state it parked FROM (read off the park line itself — never
> chosen), then prints the resume command. The lift runs nothing and
> exempts nothing: the slot re-enters the ordinary ladder under the
> batch's CURRENT config with its whole history standing, and it can
> park again (each lift is a new recorded operator act). Typical use:
> amend the config first (a dated recorded amendment — the 2026-10-01
> seamlock pattern) so the cause of the park is answered, then unpark,
> then resume. Do NOT unpark while the batch process is running: the
> append is flock-safe, but a running parent already holds the slot as
> terminal in memory and will not pick it up until the next resume.
>
> Contract E-2 also closed a third defect that is NOT knob-gated,
> because an amendment that undoes an amendment is simply wrong: a
> reconciliation can no longer WITHDRAW a term an earlier
> reconciliation ADDED, or re-add one it withdrew. That same ledger did
> both — `+manip.terraform` at line 12, `-manip.terraform` at line 14,
> on game bytes that never moved. Such a finding is refused as
> uncorroborated churn, the declaration stands, and the refusal is
> named on the ledger line (`reconciliation churn refused: …`), in the
> batch report's `churn_refused` block and in the run log. The first
> refusal buys the slot one revalidating round; a repeat falls through
> to the ordinary reject ladder.



```bash
cp config/template.yaml config/b004-<topic>.yaml
```

Then edit **only** the `batch:` block — `id`, `size`, `seed`, and
`tier_sequence` (which must name exactly `size` tiers). `config/template.yaml`
comments every other key with its default, what a non-default does, and which
batch proved it. Seeds 1, 2 and 3 are used (b001, b002, b003 + b003r2); pick an
unused one.

Validate before you spend anything — this loads the config and runs every
strict S0 check, and writes nothing:

```bash
.venv/bin/python -c "from gen.config import load_config; \
  from gen.s0_ideas import check_config, load_vocab; \
  cfg = load_config('config/b004-<topic>.yaml'); check_config(cfg, load_vocab(cfg)); \
  print('config OK')"
```

A typo in any signed knob fails right here, by name, for free.

#### `batch.mix.hazardless` — why 0.5, and the two official figures

The template ships `0.5` and you should leave it there. The officials give two
different numbers for "how much of the ecosystem is hazardless", and both are
correct, because they count different things:

| figure | what it counts | source |
| --- | --- | --- |
| **11 of 25** (0.44) | officials with no **lethal** hazard — budget exhaustion is the only loss | `spec-v0.3.md:176`; `affordance-language.md:81` names all eleven |
| **16 of 25** (0.64) | officials carrying no `hazard.*` **term** at all | `mechanics/game-term-matrix.csv`, the three `hazard.*` columns |

The seven-game wedge between them is a definition difference, not an error in
either source. `wa30` is the adjudicated exhibit: its `hazard.static` was ruled
ABSENT because the purple block can be killed and cannot kill you — a
nuisance-NPC, not a lethal hazard (`adjudication.md:62`). The matrix counts "no
hazard entity"; the prose counts "no way to die".

**The ruling (project decision, 2026-09-28): `0.5` stays, and hazardless is NOT a
conformance axis.** It sits between the two figures, it is a sampling knob
rather than a target, and nothing in this pipeline measures a batch's realized
hazardless share against either number — so do not read a batch that came out
1-of-2 or 3-of-3 hazardless as off-target. It came out as the draw fell.

The full reconciliation, with the wedge games listed, is in
`gen/visual_canon._wants_danger`. Canon-side (duckWM `GEN/`) the two sources
still each state one figure; that is flagged for the canon owner and is not
something a batch config can fix.

### Run it

```bash
.venv/bin/python -m gen.orchestrator --config config/b004-<topic>.yaml
```

That is the whole start command. It has no `--dry-run`; the cheap dry run is
the `--status` call in §3, which replays the ledger and runs nothing. The
command above was **not** executed for this document — starting a batch spends
real driver sessions. Everything documented about its output is quoted from
the real `b003r2-simplicity` run transcript, reproduced in §4.

It is long-running and foreground: b002's three slots spanned two days. Keep
a transcript:

```bash
.venv/bin/python -m gen.orchestrator --config config/b004-<topic>.yaml 2>&1 \
  | tee out/tmp/b004-run1.log
```

(`out/` is gitignored, so logs there never enter a commit.)

Slots are worked **sequentially**, one at a time, unless the config arms
`orchestrator.parallel_slots: true` beside `workers: N > 1` (contract P-5 —
what `arc-games run … --workers N` writes for you). Unarmed, `workers` is
still decorative and nothing spawns, which is what every batch to date ran.
Armed, the run becomes a parent: it draws every idea itself, then runs one
child process per slot per wave (`--slot <slug>`), each appending its own
slug's lines to the one ledger and its own console to
`out/batches/<batch>/<slot>.slot.log`. A child that fails never interrupts its
siblings — its ledger state stands and a re-run picks exactly it up.

---

## 3. Watch it

### `--status` — the replayed ledger, runs nothing

Safe at any time, including while a batch is running:

```bash
.venv/bin/python -m gen.orchestrator --config config/b003r2-simplicity.yaml --status
```

```
[b11] batch b003r2-simplicity | size 2 | ledger /…/out/batches/b003r2-simplicity/ledger.jsonl
[b11] slug                   state        lines  lint/resamp/verif/crash/dead respec       usd    tokens in/out  last
[b11] b003r2-simplicity-s001 pulled           9  0/0/0/0/0                         0    5.0129     100818/67932  2026-09-25T14:36:20.501178+00:00
[b11] b003r2-simplicity-s002 packaged         9  0/0/0/0/0                         0    3.6342     100188/61487  2026-09-25T14:36:14.128852+00:00
[b11] states: {'packaged': 1, 'pulled': 1}
[b11] attrition: 0/2 dead = 0.00 (max_attrition 0.3) | 1 pulled at review (a human verdict, not attrition)
[b11] COMPLETE (review complete) — 2/2 slot(s) terminal, 0 dead
[b11] cost note: usd totals cover s2_implement + s3_verify + s5_battery only; s0/s1 sessions and the s3_gate/s4_baselines/s6_package compute are unpriced
```

Column by column: the **slot slug** (`<batch.id>-s001`, stable from birth —
*not* the game's slug, which only exists once S1 names it and changes under a
re-sample), the current state, how many ledger lines the slot has written, the
five reject counters, the re-spec count, dollars, tokens, and the last
transition's timestamp. A slot that has never been sampled prints `(unborn)`.

The five counters are, in order: **lint kills** · **re-samples** · **verifier
rejects** · **battery crashes** · **green-loop deaths**. b001's single slot
reads `3/3/12/1/0 respec 9` — three lint kills, three re-samples, twelve
verifier rejects, one battery crash, nine re-specs. b002's three read
`0/0/6/0/0 respec 3`, `0/0/7/0/0 respec 3`, `0/0/7/0/0 respec 3`. b003r2's two
read `0/0/0/0/0 respec 0`.

The `respec` count is derived from the ledger, not from a counter — so it
survives a resume. The two closing lines apply the same §4 kill criterion the
run applies, off the same ledger: **`dead` slots are attrition; a `pulled` slot
is a human verdict and is counted separately.** A batch whose slots are all
terminal with nothing dead reads `COMPLETE (review complete)`.

### The ledger

`out/batches/<batch.id>/ledger.jsonl` is append-only, one JSON object per state
transition, and **it is the resume state**. A line is written *after* the
stage's artifact is on disk, so a kill between the two costs exactly one
idempotent re-run.

```json
{"slug": "b003r2-simplicity-s001", "from": "spec_ok", "to": "implemented",
 "reason": "validate green in 2 attempt(s)",
 "hashes": {"spec": "f368ae0b…", "game": "0fd94aa4…", "stage_input": "b9e25e3b…"},
 "cost": {"usd": 3.652365, "tokens_in": 57, "tokens_out": 40793},
 "ts": "2026-09-25T13:14:09.368668+00:00"}
```

`spec` is `sha(spec.yaml)`, `game` is `sha(game.py + solver.py)`, and
`stage_input` digests that stage's declared inputs. `cost` is `null` for stages
whose API surfaces no cost (see §6). The birth line has `"from": null`.

`out/batches/<batch.id>/batch-report.json` is rewritten at the end of every
run with the per-slot rows, the per-stage cost table, attrition and the review
queue.

### What each state means

There are twelve states and the state machine is architecture §4's diagram
transcribed edge for edge; an edge the diagram does not draw raises rather than
being recorded.

| state | reached when | what runs next |
|---|---|---|
| `ideated` | S0 sampled an idea for the slot | S1 spec writer |
| `respec` | the §11 linter killed the spec | S0 re-samples |
| `spec_ok` | the spec passed lint | S2 implementer |
| `implemented` | the coded loop reached validate-green | S2b verifier |
| `verified` | the blind intent audit came back clean | S3 merged gate |
| `gated` | structural + robustness green | S4 baselines |
| `baselined` | g-sampler + cap-fit done | S5 battery |
| `played` | the battery finished | **nothing — you decide** |
| `reviewed` | you accepted it | S6 packager |
| `packaged` | terminal ✅ the game shipped | — |
| `dead` | terminal — the green loop hit its cap twice | — |
| `pulled` | terminal — you rejected the game | — |

`played` is the checkpoint. There is no automatic path out of it.

### Exit codes

`0` every slot terminal · `2` stopped (review, blocked, or attrition) · `1`
usage or config error. Verified: `--status` exits 0; a bad `--review` argument
and a missing config both exit 1 with a one-line `[b11] ERROR …`.

---

## 4. The review stop

When a slot reaches `played`, the run stops and prints exactly this (real
transcript, `b003r2-simplicity`, 2026-09-25):

```
[b11] REVIEW REQUIRED b003r2-simplicity-s002 @ played — architecture §4 has no auto path out
[b11]   accept: .venv/bin/python -m gen.orchestrator --config config/b003r2-simplicity.yaml --review b003r2-simplicity-s002:accept
[b11]   pull:   .venv/bin/python -m gen.orchestrator --config config/b003r2-simplicity.yaml --review b003r2-simplicity-s002:pull
[b11]   visual: /…/out/corpus/b003r2-simplicity/conduit-watch/worker.gate/visual-report.md
[b11] STOPPED (review)
```

(That transcript predates the `cost note:` line, which a run now prints just
above the review block — see §6.)

Note the mismatch that will trip you up: the `--review` argument is the **slot
slug** (`b003r2-simplicity-s002`), while the artifact path is the **game slug**
(`conduit-watch`). Copy the printed command; do not retype it from the path.

### Read the visual card

`worker.gate/visual-report.md` is the legibility evidence, and it exists only
when `gate.visual_card: record` is set (the template sets it). It gives you,
per captured frame: distinct colors, connected-component object count, block
run-mode, and each number beside the officials' own measured band. Exactly one
line in it can ever reject a game — the level-1 color floor (≥ 4 distinct
colors, which is the officials' own minimum) — and the template keeps it in
`record` mode, so on your first batches it measures and never blocks.
`visual-contact-sheet.png` beside it is the same frames as one image strip.

### Play the game

**There is no playable copy of the game at the review stop.** The play mirror
is written by S6, one edge *later*, after you accept. This is a known gap: every
human review to date used a hand-built preview.

Build one yourself. The play server discovers games with
`glob(<root>/*/*/metadata.json)` and loads the first `*.py` beside the metadata
it finds, so a preview is two files in a two-deep directory:

```bash
SLOT=out/corpus/<batch>/<game-slug>
PREVIEW=/tmp/preview           # anywhere outside out/play
mkdir -p $PREVIEW/<game-slug>/preview
cp $SLOT/worker/game.py $PREVIEW/<game-slug>/preview/<game-slug>.py
.venv/bin/python - <<PY
import json, pathlib
meta = json.load(open("$SLOT/worker.s4/metadata.json"))
pathlib.Path("$PREVIEW/<game-slug>/preview/metadata.json").write_text(json.dumps({
    "game_id": "<game-slug>-preview",
    "title": "<Game Slug> (preview)",
    "tags": ["generated"],
    "baseline_actions": [int(v) for v in meta["baseline_actions"]],
    "default_fps": 30,
}, indent=2) + "\n")
PY
```

Then start the server against that root:

```bash
.venv/bin/arc-games play --root $PREVIEW
# or, the same thing by hand:
PLAY_GAMES_DIR=$PREVIEW .venv/bin/python tools/play/server.py
```

The player is **vendored** — `tools/play/`, contract L-2, with
`PROVENANCE.md` recording what it was copied from and every change made to it.
There is nothing to install and no duckWM checkout involved.

It serves `http://127.0.0.1:8009/` (`PLAY_PORT` overrides the port) and prints
which catalog is live and where it logs. Logs are **derived** from the games
root — `<root>/../play-logs-<root-name>/` — and deliberately not settable on
their own, so a preview's logs can never land in duckWM's manual-play
calibration corpus.

The **seed** selector beside `mode` plays a game at a layout other than the
packaged one: it offers `canonical (as packaged)` (the default, and exactly
`Game()` with no argument), every seed listed in that game's
`package/manifest.json` labelled with the win and level count S6 measured, and
a box for any seed you like. A preview built the way above has no manifest, so
there it is canonical plus the free box. The seed in play is on screen for the
whole session and is written into the play log (`layout_seed`, `null` =
canonical), so a seeded run can never be read as a run on the packaged build.

Verified: the recipe above, run against `conduit-watch`, was discovered by the
server's own loader as `conduit-watch-preview | levels 8`. The server was
loaded in-process to read its discovery, not bound to a port.

Once a game is packaged, the same server shows the real mirror instead — see
§8 and `OUTPUT-FORMAT.md`.

### Decide

```bash
.venv/bin/python -m gen.orchestrator --config config/<batch>.yaml --review <slot-slug>:accept
.venv/bin/python -m gen.orchestrator --config config/<batch>.yaml --review <slot-slug>:pull
```

`accept` sends the slot to S6 and packages it. `pull` is terminal: the game
stays on disk as the measurement record and is never packaged. Both were used
on b003r2 — one accept, one pull ("I need more levels"; it implemented 3 of 7
declared levels).

An `accept` that packages also **promotes**: the game is copied to
`games/<game-slug>/game/`, the tracked shelf the team shares (§9). A `pull`
withdraws that entry if one is somehow there — normally there is not, because a
pulled slot never reached S6.

The decision is recorded in the ledger like any other transition. Nothing in
the pipeline can make it for you.

---

## 5. Resume after any stop or kill

**Re-run the identical start command.**

```bash
.venv/bin/python -m gen.orchestrator --config config/<batch>.yaml
```

The ledger replays, the provenance hashes are recomputed, and a completed
stage whose inputs are unchanged **never runs again**. A stage whose inputs
*did* change re-runs and says so:

```
[b11]   s2_implement: inputs changed since the ledger — re-ran
```

This holds for a `Ctrl-C`, a machine crash, a killed session and a clean stop:
the ledger line is appended only after the artifact is on disk, so the worst
case is one idempotent re-run of the stage that was in flight. Do not hand-edit
the ledger and do not delete artifacts to "force" a re-run — change the input
and the hash cascade will do it.

There is no separate resume flag and no `--force`.

---

## 6. What a batch costs

Measured, from the ledgers (`--status`, all four batches, 2026-09-27):

| batch | slots | total | per slot | shipped |
|---|---|---|---|---|
| b001-pilot | 1 | $84.85 | $84.85 | 1 packaged |
| b002-triple | 3 | $162.34 | $54.11 | 3 packaged |
| b003-simplicity | 2 | $19.09 | — | stopped mid-run by ruling |
| b003r2-simplicity | 2 | $8.65 | $4.32 | 1 packaged, 1 pulled |

**$84.85 → $54.11 → $4.32 per slot.** The drop is not a pricing change: it is
the convergence work. b001's one slot burned 44 ledger lines, 12 verifier
rejects and 3 lint kills; b003r2's slots each ran 9 lines, one audit round and
zero rejects.

The per-stage table the run prints (real, b003r2):

```
[b11] cost $8.6470 | tokens 201006/129419 | 6 priced transition(s)
[b11]   s0_ideas        2 transition(s) | unreported | tokens None/None
[b11]   s1_spec         2 transition(s) | unreported | tokens None/None
[b11]   s2_implement    2 transition(s) | $5.3396 | tokens 99/59761
[b11]   s3_verify       2 transition(s) | $3.2990 | tokens 18/69280
[b11]   s3_gate         2 transition(s) | unreported | tokens None/None
[b11]   s4_baselines    2 transition(s) | unreported | tokens None/None
[b11]   s5_battery      2 transition(s) | $0.0084 | tokens 200889/378
```

### The caveat, stated plainly

The run and `--status` both print it now, as a fixed note:

```
[b11] cost note: usd totals cover s2_implement + s3_verify + s5_battery only;
      s0/s1 sessions and the s3_gate/s4_baselines/s6_package compute are unpriced
```

**Every dollar figure in this repo covers three stages: S2 (implement), S2b
(verify) and S5 (battery).** Those are the only stages whose public API
surfaces a cost, and the orchestrator never invents a number — S0 and S1 run
real agent sessions and report `unreported`, and the gate, S4 and S6 are pure
compute. So the real spend on any batch is **higher than the number printed**,
by the S0/S1 sessions. Do not quote a batch total as its true cost.

There is no spend limit and no stop-loss: the $120 cap was rescinded by
project decision on 2026-09-24 ("no hard limits, resilient pipeline first"). Spend is reported,
never enforced.

---

## 7. When things fail

### A blocked slot

The state machine will not travel an edge the diagram does not draw. Where a
stage's own failure routing has no §4 edge — the gate at `verified`, S4's
cap-fit reject at `gated`, S6's seed-reject at `reviewed` — the slot is
**blocked** and reported loudly instead:

```
[b11]   BLOCKED at s3_gate: <the stage's own reason>
[b11]   architecture §4 draws no failure edge out of 'verified'
```

`stop_reason` becomes `blocked` and the run exits 2. A block is a *diagnosis*,
not a state: read the stage's report under the slot dir (§8), fix the cause,
re-run. The other blocks you can hit, with the note each prints:

| block | note |
|---|---|
| lint kills at `orchestrator.respec_cap` | §4 draws no edge from respec/ideated to dead |
| an S2 driver outage | infrastructure outage, not a game failure — green_failures not charged |
| an escalated re-spec with no verifier report | §3 S2b escalates WITH its findings |
| a re-run on changed inputs that failed | the ledger still records this stage's earlier verdict |

### Driver outages

An auth expiry, a usage limit, a 429 or a missing `claude` binary says nothing
about the game. Those raise a typed driver error, consume **no** green attempt,
and block the slot instead of killing it. Resume when the driver is back and S2
picks up where it stopped. The error message carries its own user-side
remediation (`claude auth login`, or the OpenAI key fix for the codex lane).

### Respec caps

Two independent caps, both from architecture §4:

- **verifier reject ×2 → respec.** Two audit rejects against the same spec
  escalate: the spec is rewritten with the findings, and the slot returns to
  `spec_ok`.
- **green-attempts cap ×2 → dead.** The implementer gets
  `implementer.max_green_attempts` tries per attempt-set; blowing the whole
  budget twice is the only route to `dead`.

Plus `orchestrator.respec_cap` (default 2; both b002 and b003r2 ran 4): a slot
the linter keeps killing cannot die — §4 draws no such edge — so at the cap it
blocks.

### Where killed specs go

A lint-killed spec is **evidence, not rubbish**. It is moved, never deleted, to

```
out/corpus/<batch>/.killed/<game-slug>-<timestamp>/
  idea.json  lint-report.json  spec.md  spec.yaml
```

A killed *escalated rewrite* lands in the same place with `-respec-` in the
directory name — that path exists so a killed rewrite can never evict the live
spec the ledger claims and the worker is implementing (the pilot lost a spec
that way once). b001 has five entries; b002 has one. Read `lint-report.json`
there to see exactly which §11 rule killed the spec.

### Known rough edges (Generator Readiness audit, 2026-09-27)

Honesty findings on the record, all of them things you may notice and wonder
about. Four were closed the same day and are listed so that older reports and
transcripts still make sense:

**Still true:**

- The **battery has never been consumed by any gate** and rarely completes its
  passes. It is evidence, not a filter.
- The review stop **cannot offer play** (the mirror lands one edge later) —
  see §4.
- Every `$` figure covers S2/S2b/S5 only — see §6.
- There are **zero recorded play sessions** for the shipped games.
- The **entire C-4 tranche and the level-variety rule landed after the last
  live run**, so `verifier.confirm_pass`, the birth-time level-count gate and
  the variety guidance have never run on a real batch. The template arms them;
  your batch is the first measurement.

**Closed 2026-09-27 — you may still see the old shape in archived reports:**

- `verifier.reject_cap` was a **dead config key** (escalation hardwired to 2);
  it is now read. `lint.strict` and `battery.smoke` were stamped into reports
  and read by nothing; both keys are gone.
- `respec_runs` read 0 in every shipped batch report — an in-memory counter
  that died on resume, against ledgers full of re-specs. It is now derived from
  the ledger, which is why `--status` has a `respec` column.
- A human `pull` was counted as attrition, so a small batch with one deliberate
  pull printed `BATCH ABORTED`. It happened on b003r2
  (`out/pilot/b003-freeze.md` addendum 2). Attrition is now dead-only, and
  b003r2's ledger replays as `COMPLETE (review complete)`.

The standing work plan for all of this is the private **Generator Readiness**
page, sequenced by the maintainers.

---

## 8. Where every artifact lives

Per batch:

```
config/<batch>.yaml                      the batch's identity (sha-recorded in the freeze record)
out/batches/<batch>/ledger.jsonl         append-only transitions = the resume state
out/batches/<batch>/batch-report.json    rewritten each run: slots, costs, attrition, review queue
out/ideas/<batch>/idea-00N.json          one S0 idea per slot
out/ideas/dedupe-history.jsonl           cross-batch dedupe keys
out/pilot/<batch>-freeze.md              the ruling record: what this batch measured, and why
```

Per slot — one directory named by the **game** slug:

```
out/corpus/<batch>/<game-slug>/
├── idea.json                       the S0 idea this spec was written from
├── spec.yaml                       THE spec (spec_hash = sha of this file)
├── spec.md                         the same spec as prose
├── lint-report.json                every §11 rule's verdict
├── payload.md                      the exact prompt handed to the implementer
├── worker/                         the implementer's sandbox — game.py + solver.py live here
│   ├── game.py  solver.py          game_hash = sha(game.py + solver.py)
│   ├── Makefile  worker.mk  tests/ the validate targets the green loop runs —
│   │                               scope · ruff · the battery · the SEED SWEEP
│   │                               (S6's own seed list, won in-loop or red)
│   └── AGENTS.md  README.md        the sandbox's own instructions
├── worker.seeds.json               the seeds S6 will validate at — the sweep's input
├── worker.staged/                  the last validate-green snapshot (patch-baseline's source)
├── worker.attempts.jsonl           one line per green-loop attempt
├── worker.implement-report.json    S2's verdict
├── worker.verifier-report.json     S2b's blind audit: findings, both directions
├── worker.frames.json              the frames sidecar S2b captured (the visual card's input)
├── worker.lever-history.json       per-round lever sightings (corroboration windows)
├── worker.term-history.json        per-round term sightings (same)
├── worker.gate/
│   ├── acceptance-report.json      the merged structural gate
│   ├── robustness-report.json      the robustness layer
│   ├── visual-report.md            ← THE REVIEW READS THIS
│   ├── visual-report.json          the same numbers, machine-readable
│   └── visual-contact-sheet.png    the measured frames as one strip
├── worker.s4/
│   ├── metadata.json               baseline_actions per level — the difficulty budget
│   ├── actions/level-N.json        the winning solver line, per level
│   └── s4-report.json              the g-sampler + cap-fit record
├── worker.s5/
│   ├── battery-report.json         the battery's play attempts
│   └── battery-levels.csv          per-level outcomes
└── worker.s6/
    ├── s6-report.json              seeds validated, TSV stats, §6 flags, paths
    └── package/                    ← THE SHIPPED ARTIFACT (see OUTPUT-FORMAT.md)
        ├── manifest.json
        ├── tsv/level-set.tsv
        └── duck-intake/<slug>_perfect/human_policy/unprocessed_game.tsv
```

And, written by S6 outside the slot:

```
out/play/<game-slug>/<game_hash8>/    the playable mirror: <slug>.py + metadata.json
out/play-logs-play/                   play sessions against that mirror (derived path)
```

Killed specs go to `out/corpus/<batch>/.killed/` (§7). `out/tmp/` holds
per-stage scratch directories and `out/smoke/smoke.jsonl` the backend smoke
ledger. All of `out/` is gitignored — which is why an accepted game is also
copied to the tracked shelf, §9.

---

## 9. `games/` — the shared shelf

Everything above lives in `out/`, and `.gitignore` ignores `out/*`. So a
teammate who clones this repo gets the pipeline and **none of the games**. The
shelf is the fix: a tracked top-level `games/` that only ever holds **approved,
packaged** games, so sharing a game is `git pull`.

```
games/<game-slug>/game/
├── game.py                    the packaged build's bytes (identical to worker/game.py)
├── spec.yaml                  the spec those bytes were built from
├── metadata.json              the play server's record: game_id, title, baseline_actions, fps
└── package/                   the same three files OUTPUT-FORMAT.md §1 describes
    ├── manifest.json          …with its `paths` rewritten RELATIVE to this directory
    ├── tsv/level-set.tsv
    └── duck-intake/<slug>_perfect/human_policy/unprocessed_game.tsv
```

**What promotes, and when.** One call, at one edge: `reviewed --> packaged`. An
accept that packages promotes; a seed-reject packages nothing and therefore
promotes nothing; a `pull` happens one edge earlier, so a pulled game has no
package to promote and its shelf entry is withdrawn if one exists. Nothing else
writes `games/`, and promotion copies — it never re-emits a TSV or re-validates
a seed, so a shelf entry can only hold bytes `out/` already holds.

The promotion is part of what `packaged` means now: if it cannot be vouched for
(the worker's bytes moved after packaging, the spec is missing, the intake copy
is not byte-identical to the canonical TSV) the stage fails **loudly** and no
`packaged` line is appended. Fix the cause and re-run; the stage is idempotent.

**Back-promoting what predates the shelf** — and rebuilding the whole shelf from
`out/` at any time:

```bash
.venv/bin/python -m gen.tools.promote_games --backfill --dry-run   # discover only, writes nothing
.venv/bin/python -m gen.tools.promote_games --backfill             # promote, then print the table
```

It scans `out/corpus/*/*/worker.s6/package/manifest.json`, counts what is
**on disk** (never a hand-kept list), promotes every `verdict: packaged` one and
prints a row per package — including the ones it skipped and the verdict it
skipped them for. Re-running is byte-idempotent: each entry is replaced whole,
so the tree depends only on the corpus. A bare invocation with no `--backfill`
does nothing on purpose — the shelf is tracked, so writing it is never a default.

**Playing the shelf** — the same server as `out/play`, pointed one directory
over (that is why the entry is `games/<slug>/game/`: the server's discovery glob
is `<root>/*/*/metadata.json`):

```bash
.venv/bin/arc-games play                    # the shelf is the default root
PLAY_GAMES_DIR=games .venv/bin/python tools/play/server.py   # the same, by hand
```

A shelf entry carries `package/manifest.json`, so here the seed selector lists
every seed S6 validated for that game alongside `canonical (as packaged)`.

**Know what you are committing.** A shelf entry is 6–25 MB, because it carries
its trajectory TSV twice — `tsv/level-set.tsv` and the byte-identical
`duck-intake/…` copy the consumer's own glob needs (`OUTPUT-FORMAT.md` §1/§6).
Six games is ~95 MB. `games/` is **committed by hand**, like every other change
in this repo: the pipeline writes the shelf, it never commits it.

---

## What is NOT in this file

- **The build history** and the working rules for changing the pipeline
  live in the maintainers' engineering record, which is not published.
- **The rulings** that made each knob what it is:
  `out/pilot/R1-freeze.md`, `out/pilot/b002-freeze.md`,
  `out/pilot/b003-freeze.md` (read its addenda — they are the most recent
  decisions in the repo), and `out/pilot/visual-findings.md`.
- **Consuming the games** you or someone else produced:
  [`OUTPUT-FORMAT.md`](OUTPUT-FORMAT.md).
