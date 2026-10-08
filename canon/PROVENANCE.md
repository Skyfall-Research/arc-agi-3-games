# canon/ — vendored snapshot of the duckWM generator canon

This tree is a copy of the files the pipeline reads under `duckwm_docs`, at the
same relative paths the readers use, so the generator runs standalone on a
machine with no duckWM checkout (operator ruling, 2026-09-29; contract P-2).
duckWM remains the SOURCE OF TRUTH and remains read-only — this is a snapshot
of it, not a fork of it.

Do not hand-edit these files. Re-stamp the snapshot from a duckWM checkout
with:

    .venv/bin/python -m gen.tools.sync_canon --source <duckWM canon> [--force]

The file set is DERIVED from the readers themselves (see that module); it is
not a list anyone maintains here. To read the canon from a real duckWM
checkout instead of this snapshot, point `duckwm_docs` at it in your config.
The sha256 table below is what lets the snapshot vouch for itself.

## Post-copy neutralization

Every copied file is byte-identical to its duckWM source EXCEPT for one
deterministic scrub the sync tool applies after the copy (contract OS-2):
absolute machine paths become portable ones (a home-directory path into the
duckWM checkout is written `duckWM/...`, the uv cache root `$UV_CACHE_DIR`),
and the personal name in sign-off, approval and ruling attributions becomes
the neutral "operator", every date kept. Nothing else changes — no wording,
no number, no structure. The rules live in `gen/tools/sync_canon.py`
(`neutralize_canon`) and `gen/tools/public_hygiene.py`, so a re-sync from an
unchanged duckWM reproduces these bytes exactly; a config that reads a duckWM
checkout directly sees the un-neutralized originals.

## Third-party: Tufalabs re-arc-3 (MIT)

`third-party/re-arc-3/game_generation_prompt.md` and `spec_prompt.md` are
Tufalabs' re-arc-3 v0.1.2 prompts — copied VERBATIM, never neutralized or
otherwise modified — that the S0 and S1 stages quote as reference doctrine.
They are MIT-licensed: `third-party/re-arc-3/LICENSE-MIT.md` carries the
license text, the attribution, and where the grant comes from. That notice
has no duckWM source; the sync tool writes it, and it is stamped below like
every other file.

## The official games

The bestiary (`design/objects/bestiary/`) and the mechanics tables analyse the
25 official ARC-AGI-3 games published by the ARC Prize Foundation
(arcprize.org). Those games are arcprize's and are NOT vendored here — no game
source, level data or frames. What this canon carries is analysis of them:
derived numbers (counts, per-level values, line citations) and short
quotations used for analysis, with the source of every reading named.

## Snapshot

The source path is relative to the repo root — the spelling the historical
configs use for `duckwm_docs`.

- Source: ../duckWM/local-docs/arc-agi-3-generator
- duckWM commit: 3e66cffccb8030efcba0d4f3ef7d21f9abd0e3a7
- Source tree clean: yes
- Copied: 2026-10-08
- Files: 39

## Files

| path | bytes | sha256 |
| --- | --- | --- |
| design/objects/affordance-language.md | 15485 | 9e92bc36096093e8000d662888a6224e19b9f8033790455dfd895c9b7fc89790 |
| design/objects/bestiary/ar25.md | 19022 | b619ea297ee869fb8577a8ada7ac1d907ab16dcd93ed97cf317b73bc4f819425 |
| design/objects/bestiary/bp35.md | 13936 | 0cb0d70c3e5916368bdb6d6a1bb28991070acd80c0a970733c5cc1723983d2de |
| design/objects/bestiary/cd82.md | 21849 | cfd76bf072df6ef7df66617a2b8839d2a11ad513bae4f49804caf4d4f0b0dd75 |
| design/objects/bestiary/cn04.md | 25547 | 4b5de5bfc132e8e29e5f6e942665bb375c7b15e6fcd1725fbe79010b8869fc21 |
| design/objects/bestiary/dc22.md | 30861 | 7395fca99372ebde522f553ebec73e0b7f8847d72442e9b066e4f7bb7850750f |
| design/objects/bestiary/ft09.md | 21507 | 7116f2155d9589aa324ebbfde425220ee33bc7c435be629e9b29cc9b66d7874b |
| design/objects/bestiary/g50t.md | 23992 | 87713a506f693eed3ec8ee34901630b2a6ed5b9c2cc1be023bd5f43d08401e6d |
| design/objects/bestiary/ka59.md | 15540 | 41947acf71f0acab4ea8823c4ed7cabe7185a82efb3a884fc6133b4548531885 |
| design/objects/bestiary/lf52.md | 14507 | ee7defe05791effa094836fa62097c56a569fd79b08441389d2e2874542ce6d4 |
| design/objects/bestiary/lp85.md | 22803 | a47cac8984af7c4e1e9bebdd84de700f4d67911655314a6704e1781a0379cc2b |
| design/objects/bestiary/ls20.md | 26024 | 2611994f9b56f94562040428edea7ef62fb74097899e1711ae760fa336b3012f |
| design/objects/bestiary/m0r0.md | 15326 | c4fe9bc25747db625cbaa8e3711a294fda0d75006e4961dd89ff1edc0c69b4a5 |
| design/objects/bestiary/r11l.md | 27332 | 7b6b3c477eade17510934a822beeea3a21def301b71f1e225364ff035e22f053 |
| design/objects/bestiary/re86.md | 22964 | e2e9e2554e54f95465a1e760b8bbeb6b7ab6ca6a2e1eae6987235ea917182b68 |
| design/objects/bestiary/s5i5.md | 26934 | 0431fdb32f7b16958941cbd685392b53a22d2d6b5d66b48f29dbef227ab996da |
| design/objects/bestiary/sb26.md | 33373 | 4e02923845710ba6aac4d8023477a611d870d1ef3777368e736329321de1072a |
| design/objects/bestiary/sc25.md | 30358 | a26f3daad5e84ae9c07daf09444525624d09ea6c610226e29ba0dd754f76f583 |
| design/objects/bestiary/sk48.md | 28060 | ca6f224068166985c230c31b2920af61c7f83373ca3410cdfed259df6cf0b610 |
| design/objects/bestiary/sp80.md | 28513 | 8aefc5d0f4b5b14aed341bd40ede0629d7b85560c26753d22c1c0949097c60eb |
| design/objects/bestiary/su15.md | 37226 | 637a97581fe8da20155e9bc47d867210257298ca54ea6bb360bcc485ba37f21c |
| design/objects/bestiary/tn36.md | 29679 | aadf6db48f42b5edd3d3968b60e4ebb85d6f90ef81aed8066da8da1ecb01aa4e |
| design/objects/bestiary/tr87.md | 26672 | da6fcbb3a320a6a51031d7b06b8f8e2b186a84ba91638c5172c037967cfdd6d5 |
| design/objects/bestiary/tu93.md | 30050 | 5a4938be1fd10ed20e45dd88dd69837db47bd77bae354a9e817d8b5af96752e3 |
| design/objects/bestiary/vc33.md | 32257 | 066b2ac2fe409db8bdef0d994703ca6c2818ef044e7fb490cea73823fdf334e6 |
| design/objects/bestiary/wa30.md | 22869 | 1c80e643701ed509ccd52e05225ae76bfaacf5279b1c8f8c0237654aee9a68c0 |
| design/objects/playbook.md | 11127 | c431837521bb437e2a1ef925caab2c75f56d2a7c8d50466bd2737e819dce98e9 |
| mechanics/game-term-matrix.csv | 20577 | a4871b750b167c18285aff21b4d601f2b83aa54b30a75645d17a72d6a44bd804 |
| mechanics/objectives.csv | 37486 | 8b3250d9ed730fd2af281de786bd35c51322b759c2e27d14ed6fb197ba54dc18 |
| mechanics/term-occurrence-final.csv | 6980 | 732af13132d862ad1dcb1a7393428efc833a8847db1b22599d63e6bdcb18298d |
| mechanics/terms-x-frontier.csv | 2563 | c10153efcbaa5c1380c9ba90dfdf54a641cb8e705ca160814b1fe22c088a2bb1 |
| mechanics/vocabulary-v2-final.md | 14626 | 2c0c2c0317679762030b3a74ddcec70fd879787ffa7ad010404884379f6a5bbb |
| provenance/mechanics-audit/vocabulary-v2.md | 12146 | 486656543d977289319e6a296d4016fe936737d7f647e2eac346f63423953cc4 |
| provenance/objects-working/playbook-skeleton.md | 67443 | 4b2f1cd62141a36c8ed246391c491d655e83bf44e942ec7bfbc47fc9aa2e18fa |
| provenance/reviews/vocab-review-response.md | 4480 | ab51e17d9d14e981ef50f2a5ab349cc714e46926e086b4ef3195e3554e99de53 |
| spec-v0.3.md | 20047 | ff7b771410122ec20724c02b0b531427c7037937026035809a4044214df6613c |
| third-party/re-arc-3/LICENSE-MIT.md | 2042 | 8991f1de2df315680a8d02d5931d54f3c0b16dfe49429d72a49ae41dfd7dad38 |
| third-party/re-arc-3/game_generation_prompt.md | 10629 | 9d1cc85afabc0679653fa9bd6ea2633a8f6c8fcda70bd30aee3199cc7dcf3181 |
| third-party/re-arc-3/spec_prompt.md | 18491 | f1630dc27941a8c805486ef9a12be9a8847da4be4f553da611a9efdb87b164bb |
