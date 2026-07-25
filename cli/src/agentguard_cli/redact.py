"""Redaction of captured agent output, applied before anything is written to disk.

Why this module exists
----------------------
A gate that snapshots agent behaviour has to persist what the agent said, and it tells the
user to commit that file. If the agent's job is answering questions about people — students,
patients, customers — then its output *is* the user record, and the tool has just written
personal data into the repository and shared it with everyone who has read access.

Detecting sensitive content is not the same as not storing it. A tool can ship a PII check
that fails a test for leaking an email address and, in the same run, write that address
verbatim into the baseline file. That asymmetry is the defect this module closes; see
docs/g3-reproducer.md for the case that motivated it.

Design rules
------------
  * **Redact at capture, not at write.** The scrubbed value replaces the raw one before it
    is stored on the ProofObject, so every downstream writer — JSON report, SARIF, HTML —
    is safe by construction. A redactor bolted onto one writer is a redactor someone
    forgets to bolt onto the next one.

  * **Detection still sees the raw text.** Checks are evaluated *before* redaction. Masking
    first would hide the very leak a check is meant to catch — the same asymmetry as above,
    just inverted.

  * **Constant tokens, not pseudonyms.** A category token (`[REDACTED:email]`) is stable
    across runs, so a baseline diff stays readable and no key has to be managed. The cost
    is referential integrity: two different emails collapse to the same token, so a
    snapshot cannot tell you *which* user appeared. That is a deliberate trade — a
    reversible pseudonym is still personal data.

  * **No model, no new dependency.** Detection is regex plus checksums. That bounds what
    this can find: see ``LIMITATIONS``. Names, addresses and free-text identifiers need NER
    and are NOT detected. The report states this so nobody reads "redacted" as "safe".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from agentguard_core.fingerprint import SECRET_PATTERNS

# Bump when the pattern set or token format changes: two runs are only comparable if they
# were redacted by the same rules, so this is folded into the evidence digest.
REDACTION_POLICY_VERSION = "1"

# Stated in every report that carries redacted content. Redaction narrows exposure; it does
# not certify that the artifact is free of personal data.
LIMITATIONS = (
    "Pattern-based redaction only (regex + checksums, no NER). Personal names, postal "
    "addresses, free-text identifiers and domain-specific record formats are NOT detected "
    "and may remain in this artifact. Absence of redaction markers is not evidence that no "
    "sensitive data is present."
)

_MASK_FORMAT = "[REDACTED:{category}]"


def _slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")


def _luhn_ok(digits: str) -> bool:
    """Checksum used by payment cards. Without it, any 13-19 digit run — order numbers,
    timestamps, request ids — gets masked, which buries real diffs in redaction noise."""
    total, parity = 0, len(digits) % 2
    for i, ch in enumerate(digits):
        d = int(ch)
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _card_is_valid(match: re.Match[str]) -> bool:
    digits = re.sub(r"[^0-9]", "", match.group(0))
    return 13 <= len(digits) <= 19 and _luhn_ok(digits)


# Ordered: the most specific pattern must consume its text before a looser one can claim
# part of it. Credentials run first (they embed characters the contact patterns also match),
# card numbers before phone numbers (both are digit runs with separators).
_PII_PATTERNS: tuple[tuple[str, re.Pattern[str], Any], ...] = (
    (
        "email",
        re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
        None,
    ),
    (
        "iban",
        re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}[ ]?[A-Z0-9]{1,4}\b"),
        None,
    ),
    (
        "credit-card",
        re.compile(r"\b(?:\d[ \-]?){12,18}\d\b"),
        _card_is_valid,
    ),
    (
        # Excludes the ranges the SSA never issues, which are the ones test fixtures use.
        "us-ssn",
        re.compile(r"\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b"),
        None,
    ),
    (
        "ipv4",
        re.compile(
            r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b"
        ),
        None,
    ),
    (
        # Requires either an international prefix or separators: a bare 10-digit run is far
        # more often an id than a phone number, and masking ids makes every diff noisy.
        "phone",
        re.compile(r"(?:\+\d{1,3}[ \-.]?)?(?:\(\d{3}\)|\d{3})[ \-.]\d{3}[ \-.]\d{4}\b"),
        None,
    ),
)

_CREDENTIAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (_slug(label), pattern) for label, pattern in SECRET_PATTERNS
)

CATEGORIES: tuple[str, ...] = tuple(
    [slug for slug, _ in _CREDENTIAL_PATTERNS] + [name for name, _, _ in _PII_PATTERNS]
)


@dataclass
class Redactor:
    """Scrubs values on their way into a persisted artifact, counting what it removed.

    Counts are per category, never per value: reporting the matched text would copy the
    secret into the very artifact this exists to keep it out of.
    """

    enabled: bool = True
    counts: dict[str, int] = field(default_factory=dict)

    def text(self, value: str) -> str:
        if not self.enabled or not value:
            return value
        out = value
        for slug, pattern in _CREDENTIAL_PATTERNS:
            out = self._apply(out, slug, pattern, None)
        for name, pattern, validator in _PII_PATTERNS:
            out = self._apply(out, name, pattern, validator)
        return out

    def _apply(self, value: str, category: str, pattern: re.Pattern[str], validator: Any) -> str:
        hits = 0

        def repl(match: re.Match[str]) -> str:
            nonlocal hits
            if validator is not None and not validator(match):
                return match.group(0)
            hits += 1
            return _MASK_FORMAT.format(category=category)

        out = pattern.sub(repl, value)
        if hits:
            self.counts[category] = self.counts.get(category, 0) + hits
        return out

    def value(self, value: Any) -> Any:
        """Redact recursively through the JSON shapes a proof object carries.

        Dict keys are redacted too: a tool argument named after the user's email address is
        as much of a leak as one valued with it.
        """
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, dict):
            return {self.value(k): self.value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.value(v) for v in value]
        if isinstance(value, tuple):
            return tuple(self.value(v) for v in value)
        return value

    @property
    def redacted_anything(self) -> bool:
        return bool(self.counts)

    def to_dict(self) -> dict[str, Any]:
        """The `redaction` block of the evidence artifact.

        `applied: false` is recorded just as loudly as `true`. A reader who cannot tell
        whether a baseline was scrubbed has to assume it was not.
        """
        return {
            "applied": self.enabled,
            "policy_version": REDACTION_POLICY_VERSION if self.enabled else None,
            "categories_redacted": dict(sorted(self.counts.items())),
            "total_redactions": sum(self.counts.values()),
            "limitations": LIMITATIONS if self.enabled else "Redaction disabled (--no-redact).",
        }
