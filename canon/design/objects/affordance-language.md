# The affordance language — how ARC-AGI-3 games signal meaning, measured
# **SIGNED OFF (operator, 2026-09-18)**

> **Sign-off record** (3 rounds, zero flags): all 8 REQUIRED rules approved
> as stated (locus · truthful tags · budget triple · checkable goal ·
> -2-with-reader · explicit layers · declared HUD strips · default-tier
> palette discipline) · all 4 FORBIDDEN contracts approved (into the
> implementer prompt AND the intent-verifier) · refusal-knob defaults
> approved (visible-or-free at default tier; official-style silent-charged
> as declared hard setting) · corpus-mix targets approved (≈half
> hazardless; locus mix ≈10/9/6; deception ALWAYS declared) · playbook +
> objects-overview approved as implementer reference / spec-§4 table.
> Locus numbers below refined at review: 10 avatar / 9 selection-driven /
> 6 click-only (the 12/13 in §1 counted two selected-then-arrow hybrids
> as avatars; the per-game classification is objects-overview.md).

> 2026-09-18. Synthesized from the 25-game bestiary (every visual claim
> frame-verified; entries in `bestiary/`, collation in
> `affordance-collation.md`) plus the 1,053-row tufa object table
> (`tufa-objects.csv`, 165 games). Rule grades:
> **REQUIRED** — near-unanimous in officials; a generated game violating it
> is structurally off-corpus. **RECOMMENDED** — majority convention;
> deviations exist and are deliberate. **LEVER** — a device officials use
> *on purpose* to create difficulty; the generator controls it per
> difficulty tier, never by accident. **FORBIDDEN** — engine traps and
> authoring defects observed in the corpora; the implementer must never
> ship one.

## 1. The locus of control ("you")

The officials split almost exactly in half: **12 have a moving avatar
object; 13 have none** — in those, "you" is a *selection state* (cn04, ar25,
re86, s5i5, sb26, tr87…) or a pure click surface (ft09, lp85, su15, vc33,
tn36). So "player avatar must be visually unique" is NOT a corpus rule.
What is:

- **REQUIRED: the locus of control must be identifiable within a few
  actions.** Two idioms cover 25/25: (a) *unique-mover* — exactly one
  object family responds to the arrows, usually hue-unique on board (bp35's
  only blue-9; tu93's only blue-9-with-grey-nose; wa30's green-with-white
  stripe); (b) *selection-marker* — a persistent mark names the controlled
  object.
- **White `0` is the selection colour of the ecosystem** — the dominant
  idiom by far (~8/13 selection games): ar25's white pinholes, ka59's white
  core, r11l's white diamond, re86's white centre pixel, sk48's white ring,
  tr87's white brackets, cn04's white silhouette (L1-2), cd82's white
  underline. Secondary idioms: recolour-to-selection (cd82's avatar
  repaints to the chosen swatch; sp80's recolour-to-9), rings (lf52
  dark-grey, g50t HUD-blue), dim-the-rest (m0r0).
- *Responsiveness is itself the cue* in the sparse games: cd82's bucket is
  "you" because it is the only thing that moves. RECOMMENDED, not
  sufficient alone at higher tiers.
- **LEVER — selection instability:** ar25's marker vanishes when the
  selected body sits wholly on targets; su15 clears its ring before every
  settled frame (a last-frame agent NEVER sees selection); lf52 silently
  deselects after every hop. Officials use marker fragility as difficulty.

## 2. Goals

- **The hollow-outline-that-fills idiom is the corpus's goal grammar**
  (~9 officials): a hollow shape whose void matches an object's footprint,
  visually fusing/filling when satisfied — ka59's frames, tn36's
  interlocking teeth, lp85's bracket fusing with its tile, g50t's bracket,
  re86's ring-with-colour-core, ar25's blocks turning pinhole, s5i5's
  head+food composing a complete plus, r11l's dotted recipe ring locking
  white. **RECOMMENDED** as the default goal rendering.
- Second idiom: **the reference display** — a quarantined panel or HUD chip
  showing the target state (cd82's fenced picture, ls20's chip, sk48's HUD
  answer strip, re86's target frames, ft09's spec squares). RECOMMENDED for
  pattern_match-family games.
- **LEVER — no goal drawn at all**: m0r0 (rendezvous emergent), lf52 (win
  is an invisible count), cn04 (goal is a pixel state: no red left), tr87
  (opaque). 4-5 officials make the goal itself the inference problem.
  `goal_legible: obvious|inferable|opaque` is a real difficulty axis.
- **REQUIRED: goal state must be *checkable* by the game** (win predicate),
  and per D11 the solver must reach it. Whether it is *shown* is the lever
  above.

## 3. Danger

- **~11 of 25 officials contain no lethal hazard at all** — budget
  exhaustion is the only loss (ar25, cd82, cn04, ft09, lp85, ls20, tr87,
  tn36, vc33, sb26, re86). Generated corpora must NOT make every game
  lethal; roughly half the ecosystem is pure puzzle.
- Where danger exists, the tells are DELIBERATELY weak — this is the
  clearest difficulty lever in the corpus:
  - texture-not-hue: m0r0's checker over any colour (L3 walls are the same
    red as fire).
  - absence-not-presence: dc22's void is "no floor sprite here"; sp80's
    lethal grey vs inert grey differ only in strip thickness.
  - camouflage: ka59's walls share the letterbox grey; g50t's killer is a
    pixel-identical green copy of the avatar; bp35's purple is both spike
    and tool.
  - state-dependent: g50t's doors kill only in the closing transition;
    tu93's purple-15 is dormant until its trip square arms it (nose turns
    yellow-11).
- **RECOMMENDED default (low tiers): danger unique-hued + telegraphed**
  (dodger's warning row / tu93's yellow armed-nose are the telegraph
  exemplars — `info.telegraph`). The weak-tell catalog above is the
  **LEVER** for hard tiers.

## 4. Interactables

- The engine's honest advertisement is the `sys_click` tag (drives
  `_get_valid_clickable_actions`) — but officials both under-declare (cd82
  tags nothing: the engine's own action list contains NO clicks, which is
  why random policies never touch its swatches) and leave clickability
  visually unmarked (ar25: a locked mirror looks identical to a movable
  one). **REQUIRED for generated games: `sys_click` tags must be truthful**
  (the harness and any RL consumer read them); visual marking is the lever.
- Observed marking conventions worth reusing: applicator-family rim (cd82's
  light-grey-2 rim on exactly the clickable family), glyph-in-cell =
  non-blocking pickup (ls20's operator tiles/energy cells drawn small
  inside the floor cell, collidable=False), chevron/button = the only
  saturated shapes on a grey field (lp85), "on the panel side of the
  divider" (dc22).

## 5. Meters and budget

- **REQUIRED: an edge-anchored budget strip exists** — after the bestiary's
  16 enforcement corrections the officials stand at **25/25 enforced, 24/25
  displayed** (identify_the_agent-style undisplayed caps exist only in
  tufa). Placement histogram (officials): bottom row 14 · top row 3 ·
  left/right column 4 · both rows 1 · rows 61-62 with lives pips 1 ·
  row 53 1 · on-board solid sprite 1.
- Direction/anchor semantics are FREE — the corpus drains left, right,
  down, from both ends, in colour bands (ar25's five-band recolouring), or
  slides a sprite (g50t reads the bar's x for enforcement). A consumer must
  never assume "left edge = remaining".
- Lives: ls20's 3 pips (right-to-left extinguish) + budget.cap `lives`
  attribute; enforcement-via-lives is a legitimate chain.
- **REQUIRED: enforcement must be wired** (exhaustion → lose(), win check
  before the final decrement so the winning move is free — the 25/25
  pattern) **and the cap must accommodate the solver's winning line with
  the g-policy margin** (tn36 ships baseline 72 > its own cap 61; s5i5's
  card baseline 162 > cap 150 — session-sum artifacts we must not
  reproduce: OUR baselines are per-attempt by construction).

## 6. Refusal feedback — the corpus's sharpest legibility fact

Measured across all 25 officials:

- **17/25: NO refusal signal.** A blocked/illegal/wasted action returns a
  settled frame byte-identical outside the meter — and still charges
  budget (ar25, cd82, cn04, dc22, g50t, ka59, m0r0, r11l, re86, sk48,
  sp80, tn36, tr87, tu93, vc33, wa30, lp85*). (*lp85 charges nothing and
  shows nothing — a miss is a true no-op.)
- **6/25: transient-only feedback**, swallowed before the settled frame
  (bp35's 3-frame bump, lf52's 1px jiggle, s5i5's one-frame flash,
  su15's flash + oversized meter drop, ft09's L1-only bracket flash,
  sb26's two never-reached animations). A frame-differencing agent sees
  nothing.
- **2/25: real visible refusal — and both make refused actions FREE**
  (ls20's 5-frame white panel flash, no energy; sc25's 12-frame red
  panel flash, no charge).

The correlation is the design grammar: **officials either charge silently
or signal freely — never both.** For the generator this is a first-class
difficulty knob, directly aimed at the self-monitoring failure family:
- low tiers: visible refusal (flash/shake persisting ≥1 settled frame) OR
  free refusals;
- official-style hard tiers: silent-and-charged, exactly as 17/25 do.
- **FORBIDDEN: mixed accidental semantics** (some refusals charged, some
  free, with no rule — sc25's latent double-charge bug is the cautionary
  case).

## 7. The deception catalog (levers, all frame-verified)

Officials deceive *deliberately*; each device below is a tier-gated lever:
1. **Look-alike splits** — pixel-identical objects with different behavior:
   r11l's decoy targets (excluded only by name-substring; can even
   blink-and-lock as if solved), lf52's three disc kinds, tn36's white vs
   grey panel, dc22's button-that-looks-like-terrain, g50t's avatar-copy
   killer, ka59's two look-alike frame families, sc25's solid
   teleport-pad twin, ar25's fixed vs movable mirror, wa30's dump-zone vs
   target-zone (1px outline differs).
2. **Palette overloading** — one index, several roles (cd82's white ×4;
   bp35's purple hazard+tool; ka59's wall/letterbox camouflage; lp85's
   green button+budget; sp80's grey lethal+inert+border by thickness only).
   RECOMMENDED default is NO overloading of the semantic indices (§9);
   overloading is the lever.
3. **Decoy/dead actions** — declared, unhandled, still charged (≥5 officials,
   ≥12 tufa; m0r0/dc22 originals).
4. **Lying/desynced displays** — lf52's meter painted by a different
   counter than the lethal one; cn04's green highlight on wrong pairs;
   light_shadow's (tufa) ring rendering smaller than true detection radius.
5. **Invisible load-bearing state** — g50t/sb26 hidden geometry
   (`info.hidden_geometry`), su15's selection cleared pre-settle, sp80's
   commit-rewind erasing all evidence of failure, tu93's echo keyed to
   your action history.
6. **Retrospective punishment** — lf52 reveals dead-ends only after you
   land; r11l's silent irreversible wrong-absorb.

## 8. Render/engine layer — rules the implementer inherits

- **Interfaces paint AFTER the board** into reserved strips. REQUIRED:
  declare the reserved geometry (row 63 / row 0 / col 0 / rows 61-62 as
  chosen) and keep board content out of it (dc22/lp85/ft09 all overwrite
  board pixels on full-size grids).
- **FORBIDDEN: interface paint conditions keyed to palette equality that a
  real object can collide with** — r11l's line painter writes wherever
  `frame==5 or frame==10` and 10 is an object colour: the frame under-reports
  true state. Interface masks must key on geometry, never colour equality.
- **FORBIDDEN: leaving a handler without `complete_action()`** — the engine
  re-runs the action (sc25's latent double-charge).
- **`get_sprites()` is a complete inventory in ~19/25 games; the exceptions
  are structural**: bp35/lf52/m0r0 paint the board in a
  RenderableUserDisplay (lf52's ONE listed sprite isn't even rendered);
  partial caveats: filter REMOVED clones (dc22), hidden form-variants
  (cn04), L5 over-report (tu93), selection/budget not sprite-backed (ar25).
  Generated games: RECOMMENDED plain-sprite boards (display paints meters
  only) so trajectory consumers get truthful inventories.
- **`-2` semantics are per-game, not global.** Engine defaults: render
  masks `>=0`, pixel-collision masks `!=-1` (invisible-but-solid). But
  officials override: ka59 sets collidable=False on -2 interiors (NOT
  solid); tn36/ls20 use BOUNDING_BOX or tag-scans so -2 is inert; g50t
  runs TWO thresholds in one game (kill tests `>=0`, contact `!=-1` — the
  killer's effective box is smaller than its footprint); dc22 uses -2 as
  the ONLY touchable surface of intangible markers. REQUIRED: a generated
  game states which mask reads every -2 it ships; -2 without a reader is
  FORBIDDEN (dead weight that confuses extraction).
- **Z-order traps**: three officials drop or bypass the stock layer sort
  (s5i5's custom camera → declaration order; tu93's L5 deception is
  *accidentally invisible* this way). REQUIRED: rely on explicit layers,
  never list order.
- **Settled frames are not the whole truth**: wins/refusals/runs can live
  entirely in animation frames (tn36's whole program run drains inside one
  action; cn04 emits 3 frames on level change; sk48 up to 39). Trajectory
  consumers pair action *i* with `frame[-1]`; anything that must be
  learnable from trajectories has to survive into settled frames.
- **Pre-fused scenery** (Level init merges static sprites per layer) and
  **keyframes are post-transform** (cn04's marker classes unrecoverable
  from captures) — extraction pipelines read source+frames, not captures
  alone.

## 9. Palette semantics (16 indices, both corpora)

Measured roles (officials primary; tufa 1,053-row stats agree):
- `0` white — **selection/highlight** (the ecosystem's marker), spent-or-
  remaining budget, refusal flashes. Semantic; avoid as plain paint.
- `1-4` greys — structural: floors, walls, letterbox, spent-budget, fog
  masks, dimmed states. ka59/sp80 deliberately camouflage within the ramp.
- `5` black — background/outline default (BACKGROUND_COLOR in 8+ officials).
- `9` blue — the commonest "you" hue (bp35, g50t, sp80, tu93, m0r0's
  blocker; tufa's top avatar index by a wide margin).
- `11` yellow — armed/attention (tu93's armed nose, m0r0's held blocker,
  ka59's plus-cargo, ar25's targets).
- `8` red / `14` green — danger/GO conventions exist but are NOT reliable
  (L3 m0r0 walls red; g50t's killer green). Treat as free.
- `13` maroon — rare, high-salience (sp80's filled-cup win state, ka59
  pushers, tu93 echo). Good "unique event" colour.
- **REQUIRED for generated games (default tier): reserve `0` for selection,
  keep the meter's indices off the board, give "you"/goal/danger unique
  indices on-board.** Every deviation is a §7 lever.

## 10. What feeds spec-v0.3 §objects

Archetype table (roles × the measured idioms above) + per-game §1
inventories are the object library; §7 is the deception-knob catalog wired
to difficulty tiers; §8 is the implementer's hard-rule list (FORBIDDEN set
+ engine contracts); §6's refusal knob and §2/§3's legibility axes become
named spec fields (`refusal: visible|free|silent-charged`,
`goal_legible: obvious|inferable|opaque`, `danger_tell:
unique-hue|texture|absence|camouflage|none`). The intent-verifier checks
the REQUIRED rows and flags every lever it detects, so deception is always
a *declared* property of a generated game, never an accident.
