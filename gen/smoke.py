"""B0 smoke: canon loads + each driver returns a trivial completion, cost logged.

Run from the repo root:
    .venv/bin/python -m gen.smoke [--driver all|localclaude|codex] [--config config/b001-pilot.yaml]

Appends one JSON record per driver attempt to out/smoke/smoke.jsonl and
exits non-zero on any failure. Auth failures print their user-side
remediation (credentials are never touched by this repo).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime

from .backends import DRIVERS, DriverError, codex_auth_env
from .config import REPO_ROOT, load_config, matrix_row_count

SMOKE_PROMPT = "Reply with exactly: SMOKE-OK"
MATRIX_ROWS_SIGNED = 190  # 25 officials + 165 tufa — signed count, fail on drift
SMOKE_MODELS = {
    "localclaude": "claude-haiku-4-5-20251001",  # cheapest lane for a one-line reply
    "codex": None,  # CLI default; the record keeps whatever model the events report
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="B0 backend + canon smoke")
    parser.add_argument("--driver", default="all", choices=["all", *DRIVERS])
    parser.add_argument("--config", default="config/b001-pilot.yaml")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    rows = matrix_row_count(cfg)
    if rows != MATRIX_ROWS_SIGNED:
        print(f"CANON FAIL: game-term-matrix.csv has {rows} rows, expected {MATRIX_ROWS_SIGNED}")
        return 1
    print(f"canon OK: {cfg['duckwm_docs']} | matrix rows: {rows}")

    names = list(DRIVERS) if args.driver == "all" else [args.driver]
    ledger_path = REPO_ROOT / "out/smoke/smoke.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    with ledger_path.open("a", encoding="utf-8") as ledger:
        for name in names:
            stamp = datetime.now(UTC).isoformat(timespec="seconds")
            try:
                driver = DRIVERS[name]()
                if name == "codex":
                    # P-1a item 4: no credential at all is a usage error at
                    # second zero, not a network round trip. It passes on a
                    # STALE key — which is what the four 401s in this very
                    # ledger are — because presence is all a preflight knows.
                    driver.preflight(auth_env=codex_auth_env(cfg))
                result = driver.complete(SMOKE_PROMPT, model=SMOKE_MODELS[name])
            except DriverError as exc:
                print(f"FAIL  {name}: {exc}")
                ledger.write(json.dumps(
                    {"ts": stamp, "driver": name, "ok": False, "error": str(exc)}
                ) + "\n")
                failures.append(name)
                continue
            ok = "SMOKE-OK" in result.text
            cost = f"${result.usd_cost:.4f}" if result.usd_cost is not None else "$unreported"
            print(
                f"{'ok   ' if ok else 'FAIL '} {name}"
                f" | model {result.model_reported or result.model_requested or 'cli-default'}"
                f" | {cost} | tokens {result.tokens_in}/{result.tokens_out}"
                f" | {result.duration_s:.1f}s"
            )
            ledger.write(json.dumps({"ts": stamp, "ok": ok, **result.to_record()}) + "\n")
            if not ok:
                print(f"      reply was: {result.text[:200]!r}")
                failures.append(name)

    print(f"ledger: {ledger_path}")
    if failures:
        print(f"smoke FAILED for: {', '.join(failures)}")
        return 1
    print("smoke green: every driver returned SMOKE-OK with cost logged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
