# tools/play/ — vendored snapshot of the duckWM instrumented player

The browser game player used to live only in the duckWM sister repo, so
`arc-games play` exited 2 on any clone without a duckWM checkout beside it
(contract P-4 §5 left vendoring open; contract **L-2** closes it). This tree is
that player, copied out and then modified HERE and ONLY here. duckWM remains
the SOURCE OF TRUTH and remains **read-only** — nothing in this repo ever writes
into it, and the two files below were copied byte-identical before a single
character was changed.

- Source: `../duckWM/local-docs/arc-agi-3-games/tools/play/` (relative to the repo root)
- duckWM commit: `3e66cffccb8030efcba0d4f3ef7d21f9abd0e3a7`
- Source files clean at that commit: yes (`git status --porcelain` on the two
  paths was empty)
- Copied: 2026-10-01

## The byte-identical copy

sha256 of each file **as copied**, before this contract's modifications. Verify
a file is still upstream's with
`shasum -a 256 <duckWM path>/<file>` against the row below.

| file | bytes | sha256 (as copied) |
| --- | --- | --- |
| server.py | 25672 | 4ae2bf0f53184348219c1e543fc7ca5b929dd3890984ab65fad82fc374bb8e48 |
| index.html | 20908 | 1140369966e24010addd37060c5b16035d532a85fb8d6db09a758e006ee32b08 |

`index.html` is not optional: `server.py` serves it from its own directory
(`(HERE / "index.html").read_bytes()`), so the player is these two files.

## Every modification made here

A reviewer can see all of it with:

```bash
diff -u ../duckWM/local-docs/arc-agi-3-games/tools/play/server.py  tools/play/server.py
diff -u ../duckWM/local-docs/arc-agi-3-games/tools/play/index.html tools/play/index.html
```

### A. Standing alone in this repo (3 edits, `server.py`)

Upstream resolves its roots and its scorer through duckWM's own tree. Neither
exists here, and a vendored copy that still needs the sibling checkout would
vendor nothing — so these three are what the vendoring itself costs.

1. **The two roots.** `sys.path.insert(HERE.parent)` +
   `from paths import ARC3_INFERENCE, GAMES_DIR, LOG_DIR, REPO` is replaced by
   `REPO = HERE.parents[1]`, `GAMES_DIR = REPO / "games"` (the shared shelf,
   contract P-3) and the SAME derived log rule upstream already uses,
   `LOG_DIR = GAMES_DIR.parent / f"play-logs-{GAMES_DIR.name}"`. The
   `PLAY_GAMES_DIR` / `PLAY_PORT` overrides below it are untouched, and the
   default resolves to the `play-logs-games/` this repo already writes.
2. **`compute_level_score`.** `sys.path.insert(ARC3_INFERENCE)` +
   `from inference.tools.traces import compute_level_score` is replaced by that
   function copied verbatim (eight lines) with its two module constants
   inlined: `COMPLETED_LEVEL_STATUS = "COMPLETED"`, `PER_LEVEL_SCORE_CAP = 115.0`.
   Source: `duckWM/src/ARC3-Inference/inference/tools/traces.py` at the commit
   above. A human playthrough is still scored by the agents' formula.
3. **The module docstring** gains a VENDORED paragraph pointing at this file,
   and its run line becomes `arc-games play` / `tools/play/server.py`.

### B. The §7 layout-seed picker (`server.py`)

The frozen convention is `Game(layout_seed: int | None = None)` where `None` is
the authored canonical build. **The canonical path is upstream's instantiation
unchanged** — `game_cls()`, no argument at all — and a seed reaches a game only
when the operator picked one.

4. `import inspect` added.
5. New `SeedError(ValueError)`, `_SEED_HELP`, `_not_a_seed()` and
   `parse_seed()`: absent / null / `""` / `"canonical"` all mean the canonical
   build; anything else that is not an integer raises. `bool` is refused
   explicitly (it is an `int` in Python).
6. New `accepts_layout_seed(game_cls)`: asks the signature before handing a
   game a seed, so a pre-§7 game produces a sentence instead of a TypeError
   from inside somebody else's constructor.
7. New `manifest_seeds(meta_path)`: reads `package/manifest.json` beside the
   metadata the discovery glob finds and returns `seeds.validated` as
   `{seed, win, levels_completed}`. **Every failure degrades to `[]`** — an
   `out/play` mirror entry has no `package/` and that is normal, not an error.
8. `discover_games()` gains `"seeds": manifest_seeds(meta_path)`, which
   `/api/games` already forwards (it strips only `"py"`).
9. `Session.reset_state()` gains `self.layout_seed = None`.
10. `Session.load()` takes `layout_seed: int | None = None`, refuses an
    unplayable seed **before** the outgoing session is closed (a typo costs the
    session you are in nothing), and instantiates
    `game_cls() if layout_seed is None else game_cls(layout_seed=layout_seed)`.
11. `Handler.do_POST` passes `parse_seed(body.get("layout_seed"))` to
    `/api/load`, and a new `except SeedError` answers **400 with one plain
    sentence**, ahead of the existing 403/500 arms.

### C. Honest records (`server.py`)

A play log must never conflate two layouts. `null`/absent = canonical, which is
also what every log written before the picker existed means.

12. `Session.snapshot()` gains `"layout_seed"` (this is also what keeps the
    seed on screen for the whole session).
13. `Session.log()` gains `"layout_seed"`.
14. `saved_sessions()` gains `"layout_seed"` per recorded session.

### D. The picker in the UI (`index.html`)

15. A `seed` selector + hidden free-entry field in the session bar, beside the
    existing `mode` selector, styled with the existing `#gameFilter` /
    `button, select` rules so it is native to the page.
16. `drawSeedPicker` / `chosenSeed` / `showSeed` / `reloadWithSeed` and their
    two listeners: the options are **canonical (as packaged)** (default, always
    first), one per validated seed labelled with the win and level count S6
    measured (`48217 — win · 8L`), and **another seed…** which reveals the free
    field. No manifest → canonical + free field only. Changing the seed
    re-loads the game at that layout; `load()` already closes a part-played
    level as ABANDONED and flushes the log first, so nothing is lost quietly.
17. `load()` sends `layout_seed`, and rebuilds the picker (back to canonical)
    whenever the game changes, since the validated list is per game.
18. The session line shows the layout for the whole session — `canonical` in
    dim, `seed <n>` in amber — so a seeded run cannot read as the packaged one.
19. The boot path restores the picker onto a live session's seed.
20. The global keydown guard now skips `INPUT` as well as `SELECT`. Required by
    the free-entry field; it also stops a keystroke typed into the existing
    game filter reaching the board as an action.

### E. The live catalog + honest per-layout warnings (`server.py`, contract H-1)

Added 2026-10-06. Two defects the L-2 vendoring inherited from upstream, each
fixed where upstream decided it.

21. **The catalog is re-scanned, not snapshotted** (H-1 item 3). Upstream's
    `GAMES = {g["game_id"]: g for g in discover_games()}` runs ONCE at import,
    so every newly packaged game needed a server restart to become playable
    (bitten three times in one week). Replaced by a `GAMES: dict` that
    `refresh_games()` rebuilds **in place** — `Session.load` still reads
    `GAMES[game_id]`, so this edit leaves the per-game play flow untouched —
    called once at import (`main`'s startup count is unchanged) and then on
    every `/api/games` request. Cost measured on this repo's shelf: **1.8 ms**
    for 11 entries (one glob + two small reads per entry), on a request the
    browser makes at page load. A top-level mtime check was the cheaper
    alternative and is the wrong one: an entry's own `metadata.json` rewritten
    in place — a re-packaged game — does not move the parent's mtime.
22. **`finished_modes` is per LAYOUT** (H-1 item 11). Upstream collapses every
    layout into one answer, which L-2's seed picker made wrong: a finished
    canonical `discovery` run warned "a second discovery log supersedes the
    first" when the operator loaded seed 48217, a different board that
    supersedes nothing. `finished_modes(game_id, layout_seed=None)` now filters
    on the `layout_seed` `saved_sessions` already reports (absent/null = the
    canonical build, which is what every pre-picker log means), `Session.load`
    passes the seed it is loading, and the warning names the layout it is about.

### F. The public face (`server.py`, contract OS-2)

Added 2026-10-08.

23. **The module docstring describes this player as it now is**: the shelf's
    player (no longer "the 25 official games"), scored by the inlined
    `compute_level_score`, with the live catalog and the seed picker named;
    the upstream file cites (the scorer's module, the agent vocabulary file,
    the reference harness's RESET line) are replaced by plain statements of
    the same three constraints. Behavior unchanged — docstring only.

## Keeping this in step with duckWM

There is no sync tool for this tree (unlike `canon/`, which has
`gen.tools.sync_canon`): it is twenty-three hand-made edits on a file that
upstream rarely touches. To re-base on a newer duckWM, re-copy both files,
re-apply the list above, and re-stamp the commit, the shas and the date here.
