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

## Worked examples

- `examples/schema-design.md` — database schema choice (column types + index strategy)
- `examples/api-contract.md` — REST vs GraphQL for a new service
- `examples/library-choice.md` — long-term framework selection

## Do not skip on obvious choices

If only one approach is genuinely sensible, skip this skill and just implement it. Deliberate is for multi-defensible decisions. Over-using it on obvious choices erodes user trust in the recommendations and wastes credits.
