# Fixtures — real CLI payloads (captured, never hand-written)

Captured 2026-09-21 from the installed CLIs (claude 2.1.232, codex-cli
0.142.5) during the B0 smoke. These are the parser regression base for
`gen/backends.py` (B3 will grow tests over them).

- `localclaude-success-record.json` — a full smoke ledger record for a green
  `claude -p … --output-format json` call (the `raw` field is the CLI's
  verbatim result payload). Note `usage.output_tokens` includes thinking
  tokens (`output_tokens_details.thinking_tokens`) — a one-line reply cost
  166 output tokens on haiku.
- `localclaude-authfail-payload.json` — the CLI's verbatim stdout JSON for
  an expired-OAuth call: exit 1, `is_error: true`, error text in `result`,
  and — the trap — `subtype: "success"`. Exit code + `is_error` are the
  error signals, never `subtype`.
- `codex-success-events.jsonl` — the FIRST green codex event stream,
  captured 2026-10-01 (codex-cli 0.142.5, API-key login via
  `codex login --with-api-key`, CLI-default model) with the driver's exact
  argv: `codex exec -s read-only --skip-git-repo-check --json -o <tmp>
  "Reply with exactly: SMOKE-OK"`. Verbatim stdout, 5 JSONL events.
  What it proves: the session handle is `thread_id` on the
  `thread.started` event (top-level, not under a payload) — the first key
  in `_CODEX_SESSION_ID_KEYS`' scan order, now confirmable (P-1b pins
  flip over this file); usage arrives on `turn.completed` (29,838 in /
  19 out, `reasoning_output_tokens` broken out); and — the trap — a GREEN
  stream can carry an `item.completed` whose item has `type: "error"`
  (here a skills-context advisory): an error-typed item is NOT a failed
  turn, `turn.failed` is. The failure shape (`turn.failed` with
  `error.message`) remains exercised in `gen/backends.py::CodexDriver`
  from the live 401s.
