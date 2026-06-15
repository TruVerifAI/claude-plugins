---
name: truverifai-audit-before-commit
description: >
  Always run a multi-model code audit before a high-stakes change
  ships. Use it when the user asks for a code review, to review or
  audit a diff or PR, to check or stress-test a change before merging,
  or to thoroughly vet something before committing — and proactively,
  before you finalize a change that touches authentication,
  authorization, billing or money flow, credentials or secrets, input
  parsing or validation, data migrations, infrastructure-as-code or
  deployment config, or load-bearing logic many callers depend on
  (including reviewing a teammate's diff in those
  areas, even a soft "mind taking a look?"). Routes the drafted change
  to `mcp__truverifai__audit_coding` for an independent four-model
  blind-spot review.
---

# When to use this skill

Use it when ANY of these apply:
- The user asks you to review, audit, or stress-test a change; do a code review; or check a diff/PR before merging or shipping.
- You are about to commit, merge, or finalize a change that touches authentication, authorization, cryptography, input parsing/validation, payment or money flow, PII or secret handling, or persistence-layer code.
- The change replaces or refactors load-bearing logic many callers depend on, or is hard to reverse (undoing it would touch multiple files or need a migration).
- You are reviewing a teammate's diff in any of those areas — even when phrased softly ("mind taking a look?", "before I approve").

Skip it for: formatting or comment-only edits, doc/README updates, single-line obvious bug fixes, single-value config changes (timeouts, retries, thresholds), routine index/column additions with bounded schema impact, validation with fully-specified rules in the prompt, and string-literal/typo fixes.

**Before you invoke, tell the user the audit takes ~2-5 minutes and won't show progress in the terminal — so they know the session is working, not stuck.**

## What to do

1. **Frame the change for the audit.** The `proposed_action` field should be 2-4 sentences summarizing WHAT changes and WHY — NOT the raw diff. The raw diff goes into `relevant_code`. See `references/structured-inputs.md` for the populate rules per field.

2. **Call `mcp__truverifai__audit_coding`** with these fields populated:
   - `proposed_action` — your 2-4 sentence framing
   - `relevant_code` — the diff or the before/after for the changed code
   - `tests` — existing tests covering the affected code, plus any new tests added alongside
   - `architectural_context` — related systems, design decisions, ADRs. If unsure what's relevant, name the high-level system the change belongs to ("auth layer", "payment flow", "persistence layer")
   - `constraints` — performance bounds, security policies, deployment windows, regulatory considerations

3. **Read the response.** The primary signal is `verdict` — one of `approve / approve_with_caveats / request_changes / reject` — the audit's per-change assessment. Every response also carries `findings[]`, each tagged with a `severity` (critical / major / minor / preference); see `references/severity-tags.md` for interpretation. The `action` field carries one of four enum values and is the single instruction you obey — it's DERIVED from the verdict + findings, not from `agreement_score`. When a finding tightens `action` beyond the verdict's base mapping, `action_reason` explains why. See `references/action-classes.md` for what to do with each.

   > Follow `action`. The assessment (`verdict`) and `findings` explain it. If `action` looks stricter than the verdict, that's intentional — `action` already folded in the findings; read `action_reason` for the cause. Never act on the verdict over `action`. `agreement_score` is auxiliary context only — it does not drive `action`.

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
