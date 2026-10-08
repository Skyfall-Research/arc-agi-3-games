You are designing a new deterministic puzzle game specification in the style of small ARC-agi 3 puzzle games.

Invent a completely original game description. The game should feel like a tiny formal system: visually clear, deterministic, easy to simulate once the rules are known, but capable of producing nontrivial puzzles through composition.

The most important design goal is coherent systemic depth. The game should feel like one focused game family, not a bag of unrelated devices, but it should develop that family through several related object or rule types.

## Design goal

Create a game with one central theme and a clear one-sentence identity:

> “This is a game about [simple operation] becoming difficult because [contextual consequence].”

Use only a few meaningful player actions. For the assigned game idea, preserve the core mechanic vocabulary: the concrete actions, object categories, spatial operations, timing rules, and validator quirks should remain recognizable. Do not replace the idea with a cleaner but different abstraction.

Keep a strong rule-to-level ratio: prefer a small number of rules with many consequences over many special objects. New object types should be introduced only when they create a distinct planning pressure that still belongs to the same game family.

Difficulty should come from interactions among related rules, not from denser layouts, arbitrary extra devices, or larger checklists. Later levels should combine existing mechanics through placement, timing, state dependency, route structure, resource pressure, or forced revisits. Each level must make these interactions concrete through exact object placement, initial state, and an example solving path.

The level should teach through play. When a new mechanic is introduced, the player should encounter a local impasse: ordinary actions no longer make useful progress, but a nearby object, state, route, or affordance suggests experimentation. Trying it should produce an immediate, visible, physically meaningful consequence: a route opens, a state flips, the player moves, a danger is avoided, or a future consequence becomes understandable.

A mechanic is not well-established until it is reused in contrasting contexts. The same rule, object, or action should have different strategic roles depending on position, timing, direction, state, resources, future consequences, or interaction with other mechanics. It may solve one problem while creating another; act as a tool in one level and a liability in another; need to be activated, preserved, delayed, avoided, reversed, or combined with something else.

Important: contrasting roles must come from context, not hidden exceptions. A mechanic’s operational rule must remain identical wherever it appears unless a new named mechanic is explicitly introduced. Design richness should come from authored layout, timing, dependency structure, and state interactions, not from ambiguous or special-case behavior.

The objective should be visible and natural from the board. Define the success condition exactly, including what is relevant, ignored, allowed, and forbidden.


## Avoid these bad patterns

- attribute checklist puzzles where the player independently adjusts several variables until a checker accepts them;
- device errand puzzles where the player mostly travels between state-changing stations;
- predicate pileup where the win condition is just many exact requirements joined by AND;
- level progression that introduces new nouns instead of new consequences;
- visual legend-reading where many arbitrary symbols must be memorized;
- fake depth from decoys, optional objects, or recovery paths that do not test a real misconception;
- late mechanics that appear only in final levels;
- objectives that are precise but not visually natural;
- solutions that are merely recipes rather than containing an insight;
- rules that work differently in one special case without a principled reason;
- layouts where spatial structure could be removed without changing the puzzle;
- Adding borders to the internal part of a logic grid. 
- A level that is solvable by ignoring the mechanics in that level. 
- Levels with trivial solution which can be solved with random actions (this should be avoided)
- mechanics introduced only by description rather than by a local playable impasse;
- tutorial levels where the new mechanic is used once and never reinterpreted;
- levels where new objects are visible but not needed to resolve a concrete local problem;
- mechanics that always have the same role whenever they appear;
- long movement sequences with no new decision, surprise, reinterpretation, or local experiment;
- puzzles where the intended solution is clear from the object list rather than discovered from the board state.

## Hard constraints
- Render using only integer color IDs 0–15
- Do not render text in the grid
- Respect the provided action space exactly
- The action space is UP, DOWN, LEFT, RIGHT, SPACE, and clicking on any cell (you can use a subset of this).
- State updates only on `step()` after actions
- The game idea JSON includes `num_levels`. The game must contain exactly that number of levels, and the spec must state that exact count explicitly.
- Energy, budget, or timers should support A LOT of exploration especially in early levels.

## Implementation contract

The final spec must be both a playable design document and an implementation-ready contract. It should describe why the game is interesting from the player’s perspective, but it must also give enough exact operational detail that an implementer can build the game without inventing missing behavior.

Do not leave important interactions only in narrative terms. When a level depends on a mechanic, state change, object placement, timing rule, collision, click target, or update-order detail, translate it into concrete implementation information: coordinates or logical positions, initial state, relevant object states, action semantics, and the intended resolution order.

The spec should be implementation-dense, not terse. For each level, include concrete initial state, object coordinates or logical positions, selected object/cursor state, exact action semantics, win validation, intended solution outline, and at least one anti-degenerate/necessity note. Prefer explicitness over brevity.

Use two layers of description:

1. **Player-facing discovery**
   Explain what the player discovers, what local impasse teaches the mechanic, and why the interaction is interesting.

2. **State-machine detail**
   Compile that discovery into exact rules, state variables, object behavior, coordinates, and replayable solution steps wherever those details matter.

Design richness must not create implementation ambiguity. If a mechanic has different strategic roles in different levels, those roles must emerge from placement, timing, state, geometry, or dependency structure while the operational rule remains unchanged.


## Authored level specification

The final spec must document both the general rules and the exact authored level instances. Each level should be detailed enough that an implementer could reconstruct the intended puzzle without inventing missing structure.

The game should not merely be a set of rules to satisfy. For every game type, the level instance itself must be part of the puzzle. Use authored structural irregularity: asymmetrical layouts, uneven timing, awkward object placement, partial information, scarce resources, offset dependencies, misleading affordances, state bottlenecks, delayed consequences, changing object roles, forced revisits, or interaction paths that are useful only during certain phases.

This irregularity must not be random clutter. Every irregular feature should create a consequence: commitment, shortcut prevention, timing pressure, resource tension, information ambiguity, approach asymmetry, recovery cost, changed object meaning, staging requirement, or a plausible wrong plan.

For level 1, add explicit visual guidance only when the game’s objective is not immediately understandable from physical cause and effect. This is especially important for games based on matching, balancing, counting, pattern completion, symbolic rules, exact target validation, or “make this configuration correct” logic. In these cases, the first level should include some small form of positive goal evidence: a solved or partially solved reference, a target silhouette, an already-open example door, a before/after mini-demonstration, or a one-action setup where the correct interaction immediately produces visible success feedback.

Each level should describe how its mechanics are being combined. Do not progress by assigning one isolated mechanic to each level. Instead, each new level should reuse earlier mechanics under a new constraint, make two systems depend on each other, turn a previous tool into a liability, require staging before commitment, force multiple targets to be satisfied simultaneously, or change the role of a familiar object. The introduces mechanics should be necessary in order to solve the level. You must check as thoroughly as possible that everything which is added in a level is actually necessary. There shouldn't be random object or feature that you add only to have more mechanics in the level. Keep this in mind but don't limit the complexity of the level just because you need to check this. 

Mechanics should be introduced through local impasses, not through abstract pre-planning. The player should be presented with a game state where known rules don't allow to move forward, see a unfamiliar or changed object, try interacting with it, and immediately observe a physical consequence that reveals the rule.  Each mechanic should be reused in contrasting contexts, so it becomes a general tool rather than a one-off key. The same rule, object, or action should play different roles depending on position, timing, state, resources, or interaction with other systems. It may help in one situation and constrain in another; solve an immediate problem while creating a future one; need to be activated, preserved, avoided, delayed, reversed, or combined with something else.

Avoid levels where the solution is mostly preparing a list of required objects or states and then executing a straightforward route. The player should repeatedly face situations where the meaning of a mechanic depends on context: position, timing, direction, order, available resources, future consequences, or interaction with other mechanics.

Avoid clean instances where objects, states, regions, or actions appear in the exact order they are used. Avoid designs that read like a recipe: do A, then B, then C, with each step placed directly after the previous one. The player or agent should need to understand how parts relate, not merely follow an obvious sequence.

For each level, specify an intended solution depth. Early tutorial levels may be short, but middle and late levels should usually require longer verified solutions. Do not lengthen solutions by adding corridors, repeated no-op movement, redundant toggles, or mechanical padding. Extra actions must be required by puzzle structure: staging, preserving state, returning through altered terrain, synchronizing timing, satisfying multiple goals, setting up temporary blockers, conserving or spending resources, or using one object to enable another.

For games with 7–9 levels, target solution lengths should usually ramp like:

* first tutorial levels: 8-10 meaningful actions;
* second, third levels: 10-20 meaningful actions;
* fourth and firth levels: 30-40 meaningful actions;
* fifth level and later: 40+ meaningful actions with increased difficulty

Use a consistent logical coordinate system when relevant. For click-based games, identify clickable regions by coordinates or logical module IDs. For non-budget timers, phases, queues, ghosts, helpers, enemies, hidden-but-visible state, or update order, give exact initial values per level. Level descriptions must be concrete, not just thematic.

After drafting each level, perform an anti-cleanliness check. Revise if the solution is mostly a linear chain, if the level could be replaced by a corridor, checklist, counter, or timer, if every object is encountered exactly when needed, or if wrong plans fail only because an abstract rule blocks them rather than because the authored instance creates real consequences.

The starting from the third level there should be a dependency network, not a single dependency chain. A solution may have logical phases, but the level must not simply present those phases in order.


## Visual

* Game entities should usually be rendered as connected multi-tile shapes such as 2×2, 2×3, 3×3, or longer patterned structures. Avoid representing the main entities as plain 1×1 colored squares unless the idea absolutely requires a tiny token.
* Prioritize negative space and first-frame readability over decorative size. Not every interactable needs to be large; use the smallest footprint that remains clearly readable.
* Use a 64×64 render canvas, but define the native gameplay space separately: it may be a small tile board, pixel coordinates, graph nodes, panel slots, reservoirs, reticle centers, or another geometry. Do not force a small logical board when the mechanic depends on pixel-scale movement, panels, overlap, radii, handles, or exact object footprints.
* Objects that share a role may share a visual family, but if the player must track them separately, they must differ clearly at a glance through high-contrast color, position, shape variant, size, or attachment. Do not rely on near-neighbor colors alone to distinguish same-shaped objects.
* Use a restrained, harmonious palette: quiet neutral colors for background and structure, and only a few saturated gameplay colors at once. Colors that must be compared should be clearly distinct, but avoid giving every component an equally bright unrelated hue.
* Prefer high-contrast quiet backgrounds, edge HUDs for step/time bars, and spatially separate reference/control panels from the play area. Group related things by matching color, shared frames, connector lines, or consistent placement. Introduce mechanics visually through simple early layouts, then add constraints and composed relationships while preserving the same visual grammar.
* Provide sketches only for central multi-tile elements whose silhouette, visual detail, or interaction would otherwise be ambiguous. Sketches should clarify gameplay purpose, not document inert background or decoration.
* Visual detail should improve readability without competing with gameplay. Use large simple shapes and consistent color regions by default; add markings only when they communicate essential state such as direction, active/inactive status, exact match shape, ownership, or required counting. Avoid background patterns, subtle corner markers, ornamental dots, pipe textures, nested outlines, repeated small bars, and tiny glyphs unless they are clearly necessary for the puzzle.
* When a game has several interacting components, render them as a clean schematic rather than a detailed machine diagram. Show only the state variables the player must compare at a glance, using large simple shapes and consistent color regions. Avoid repeated small bars, pipe textures, nested outlines, and per-unit markings unless counting those units is the actual puzzle.

### Animation and state feedback
Use animation only when it is necessary for readability, causality, or learning the mechanic. Do not specify animation for every ordinary move or state change by default. Most simple movements, selections, toggles, and one-step updates should render as immediate state changes with brief visual feedback only when needed. Add short, deterministic animations when the player would otherwise struggle to understand what happened: for example a gate sliding, a block cracking, a force pushing the avatar, a color spreading, a switch flipping, a falling object settling, or an invalid action flashing and reverting. The spec should state when the important state change happens during the animation, whether animation frames consume player steps, and what visual feedback distinguishes success, failure, danger, and completion. Prefer sparse animations that teach timing, causality, and object roles through visible motion; avoid dense, repeated, or ornamental animation that slows down play or does not clarify a rule or consequence.

For mechanics where one player action causes an object to move more than one logical cell, rotate/pivot around another object, slide until blocked, fall/settle, roll through a redirector, or trigger a chain of visible physical consequences, the spec should explicitly require a short deterministic animation. State which object moves, the frame sequence at a logical level, when the final state is committed, and whether animation frames consume player budget. Do not rely on the implementer to infer animation from verbs like “roll”, “slide”, “pivot”, “drift”, or “push”.


### If the game is movement-based

* Define a logical movement lattice separate from rendered pixels.
* Each movement action must move the avatar by one logical unit, not by one rendered pixel, although the logical unit may coincide with the rendered pixel.
* Do not treat the board as a neutral container for mechanics. The traversable space should actively shape the puzzle.
* Avoid layouts that are just a single corridor, a sequence of horizontal lanes, or a left-to-right checklist. A good late level should feel like a small navigable place, not a recipe written onto the board.

### If the game is click-based

* Major clickables should be clear, module-sized hit regions.
* The intended interaction should be “click this device / tile / cluster,” not “hunt for the exact tiny pixel.”

  ## Color Palette

  - 0 `#FFFFFFFF` -> white
  - 1 `#CCCCCCFF` -> light gray
  - 2 `#999999FF` -> gray
  - 3 `#666666FF` -> dark gray
  - 4 `#333333FF` -> very dark gray
  - 5 `#000000FF` -> black
  - 6 `#E53AA3FF` -> magenta
  - 7 `#FF7BCCFF` -> light magenta / pink
  - 8 `#F93C31FF` -> red
  - 9 `#1E93FFFF` -> blue
  - 10 `#88D8F1FF` -> light blue
  - 11 `#FFDC00FF` -> yellow
  - 12 `#FF851BFF` -> orange
  - 13 `#921231FF` -> maroon
  - 14 `#4FCC30FF` -> green
  - 15 `#A356D6FF` -> purple

Write in plain text or Markdown. 
