# Redaction of captured agent output

AgentGuard's local scan writes an evidence artifact that teams are meant to commit. If the
agent under test answers questions about people, its output *is* the user record — so the
artifact would carry personal data into the repository and share it with everyone who has
read access.

Redaction is **on by default** for that reason. `--no-redact` opts out.

## The failure mode this closes

Detecting sensitive content and not storing it are different things. A tool can ship a PII
check that fails a test for leaking an email address and, in the same run, write that
address verbatim into the baseline file. That asymmetry is a real defect, reproduced
against another tool in [g3-reproducer.md](g3-reproducer.md); it is the one gap the
[competitive teardown](competitive-teardown.md) found unfilled across the category.

## Where redaction happens

At **capture**, not at write. The scrubbed value replaces the raw one before it is stored
on the Proof Object, so every writer — JSON report, SARIF, HTML — is safe by construction,
including writers that do not exist yet. A redactor attached to one writer is a redactor
someone forgets to attach to the next one.

Detection still runs on the **raw** text. Checks are evaluated before redaction, because
masking first would hide the very leak a check exists to catch — the same asymmetry,
inverted.

```
capture ──► evaluate checks (raw) ──► redact ──► Proof Object ──► digest ──► all writers
```

## What is detected

| Category | Method |
|---|---|
| Credentials — OpenAI, Anthropic, AWS, GitHub, Google, Slack, AgentGuard keys, private key blocks | shared pattern set with the manifest secret scanner |
| `email` | regex |
| `credit-card` | regex + Luhn checksum |
| `us-ssn` | regex, excluding never-issued ranges |
| `iban`, `phone`, `ipv4` | regex |

Digit runs that fail Luhn — order numbers, request ids, timestamps — are deliberately left
alone. Masking every long number would bury real behaviour changes in redaction noise.

## What is NOT detected

Pattern matching cannot find **personal names, postal addresses, free-text identifiers, or
domain-specific record formats**. There is no NER model and no new dependency. Every report
states this in `redaction.limitations`.

**Absence of redaction markers is not evidence that no sensitive data is present.**

## Tokens, not pseudonyms

Matches are replaced with a constant category token, `[REDACTED:email]`. This keeps a
baseline diff stable across runs and requires no key management. The cost is referential
integrity: two different emails collapse to the same token, so the artifact cannot tell you
*which* user appeared. That trade is deliberate — a reversible pseudonym is still personal
data.

## What the artifact records

```json
"redaction": {
  "applied": true,
  "policy_version": "1",
  "categories_redacted": { "credit-card": 1, "email": 2, "ipv4": 1, "us-ssn": 1 },
  "total_redactions": 5,
  "limitations": "Pattern-based redaction only (regex + checksums, no NER). ..."
}
```

The block is present even when nothing matched, and `applied: false` is recorded just as
loudly as `true`. A reader who cannot tell a scrubbed report from an unscrubbed one has to
assume the worst.

`policy_version` is folded into `evidence_digest`, so two runs scrubbed by different rule
sets never collide and read as identical evidence. The digest covers the **redacted**
values, which keeps it recomputable by a reader holding only the published artifact.

## Current scope

The redactor is wired at the capture boundary and covers manifest-derived detail in the
static path today. The captured-output path it primarily protects is exercised through the
library API (`do_local_scan(..., mode="live", observed_outputs=...)`) and its tests; the CLI
does not yet ship a local live-model runner, so `scan --local` is static-only. When that
runner lands, redaction is already in front of it.
