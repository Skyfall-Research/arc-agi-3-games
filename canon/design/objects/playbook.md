# Implementation playbook — how to build each mechanic the way the corpus does

> 2026-09-18. The curated layer: per high-frequency v2-final term — the
> engine pattern officials/tufa actually use, the knobs a generator turns,
> and the traps that produced real defects. Evidence layers underneath:
> `provenance/objects-working/playbook-skeleton.md` (all 73 terms, every grid evidence line) and
> `bestiary/<slug>.md` §3 (per-game implementation notes, path:line).
> Engine-wide contracts live in `affordance-language.md` §8 (REQUIRED /
> FORBIDDEN) — read that first; nothing here repeats it.

## Movement & physics

**move.grid** (o:12+, t:100+) — arrow handler moves the mover by one cell
(or one lattice step: ka59 moves 3px on a mod-3 lattice; dc22's avatar is
2×2 on a 2px lattice) with a passability test. Knobs: lattice size,
footprint (`move.grid[footprint]`: 2×2 avatars make corridor WIDTH the
constraint — 3 tufa games), which arrows are exposed, walls-as-sprites vs
grid-array. Traps: refused moves must still `complete_action()` (engine
re-runs otherwise); decide refusal charging per §6 of the affordance doc;
tufa's grid_archery fences show entity-selective passability wants an
explicit axis declaration.

**move.slide** (o:ls20/ka59, t:ice_stop/gravity_flip…) — loop the step
until the stop rule fires, INSIDE one action (defer complete_action, emit
animation frames). Knobs: subject (avatar|object), distance
(unbounded|fixed), stop rule (wall, water-edge, object). Trap: a game
"named for gravity" that moves per-action is slide, not platform — the
falling-clock distinction is the term boundary.

**move.coupled** (o:lf52/m0r0/s5i5, t:orbx/mirrored/command_twins/
mirror_walk) — ONE input, N bodies, per-body collision resolution. Knobs:
coupling (same|mirrored-x|mirrored-y|identity|channel|parent-child),
body count, per-body blockability (the puzzle IS the desync). Trap:
resolve each body independently then commit (m0r0 reverts the pair when
either is blocked — pick and DECLARE a semantics).

**move.push** (o:ka59, t:sokoban family) — displaced-object chain with a
depth rule. Knobs: chain depth 1 vs recursive (ka59 recurses), push-only
vs pull, momentum handoff (ka59's bump launches 5 cells). Traps:
sokoban-class games NEED loss.deadlock or state.undo as the escape valve
(the corpus pairs them); crush semantics (hazard.crush) must be explicit.

**phys.drift / terrain.conveyor** — the pair to keep distinct: drift is a
global field on its own clock (airtime wind, fan_drift rays, dodger's
4-tick column drift), conveyor is cell-anchored transport (belts,
arrows). Knobs: period, strength, toggleability, whether the force queues
(airtime applies the push BEFORE the next action reads input — an
action_lag composition). Trap: deliver_the_package shipped its conveyor
DEAD via parser-clause shadowing — parse-order tests are mandatory.

**phys.bounce / phys.reflect** — split on cast-beam vs travelling
projectile (grid_archery vs boulder_mirror). Knobs: reflector set,
recursion depth (ar25 re-reflects to depth 12 — images COUNT for the win
predicate), split (pong's dead splitter). Trap: ar25's win-satisfying
shadows show reflect needs an explicit "do copies count?" bit.

## Budget, loss, structure

**budget.cap** (25/25 officials enforced) — counter decrement + edge-strip
paint + exhaustion→lose() with the win check FIRST (winning move free —
the universal pattern). Knobs: cap per level, displayed?, enforced
(default YES), counts (what decrements: all actions | moves only |
effective clicks | direction changes | variable cost — su15 escalates
2/4/6), refillable (snake's food, territory's captures), lives chain
(ls20), scope (per-level via engine reset is the default). Traps: the
SIXTEEN v1 misreads all came from lose() living far from the counter —
put them adjacent; never let a session-summed baseline exceed the cap
(tn36 ships that defect).

**loss.deadlock** (t:10) — an explicit solvability oracle (BFS or rule
test) ending the run. Knobs: oracle strictness, escape valve (undo pairs
with it in sokoban). Trap: the oracle must agree with the solver's
reachability or it strands winnable states (latch_bridges' missing
interlock is the sibling failure).

**goal.confirm** (t:7) — reaching the goal state sets a flag; a further
action banks it. Knobs: gesture (explicit verb | any action), free?.
Baseline note: the solver's trailing action is PART of the winning line —
count it.

**goal.survive** (t:4) — the counter emptying WINS. Implement as
budget.cap with inverted terminal semantics — never overload one counter
with both meanings in one level.

## Interaction verbs

**manip.select_cycle / click-select** — persistent selection + white-0
marker (the ecosystem idiom). Knobs: cycle vs direct-click, selection
survives what (lf52 clears on every move — a lever), marker style. Trap:
`sys_click` tags must be truthful; cd82's untagged everything hides the
game from random policies and RL action lists.

**manip.attribute** (the workhorse: o:10 partB rows, t:everywhere) — an
operator (tile, zone, press, verb) applies a transform to a carried
attribute (shape/colour/size/rotation/length/symbol). Knobs: which
attribute, transform group (cycle mod-N, form-chain with parity
constraints — cn04's marker parity gates variant solvability!),
where it applies (zone-on-contact vs verb). Traps: re86's press-morph is
direction-asymmetric and its plain-X pieces LOSE their marker on first
deselect — attribute state must round-trip; rotation is RENDER-side in
the engine (ka59/g50t run logic on unrotated arrays — decide one space
and stick to it).

**manip.terraform** — click/movement mutates terrain. Knobs: by(click|
movement), one_use, what mutates (solid↔empty, colour). Trap: bp35's
upside-down grid authoring ([::-1] + no y-flip) is a working style, not a
bug — but pick ONE orientation convention for generated code.

**manip.interlock** (t:6) — refuse operations whose sweep/result violates
a constraint w.r.t. the player/load. Knobs: what is protected (the
walker, the cargo, the mechanism). Trap: hinge_bridge HAS it,
latch_bridges LACKS it and strands the hiker — ship the interlock or ship
the failure as an explicit loss, never the strand.

**manip.ranged** (t:3 + o:sc25-kin) — verb resolves at distance along
facing/LOS/band. Knobs: medium (instant ray | projectile), occlusion
rule, range. Trap: raycasts must state their pixel mask (g50t's two
thresholds).

**state.undo** (o:5, t:several) — snapshot stack per spending action.
Knobs: depth (1 | unbounded), free?, restart-vs-step (5 tufa games ship
free full-level restart as a verb). Traps: sb26's stack makes ACTION7-spam
a free restart (declare it); su15's undo mutates counters at different
rates (the decoupling); paint_snakes hides 7 from its own valid-action
list — advertise what exists.

**state.wait** (t:20) — an explicit pass-time verb in a per-action world.
Knobs: dedicated action vs move-into-wall, charged?. Required wherever
timing games (gate.phase, hazard.timed, agent.patrol crossings) demand
letting the clock advance.

**state.action_lag** (t:16) — input queued, applied next tick. Knobs: lag
length, what lags (all input vs one verb). Trap: the solver must model the
lag (sokoban's DSL appends a flush action; every lag game's baseline
carries it).

## World structure

**gate.plate / gate.remote / gate.key / gate.phase** — the door quartet.
Plate = occupancy-held, reverts on leave (m0r0/g50t); remote = control at
A changes B (dc22's whole game); key = collectible unlock (tufa-only:
keys/roomswap/locksmith's mutable keys); phase = autonomous clock flips
passability, NO control, NO lethality (t:4+1dead — the promoted gap).
Knobs: latching vs reverting (magnet/trail_follow's edge-triggered toggles
are gate.remote, NOT plate — the boundary the fleet ratified), wiring
visibility (g50t's 17/17 pip-side convention is the legibility idiom).
Trap: door state must be sprite-or-frame visible; g50t's only lethal door
state (closing) is unmarked — that's a LEVER, not a default.

**terrain.one_way / terrain.keyed / terrain.track / terrain.dual_role /
terrain.trail** — passability modifiers. Knobs: axis (substrate|entity —
wa30 cargo-barriers == grid_archery fences), form (diode|platform), keyed
device (tile|portal), trail persistence/consequence. Traps: skewer parsed
rails and never read them (every parsed field needs a reader);
tron's trail-gap verb shows trail games want a crossing valve.

**topo.wrap / info.viewport** — non-planar adjacency; board exceeding the
window. Knobs: scope (edge|portal|strip), scroll trigger, click-reach
rule (bottomless_pit limits clicks to visible rows). Trap: viewport games
must letterbox-map clicks through display_to_grid (dc22's 10/8-row
offsets); ft09's Camera constructor lies (engine re-fits per level) —
NEVER trust constructor geometry, always grid_size.

**info.fog / info.probe / info.recall / info.telegraph / info.deception /
info.hidden_geometry** — the information group. Knobs per the affordance
doc §7 (all levers). Implementation notes: fog as post-hoc mask (cn04
flattens unselected pixels to grey-4 — which also silently disables merge
markers there: masking interacts with progress display); probe as a verb
with a flash window that may swallow actions (light_out — an action_lag
composition); hidden_geometry REQUIRES a declared reader (see -2 rules).

## Agents & programs

**agent.patrol / agent.vision / agent.echo / agent.delegate** — NPC
policies. Knobs: policy period, vision cone, echo delay (tu93 counts
LEGAL moves only — declare the clock), delegation reachability (wa30's
L3/L4 are BFS-provably delegation-only: if the player can't reach it, the
NPC path MUST be complete). Traps: stealth_to_exit's sentry mode had no
branch in its own update function (shipped stub); tu93's phase order
(player first, enemies second) decides kill-trades — declare initiative.

**program.compose / program.commit** — build-then-run. Knobs: slot count,
recursion (sb26's call/return; L8 re-enters its entry row), run
visibility (tn36's whole run drains inside ONE action — nothing survives
to settled frames; sp80's commit REWINDS failures invisibly). Trap: for
trajectory consumers, either emit the run as animation frames (they exist)
or telegraph the outcome in the settled frame; a commit game that rewinds
silently is the maximum-difficulty end of the legibility axis.

## Using this document

Per generated game: pick terms → copy the official pattern (bestiary §3 of
its exemplar is the reference implementation) → set every knob explicitly
in the spec → run the trap list as a checklist. The intent-verifier (D11)
re-derives the term list from the shipped code and diffs it against the
spec — including the dead-code and truthful-tags checks that caught 28
dead mechanics and 16 wrong enforcement verdicts across the corpora.

---
**SIGNED OFF (operator, 2026-09-18)** as implementer-stage reference material,
zero flags, together with `objects-overview.md` as the spec-§4 table.
