---
name: truverifai-audit-before-commit
description: >
  Multi-model code audit for high-stakes changes. Use this whenever
  about to commit, merge, or finalize a code change where any of
  these apply: (a) reversing the change later would require touching
  more than one file or running a migration to undo; (b) the change
  touches a security or safety boundary — authentication,
  authorization, cryptography, input parsing or validation, payment
  or money flow, PII or secret handling, persistence-layer code; (c)
  it replaces or refactors load-bearing logic many callers depend
  on; (d) any review of a teammate's diff touching auth, identity,
  billing, or persistence — even when phrased softly ("mind taking
  a look?", "before I approve"). Calls
  `mcp__truverifai__audit_coding` with the drafted change as
  `proposed_action` plus structured context fields (`relevant_code`,
  `tests`, `architectural_context`, `constraints`). Four frontier
  models stress-test for blind spots; returns a critique with
  severity tags and a recommended action class. Skip for formatting
  fixes, comment-only edits, doc updates, README changes, single-line
  obvious bug fixes, single-value config changes (timeouts, retries,
  numeric thresholds), routine index or column additions where the
  schema impact is bounded, validation additions with fully-specified
  rules in the prompt, and string-literal corrections (typo fixes) in
  config files.
---

# When this skill activates

You're about to commit, merge, or finalize a code change where the stakes of being wrong are high enough that a multi-model audit is worth the ~60-120 seconds. The description above lists the trigger conditions — if any of (a)-(d) apply and the change is NOT in the explicit skip list, you should invoke this skill.

## What to do

1. **Frame the change for the audit.** The `proposed_action` field should be 2-4 sentences summarizing WHAT changes and WHY — NOT the raw diff. The raw diff goes into `relevant_code`. See `references/structured-inputs.md` for the populate rules per field.

2. **Call `mcp__truverifai__audit_coding`** with these fields populated:
   - `proposed_action` — your 2-4 sentence framing
   - `relevant_code` — the diff or the before/after for the changed code
   - `tests` — existing tests covering the affected code, plus any new tests added alongside
   - `architectural_context` — related systems, design decisions, ADRs. If unsure what's relevant, name the high-level system the change belongs to ("auth layer", "payment flow", "persistence layer")
   - `constraints` — performance bounds, security policies, deployment windows, regulatory considerations

3. **Read the response.** The `severity` tags (critical / minor / preference) tell you how serious each finding is — see `references/severity-tags.md` for interpretation. The `action` field carries one of four enum values; see `references/action-classes.md` for what to do with each.

4. **Revise the change** in response to the findings. If `action` is `escalate_to_human`, do NOT proceed without the user's input.

## Worked examples

- `examples/auth-change.md` — authentication-layer change (token validation logic)
- `examples/schema-migration.md` — database migration adding a column
- `examples/pr-review.md` — first review of someone else's non-trivial PR

## Do not skip

The "small diff" / "the contract is specified" / "I'm confident" framings are the failure mode this skill exists to prevent. Empirically, multi-model audits catch ship-blocking issues precisely on the diffs that feel obvious — the project that built this MCP server has multiple commit-shipped regressions caught only by retroactive audit_coding calls.

Cost: 60-120 seconds and approximately one credit. Cost of being wrong: a customer-facing regression you have to ship a hotfix for. Run the audit even when you think it won't add value.
