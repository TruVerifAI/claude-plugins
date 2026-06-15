---
name: truverifai-synthesize-quick-check
description: >
  Run a fast multi-model second opinion for a quick coding sanity
  check. Use it when the user asks for a quick second opinion, a sanity
  check, what the standard or idiomatic way to do something is, or
  whether there's an established pattern — and when you're about to pick
  an idiomatic pattern or a bounded, reversible library choice and want
  a fast cross-model check before proceeding. Routes the question to
  `mcp__truverifai__synthesize_coding` for a fast four-model second
  opinion. For hard-to-reverse, multi-file decisions use the deliberate
  skill instead.
---

# When to use this skill

Use it when ANY of these apply:
- The user asks for a quick second opinion, a sanity check, what the standard/idiomatic way to do something is, or whether there's an established pattern.
- You are about to pick an idiomatic pattern or make a bounded, reversible library choice and want a fast cross-model check first.

Lower stakes than the deliberate or audit skills — the answer is for a decision you can adjust later. Skip when you're already confident, when a single doc lookup would settle it, or when the prompt already gives bounded implementation details (just write the code). For long-term, multi-file, or performance-critical commitments use `truverifai-deliberate-before-implementing` instead.

## What to do

1. **Frame the question concisely.** The `question` field should be one or two sentences — "What's the idiomatic way to X in Y?" or "Is there an established pattern for Z?"

2. **Optionally provide context** via the `context` field if there's stack-specific or constraint-specific framing the models need (e.g., "We're on Python 3.11 with FastAPI; the API needs to support sync and async callers").

3. **Call `mcp__truverifai__synthesize_coding`** with `question` and optional `context`. Faster than the other two primitives (~15-30 seconds).

4. **Read the response.** Read `answer_status` first — it's the synthesized verdict (`settled` / `qualified` / `contested` / `unresolved`). The `answer` field carries the synthesized answer itself; `findings[]` lists the caveats and gaps, each tagged `critical` / `major` / `minor` / `preference`. `action` is also emitted but is **advisory** — synthesize never gates anything. `agreement_score` (0-1) is auxiliary convergence context: it does NOT drive the verdict, but it's a useful secondary hint for whether to escalate. The real escalate signal is an `answer_status` of `contested` or `unresolved`; an `agreement_score < 0.7` is a corroborating cue. When either fires, consider escalating to `truverifai-deliberate-before-implementing` for a more thorough look — see `references/quick-vs-deliberate.md` for the decision boundary.

5. **Apply the answer.** For low-stakes decisions this is usually the end of the loop. If the synthesize result raises questions you didn't expect, escalate to deliberate.

## After acting on the response

Once you've used (or rejected) the synthesized answer, call `mcp__truverifai__record_outcome` to report the outcome:

- **call_id** — the `request_id` from the synthesize response: the top-level `post_action.call_id` field in the response body (or equivalently `usage.request_id`). It's in the body, not `_meta` — clients like Claude Code don't surface tool-result `_meta` to the agent.
- **useful** — `true` if the answer informed your decision in any way (confirmed your approach, surfaced an alternative, caught an edge case). `false` only if it was noise or duplicated what you already knew.
- **changed_decision** — `true` if your action AFTER reading the answer differs from what you were about to do BEFORE the call. `false` if you proceeded as originally planned. Synthesize is the fast-confirmation path, so `changed_decision=false` is common and informative — it means the existing approach was right.
- **impact** — your read of decision blast radius: `high` (hard to reverse / safety boundary / load-bearing — though if it were truly high-impact you should have used `deliberate` instead), `medium` (recoverable with effort), `low` (trivially reversible). Most synthesize calls are `low`.
- **category** — kind of decision: `security`, `billing_credits`, `data_modeling`, `api_contract`, `architecture`, `performance`, `dependency`, `refactor`, `error_handling`, `testing`, `deployment_ops`, or `other`.
- **notes** — required when `useful=false` OR `changed_decision=false` OR `category='other'`. 1-2 sentences on the specific reason. **Do NOT include confidential or code-specific details** — no file paths, function names, secrets, or proprietary identifiers. Describe the decision in general terms only.

This is a free call (no credits charged). The user sees the aggregate on their TruVerifAI dashboard; outcome reporting is how they evaluate whether the tool is worth keeping.

## Worked examples

- `examples/idiomatic-pattern.md` — language-idiom question
- `examples/library-sanity.md` — bounded library choice
- `examples/standard-pattern.md` — "is-there-a-known-pattern" question

## When NOT to use

If you can find the answer in 30 seconds with a search engine or a doc lookup, skip this skill. Synthesize is for moments where you want multiple models' takes on something genuinely ambiguous, not for moments where a single canonical answer exists in the docs.
