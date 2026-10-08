"""What the public tree must never carry, encoded once (contract OS-2).

    nothing to run — a library for two maintainer tools

Two maintainer tools read this module and nothing in the pipeline does:

* `gen.tools.sync_canon` — the deterministic POST-COPY NEUTRALIZATION of the
  vendored canon (machine paths and personal names out, content otherwise
  byte-identical), so a re-sync from duckWM reproduces the public canon
  instead of resurrecting what was scrubbed.
* `gen.tools.export_public` — the `--verify` gate over an assembled public
  mirror: every class below must have ZERO hits there.

A RULE ABOUT THIS FILE'S OWN TEXT. It ships in the mirror, and the gate it
defines sweeps the mirror — this file included. So no pattern here is written
as the literal it hunts. Personal names are held only as sha256 digests of
their lowercase spelling (a name is matched by hashing the candidate word, so
the name itself never appears in the tree); the path, link and account
patterns are spelled with a one-character class (`User[s]`, `privat[e]`) so
the regex SOURCE cannot match itself. The secret patterns need no such care:
their sources are regex syntax, not key-shaped strings. A test that plants a
violation to prove the gate has teeth builds the planted string at runtime for
the same reason.

stdlib only: the export tool that imports this must run on a bare python.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator
from dataclasses import dataclass

# --- personal names -----------------------------------------------------------

# (length, sha256 of the lowercase spelling) for each personal name the public
# tree must not carry: the operator's given name and family name, and one
# collaborator's given name — the three names the opensource audit's PII sweep
# found (OPENSOURCE-AUDIT §3). Matching is by WORD PREFIX, exactly like the
# audit's `\b(name)` sweep: a letter run (or a camelCase part of one) whose
# first `length` letters hash to a digest is a hit. That catches the possessive,
# the hyphenated and the run-together spellings, while a word that merely
# CONTAINS a name after its first letter (the audit's "vanish" case) is not.
PERSON_NAME_DIGESTS: tuple[tuple[int, str], ...] = (
    (5, "03fa5e7090f6cc48b78927499cfced2256b766c3b6131d75dd10a1675688e4c4"),
    (7, "9cca8134199d25ca7bac4a663ed605b0999a70697a8b5dfb6caca097fa496f5e"),
    (8, "28182f0a278161989f90f090dabd6cab331663d8509ddbae617bb1e77ff81595"),
)

_LETTER_RUN_RE = re.compile(r"[A-Za-z]+")
_CAMEL_PART_RE = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])")


def _digest(word: str) -> str:
    return hashlib.sha256(word.lower().encode("ascii")).hexdigest()


def is_person_name(word: str) -> bool:
    """True when `word` IS one of the names (whole word, any letter case)."""
    return any(len(word) == size and _digest(word) == digest
               for size, digest in PERSON_NAME_DIGESTS)


def _starts_with_person_name(word: str) -> bool:
    return any(len(word) >= size and _digest(word[:size]) == digest
               for size, digest in PERSON_NAME_DIGESTS)


def _candidates(run: str) -> Iterator[str]:
    yield run
    parts = _CAMEL_PART_RE.findall(run)
    if len(parts) > 1:
        yield from parts


def person_name_spans(text: str) -> list[tuple[int, int]]:
    """(start, end) of every letter run that starts with a personal name.

    A camelCase run is also checked part by part, so a run-together handle
    (given name + family name) is caught on either half.
    """
    spans = []
    for match in _LETTER_RUN_RE.finditer(text):
        if any(_starts_with_person_name(part) for part in _candidates(match.group(0))):
            spans.append(match.span())
    return spans


def has_person_name(text: str) -> bool:
    """Cheap whole-text test: hashes each DISTINCT letter run once."""
    words = set(_LETTER_RUN_RE.findall(text))
    return any(_starts_with_person_name(part) for word in words for part in _candidates(word))


# --- machine paths, private links, account ids ---------------------------------

# The gate's classes 3 and 4 (contract OS-2 §E). Each pattern is (label, regex).
MACHINE_PATH_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("absolute home-directory path", re.compile(r"/User[s]/")),
    ("user cache path", re.compile(r"~/\.cache")),
    ("macOS private temp path", re.compile(r"/privat[e]/tmp")),
)

PRIVATE_LINK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private artifact link", re.compile(r"claude\.ai/artifac[t]")),
)

# A home-directory path as the canon writes them (the macOS and the Linux home
# roots, then one user segment), used by the canon neutralization.
HOME_DIR_RE = re.compile(r"/(?:User[s]|hom[e])/[^/\s`'\"<>()]+/")


# --- secrets -----------------------------------------------------------------

# The gate's class 1: the key-shape family the opensource audit swept the tree
# and its full history with (OPENSOURCE-AUDIT §9). Shapes only — a real key of
# one of these families matches; prose about keys does not.
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("sk- style API key", re.compile(r"\bsk-[A-Za-z0-9][A-Za-z0-9_-]{15,}")),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("AWS access key id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}")),
    ("JSON web token", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("credential assignment", re.compile(
        r"\b[A-Z][A-Z0-9_]*(?:API_KEY|SECRET_KEY|ACCESS_TOKEN|AUTH_TOKEN)\b\s*[=:]\s*"
        r"['\"]?(?P<value>(?!\$|<|\{)[A-Za-z0-9_./+=-]{16,})")),
)

# The two self-labelled FAKE keys the test suite feeds its own redaction and
# presence checks (OPENSOURCE-AUDIT §2: "only self-labeled fakes, ever"). They
# are key-SHAPED on purpose — that is what makes them good fixtures — so they
# are exempted here by EXACT value (the matched key, or the value half of a
# matched assignment), and nothing else is. Their spelling below is the one
# place this file carries key-shaped text; the exemption covers it.
ALLOWED_FAKE_SECRETS: frozenset[str] = frozenset({
    "sk-or-v1-FAKE-KEY-DO-NOT-USE-0000000000000000",
    "sk-fixture-presence-only",
})


@dataclass(frozen=True)
class Hit:
    """One gate finding, printed as `path:line: [class] detail`."""

    path: str
    line: int
    gate: str
    detail: str

    def render(self) -> str:
        return f"{self.path}:{self.line}: [{self.gate}] {self.detail}"


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _clip(text: str, start: int, end: int) -> str:
    return text[start:end][:60]


# A cheap substring that must be present before a pattern can match at all —
# the mirror is ~150 MB, mostly digits, so most regexes never need to run. No
# needle is itself a hit (none completes the literal its pattern hunts).
_NEEDLES: dict[str, tuple[str, ...]] = {
    "sk- style API key": ("sk-",),
    "GitHub token": ("gh", "github_pat_"),
    "Slack token": ("xox",),
    "AWS access key id": ("AKIA", "ASIA"),
    "Google API key": ("AIza",),
    "JSON web token": ("eyJ",),
    "private key block": ("PRIVATE KEY",),
    "credential assignment": ("API_KEY", "SECRET_KEY", "ACCESS_TOKEN", "AUTH_TOKEN"),
    "absolute home-directory path": ("/User",),
    "user cache path": (".cache",),
    "macOS private temp path": ("/privat",),
    "private artifact link": ("claude.ai",),
}


def _may_match(label: str, text: str) -> bool:
    return any(needle in text for needle in _NEEDLES.get(label, ("",)))


def scan_text(path: str, text: str) -> list[Hit]:
    """Every gate hit in one file's text (classes 1-4), in file order."""
    hits: list[Hit] = []
    for label, pattern in SECRET_PATTERNS:
        if not _may_match(label, text):
            continue
        for match in pattern.finditer(text):
            value = match.groupdict().get("value") or match.group(0)
            if value in ALLOWED_FAKE_SECRETS:
                continue
            hits.append(Hit(path, _line_of(text, match.start()), "secret",
                            f"{label}: {value[:12]}…"))
    if has_person_name(text):
        for start, end in person_name_spans(text):
            hits.append(Hit(path, _line_of(text, start), "name",
                            f"personal name in {_clip(text, start, end)!r}"))
    for gate, table in (("path", MACHINE_PATH_PATTERNS), ("link", PRIVATE_LINK_PATTERNS)):
        for label, pattern in table:
            if not _may_match(label, text):
                continue
            for match in pattern.finditer(text):
                hits.append(Hit(path, _line_of(text, match.start()), gate, label))
    hits.sort(key=lambda hit: (hit.line, hit.gate))
    return hits
