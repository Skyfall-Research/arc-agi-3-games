Generate a single game idea like the ones in the examples below. the game idea will then be implemented on a 64x64 grid with like 15 colors. In the game, it must be easy to understand what needs to be done, and the feedback must make this learning fast. For instance, I don't want a game where there is only one cell out of 64x64 that needs to be clicked in order to have meanigfull feedback from the game (exception if it's very clear from the graphic and some random interaction that a certain action should be made).  It is very important that the games that you generate are very diverse, both between each other and the games that I have already provided (at the end of the prompt I will give a list of short game descriptions that you can use for reference). Diversity can come in many ways. I care especially about the diversity of mechanism that needs to be understood in order for the game to be played, diversity of environments, so which kind of view or how the player perceives the environment, diversity of goal, diversity of actions. It is also important that you make the idea of the game decently complicated. Every level should introduce additional difficulty that needs to be solve in order to finish the level. Implement 3 levels. Make sure that the generated idea have the sam amount of details as the good examples provided below. 

- It is very important that you keep the objects and mechanics of the games visually simple. You need to keep in mind that the game will be implemented on a 64x64 grid so the resolution is quite limited!!
- The game should use **very few object types**. Level 1 should ideally have only 2–3 interactable categories.
- Prefer mechanics that can be represented with **simple geometric primitives**: blocks, lines, bars, pads, tokens, arrows, gates.

From the idea that you generate, I will generated more detailed specs with the following prompt. 

— spec prompt starts

Write an implementation-ready specification for a 2D grid game.

## Goal

Turn the idea into specs for a bold, self-explanatory microgame for a 64×64 grid where the first successful level teaches the core mechanic almost completely. Some of the mechanics described in the idea cannot be revealed in the first level and should be added in later levels. Aside from these additional mechanics, difficulty is not intended to arise from obscurity or increasing complexity. Rather it is intended to arise from the composition of reasoning demands acquired over the course of play. Later levels are therefore expected to require the accumulation and integration of concepts learned earlier in the environment. These specifications, together with a solver for the game, will then be implemented by Codex. What you write will be directly passed to Codex for implementation.

## Hard constraints

- 64×64 grid world
- Render using only integer color IDs 0–15
- Do not render text in the grid
- Respect the provided action space exactly
- The action space is UP, DOWN, RIGHT, LEFT, SPACE, and clicking on any cell (you can use a subset of this).
- State updates only on `step()` after actions
- No built-in tweening or animation; any animation must be represented as explicit extra grid states
- The game idea JSON includes `num_levels`. The game must contain exactly that number of levels, and the spec must state that exact count explicitly.
- Levels should be progressively more difficult, and knowledge from previous levels should help with the next ones.
- The game must be learnable for someone brand new just by interacting and observing cause and effect.
- Early levels should expose only a small number of interactable object categories so the goal is easy to infer from the screen.
- Do not provide exact action budgets, move limits, timer values, or per-level budget numbers. The implementer will derive the step limit after implementing the solver.

— spec prompt ends

keep this in mind when writing the idea and make sure that from the idea that you write it’s easy to write the specs by following these instructions. 

Here I also provide

Good examples: 

A game where you need to make water from a source and pour it into a bucket. The water source is placed somewhere in the upper edge of the screen, and it has to arrive in a bucket somewher on the screen. Water flows down with gravity, and it splits if it hits a flat surface. But if the flat surface is blocked on one side, then it only flows in the other direction. The player can place blocks anywhere on the screen by clicking on the point, and the block will appear there. By clicking the space, the water starts flowing, and blocks can’t be placed anymore, so either the water lands in the bucket, or it doesn’t (so you either win or lose the level). The first level is a single bucket and a source not aligned with each other so the player need to construct something to make the water fall into it (like a stair like pattern). The second level has 2 buckets, so the player needs to make the water split into both of them. The third level has 3 buckets. 

Another good example: 

This is an airflow routing puzzle played on a 64x64 board. A ball-like token starts at a marked start cell, and the objective is to make it land on a marked goal cell by building airflow channels that transport it automatically. The player does not move the ball directly. Instead, the player creates straight directed airflow segments with a two-click interaction: the first click selects the source cell, and the second click selects the destination cell. A valid destination must lie on the same row, same column, or same 45-degree diagonal as the source. If the straight segment between the two clicked cells is completely clear, an airflow appears from the first point to the second; otherwise the placement fails and the board flashes red.

Airflow segments are drawn as visible streams with repeated directional markings so their direction is obvious at a glance. Whenever the ball occupies a cell that belongs to an airflow segment, it is pushed one cell forward along that segment after each player interaction. If it reaches the end of a segment and no new airflow continues from that endpoint, it stops. The challenge is to place airflow segments in the correct arrangement and sequence so the ball is carried from start to goal. Level 1 should use an open board and a very simple route so the construction rule is learned immediately. Level 2 fixes a maximum number of airflow which ca be drawn, thus forcing the player to find the optimal path. The third level introduces multiple balls, which need to arrive at the same target. 

Bad examples:

This is a vertical lift puzzle where the player moves a worker through a scaffold tower and adjusts a platform\u2019s height by clicking large counterweight baskets. The board should look like a cross-section of a lift shaft: a central elevator platform, ropes or rails beside it, two chunky weight baskets at the bottom, and an exit door on a ledge higher up. Clicking the left or right basket moves one visible weight block from one side to the other, causing the platform to rise or fall by one clean level. The player uses UP, DOWN, LEFT, and RIGHT to walk on and off the platform, so the core puzzle is to set the lift to the right height and use it to reach useful ledges. Level 1 should show a single ledge one step above the floor, so one click makes the mechanic obvious and the worker can ride directly to the exit area. In later levels, the exit should not be reachable directly from the first lift. Instead, the player must ride to an intermediate ledge, step off, and travel to a different lift station or control point, then change the height of another lift to continue upward. These later levels should use multiple ledges and small wall partitions so that ledges are not decorative resting places but necessary transfer points between lift systems on the way to the exit.

Why is it bad: 

- “The board should look like a cross-section of a lift shaft: a central elevator platform, ropes or rails beside it, two chunky weight baskets at the bottom, and an exit door on a ledge higher up.” This is quite hard to implement in a 64x64 grid; it assumes that you can draw complex objects with such a low resolution but that’s very hard. So the result is a game where it’s hard to interpret what needs to be done and how we can interact with it.
- "Clicking the left or right basket moves one visible weight block from one side to the other” this could be fine, but we need to implement some guidelines on how to visually implemen this. And in the first level, the player should have some kind of hints that it needs to click on the block so that it will move from one side to the other.

Here is a revisited version of the same game idea: 

This is a vertical lift puzzle where the player moves a worker through a scaffold tower and adjusts a platform’s height by clicking large counterweight baskets. Vertical lines divide the platforms from each other, and the platform is represented by a single horizontal line. Platforms are connected two by two by a rope, so if we add weight on one of the two connected platforms, that platform will go down by a level, and the connected one will go up by a level. 

Counterweights are shown as large basket blocks stored in a clearly marked storage rack near the top of the screen. Beneath each platform is a matching basket slot, drawn with the same distinctive color and shape as the storage rack to signal that baskets can be transferred between them. The interaction is click-based and works in two steps: first click a basket in the storage rack or in a platform’s basket slot to pick it up, then click another valid basket slot to place it there. When a basket is placed into a platform’s slot, that platform immediately changes height. Baskets can therefore be moved either from the storage rack onto a platform or from one platform slot to another.

The player can move an agent (another block) with WASD. The platform compartment exists so that the player can move freely on top of the platform.  The objective is to align the platforms so that the agent can reach the target. Weights can be moved from one platform to the other by clicking on the original platform first and then on the final one. The first level only has two platforms, the second has four, and the third level has two platforms, but it requires the agent to jump off a platform in an opening in the wall, make the platform go up, and then go below the platform where the target is.

Here are the games that have already been generated:
