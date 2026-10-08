# Mechanics vocabulary v2 — DRAFT for team review

> 2026-09-17. Built from three evidence bases, all on disk and reproducible:
> **(1)** the adjudicated 25-official grid (`adjudicated.csv`, operational
> semantics, three raters); **(2)** the RE-ARC-3 idea corpus
> (`re-arc-3-coverage.csv`, 258 ideas, 69% covered by v1+families);
> **(3)** source-level audits of 12 RE-ARC-3 games (`re-arc-3-games/*.csv`).
> Nothing here is unsourced; each term cites its evidence. This replaces
> spec-v0.2 §3 once the team signs off (spec-v0.3 change, not made here).
>
> **Judgment style carries over from the audit definitions doc**: operational
> (the code implements it), `present/absent/unclear`, evidence as path:line,
> dead code is absent. Terms are namespaced; ATTRIBUTES qualify a term
> instead of multiplying terms.

## What changed from v1, and why

| change | evidence |
|---|---|
| **`budget.actions` + `budget.step_bar` → one term `budget.cap`** with attributes | one counter satisfied both texts in ≥7 games; caused 5 boundary disputes and both residual inter-model disagreements |
| **`gate.key` kept, scoped** | 0/25 officials, but real in tufa-space (`keys`, `ice_stop` verified in source) |
| **`budget.time` kept, flagged unverified** | 0/25 officials AND 0/12 sampled tufa sources live (every "timebar" so far is an action counter); alive only in idea prose. Needs one code sighting or retirement |
| **`goal.*` expanded from 2 to 7** | the group was provably under-provisioned: plain reach-goal and clear-all — the two commonest wins — were unnameable (`maze`, `breakout` audits) |
| **12 recurring gap families promoted to terms** | 65 GAP rows over 25 officials + idea/source confirmation from RE-ARC-3 |
| **`agent.hide` split** | it conflated stealth (agent-relative) with fog (information-relative); both real, different mechanics |

## The terms (36, in 12 groups)

Format: **term** — definition. *Counts:* … *Not:* … *Ex:* examples (o=official, t=tufa, i=idea-level only).

### move
- **move.grid** — player-steered entity steps discretely with collision. *Not:* cursor/UI motion; program-driven steps get attribute `drive: direct|programmed` (tn36 ruling). *Ex:* o:ls20, t:maze.
- **move.push** — moving into a movable displaces it. *Not:* carrying, destroying. *Ex:* o:ka59, t:sokoban (textbook).
- **move.platform** — gravity/fall with support. *Not:* buoyant pinning (vc33 ruling); Gravity level-key alone is NOT evidence. *Ex:* o:bp35.
- **move.slide** — inertial motion resolved by a stop rule; attribute `subject: avatar|object`, `distance: unbounded|fixed`. *Ex:* t:ice_stop (avatar/unbounded), o:ka59 water (object/fixed). [was NEW.momentum-slide + momentum-terrain]
- **flow.pumped** — substance propagates only as the player advances it. *Ex:* o:sp80, o:vc33.
- **flow.autonomous** — substance propagates on its own clock; hazard/timer role. *Ex:* t:flood_fill_water (sim-verified split). Sub-mechanics: `flow-actuated-switch`, `hazard-sink` as attributes.

### carry (new group — the audit's biggest recurring gap, 3 polarities)
- **carry.hold** — attach/detach and transport at fixed offset, deposit on target. *Ex:* o:wa30 crane, t:claw-lanes(i).
- **carry.vehicle** — a steered container transports contents across terrain contents can't cross. *Ex:* o:lf52 trolley, t:river-ferry(i).
- **carry.ride** — a mover transports the PLAYER standing on it; often the only safe footing. *Ex:* t:frogger logs (`was_on_float` ruling), t:winch_line (player-as-cargo).

### gate
- **gate.key** — collectible unlocks barrier. *Ex:* t:keys (lock-on-win-cell), t:ice_stop L5. officials: 0.
- **gate.plate** — occupancy-held state, reverts on leave. *Ex:* o:m0r0, o:g50t.
- **gate.remote** — control at A changes barrier/state at B. *Not:* clicking the barrier itself. *Ex:* o:dc22 (whole game), o:sc25 (bullet raycast).
- **gate.direct** — the control IS the barrier (click-to-open door). *Ex:* t:maze (fell through v1's trichotomy).

### hazard
- **hazard.static** — fixed lethal/fail-on-contact. Attribute `trigger: contact|approach-geometry`. *Not:* nuisance NPCs (wa30 ruling). *Ex:* o:bp35 pillars, t:snake walls (lethal-not-blocking).
- **hazard.timed** — temporal phase decides lethality. *Ex:* o:tn36 laser (mod-3), t:frogger turtles.

### agent
- **agent.patrol** — autonomous mover with own policy. *Ex:* o:su15 homing, t:frogger lanes.
- **agent.vision** — behavior conditioned on directional detection. *Ex:* o:tu93 facing-fire, t:stealth_to_exit cones.
- **agent.stealth** — the player can suppress/evade detection (hiding spots, lures). *Ex:* t:stealth_to_exit (engine-complete), i:distraction-lure. [split from v1 agent.hide]
- **agent.delegate** — an NPC performs objective steps the player cannot; feeding/steering it is the mechanic. *Ex:* o:wa30 (L3/L4 provably delegation-only), t:lantern-moths(i).
- **agent.echo** — an entity's behavior replays the player's own action history. *Ex:* o:g50t ghost clones, o:tu93 delayed chaser, t:echo-step(i). [self-history-as-content]

### manip
- **manip.select_cycle** — persistent selection; later actions apply to it. *Ex:* o:re86, t:sliding_rows.
- **manip.swap** — atomic exchange. *Ex:* o:sb26, o:vc33 L5.
- **manip.attribute** — operations transform a carried/owned attribute (shape, color, size, rotation, weight); attribute `which:`. Subsumes v1 manip.rotate (keep `manip.rotate` as alias for the rotation instance). *Ex:* o:ls20 operator tiles, o:cn04 form-chain, o:sc25 resize, o:re86 dye/press.
- **manip.group_shift** — rows/strips/regions move as rigid units. *Ex:* t:sliding_rows (mod-12 offsets), t:frogger lanes, i:room-swap.
- **manip.terraform** — player creates/removes/mutates terrain; attributes `one_use`, `by: click|movement`. *Ex:* o:bp35 click-terraform, t:glass-orchard(i), o:m0r0 placeable blocker.

### goal (expanded — v1's two terms could not name the two commonest wins)
- **goal.reach** — arrive at a cell/zone. *Ex:* t:maze, o:ls20.
- **goal.cover** — satisfy every target; attribute `mode: cover|clear|collect`. *Ex:* t:sokoban (cover), t:breakout (clear), o:sp80 cups.
- **goal.pattern_match** — region/attribute equality against a target. *Ex:* o:ft09, t:memory-family.
- **goal.path_connect** — connectivity itself is checked/required. *Ex:* o:sb26 (the one official), t:wire-the-circuit(i).
- **goal.rendezvous** — bring entities together / to a common phase; no designated exemplar. *Ex:* o:m0r0 (all avatars co-located), t:sliding_rows (common offset).
- **goal.keyed** — targets admit only matching shape/type/polarity. *Ex:* o:ka59 footprint-homes, o:cn04 overlay-pairing.
- **goal.sequence** — order of operations is itself the constraint. *Ex:* t:keys (ordered-collection), o:sk48, i:taps.

### budget
- **budget.cap** — game-enforced action cap; attributes `displayed` (bar/meter), `refillable`, `exact` (must-equal), `lives` (retry allowance). Merges v1 actions+step_bar; kills the fleet's most-disputed boundary. *Ex:* 23/25 officials displayed; t:sokoban (refill-by-undo); o:ls20 lives.
- **budget.time** — real-clock/fps countdown independent of actions. **Unverified in any code to date** — 0/25 officials, 0/12 sampled tufa; idea-prose only. Retire if the full-corpus pass finds none.

### topo
- **topo.wrap** — non-planar adjacency; attributes `scope: board-edge|portal|content-strip`. *Ex:* o:sc25 teleport pads, t:sliding_rows strips.

### info (new group)
- **info.fog** — board state concealed until revealed by position/act. *Ex:* o:ls20 L7 Fog, o:cn04 GreyMasking.
- **info.probe** — an explicit query verb reveals hidden state transiently (echo pulses, hot-cold). *Ex:* t:echo-maze(i), i:hot-cold. [active-sensing]
- **info.recall** — required state was shown but is no longer displayed (memory burden by design); attribute `span: within-level|cross-level`. *Ex:* t:memory (cross-level appearance order), i:Simon. [sequence-memory]
- **info.legend** — an in-game queryable reference demonstrates rules. *Ex:* o:tn36 reference machine, o:sb26-family exemplars.
- **info.deception** — the game actively misleads: decoy actions, lookalike entities, lying feedback. *Ex:* o:cn04 (green highlight on wrong pairs), o:tu93 L5 lookalike, decoy ACTION5s (5 sightings).

### program
- **program.compose** — build an instruction structure, then run it; attributes `recursion`, `pointer`. *Ex:* o:tn36, o:sb26 call/return.
- **program.commit** — two-phase edit-then-simulate; the run accepts no input. *Ex:* o:sp80 (ACTION5 cascade), t:conveyor-sort(i), t:mirror-shot(i).

### state
- **state.facing** — persistent orientation set implicitly by movement, consumed by interactions. *Ex:* o:sc25 aim, o:wa30 interact-cell, o:tu93 kill-trade.
- **state.undo** — a player action rewinds world state; attributes `depth`, `free` (budget-exempt). **6 official + 2 tufa sightings; our harness amputates ACTION7 — flagged.** *Ex:* o:su15 (load-bearing), t:sokoban (deadlock escape).
- **state.checkpoint** — re-anchorable respawn. *Ex:* o:tn36.

### phys (new group — tufa-space extends beyond official physics)
- **phys.bounce** — ballistic reflection of a moving projectile; sub: deflect-aim. *Ex:* t:breakout (irreducible, source-verified), i:mini-golf/pong.
- **phys.reflect** — mirrors cast copies/beams/symmetry that count as real. *Ex:* o:ar25 (recursive ghosts), i:laser mirrors, i:mirror-paint.
- **phys.weight** — heaviness as mechanic (seesaws, counterweights, balance). *Ex:* i:×5 (counterweights, stack-equalizer…); no source sighting yet in sample.
- **phys.attract** — a field/point pulls entities (magnet, vacuum well, light). *Ex:* o:su15 click-well (source-verified), i:magnet-crane.

### terrain
- **terrain.trail** — an entity's own path becomes terrain; attributes `persistence: fifo|permanent`, `consequence: lethal|blocking|paint`. *Ex:* t:snake/tron/shadow-step/paint-snakes (one family, four variants).
- **terrain.dual_role** — passability inverts on substrate (bridge over void = wall over floor). *Ex:* t:winch_line (BFS-verified load-bearing).

## Parked (single sightings or engine-level; not terms yet)

`mechanism-interlock` (winch_line) · `deadlock-fail-state` (sokoban's
unsolvability oracle) · `action-lag` (sokoban) · `confirm-finalize` (memory)
· `turn-locked-clock` + explicit WAIT (arguably the ecosystem's default
physics — a spec note, not a term) · `conveyor-routing` (idea-level ×3, no
source sighting) · `ambient-drift` (idea-level; refuted in every sampled
source — frogger's logs are carry.ride) · scrolling/rotated **viewport**
(o:bp35, o:lf52, o:sp80 — kept as spec §2 authoring levers `view.scroll` /
`view.rotate` rather than mechanics) · `match-collapse`, `wave-defense`,
`jump-capture`, `projection-reasoning` (one idea each).

## Corpus-quality findings the vocabulary work surfaced (for the screen re-run)

1. **Dead code is normal, both corpora**: 5/25 officials and 5/12 sampled
   tufa games ship complete unreachable mechanics; decoy declared-actions in
   ≥5 games. Keyword/idiom evidence is structurally unreliable — only
   reachability-checked audits count.
2. **A solver-validated game can be broken against its own intent**:
   `flood_fill_water` has four documented defects (a level with no flood, an
   impossible stated mechanic, a push bug the optimal solve exploits, a dead
   loss region) yet passes `require_dsl_win` and carries exact synced
   baselines. `stealth_to_exit` is a shipped stub whose own solver would
   crash. **Validators prove winnability, never intent** — the case for a
   mechanics-aware review pass in our pipeline.
3. `budget.cap` displayed-meter is near-universal ecosystem-wide (23/25
   officials, 8/12 sampled tufa).

## Sign-off checklist (team)

- [ ] approve merges/splits (budget pair; agent.hide split; flow split; goal expansion)
- [ ] rule on `budget.time` (retire vs keep-unverified)
- [ ] approve the carry group's 3 polarities vs 1 term + attribute
- [ ] then: spec-v0.3 §3 rewrite + re-tag `adjudicated.csv` terms → v2 names (mechanical rename map, no re-judging)
