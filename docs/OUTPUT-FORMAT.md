# OUTPUT-FORMAT — consuming a packaged game

This is the **consumer** half of the docs: what a shipped game looks like on
disk, how to read its trajectory file, and how to feed it to the one consumer
that has actually eaten it. You do not need to run the generator to use any of
this. If you want to *produce* games, read [`RUNBOOK.md`](RUNBOOK.md).

**Read this first — the honest scope.** `sprite_lib` (the duck's perception
stack) is today's **proven** consumer: all five packaged games run its
parse → bootstrap → scored-eval ladder with zero errors and 100% pixel-exact
reconstruction, and 4 of 5 pass its own gate — which the official control game
`ar25` fails. **World-model training is not testable from duckWM**: there is
no WM trainer in that repo (verified across all 60 refs;
`out/pilot/b003-freeze.md` addendum 7). So what has been demonstrated is that
our output is *parseable and perceptually well-formed to a real existing
consumer*, not that it is trainable. Do not stretch the claim.

Everything below was measured against this tree on 2026-09-27.

---

## 1. Where the games are, and what is in a package

Five games are packaged today:

| game | batch | TSV rows | levels | size | mouse verbs |
|---|---|---:|---:|---:|---:|
| `pump-flow-match-glow` | b001-pilot | 97 | 8 | 3.0 MB | 0 (keyboard only) |
| `pump-phase-time-echo` | b002-triple | 153 | 8 | 4.9 MB | 152 CLICK |
| `core-ward-phase-gates` | b002-triple | 285 | 8 | 10.9 MB | 124 CLICK |
| `convoy-in-the-fog` | b002-triple | 419 | 8 | 12.5 MB | 15 CLICK |
| `conduit-watch` | b003r2-simplicity | 349 | 8 | 10.5 MB | 116 CLICK |

Each package sits at
`out/corpus/<batch>/<game-slug>/worker.s6/package/` and holds exactly this:

```
package/
├── manifest.json                                              the provenance + assumptions record
├── tsv/level-set.tsv                                          the CANONICAL trajectory surface
└── duck-intake/
    └── <slug>_perfect/human_policy/unprocessed_game.tsv        a byte-identical copy at the
                                                                consumer's own literals
```

Three files, no more. `tsv/level-set.tsv` is the canonical artifact;
`duck-intake/…/unprocessed_game.tsv` is a **byte-identical copy** of it, laid
out at the path the duck's own discovery glob looks for (§6). Verified for all
five packages: the mirror's bytes equal the canonical file's, and no package
contains the string `MOUSE`.

The package is deterministic: the same worker and the same config produce a
byte-identical TSV, manifest and report on a re-run. Nothing in it is
timestamped or path-random.

`out/` is gitignored, so an approved game is ALSO copied to the tracked shelf
`games/<game-slug>/game/` — these same three files plus `game.py`, `spec.yaml`
and a play-server `metadata.json` (§8). **If you cloned this repo to use games
rather than to produce them, `games/` is the directory you want.**

---

## 2. The TSV dialect, column by column

14 tab-separated columns, one header row, `\n` line endings, UTF-8. One row per
action, plus one terminal row. The dialect is adapted (never imported) from the
canon's own reference emitter and was proven 8/8 structurally against
the reference `sprite_lib_v2` file with a byte-identical first observation.

The rows are **SARS**: `observation` and `level` describe the state *before*
the action in that same row; `reward` and `terminated` are the *result* of it.

**`sprite_lib` reads exactly three of the fourteen columns** — `observation`,
`action` and `level`, marked ★ below. (Verified: its `load_tsv_transitions`
touches those three and nothing else, and no Python file in the library reads
the `info` column's `arc_frame` payload.) Every other column exists for parity
with the reference dialect.

| # | column | ★ | value | notes |
|---:|---|:-:|---|---|
| 1 | `step` | | `1`…N | 1-based. The terminal row **repeats** the last action's step number. |
| 2 | `observation` | ★ | `[[0, 0, …], …]` | 64×64 ints, palette 0–15. Python `repr` of a list of lists, so `", "` separators. The board **before** this row's action. `json.loads`-able. |
| 3 | `info` | | `{"arc_frame": "…"}` | Doubly encoded — see below. |
| 4 | `level` | ★ | `1`…N+1 | 1-based current level = `levels_completed + 1` before the action. |
| 5 | `action_valid` | | `True` / `""` | Literal `True` on action rows, empty on the terminal row. Never `False` in a shipped package (only winning lines ship). |
| 6 | `duration` | | `0.0000` / `""` | A **constant**, not a measurement. See §5 Q4. |
| 7 | `action` | ★ | `["CLICK", {"x": 13, "y": 17}]` | The grammar is §3. Empty on the terminal row. `json.loads`-able. |
| 8 | `reward` | | `0` / `1` | Sparse. See §4. |
| 9 | `terminated` | | `True` / `False` | `True` only on the winning step and the terminal row. |
| 10 | `truncated` | | `False` | Always. No shipped line is truncated. |
| 11 | `explore_exploit` | | `""` | Always empty (a world-model column). |
| 12 | `world_model_path` | | `""` | Always empty. |
| 13 | `goal` | | `""` | Always empty. |
| 14 | `exploration_output` | | `""` | Always empty. |

Columns 11–14 are empty in **every** row, terminal included — matching the
officials, where all 260 rows of the reference file are empty there too.

### `info`, unpacked

`info` is JSON whose single key holds *another* JSON string:

```python
info  = json.loads(row["info"])               # {"arc_frame": "<json string>"}
inner = json.loads(info["arc_frame"])         # {"frame", "frame_data", "timestep", "trajectory_step"}
fd    = json.loads(inner["frame_data"])        # another JSON string, unpacked
```

`inner["frame"]` is the same grid as `observation` (verified equal), and
`inner["timestep"] == inner["trajectory_step"] == step - 1`. `fd` carries
`game_id` (`<slug>-<game_hash8>`), `guid` (`local-gen-<slug>` — a producer tag,
not a join key), `frame`, `state` (`NOT_FINISHED` / `WIN`), `levels_completed`,
`win_levels`, `full_reset`, and `available_actions` (e.g. `[5, 6, 7]`).

No Python file in `sprite_lib` reads `info` at all (grepped for `arc_frame`
across the library: zero `.py` hits, only the sample TSVs themselves). It is
there because the reference dialect has it.

---

## 3. Action-cell grammar

The cell is a two-element JSON array: `[verb, payload]`.

```
["UP", {}]                          a keyboard action — payload always empty
["CLICK", {"x": 13, "y": 17}]       the mouse verb — payload always exactly {x, y}, ints
""                                  the terminal row
```

The engine's action ids map to verbs like this:

| id | verb |
|---:|---|
| 1 | `UP` |
| 2 | `DOWN` |
| 3 | `LEFT` |
| 4 | `RIGHT` |
| 5 | `INTERACT` |
| 6 | `CLICK` |
| anything else | `ACTION<id>` (the reference emitter's fallback; includes `RESET`=0 and undo=7, both unmapped) |

Measured across the five packages: `{UP, DOWN, LEFT, RIGHT, INTERACT, CLICK}`
and nothing else.

### ACTION6 spells CLICK, and the spelling is load-bearing

This is the one place where getting a string wrong costs you 100% of the mouse
rows, silently. All 24 official trajectory files (duckWM sha `31f3a8b`) contain
**zero** `MOUSE` cells and 1575 `CLICK` cells. The consumer gates on the
literal in four modules plus two action-budget lists — `operation_tracking.py`
insists on `name == 'CLICK'` **and** `set(params) == {'x','y'}`, and
`selection.py`, `selection_markers.py` and `heuristic_sprite_bootstrap.py` each
compare against the same literal. A `MOUSE` spelling is not a synonym it
tolerates: it drops those rows without a word. Measured on `conduit-watch`,
116 of 348 actions became invisible; under `CLICK` the library learns button
semantics instead (`DarkGrayRect` → `DarkGrayButton`).

Every shipped package now emits `CLICK` and none contains `MOUSE` (verified).
If you hold an older copy, check it.

---

## 4. Terminal row, reward and level conventions

### The terminal row

One per file, always last. Blank `action`, blank `action_valid`, blank
`duration`, the **last action's step number repeated**, `terminated: True`,
`reward: 1`, and the final board in `observation`.

It matters to the parser in a way that is easy to miss: `sprite_lib` builds
transitions from `rows[:-1]` and takes each transition's *after* frame from the
**next** row. So the terminal row is consumed as the final `after`
observation, and its blank action means it is never a transition source.
Dropping it would cost you the last transition.

### Reward

Sparse 0/1 per row: `1` on a `levels_completed` increment or on `WIN`, and the
terminal row echoes the win reward. A winning file therefore carries
**`levels + 1` ones** — verified: all five packages report 9 ones over 8
levels. The engine's own per-transition reward is **not** emitted.

### Level

1-based and reads as "the level this action was taken in". It is
`levels_completed + 1` measured *before* the action, so the counter advances on
the row after a completion. The terminal row lands one past the last real
level: `conduit-watch`'s rows distribute as level 1→9 rows, 2→18, 3→21, 4→36,
5→75, 6→51, 7→45, 8→93, and level **9 holds exactly one row — the terminal
one**. If you group by level, expect that trailing singleton.

### Volume

Exactly one trajectory per game: S4's winning solver line, replayed at the
authored layout seed. No noisy lines, no failed lines, no pre-baked colour /
rotation / flip augmentation. Layout variants stay a sampler call rather than
extra files.

---

## 5. `manifest.json`, field by field

Twelve top-level keys.

| field | what it is |
|---|---|
| `schema_version` | the packager's schema (`b10.1` on all five). |
| `slug` | the game's slug, and the directory name everywhere. |
| `game_id` | same as `slug` at manifest level; the TSV's embedded `frame_data.game_id` is `<slug>-<game_hash8>`. |
| `verdict` | `packaged`. |
| `seeds` | `{requested, validated[], authored_seed}`. Each `validated` entry is `{seed, win, levels_completed, actions_total, error}`. All five games: 5 requested, 5 validated, all `win: true` at 8 levels. |
| `split` | `{train: 0.7, eval: 0.3}` plus the note that it is applied at slug level and officials are never in train. It is a **declaration**, not a directory layout — nothing here is pre-split. |
| `spec_hash` | `sha256(spec.yaml)` — the spec this game was built from. |
| `game_hash` | `sha256(game.py + solver.py)`, that concatenation in that order. Its first 8 hex chars name the play mirror directory. |
| `layout_contract` | `{present, legacy_no_layout}`. `present: true` means the game has a real `build_layout(seed)`; `legacy_no_layout` flags the pre-D13 toys that were packaged without one. All five shipped games: `{present: true, legacy_no_layout: false}`. |
| `section6_flags` | the assumptions this package leans on — see below. |
| `versions` | `{arcengine: "0.9.3", python: "3.12.8"}`. |
| `paths` | absolute paths back into the producing tree (`worker`, `out_dir`, `s4_metadata`, `tsv`, `manifest`, `play_mirror`, `report`) **plus** `duck_intake`, which is the one **relative** entry: it resolves against `out_dir`, not against the package dir. |

### `section6_flags` — read this before you build on the dialect

The trajectory contract with the duck team has open questions. Rather than
guess quietly, the packager **names every default it applied** in the manifest,
each with `pending_contract_answer: true` and a note giving the evidence. Seven
questions bind the packager and all five packages carry all seven:

| Q | default applied | what it means for you |
|---|---|---|
| Q1 | TSV canonical | `tsv/level-set.tsv` is the shipped trajectory surface; `duck-intake/` is the same bytes at the consumer's path. |
| Q3 | verbs in TSV dialect | the §3 mapping table, ACTION6 = `CLICK`. |
| Q4 | duration omitted | **a deliberate divergence.** The contract text says omit `duration`; the dialect we proved parity against writes the constant `0.0000` in every action row. We follow the proven dialect and flag it here. |
| Q5 | sparse reward | 0/1, `levels + 1` ones, engine transition reward not emitted. |
| Q6 | no baked augmentation | one TSV at the authored seed. |
| Q7 | empty WM columns left empty | columns 11–14 blank in every row. |
| Q9 | volume = 1 near-optimal per level-set per game | the solver's winning line, once. |

`pending_contract_answer: true` means exactly that: **an assumption, not a
ruling.** If your consumer needs a different answer to any of these, that is a
contract conversation, not a bug report — and Q4 is the one most likely to
surprise you.

---

## 6. The duck-intake mirror, and a worked `sprite_lib` run

`sprite_lib`'s evaluator discovers games by globbing
`<sample-dir>/*_perfect/human_policy/unprocessed_game.tsv` and derives each
game's id from the directory name with `removesuffix("_perfect")`. The
`duck-intake/` tree is written at exactly those literals, so intake needs
**zero renaming**.

### Getting the tool

`sprite_lib` is not in duckWM's working tree — it lives on the upstream
`sprite_lib_v2` feature branch, and the pinned sha every measurement in this
repo used is **`31f3a8b`** (the branch tip has since moved to `9f8eee1`, so pin
the sha, not the branch). Extract it read-only:

```bash
S=/tmp/spritelib                       # anywhere outside both repos
mkdir -p $S
git -C ../duckWM archive 31f3a8b src/ARC3-Inference | tar -x -C $S
```

Nothing in this repo writes into duckWM, and `git archive` does not either.

### The worked invocation (the C-5 closing proof's shape)

```bash
S=/tmp/spritelib
INTAKE=/tmp/intake
mkdir -p $INTAKE
cp -R out/corpus/b003r2-simplicity/conduit-watch/worker.s6/package/duck-intake/. $INTAKE/

PYTHONPATH=$S/src/ARC3-Inference ../duckWM/.venv/bin/python \
  -m inference.sprite_lib.tools.evaluate_sprite_library \
  --sample-dir $INTAKE --levels 1 -j 1 --exclude "" --json-out /tmp/result.json
```

Executed, verbatim, 2026-09-27:

```
conduit-watch L1: encoded 9/9 frames; 7 classes; 0 BaseSprites; completed without refitting
conduit-watch L1: pixel 100.00%; perfect frames 100.00%; base sprites 0; generation 5.78s; total 6.73s; PASS
TOTAL overall: 1/1 Passed; pixel 100.00%; perfect frames 100.00%; base sprites 0; PASS
```

Notes on the flags: `--exclude ""` is needed because the tool's default is
`lf52,bp35` (two official games it skips) — the empty string disables the skip
list. `-j 1` keeps it sequential and readable. Drop `--levels` to run the whole
level set. `--json-out` gives you `{summary, rows}` with per-level pixel
accuracy, base-sprite counts and timings.

Copy the mirror to a scratch directory rather than pointing `--sample-dir` at
`out/`. This particular tool wrote nothing beside its input in the verified run
above, but other entry points in that library were not checked, and a packaged
artifact is a provenance record.

To run all five games at once, copy all five `duck-intake/` trees into the same
scratch root. The lead's full ladder over the five fresh mirrors found all five
with zero renaming: **4 of 5 pass the duck's own gate, and the official control
`ar25` fails it** (one residual base sprite). The single outlier is
`convoy-in-the-fog` — 3 base sprites, 24 classes, 98 s against a 30 s flag —
the same failure mode as the control, just larger, and consistent with its own
visual-card object findings.

---

## 7. The play mirror

Packaged games are also mirrored into a shape a human can play:

```
out/play/<game-slug>/<game_hash8>/
├── <game-slug>.py        the game module, byte-identical to worker/game.py
└── metadata.json         {game_id, title, tags: ["generated"], baseline_actions, default_fps: 30}
```

`baseline_actions` is one action budget per level (its length is the level
count), carried over from the S4 metadata.

Contract I-1 (2026-10-07) added four additive keys to the S4 surfaces, all
absent on reports written before it: `s4-report.json` gains `caps.probe` (the
probe that measured the caps — `allowance`, the reworked budget-cap reader, or
`burn`, the legacy repetition reader), `caps.legacy_burn` (the old probe's
figures, always recorded beside the new under their own label) and
`config.g.centering` (`d7-replay`, the adjudicated ruler, or `effort-blind`,
the named alternative); `metadata.json` mirrors `caps_probe` and
`caps_legacy_burn`. A config carrying none of the new keys produces the
pre-I-1 bytes exactly.

The play server discovers games with
`glob(<root>/*/*/metadata.json)` and loads the first `*.py` beside the metadata
it finds — which is exactly why the layout is two levels deep.

Start it:

```bash
.venv/bin/arc-games play --root out/play
# or, by hand — the player is vendored at tools/play/ (contract L-2):
PLAY_GAMES_DIR=out/play .venv/bin/python tools/play/server.py
```

It serves `http://127.0.0.1:8009/` (override with `PLAY_PORT`) and prints which
catalog is live and where it logs. The log directory is **derived** from the
games root — `out/play-logs-play/` — and deliberately not settable on its own,
so generated-game logs can never contaminate duckWM's manual-play calibration
corpus.

`out/play/` currently holds 7 entries: the five packaged games plus `s6-seeded`
and `toy-play`, which are test fixtures, not games. The server command above
was not executed for this document (it binds a port and serves indefinitely);
its discovery was verified by loading the server module in-process, which found
each mirror and its level count.

---

## 8. `games/` — the shared shelf

Everything above is under `out/`, and `.gitignore` ignores `out/*`: a clone of
this repo carries the pipeline and no games. Approved games are therefore also
copied into a **tracked** top-level `games/`, so getting them is `git pull`.

```
games/<game-slug>/game/
├── game.py                    the packaged build's bytes (== the slot's worker/game.py)
├── spec.yaml                  the spec those bytes were built from
├── metadata.json              the play-server record (§7's shape, un-suffixed title)
└── package/                   §1's three files, copied
    ├── manifest.json          the ONLY file whose bytes differ from out/ — see below
    ├── tsv/level-set.tsv
    └── duck-intake/<slug>_perfect/human_policy/unprocessed_game.tsv
```

**What promotes:** only a game the human accepted and S6 packaged
(`verdict: packaged`). A seed-reject writes no package, and a pull happens one
state before S6 runs, so neither can reach the shelf. Promotion is a **copy**:
no TSV is re-emitted and no seed re-validated, so a shelf entry holds bytes
`out/` already holds. The count is whatever the corpus holds — six at the time
of writing, the five measured in §1 plus `tidegate-mosaic` (b004-validation),
which postdates that table.

**The one difference from `out/`.** `manifest.json` in `out/` embeds **absolute**
machine paths on purpose: it is one operator's record of one machine's run. A
shared copy cannot, so on the shelf every `paths` entry is either relative to the
entry's own directory or `null`, and the promoted manifest carries a `paths_note`
field stating which rule applied to what, plus a `promotion` block
(`{contract, shelf_entry, source_batch}`). Nothing else in the manifest changes,
and the `out/` manifest itself is untouched.

```json
"paths": {
  "worker": null,          "out_dir": ".",             "s4_metadata": null,
  "spec": "spec.yaml",     "game": "game.py",          "metadata": "metadata.json",
  "tsv": "package/tsv/level-set.tsv",
  "manifest": "package/manifest.json",
  "duck_intake": "package/duck-intake/<slug>_perfect/human_policy/unprocessed_game.tsv",
  "play_mirror": null,     "report": null
}
```

**Serving the shelf** is §7's command with the root moved — the entry is one
directory deep inside `games/<slug>/` precisely so the server's
`<root>/*/*/metadata.json` glob finds it:

```bash
.venv/bin/arc-games play                                     # the shelf is the default root
PLAY_GAMES_DIR=games .venv/bin/python tools/play/server.py   # the same, by hand
```

A shelf entry carries `package/manifest.json`, so the player's **seed**
selector lists every seed S6 validated for that game next to
`canonical (as packaged)` — the default, and exactly `Game()` with no argument.
An `out/play` mirror entry has no manifest, so there the choice is canonical or
a seed you type. Either way the seed is recorded in the play log as
`layout_seed` (`null` = canonical).

**Rebuilding the shelf from `out/`** (also how games packaged before the shelf
existed got there) — it counts what is on disk, not a list, and re-running is
byte-idempotent:

```bash
.venv/bin/python -m gen.tools.promote_games --backfill --dry-run   # discover only
.venv/bin/python -m gen.tools.promote_games --backfill
```

A shelf entry is 6–25 MB: like the `out/` package it carries the trajectory TSV
twice (§1), and the game modules and spec are small beside it.

If you only want to consume games, you never need the backfill: read `games/`
and stop. `RUNBOOK.md` §9 is the producer's half.

---

## 9. A short reader, in code

```python
import csv, json
csv.field_size_limit(10**9)          # observation cells are large

path = "out/corpus/b003r2-simplicity/conduit-watch/worker.s6/package/tsv/level-set.tsv"
with open(path, newline="") as fh:
    rows = list(csv.DictReader(fh, delimiter="\t"))

transitions = []
for before, after in zip(rows, rows[1:]):        # the terminal row is the last `after`
    if not before["action"]:
        continue                                  # never a transition source
    verb, payload = json.loads(before["action"])
    transitions.append({
        "level":  int(before["level"]),
        "before": json.loads(before["observation"]),
        "after":  json.loads(after["observation"]),
        "action": (verb, payload),                # payload is {} or {"x":…, "y":…}
        "reward": int(before["reward"]),
    })
```

That is the whole contract of the three read columns. Three cautions: raise
`csv.field_size_limit` (each `observation` cell is ~10 KB and each `info` cell
larger), use `json.loads` on `observation` and `action` (they are JSON, not
Python literals — `observation`'s `repr` spacing happens to be valid JSON), and
do not drop the terminal row.

---

## Where the rest of it is

- **Producing games:** [`RUNBOOK.md`](RUNBOOK.md).
- **Why the dialect is what it is:** `out/pilot/b003-freeze.md` addenda 7–8
  (the duck-consumption smoke and the CLICK/intake work), and the module
  docstring of `gen/s6_package.py`, which carries the full provenance for every
  choice above.
- **Per-game legibility measurements:** each slot's
  `worker.gate/visual-report.md`, and `out/pilot/visual-findings.md`.
