---
name: skip-gate-when-not-needed
description: >
  Release a TruVerifAI proactive review gate WITHOUT running the review,
  but only when the review is genuinely unnecessary. Use it when a gate
  blocked your git commit (audit gate) or your Write/Edit (deliberate or
  synthesize gate) and you judge it a false positive, an already-reviewed
  change, a trivial/generated/test-or-docs change, or a true time-critical
  hotfix. Calls the TruVerifAI record_gate_skip tool with a structured
  reason_code (+ free-form text for judgment calls) to log the skip and let
  the change proceed on retry. Free — no credits. DEFAULT to actually running
  the suggested review; skipping is the exception, and every skip is logged.
---

# When to use this skill

Use it when ALL of these apply:
- A TruVerifAI review gate just **blocked** your action (a `git commit`, or a
  `Write`/`Edit`/`MultiEdit`) with a message naming `audit_coding`,
  `deliberate_coding`, or `synthesize_coding` and offering a skip.
- You have **genuinely** judged that running that review is unnecessary for this
  specific change (see "Legitimate reasons" below).
- You are NOT skipping merely to move faster, avoid latency, or because you're
  confident. Confidence is not a reason — that's exactly when a second opinion
  pays off.

If in doubt, **run the suggested review instead.** The gate fired because a local
classifier flagged the change; the classifier is tuned for high recall, so some
false positives are expected — but the cost of a wrong skip on a real risk is
much higher than ~15s–5min of review.

## What to do

1. **Read the gate message.** It prints, ready to copy verbatim:
   - `gate_repo` — always.
   - The **release key** the skip needs — the gate computes and prints it for you, so
     you never reconstruct it:
     - audit / commit gate → a `hunk_hashes = [...]` list.
     - deliberate / synthesize write gate → an `area = "..."` directory path.
   - `gate_session_id` (when the write gate provides one) and a `gate_signal` line
     (`classifier_version` / `score` / `risk_categories`).

2. **Call `record_gate_skip`** (it may appear as `mcp__truverifai__record_gate_skip` depending on your client) with:
   - `gate_repo` — copied from the gate message.
   - `reason_code` — the closest fit from the enum (see `references/reason-codes.md`):
     `false_positive_not_risky`, `trivial_change`, `already_reviewed_this_session`,
     `reviewed_outside_truverifai`, `generated_or_vendored_code`, `test_or_docs_only`,
     `time_critical_hotfix`, `disagree_with_classification`, `tool_unavailable`,
     `other`.
   - `reason_text` — REQUIRED for `other` and `disagree_with_classification`; a
     1-sentence reason. General terms only — no secrets, file paths, or proprietary
     identifiers (same privacy rule as `record_outcome`).
   - `hunk_hashes` (audit/commit gate) **OR** `area` (deliberate/synthesize write
     gate) — **copy the value the gate printed**, verbatim; do NOT re-derive it. Plus
     `session_id` if the gate gave one, and the `gate_signal` fields if you have them.

3. **Retry the original action.** The gate recomputes the same key in-process, sees
   your logged skip covering it, and releases.

## Legitimate reasons to skip (and the matching code)

- It's a **false positive** — the flagged change isn't actually risky → `false_positive_not_risky`.
- You **already reviewed** this exact change this session (ran audit/deliberate) → `already_reviewed_this_session`.
- It was reviewed **outside** TruVerifAI (human review, another tool) → `reviewed_outside_truverifai`.
- It's **generated or vendored** code, not hand-written risk → `generated_or_vendored_code`.
- It's **test or docs** only → `test_or_docs_only`.
- It's a genuine **time-critical hotfix** and you accept the risk → `time_critical_hotfix`.
- The classifier mis-categorized it and you disagree → `disagree_with_classification` (explain).
- The review tool is **down/unavailable** → `tool_unavailable`.

## When NOT to use

- The change really does touch auth/billing/migrations/secrets/load-bearing logic
  and hasn't been reviewed → **run `audit_coding` / `deliberate_coding` instead.**
- You're skipping to save time or because you feel confident → not a valid reason.
- No gate fired → there's nothing to release.

## Why this matters

The skip is **logged with its reason** (free, no credits). Two things ride on it:
the user sees how often the gate is skipped and why (a high `false_positive_not_risky`
rate tells them the classifier is over-firing), and the free-form reasons train the
classifier to fire more precisely over time. An honest skip-with-reason is useful
signal; a reflexive skip to dodge review defeats the gate and pollutes that signal.
