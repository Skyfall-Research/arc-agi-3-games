# Contributing

Issues and pull requests are welcome — bug reports, new checks, better games,
clearer docs.

## Before you open a pull request

1. **The suite passes.** From the repo root:

   ```bash
   python3.12 -m venv .venv
   .venv/bin/pip install -e '.[dev]'
   .venv/bin/python -m pytest gen/tests -q
   ```

   Zero failures. On a fresh clone some tests SKIP, and say why: they measure
   evidence this public tree does not carry (the maintainers' private run
   corpus, the official-games corpus, a sibling canon checkout). That is
   expected; a failure is not. `gen/tests/conftest.py` lists every one.

2. **`ruff` is clean:**

   ```bash
   .venv/bin/ruff check gen/
   ```

3. **No secrets, ever.** Never commit an API key, token, credential file or
   `.env` — not even a revoked one, not even in a test. Keys belong in your
   environment (`OPENROUTER_API_KEY`) or in your agent CLI's own login. A test
   that needs a key-shaped string uses an obviously fake one. Run outputs live
   in `out/`, which is gitignored for a reason: do not force-add anything from
   it.

## Good to know

- A behavior change ships with its default unchanged and a config key to turn
  it on; `config/template.yaml` documents every key.
- `canon/` is a stamped snapshot. Do not hand-edit it — the sha256 table in
  `canon/PROVENANCE.md` will reject the edit, and the pipeline spot-checks
  that table before every batch.
- `canon/third-party/` is vendored third-party material under its own license
  (see `NOTICE`); it is never modified.
- New games reach `games/` through the pipeline's own packaging step, not by
  hand.

By contributing you agree that your contribution is licensed under the Apache
License, Version 2.0 (see `LICENSE`).
