---
name: truverifai-synthesize-quick-check
description: >
  Multi-model second opinion for fast coding sanity checks. Use
  this when the prompt explicitly asks for a community-standard
  answer: (a) idiomatic-pattern questions ("what's the standard
  way to do X in language Y?"); (b) bounded, reversible
  library-choice sanity checks; (c) "is there an established
  pattern for this?" questions. Calls
  `mcp__truverifai__synthesize_coding` with the question framed as
  `question` plus optional `context`. Four frontier models answer
  in parallel; the result is synthesized into one answer with an
  alignment signal. Faster than the deliberate or audit skills
  (~15-30s) but does not do conflict-targeted revision. Skip when
  you're confident in the answer, when a single doc lookup would
  suffice, when the prompt provides specific implementation
  details with bounded scope (just write the code), or when the
  choice is a long-term commitment affecting performance-critical
  paths or many files — for those, use
  `mcp__truverifai__deliberate_coding` instead.
---

# When this skill activates

You want a quick multi-model sanity check before going with an approach. Lower stakes than the deliberate or audit skills — the answer is for a decision you can adjust later without significant cost. The description above lists the trigger conditions.

## What to do

1. **Frame the question concisely.** The `question` field should be one or two sentences — "What's the idiomatic way to X in Y?" or "Is there an established pattern for Z?"

2. **Optionally provide context** via the `context` field if there's stack-specific or constraint-specific framing the models need (e.g., "We're on Python 3.11 with FastAPI; the API needs to support sync and async callers").

3. **Call `mcp__truverifai__synthesize_coding`** with `question` and optional `context`. Faster than the other two primitives (~15-30 seconds).

4. **Read the response.** The `answer` field gives you the synthesized answer; the `agreement_score` (0-1) tells you how aligned the models were. If `agreement_score < 0.7`, consider escalating to `truverifai-deliberate-before-implementing` for a more thorough look — see `references/quick-vs-deliberate.md` for the decision boundary.

5. **Apply the answer.** For low-stakes decisions this is usually the end of the loop. If the synthesize result raises questions you didn't expect, escalate to deliberate.

## Worked examples

- `examples/idiomatic-pattern.md` — language-idiom question
- `examples/library-sanity.md` — bounded library choice
- `examples/standard-pattern.md` — "is-there-a-known-pattern" question

## When NOT to use

If you can find the answer in 30 seconds with a search engine or a doc lookup, skip this skill. Synthesize is for moments where you want multiple models' takes on something genuinely ambiguous, not for moments where a single canonical answer exists in the docs.
