---
name: truverifai-deliberate-before-implementing
description: >
  Multi-model deliberation for design decisions with multiple
  defensible answers. Use this whenever about to commit to a design
  choice involving any of: schema or table design; API contract
  shape (REST vs GraphQL, field naming, versioning); module or
  service boundary placement; state-management architecture;
  library or framework selection with long-term commitment;
  caching strategy; concurrency model; migration or refactoring
  strategy for load-bearing code. Calls
  `mcp__truverifai__deliberate_coding` with `question` plus
  structured context (`relevant_code`, `architectural_context`,
  `options_considered`, `constraints`). Four frontier models reason
  independently; conflicts are routed back as targeted points each
  model must defend or revise. Returns a reasoned conclusion,
  agreement signal, dimensions of disagreement, and recommended
  action class. Skip for choices with one sensible answer, refactors
  where any reasonable approach works, or minor SDK version bumps
  and library updates documented as drop-in or backward-compatible
  by the vendor.
---

# When this skill activates

You're about to commit to a design choice where multiple approaches are defensible and reversing later requires touching more than one file. The description above lists the trigger conditions — if any of (a)-(h) apply and the decision is NOT obvious, you should invoke this skill.

**Before you invoke, tell the user the deliberation takes ~2-5 minutes and won't show progress in the terminal — so they know the session is working, not stuck.**

## What to do

1. **Frame the question.** The `question` field should state the decision clearly: "Should we use X or Y for Z?" or "How should we shape the API for W?" See `references/when-to-deliberate.md` for what counts as a deliberate-worthy decision vs. an obvious choice.

2. **Call `mcp__truverifai__deliberate_coding`** with these fields populated:
   - `question` — the decision statement
   - `relevant_code` — code being affected, schema definitions, API samples, current implementations
   - `architectural_context` — related systems, ADRs, design docs, constraints from upstream/downstream dependencies
   - `options_considered` — approaches you've thought about, with their trade-offs. See `references/options-considered-field.md` for how to populate this to maximize signal — half-articulated options waste the deliberation
   - `constraints` — performance requirements, scalability concerns, team-skills considerations, regulatory considerations

3. **Read the response.** The `agreement_score` (0-1) tells you how aligned the models are. `dimensions_of_disagreement` surfaces the specific axes where they diverged — see `references/dimensions-of-disagreement.md` for how to interpret. The `action` enum tells you what to do next.

4. **Use the synthesized conclusion to make your decision.** If `agreement_score < 0.7` AND severity tags on the dimensions are critical, treat the decision as still open and either gather more context or escalate to the user.

## After acting on the response

Once you've committed to a design choice — whether you went with the deliberation's recommendation, picked a different option, or escalated — call `mcp__truverifai__record_outcome` to report the outcome:

- **call_id** — the `request_id` from the deliberate response: the top-level `post_action.call_id` field in the response body (or equivalently `usage.request_id`). It's in the body, not `_meta` — clients like Claude Code don't surface tool-result `_meta` to the agent.
- **useful** — `true` if the deliberation informed your decision in any way (caught something, confirmed an approach, surfaced a tradeoff you hadn't considered). `false` only if it was noise or duplicated what you already knew.
- **changed_decision** — `true` if your action AFTER reading the deliberation differs from what you were about to do BEFORE the call. `false` if you proceeded with your original approach (even when the call was useful as confirmation).
- **impact** — your read of decision blast radius: `high` (hard to reverse / safety boundary / load-bearing), `medium` (recoverable with effort), `low` (trivially reversible).
- **category** — kind of decision: `security`, `billing_credits`, `data_modeling`, `api_contract`, `architecture`, `performance`, `dependency`, `refactor`, `error_handling`, `testing`, `deployment_ops`, or `other`.
- **notes** — required when `useful=false` OR `changed_decision=false` OR `category='other'`. 1-2 sentences on the specific reason. **Do NOT include confidential or code-specific details** — no file paths, function names, secrets, or proprietary identifiers. Describe the decision in general terms only.

This is a free call (no credits charged). The user sees the aggregate on their TruVerifAI dashboard; outcome reporting is how they evaluate whether the tool is worth keeping.

## Worked examples

- `examples/schema-design.md` — database schema choice (column types + index strategy)
- `examples/api-contract.md` — REST vs GraphQL for a new service
- `examples/library-choice.md` — long-term framework selection

## Do not skip on obvious choices

If only one approach is genuinely sensible, skip this skill and just implement it. Deliberate is for multi-defensible decisions. Over-using it on obvious choices erodes user trust in the recommendations and wastes credits.
