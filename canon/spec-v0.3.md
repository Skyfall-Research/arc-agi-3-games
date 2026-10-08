# spec-v0.3 — the ARC-AGI-3 game generator specification

> **Status: APPROVED (operator, 2026-09-21 — D26).** Assembled 2026-09-18 from
> the signed sources per D22; both D15 gates (this spec + the pilot plan)
> are now approved and the build is authorized. Supersedes spec-v0.2.
> Every section names its signed source; nothing here is new judgment.
> Assembly map: `provenance/spec-history/spec-v0.3-skeleton.md`. Decision log: `design/decisions.md`
> (D1–D25; build home = the sister repo `arc-agi-games`, dual agent
> backend localclaude | codex — D25).

## §0 Pipeline overview (source: provenance/reviews/re-arc-3-design-review.md, signed D22)

Our own build (D10-revised — no fork; Tufa's RE-ARC-3 is read-only
reference, D14), on the same proven stage interfaces:

```
ideas ──▶ spec ──▶ implement ──▶ validate ──▶ baselines ──▶ review ──▶ package
 (0)      (1)        (2)           (3)           (4)          (5)        (6)
```

- **Stage 0 — ideas**: coverage-steered sampling from the signed
  vocabulary (term-occurrence quotas; combat/rarity holes as optional
  targets); the five agent-failure families as first-class seeds; dedupe
  by mechanics tags; batch composition checked against the §5 corpus-mix
  targets **and the §3b objective floors + reach cap** (every family ≥ its
  floor per batch, `reach_goal` capped — unsteered generation collapses to
  reach/cover, measured on tufa: 82+47 of 165). Tufa's design-doctrine
  prompt text kept verbatim (an asset, vendored: `third-party/re-arc-3/`).
- **Stage 1 — spec**: emit the §11 machine-checkable spec alongside prose;
  a **linter kills** bad specs (closed vocabulary, curriculum shape vs the
  escalation grammar, contradiction scan) before implementation spends.
- **Stage 2 — implement**: Claude implements game + solver together in an
  isolated worker repo with a validate-until-green loop (their engineering,
  kept). The prompt carries the playbook, the four FORBIDDEN contracts,
  and the single orientation convention.
- **Stage 3 — validate**: the merged four-layer gate (§9).
- **Stage 4 — baselines**: the g-policy (§8) + baselines-fit-caps.
- **Stage 5 — review**: human reviewer sees GIF + verifier diff + battery
  stats + the objects-overview row.
- **Stage 6 — package**: seeded layouts (§7), the shippables (§10).

Component-level system design (artifact tree, stage templates, orchestrator,
config schema): `design/architecture.md` (ARCHITECTURE DRAFT, approved with
this spec). The five extensions over Tufa's design, each evidence-backed (D22):
intent validation (their co-adaptation hole), play-based difficulty (their
missing layer), statistical baselines (their raw solver counts), coverage-
steered ideas (their prose steering), solver-quality bar (their padding).

## §1 Purpose & consumers (source: D1)

The generator exists to produce **trajectories that improve the duck**,
consumed three ways: **world-model pretraining** (gym-TSV lane), **policy
SFT on wins** (duck-rollout lane), **RL / self-play** (the runnable env
itself). NOT built for eval. Consequences: every game solvable by
construction (solver-first), diversity and difficulty targeted at the
agent's frontier, honest per-level baselines as a by-product.

## §2 Engine & authoring contract (source: affordance-language.md §8, signed D21)

**REQUIRED (hard gates, the 8):**
1. The locus of control is identifiable within a few actions — unique-mover
   or selection-marker idiom (the corpus split is 10/9/6
   avatar/selection/click-only; a literal avatar is NOT required).
2. `sys_click` tags are truthful — always (the engine's click-action list
   and RL consumers read them); *visual* marking of clickability is a knob.
3. The budget triple: an edge-anchored meter exists · exhaustion is wired
   to `lose()` with the win check first (the 25/25 official pattern; the
   winning move is free) · the cap accommodates the solver's line + the
   g-margin (never a tn36-style baseline>cap).
4. The goal state is game-checkable (win predicate; solver reaches it —
   D11). Whether it is SHOWN is the `goal_legible` knob.
5. Every `-2` pixel ships with a declared reader (which mask consumes it);
   `-2` nothing reads is forbidden dead weight.
6. Explicit layer values for every overlap that matters — never
   declaration-order z (an official shipped an invisible mechanic that way).
7. Reserved HUD geometry declared (row 63 / row 0 / col 0 / custom);
   interfaces paint after the board and WILL overwrite it.
8. Default-tier palette discipline: white-0 reserved for
   selection/highlight; meter indices off-board; you/goal/danger unique
   on-board. Overloading is a *declared* deception lever only.

**FORBIDDEN (engine contracts, the 4):** interface paint keyed to palette
equality a real object can collide with (the frame lies) · leaving a
handler without `complete_action()` (the engine re-runs the action —
double-charge) · mixed accidental refusal semantics (charge-or-signal by
RULE, never by accident) · unread `-2`.

**Conventions:** one grid orientation for all generated code (no
bp35-style `[::-1]` authoring); rotation is render-side in the engine —
game logic runs in ONE declared space; static scenery pre-fuses per layer
at Level init (authored sprite counts ≠ runtime counts); settled frame =
`fd.frame[-1]`; a mechanic that must be learnable from trajectories must
survive into settled frames.

## §3 Mechanics vocabulary (source: vocabulary-v2-final.md, SIGNED D20 — 71 terms + budget.time kept-flagged/unverified, 16 groups; header corrected per the B4 adjudication, operator R1 ruling 2026-09-22)

Operational semantics throughout: a term is present iff the code
implements it reachably; dead code is recorded, never counted. Counts
below: (officials/tufa-live) from `mechanics/term-occurrence-final.csv`.

- **move**: coupled(3/5) · grid(17/119) · platform(1/5) · push(2/18) · slide(2/13)
- **flow**: autonomous(0/6) · pumped(2/1)
- **carry**: hold(2/7) · ride(0/6) · vehicle(1/1)
- **gate**: direct(0/4) · key(0/12) · phase(0/4) · plate(3/12) · remote(5/33)
- **hazard**: crush(0/2) · static(7/29) · timed(3/20)
- **agent**: delegate(1/1) · echo(2/1) · patrol(6/31) · stealth(0/2) · vision(1/5)
- **manip**: attribute(11/30) · group_shift(0/10) · group_toggle(1/2) · interlock(0/6) · merge(2/0) · ranged(0/3) · select_cycle(12/25) · swap(3/1) · terraform(3/18)
- **goal**: confirm(0/14) · cover(8/49) · keyed(7/18) · path_connect(1/7) · pattern_match(11/17) · reach(11/88) · rendezvous(2/16) · sequence(3/14) · survive(0/4) *(re-rated D24 — the v2 assembly had only ever adjudicated two of these nine for officials)*
- **budget**: cap(25/141) · time(0/0) — KEPT flagged-unverified (operator ruling; any claim must show a wall-clock read)
- **topo**: wrap(4/18)
- **info**: deception(1/39) · fog(3/5) · hidden_geometry(2/0) · legend(1/2) · probe(0/2) · recall(0/2) · telegraph(0/3) · viewport(2/2)
- **program**: commit(1/8) · compose(3/1)
- **state**: action_lag(0/16) · checkpoint(1/0) · facing(2/14) · health(0/2) · undo(5/22) · wait(0/20)
- **phys**: attract(1/3) · balance(2/2) · bounce(0/6) · drift(0/3) · reflect(1/5)
- **terrain**: conveyor(0/5) · dual_role(1/3) · keyed(0/3) · one_way(0/4) · track(2/0) · trail(0/7)
- **loss**: deadlock(0/10)

Full definitions with Counts/Not/Examples:
`mechanics/vocabulary-v2-final.md`. Per-game usage: `officials-mechanics-matrix.md`
(25×16 + frequencies), `officials-mechanics-digest.md` (196 how-lines),
`game-term-matrix.csv` (all 190 games). Rarities (29 rows) stay recorded
termless; promotion needs ≥2 independent sightings (D24 promoted r11l's
centroid-linkage into `phys.balance`).

## §3b Objectives (8 families, play-validated — restored by D24)

Every game declares **one primary objective family** (+ optional secondary)
from the closed vocabulary the operator's manual-play workstream validated against
all 25 officials (it consolidates tufa's 32 fragmented `obj.*` tags):
`reach_goal · cover_targets · collect_all · match_pattern · sequence ·
survive · connect · balance`. The field was first-class in spec-v0.1/v0.2
and silently dropped at the v0.3 assembly; D24 restores it with teeth.

**Crosswalk (family ↔ witnessing term).** A declared family must be
witnessed by a present term in `terms` (the §11 linter kills specs where it
isn't): reach_goal ← `goal.reach`, or `goal.rendezvous` for co-location
wins (co-location = reaching a moving goal; the "common-phase" reading of
rendezvous witnesses nothing — those games carry `goal.pattern_match`) ·
match_pattern ← `goal.pattern_match` (a VALUE comparison against a
reference; occupancy-only checks are `goal.cover`) · cover_targets /
collect_all ← `goal.cover` (cover = occupy/fill target cells, collect =
remove/consume every X) · sequence ← `goal.sequence` · survive ←
`goal.survive` · connect ← `goal.path_connect` · balance ← `phys.balance`.
`goal.keyed` and `goal.confirm` are structural modifiers, never a family's
witness on their own (`goal.confirm` = banking the reached goal state takes
a further player action — explicit or any-action; auto-expiring win
animations and simulation-trigger verbs do not qualify).

**Descriptive vs generative (D24 split rule).** For the measured corpus
(`mechanics/objectives.csv`, 190 rows: 25 triage-ground-truth + 57
fleet-judged + 108 crosswalk-derived) primaries are strictly witnessed;
official secondaries may be play-workstream **difficulty qualifiers**
(connect/survive/balance) without a win clause, tagged
`triage(qualifier-secondary)` — 12 of 25. Generated games get no such
exemption: both declared slots must be witnessed.

**Measured distributions (the diversity rationale).** Officials primaries:
reach 11 · match 6 · cover 4 · collect 2 · balance 1 · sequence 1. Tufa
primaries: reach 87 (52.7%) · cover 37 · match 15 · sequence 11 · connect 6
· collect 5 · survive 4. Unsteered prose-diversity generation (tufa's idea
prompt, vendored at `third-party/re-arc-3/`) collapses onto reach/cover —
hence §0's Stage-0 **objective floors** (each family ≥1 per ~20-game batch)
**+ reach cap ≈0.25** (`batch.mix.objective`, architecture §5), tuned at
the pilot.

## §4 Objects & archetypes (source: affordance-language.md §1-5,§9 + objects-overview.md, signed D21)

- **Locus idioms**: unique-mover (10 officials; usually hue-unique, blue-9
  the commonest "you") · selection-marker (9; **white-0 is the ecosystem's
  selection colour** — pinholes/cores/rings/brackets in ~8 games) ·
  click-only (6). Secondary: recolour-to-selection, rings, dim-the-rest.
- **Goal grammar**: the hollow-outline-that-fills idiom (~9 officials —
  frames, brackets, interlocking teeth; fuse/fill on satisfaction) ·
  the reference-display idiom (quarantined target panel / HUD chip) ·
  no-goal-drawn as the `goal_legible: opaque` lever (4-5 officials).
- **Danger**: ~11/25 officials have NO lethal hazard (budget is the only
  loss) — generated corpora must include hazardless games. Where danger
  exists the tell is a lever: unique-hue+telegraph (default) → texture /
  absence / camouflage / state-dependent (hard tiers).
- **Meters**: 25/25 exist; placement free (bottom row 14 · top 3 · side
  columns 4 · other 4); direction semantics free; lives-pips a variant.
- **Palette semantics** (16 indices): 0 selection/highlight (reserved) ·
  1-4 structural greys · 5 background/outline default · 9 the commonest
  avatar hue · 11 armed/attention · 13 rare high-salience event · 8/14
  unreliable as danger/GO. Full map in affordance-language §9.
- Per-game object detail: `design/objects/bestiary/<slug>.md` (25 files,
  frame-verified) and `design/objects/tufa-objects.csv` (1,053 rows).
  At-a-glance: `design/objects/objects-overview.md`.

## §5 Legibility & difficulty knobs (source: affordance §6-7, signed D21)

Named spec fields, every one DECLARED in §11:
- `refusal: visible | free | silent-charged` — default tier ships visible
  or free; silent-charged (17/25 officials) is the declared hard setting
  (drills the self-monitoring failure family).
- `goal_legible: obvious | inferable | opaque`.
- `danger_tell: unique-hue | texture | absence | camouflage | none`.
- `deceptions: [...]` — from the catalog (look-alike splits, palette
  overloading, decoy actions, lying displays, invisible load-bearing
  state, retrospective punishment). ALWAYS declared; the verifier diffs
  declared-vs-detected both directions.
- **Corpus-mix targets (per batch, not per game)**: ≈half hazardless;
  locus mix ≈ 10/9/6; deception density rising with tier.

## §6 Per-term implementation (source: playbook.md, signed D21)

The playbook carries pattern/knobs/traps for the ~30 high-frequency terms;
`provenance/objects-working/playbook-skeleton.md` holds every term's evidence lines; bestiary §3 = 25
reference implementations. Cross-cutting traps promoted to authoring
rules: refused moves still `complete_action()` · solver models
`state.action_lag` and `goal.confirm` trailing actions (they are PART of
the winning line and the baseline) · sokoban-class push pairs with
`loss.deadlock` or `state.undo` · one counter never means both budget and
`goal.survive` · every parsed field has a reader.

## §7 Layout & levels — the seeding mechanism (source: D13 + games-workstream constants, signed D22)

- **layout-from-seed is REQUIRED from birth**: a generated game's level
  layouts are functions of `layout.seed` — structure (walls, object
  placement, distances) varies under seed while the SPEC (terms, knobs,
  curriculum) holds. This is what Tufa's design promised and dropped
  (their layouts are hardcoded; augmentation never varies structure), and
  it turns the sampler into a true layout-variant source. Retrofit of the
  190 existing games is impossible; the requirement applies to ours only.
- Constraints per game: **6-10 levels** (official range); log effort range
  ≈ **9× cheapest→dearest level** (median 2.23, sd 0.88, independent of
  level count); **escalation grammar**: each level declares
  `relation_to_prev ∈ {new, reuse, compose}` — officials escalate by
  composition, and a mechanic is not established until reused in a
  contrasting context (their doctrine, kept).
- Baseline staircase must NOT be monotonic (0/25 officials are);
  `random_beats_L1` must be false; sprite/structural floors per the
  acceptance gate.

## §8 Difficulty & baselines (source: D7/D8/D9, signed D22; full model: design/difficulty-model.md)

- **g-policy (D7)**: `baseline_i = solver_i × g_i`, g drawn from the
  measured competent-replay distribution — per-level median **2.00×**
  (IQR 1.54-2.96, n=183), per-game **2.36×** (n=25) — reshaped to official
  statistics (non-monotonic, trend +0.65, floor ≥6, ~9× span), then
  batch-checked against the human band. Caveat carried: the reference
  replays are one human per game.
- **NEW hard check**: every level's baseline fits inside the game's own
  enforced cap (officials ship violations — tn36 72>61 — as session-sum
  artifacts; ours are per-attempt by construction and must fit).
- **D8**: the public runner grants exactly **5× baseline** per level —
  the budget convention batteries use. **D9**: difficulty calibration is
  fleet-level ONLY (per-game play ratios are residuals, ICC ≈ 0).
- Frontier context for targeting: 85/183 official levels unbeaten by any
  public model; five failure families (belief maintenance,
  self-monitoring, agency attribution, composition/commitment, temporal
  perception) are stage-0 seeds.

## §9 Validation gates (source: D11/D12/D22)

The merged four-layer gate, in order:
1. **Structural acceptance** (calibrated): sprite floors, level count,
   non-monotonic staircase, random-fails-L1, loc floor.
2. **Robustness**: Tufa's seven degenerate policies must all fail
   (adopted — better than a single random check).
3. **The intent-verifier (D11, expanded list locked at D22)**: an
   independent agent reads only the finished game and re-derives its
   mechanics audit-style — term-diff vs spec · reachability/dead-code ·
   truthful `sys_click` · enforcement wiring · `complete_action` audit ·
   every-parsed-field-has-a-reader · the canary defect classes ·
   deceptions declared-vs-detected · solver quality (no-op-prefix, BFS
   spot-checks on small levels, lag/confirm modeling). FP/FN rates get
   measured in the pilot.
4. **The battery (D12)**: the duck (OpenRouter) plays each batch at the
   5× convention, scored fleet-level against the band and frontier
   targets. Pilot runs a **smoke-scale battery** (tiny cap) until the
   OpenRouter budget is agreed.

## §10 Outputs & packaging (source: trajectory-contract.md D18 + D22)

Per generated game ships: `game.py` (arcengine-compatible, §2-compliant) ·
the solver · per-level winning action lists (`[action_id,{x,y}]` JSON) ·
`metadata.json` (per-level baselines per §8, tags, spec hash, seed) ·
**gym-TSV emission** (the sprite_lib dialect, SARS rows + terminal row —
our emitter is proven: 8/8 structural parity vs the team's own ar25 file,
byte-identical first observation). Batch ships an EnvSampler-style
sampler (ours-built on their design: gym interface, transition reward,
70/30 split convention, tag system). Augmentation ownership (sample-time
vs baked) awaits the team's §6 answer; sample-time is the default
assumption. Action↔frame pairing rule for all trajectory work: action *i*
↔ `frame[-1]` (the decoupling finding).

## §11 The machine-checkable game spec (stage-1 output; linted before stage 2)

```yaml
game:
  slug: str            # generated id
  title: str
  idea_ref: str        # stage-0 idea id
  terms: [v2-term]     # closed vocabulary (§3); linter rejects unknowns
  objective:           # §3b 8-family taxonomy (play-validated; restored from v0.2 by D24)
    primary: reach_goal | cover_targets | collect_all | match_pattern | sequence | survive | connect | balance
    secondary: same-enum | null
  locus: unique-mover | selection | click-only
  actions: {ACTION1..7: declared|absent, decoys: []}   # decoys = declared deception
  knobs:               # §5 — all mandatory
    refusal: visible | free | silent-charged
    goal_legible: obvious | inferable | opaque
    danger_tell: unique-hue | texture | absence | camouflage | none
    deceptions: [catalog-entries]
  palette: {you: idx, goal: idx, danger: idx|null, reserved: [0, meter-indices]}
  hud: {reserved: row63|row0|col0|custom-rect, meter: {placement, direction}}
  neg2_readers: [{sprite-class: mask}]    # every -2 declared (§2.5)
  layers: explicit                        # §2.6 attestation
  layout:
    seed: int          # §7 — layouts are functions of this
    grid: [w, h]
  levels:              # 6-10 entries
    - relation_to_prev: new | reuse | compose
      terms_introduced: [v2-term]
      sketch: prose
  budget: {enforced: true, displayed: bool, counts: str, lives: int|null}
  solver_notes: prose  # incl. lag/confirm obligations
```

Linter rules (stage-1 kill list): unknown terms · knob fields missing ·
undeclared deceptions referenced in sketches · curriculum violating the
escalation grammar (e.g. >2 consecutive `new`, nothing reused) · level
count outside 6-10 · palette collisions with reserved indices ·
**objective not witnessed** (declared family lacks its §3b crosswalk term
in `terms`) · contradiction scan (e.g. `danger_tell` set with no hazard
term; `refusal: visible` with a decoy-silent deception).

---
*Assembled from: vocabulary-v2-final.md (D20) · affordance-language.md +
playbook.md + objects-overview.md (D21) · provenance/reviews/re-arc-3-design-review.md as
signed (D22) · trajectory-contract.md (D18, team round pending) ·
decisions.md D1-D22. Approval of THIS document + the pilot plan are the
two remaining gates before generator code (D22's D15 disposition).*
