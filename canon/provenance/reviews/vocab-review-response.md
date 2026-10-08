# Re: your vocabulary review

Thanks — this was genuinely useful. Net result: five of your points land
as amendments this week, the hierarchy idea becomes the v3 redesign
after the pilot, and several things you flagged as missing turn out to
exist under names you couldn't find — which is our documentation's
fault, so the crosswalk below fixes that. Every claim here is checked
against engine source (file:line), not memory. Nothing requires
re-researching any game.

## Adopted now (v2.1)

- `flow.pumped[mode: continuous | transfer]` — you're right that sp80
  (velocity-seeded flow, `sp80.py:634`) and vc33 (conserved-pool pours,
  `vc33.py:2030`) don't belong under one tag. Attribute rather than
  split because transfer has only one witness and our promotion rule
  needs two. `fluid.*` naming → v3.
- `move.grid[step]` — dc22 steps ×2, sc25 steps 2/4 by avatar scale.
- `move.grid[topology: lattice | ring]` — see cd82 below.
- `move.platform[gravity_dir]` — bp35's weird fall is the witness.
  (Rename to a gravity family → v3, batched with the other renames.)
- `topo.wrap[kind: edge | pad]` — pads and screen-wrap separated.
- Sharpened wording: **push** = your move displaces another body
  (`ka59.py:41170`); **slide** = your own motion continues/stops by
  rule (`ka59.py:41163`) — ka59 legitimately has both, which is why it
  shows up twice. And an explicit boundary note: `hazard.*` = field
  dangers; moving adversaries = `agent.*`, co-tagged only where contact
  kills.

## Already there (findability, not coverage)

- Bounce = `phys.bounce[split]` (6 witnesses).
- Teleport = `topo.wrap` (dc22/sc25 pads, engine-cited).
- Remote = `gate.remote`, tagged on exactly the games you named.
- Move-on-click = the locus axis (control style) × the manip term doing the moving — deliberate two-axis split.
- Mirrored-axis parameter = `move.coupled[coupling: mirrored-x | mirrored-y | …]`, already signed; parameters in general = attributes.
- `agent.delegate` is witnessed (wa30 official + lantern_moths — figures
on the artifact). 
- And your "two main branches" exist as two documents: this vocabulary (change types) + the objects layer (sprite types, `design/objects/`).

## Checked and keeping the tag

- **ar25** ≠ move.coupled: its mirrors are derived images (shadow set
  recomposed by BFS, `ar25.py:1555`; UNDO restores piece+mirrors as one
  state) → `phys.reflect`. Coupled stays for independent co-driven
  bodies (lf52, m0r0, s5i5).
- **cd82**: the engine moves a cursor on a 3×3 index lattice with
  stations mapped clockwise from N (`cd82.py:531-549, 403-412`). The
  rotation is the board's arrangement, not the mechanism — tags follow
  mechanisms. Now expressible as `topology: ring`.
- **Orbit movement**: one witness (anchor_drift's pivot-rotate, in the
  rarities appendix) — promotes at a second. dc22's rotation is object
  rotation (`manip.attribute`).
- **vc33 L4**: it's the `manip.swap` gate + the recorded alignment-gate
  rarity, not `gate.direct`.

## Later

**v3 (post-pilot):** your factored entity×change taxonomy — agreed as
the end state (`agent.echo/patrol` being movement-kinds is the clearest
symptom), plus the renames (`manip`, gravity, fluid) and
locality-as-parameter. It's a migration over recorded facts, so it
waits until it can't stall the first generated games. We'd like your
eyes on its design. **ALE/Atari:** parked — idea inspiration only
(different frame/action contract, so it can't enter the witnessed
corpus); licence check first.

## Crosswalk (your words → our terms)

| You said | We have |
|---|---|
| bounce | `phys.bounce[split]` |
| teleport | `topo.wrap[kind: pad]` |
| remote (general) | `gate.remote`; locality-as-parameter in v3 |
| move on click | locus axis × `manip.select_cycle` / `manip.swap` |
| gravity | `move.platform[gravity_dir]` + `phys.*` |
| rotation around a point | `move.grid[topology: ring]` · `manip.attribute` · pivot-rotate rarity |
| fluid fill / flow / transfer | `goal.cover` · `flow.autonomous` · `flow.pumped[mode]` |
| sprite-type taxonomy | the objects layer (`design/objects/`) |
| parameters | attributes — `term[attr: values]` |
| enemy / ally / neutral | v3 entity branch; today `agent.*` + hazard note |

Amendment doc: `mechanics/vocabulary-v2.1-amendments.md`. Evidence:
`mechanics/officials-mechanics-digest.md` (per-claim file:line) + the
190×71 matrix. Corrections welcome — and keep this kind of review
coming.
