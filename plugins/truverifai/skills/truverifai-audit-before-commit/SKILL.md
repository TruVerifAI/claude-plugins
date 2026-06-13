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

## After acting on the response

Once you've decided what to do with the audit's findings — whether you accepted them, revised your plan, or kept your original approach — call `mcp__truverifai__record_outcome` to report the outcome:

- **call_id** — the `request_id` from the audit response: the top-level `post_action.call_id` field in the response body (or equivalently `usage.request_id`). It's in the body, not `_meta` — clients like Claude Code don't surface tool-result `_meta` to the agent.
- **useful** — `true` if the audit caught something, confirmed something, or surfaced a tradeoff you hadn't considered. `false` only if it was noise or duplicated what you already knew.
- **changed_decision** — `true` if your action AFTER reading the audit differs from what you were about to do BEFORE the call. `false` if you proceeded as originally planned (even when the audit was useful as confirmation).
- **impact** — your read of decision blast radius: `high` (hard to reverse / safety boundary / load-bearing), `medium` (recoverable with effort), `low` (trivially reversible).
- **category** — kind of decision being audited: `security`, `billing_credits`, `data_modeling`, `api_contract`, `architecture`, `performance`, `dependency`, `refactor`, `error_handling`, `testing`, `deployment_ops`, or `other`.
- **notes** — required when `useful=false` OR `changed_decision=false` OR `category='other'`. 1-2 sentences on the specific reason. **Do NOT include confidential or code-specific details** — no file paths, function names, secrets, or proprietary identifiers. Describe the decision in general terms only.

This is a free call (no credits charged). The user sees the aggregate on their TruVerifAI dashboard; outcome reporting is how they evaluate whether the tool is worth keeping.

## Worked examples

- `examples/auth-change.md` — authentication-layer change (token validation logic)
- `examples/schema-migration.md` — database migration adding a column
- `examples/pr-review.md` — first review of someone else's non-trivial PR

## Do not skip

The "small diff" / "the contract is specified" / "I'm confident" framings are the failure mode this skill exists to prevent. Empirically, multi-model audits catch ship-blocking issues precisely on the diffs that feel obvious — the project that built this MCP server has multiple commit-shipped regressions caught only by retroactive audit_coding calls.

Cost: 60-120 seconds and approximately one credit. Cost of being wrong: a customer-facing regression you have to ship a hotfix for. Run the audit even when you think it won't add value.
