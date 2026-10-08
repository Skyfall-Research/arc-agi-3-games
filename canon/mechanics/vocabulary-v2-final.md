# Mechanics vocabulary v2-FINAL — **SIGNED OFF (operator, 2026-09-18)**

> **Sign-off record** (walk-through, grouped-by-strength; all rounds in the
> session log): budget.time **KEPT, flagged unverified** (operator ruling —
> private-set insurance; overrides the retire recommendation below, term
> count 71→**72**) · phys.weight→phys.balance APPROVED · budget.cap
> enforcement-as-attribute + all 16 sweep corrections RATIFIED · loss.*
> group KEPT · all five 2-sighting promotions KEPT (hazard.crush,
> manip.group_toggle, manip.merge, state.health, info.hidden_geometry) ·
> all 16 strong promotions APPROVED · rarities CONFIRMED termless · lp85
> manip.swap RATIFIED present · the three residual-unclear cells CLOSED:
> bp35×flow.pumped absent (replication = its recorded rarity),
> ls20×gate.remote absent (no barrier; operators are manip.attribute),
> tn36×goal.pattern_match absent with **tn36 + goal.keyed** recorded in
> Part B (footprint/orientation fit). The officials grid now has ZERO
> unclear cells. Spec-ready tables: `officials-mechanics-matrix.md` +
> `officials-mechanics-digest.md` + `game-term-matrix.csv`.

> 2026-09-18. The draft (`vocabulary-v2.md`, frozen md5 9e67d4be…) was tested
> against **the entire corpus**: all 165 RE-ARC-3 customs (13-batch fleet,
> validator 0 FAIL, 6/6 hand spot-checks confirmed, Opus↔Fable calibration
> 97.2% — `calibration-v2-fleet.md`, `v2-fleet-spot-checks.md`) plus the 25
> officials (mechanical rename Part A `adjudicated-v2.csv` + GAP mapping
> Part B `adjudicated-v2-partB.csv`). Aggregates: `term-occurrence-final.csv`,
> `coverage-final.csv`, `new-families.csv`.
>
> **Correction to the draft's own header**: it said "36 terms"; it actually
> defines 51 (miscount in the draft, terms themselves unchanged).
>
> **Coverage verdict: 190/190 games accounted.** Customs: 71 covered by the
> draft as-is · 73 covered by the promotions below · 21 flagged with
> documented rarities (list at bottom; no term assigned, nothing lost).
> Officials: covered by construction (Part A grid + Part B mapping; 8
> rarity rows recorded). **Zero mechanics anywhere left unnamed or
> unrecorded.**

## Rulings on the draft's open flags

- **`budget.time`: recommended retirement OVERRIDDEN at sign-off — KEPT,
  flagged unverified.** 0 live sightings in 165 customs + 0/25 officials
  (~30 games ship something *named* "time"/"timebar" and every one
  decrements per action; engine semantics arcengine/base_game.py:331-339).
  Operator ruling: keep the term as private-set insurance. It appears in
  every table with zero counts; any auditor claiming it must show a real
  wall-clock read.
- **`phys.weight` → `phys.balance`.** Its cited idea exemplar was refuted at
  source (stack_equalizer = two counters + equality, no physics). What is
  real: loading/threshold equilibria that gate devices — scale_lock's exact
  per-pan counts, vc33's conserved pool vs capacities (Part B), hll1's
  heavy/light classes (attribute `classes:yes`).
- **`budget.cap` definition fixed** (the known rubric wart): core = *a
  per-level action allowance tracked by the game*; `enforced` is an
  ATTRIBUTE alongside `displayed`, `refillable`, `exact`, `lives`
  (ls20-style retry allowance; territory_capture implements lives as a time
  penalty), and new `counts:` (limited_turns caps direction-changes only).
  Officials: present 25/25 (enforced ~10, displayed 23). Tufa
  counterexamples exist both ways (identify_the_agent: enforced,
  undisplayed; orbx/swch/rotate_pattern: no cap at all).
- **Exemplar correction (bestiary phase):** the draft cites "o:tu93 L5
  lookalike" as an `info.deception` example — the bestiary proved that
  lookalike INVISIBLE (its board sprite is the only one missing `layer=-1`
  and the custom camera's list-order z-buries it) and inert (its trip
  square is off-board). Dead, not deceptive. Replacement exemplars:
  t:r11l's pixel-identical decoy targets (which can even blink-and-lock as
  if solved), o:cn04's lying highlight, the ≥12-game decoy-action corpus.
- **The parked list was too pessimistic.** `ambient-drift` ("refuted in
  every sampled source") is live in 3 games; `conveyor-routing` ("no source
  sighting") is live in 5; both are terms now. Parked names were reused
  verbatim by auditors exactly as instructed, which is what made the
  promotion counts trustworthy.

## New terms (21) — each with corpus counts (tufa-live / tufa-dead / officials)

### state (3 new)
- **state.wait** (20/0/0) — an explicit pass-time verb (dedicated no-op
  action, or a declared idle) whose use is load-bearing because the world
  advances per action. *Not:* the per-action world clock itself (that is
  engine default — spec §2 note). *Ex:* airtime_glider ACTION5 idle,
  key_door ACTION5→(0,0), trail_follow's DSL maps unhandled ACTION5 to "W".
- **state.action_lag** (16/0/0) — player input is queued/applied on a later
  tick than issued (pending-rotation, flush-step, probe-stun). Solvers pad
  for it — baseline-relevant. *Ex:* boulder_mirror (mirror flips apply next
  step), sokoban (DSL appends flush action), light_out (probe swallows 2).
- **state.health** (2/1/0) — a per-level damage pool absorbing hazard
  contacts; attributes `pool`, `shield` (timed invulnerability pickup).
  *Ex:* airtime_glider 3-point pool + shield, one_enemy_duel; dead in
  breakout.

### goal (2 new)
- **goal.confirm** (7/0/0) — reaching the goal state does not bank the
  level; a further action does. Attribute `gesture: explicit|any-action`.
  The shipped DSLs append the trailing action — part of the solver-padding
  story in baselines. *Ex:* memory (deliberate two-step), flood_fill,
  junction_click_maze, traffic_jam.
- **goal.survive** (4/0/0) — outlast a counter: the meter emptying WINS
  (inverse of budget.cap). *Ex:* dodger_falling_blocks (48 ticks), tron
  levels 1-2 (only win path), pong, airtime_glider.

### loss (new group)
- **loss.deadlock** (10/0/0) — the game detects unsolvability (no legal
  move / dead configuration) and ends the run. *Not:* merely being stuck
  with the engine idle. *Ex:* sokoban's oracle, magnet, boulder_push_roll,
  push, trail_follow. (Candidate members recorded as rarities:
  fail-on-miss, protect-region.)

### gate (1 new)
- **gate.phase** (4/1/0) — a barrier whose passability flips on an
  autonomous clock, with no player-side control and no lethality (which is
  what excluded it from gate.*'s control requirement and hazard.timed's
  lethality clause — 2 independent batches coined the same gap). *Ex:*
  turn, laseretch shutters, doortimers, golf_grid_putt; dead in
  territory_capture.

### hazard (1 new)
- **hazard.crush** (2/0/0) — a *moving/displaced* object occupying the
  avatar's cell is lethal (hazard.static requires fixed position;
  agent.patrol requires own policy). *Ex:* boulder_push_roll, cutline_drop.

### manip (4 new)
- **manip.interlock** (6/0/0) — a mechanism refuses an operation whose
  sweep/result would violate a constraint w.r.t. the player or load. *Ex:*
  hinge_bridge (refuses rotation that would hit the walker — and its sibling
  latch_bridges LACKS it and strands the hiker: the pair is a
  positive/negative exemplar for the intent-verifier), winch_line, sliders.
- **manip.ranged** (3/0/0*) — a verb whose effect lands at distance under
  geometric constraints (facing ray, line-of-sight, band). Attributes
  `medium: instant|projectile`, `effect`. *Ex:* hookshot raycast-relocate,
  painttheroom LOS-paint, one_enemy_duel strike band. (*sc25's raycast
  bullet is the probable official instance; left with its Part A verdict
  gate.remote — additive re-audit not done.)
- **manip.group_toggle** (2/0/1) — one input flips a structured SET of
  cells (row/column, fixed mask). *Ex:* rows (line XOR), ft09_close (3×3
  own-art mask), official ft09 (coupled stencil, Part B).
- **manip.merge** (0/0/2) — co-located entities fuse/absorb into an
  upgraded one; attributes `mode: tier|attribute-sum`. Officials-only so
  far: su15 tier-fusion, r11l attribute absorption. (Watch: idea corpus has
  merge-tiers family.)

### terrain (4 new)
- **terrain.conveyor** (5/1/0) — cell-anchored directional transport moves
  entities along fixed arrows/belts. *Not:* phys.drift (global field), not
  agent.patrol (no policy). *Ex:* conveyor_sort_gpt (belts + settable
  junctions), rotor_junction, alternating_helpers, golf_grid_putt wind
  tiles, locksmith; dead in deliver_the_package (shadowed parse branch).
- **terrain.keyed** (3/0/0) — passability/effect of terrain or devices is
  conditioned on an avatar-carried attribute (phase, polarity, colour).
  Attribute `device: tile|portal`. *Ex:* flux, weav, teleport_maze
  (colour-keyed portals).
- **terrain.one_way** (4/0/0) — directional passability. Attribute
  `form: diode|platform`. *Ex:* circuit_connect diodes, herding, and the
  jump-through platforms of gravity_platformer / one_screen_precision_jumps.
- **terrain.track** (0/1/2) — movement constrained to (or enabled by)
  marked rails. Officials: sk48 (track-enabled move), lp85 (cyclic tracks,
  shared-cell transfer); dead in skewer (rails parsed, never read).

### phys (1 new + 1 rename)
- **phys.drift** (3/0/0) — a global environmental force displaces entities
  on its own schedule/field (wind, fans). *Not:* terrain.conveyor
  (cell-anchored). *Ex:* airtime_glider wind, fan_drift, dodger L6.
- **phys.balance** (2/0/1) — see ruling above (rename of phys.weight).

### info (3 new)
- **info.viewport** (2/0/2) — the board exceeds the visible window and the
  window's position is gameplay-relevant (clicks reach only visible rows).
  Officials use it as an authoring lever (bp35, lf52 scroll); tufa as a
  mechanic (bottomless_pit, tunnel_search). Absorbs the parked viewport
  family; `view.rotate` (sp80) stays a lever, recorded as a rarity.
- **info.telegraph** (3/0/0) — the game actively signals upcoming state or
  the correct next input (the inverse of info.deception). *Ex:* dodger's
  warning row, pattern_match_sequence_2's outlined answer, nonogram's live
  distance-to-solution bar.
- **info.hidden_geometry** (0/0/2) — load-bearing geometry that renders as
  background but interacts (the -2 invisible-but-solid device; render masks
  `>=0`, collision `!=-1`). Officials: g50t invisible rails, sb26
  hit-testable background; the engine device exists in 16/25 officials
  (feature-report) — a deliberate generator lever.

### move (1 new)
- **move.coupled** (4/0/3) — one input drives several bodies at once.
  Attributes `coupling: same|mirrored-x|mirrored-y|identity|channel|
  parent-child`, `bodies`. *Ex:* orbx, mirrored, command_twins,
  mirror_walk; officials lf52 (N avatars), m0r0 (mirrored), s5i5.

## New/updated attributes on existing terms

`move.grid[footprint]` (2×2 avatars: 3 games — corridor *width* becomes the
constraint) · `terrain.dual_role[axis: substrate|entity]` (grid_archery
fences block avatar not arrows; wa30 cargo-only barriers — same axis) ·
`manip.attribute[region:component]` (flood_fill click repaints a connected
component) · `state.undo[mode: step|restart]` (free full-level restart in 5
games) · `state.facing[set_by: movement|click]` (ss99, crane_dipper compass
ring) · `phys.bounce[split]` (glass_orchard live, pong dead) ·
`terrain.trail[gap-verb]` (tron's 3-step trail suspension) ·
`gate.key[mutable]` (locksmith's three-attribute rework of keys).

## Final counts

**71 terms in 16 groups** (draft's real 51 − budget.time + 21). The count
grew because the corpus is genuinely wider than the officials (the draft
was officials-first). Discipline lever if 71 feels heavy at sign-off: the
five 2-sighting promotions (hazard.crush, manip.group_toggle, manip.merge,
state.health, info.hidden_geometry) could be demoted to attributes/parked —
none of the counts above changes.

## Rarities appendix (documented residuals, NO term — 21 customs + 8 official rows)

Combat cluster (one_enemy_duel strike-window/guard-parry + npc-stun +
timed-blast-charge — a real hole if combat ideas are wanted; propose
`combat.*` group only when ≥2 games per member) · jump-capture (leap_frog)
· graph-topology (junction_click_maze) · constraint-clues (nonogram) ·
phase-keyed-verb (dash_puzzle) · fail-on-miss (catch_eggs) · protect-region
(flood_fill_water) · gravity-flip (bottomless_pit) · speed-pad ·
dash-cooldown · cost-terrain (tag) · anchor-leash (select_and_settle) ·
shear-cutter (shape_mold) · click-drag-relocate (home_finding) ·
role-discovery (identify_the_agent — belief/agency drill material) ·
simultaneity-lock (greedy_friend) · pivot-rotate (anchor_drift) ·
fragile-barrier + rubble-decay (dodger — degrading-terrain candidates) ·
area-enclosure (territory_capture) · collapse-underfoot (dead) ·
Officials: self-replicating-block (bp35), compound-control +
shared-track-transfer→track (lp85), centroid-linkage (r11l — **promoted
into `phys.balance` at D24**: the centroid re-seat makes the win reachable
only by loading the arms, which is this section's own "loading/threshold
equilibria" definition; the rarity name stays recorded here per policy),
view-rotation (sp80), objective-inversion + rotation-invariant-identity
(tr87), contact-crush kill-trade (tu93), alignment-gate (vc33).

## Corpus-quality yield of the full pass (for the intent-verifier spec)

28 dead-mechanic rows across 165 customs (validator count), incl. 4 proven
by exhaustive BFS/simulation (scale_lock collapse, one_screen checkpoints +
unloseable, pong splitter, js26's full model reproducing its baselines
11/22/24/26/15/24) · `ACTIVE_LEVEL_COUNT` stubs: stealth_to_exit (=1, 3 of
5 declared mechanics dead), territory_capture (=1, 5 of 6 levels dead),
painttheroom (=4) · both D2 canaries reproduced independently
(flood_fill_water's crates-not-a-dam + inert conduits; stealth_to_exit
stub) · decoy declared-actions in ≥12 games · manifests lying in both
directions (path_connect_sequence declares 3 mechanics and implements none;
make_all_same tagged no-time-bar while shipping an enforcing bar).

## Sign-off checklist (operator) — ALL TICKED 2026-09-18

- [x] the 21 promotions — all kept (five levers reviewed individually)
- [x] budget.time (KEPT-flagged, override) · phys.balance rename (approved)
      · budget.cap fix + 16 corrections (ratified)
- [x] loss.* as a group — kept
- [x] rarities stay termless — confirmed
- [x] spec-v0.3 §3 = this doc; officials grid = Part A + Part B
      (+ the three unclear-cell closures and tn36 goal.keyed above)
