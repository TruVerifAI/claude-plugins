# Interpreting `dimensions_of_disagreement`

The deliberate response carries a `dimensions_of_disagreement` array. Each entry surfaces a specific axis where the four models diverged, with the dissenting model named explicitly and the disagreement summarized.

## The response shape

```json
"dimensions_of_disagreement": [
  {
    "model": "<which model dissented, e.g., 'gemini-3-flash'>",
    "model_stance": "<that model's position on this dimension>",
    "consensus_stance": "<what the other three converged on>",
    "disagreement": "<one-sentence summary of where they diverged>",
    "severity": "<low | medium | high>"
  }
]
```

The array may have 0, 1, or multiple entries:

- **Empty array** → all four models agreed. `agreement_score` will be high (>0.9 typically). Confidence in the conclusion is high.
- **1 entry, severity=low** → one model dissented on a minor point. Worth reading but not load-bearing.
- **1+ entries, severity=medium** → real trade-off the models disagreed on. Read and weigh.
- **Any entry, severity=high** → meaningful disagreement on a load-bearing dimension. This is the strongest "decision is not closed" signal; treat the question as still open and bring the user in.

## How to read a single entry

For each entry, ask:

1. **Which model dissented?** Different models have different strengths (Gemini on web-search-heavy questions, Claude on long-context reasoning, etc.). A dissent from a model that's strong in the relevant domain is more weighty.
2. **What's the dissent about?** Is it about a foundational assumption (high severity) or a stylistic preference (low severity)?
3. **Is the consensus_stance the right reference point?** Sometimes the three-vs-one split is actually a "the three are wrong; the one is right" situation. Read the dissent's reasoning, not just the count.

## The agreement_score signal

`agreement_score` is a scalar 0-1 that summarizes how aligned the models are.

| Score | Interpretation | Default response |
|---|---|---|
| ≥0.9 | High alignment. Conclusion is robust. | Adopt the conclusion. |
| 0.7-0.9 | Moderate alignment with some disagreement. | Read dimensions_of_disagreement; if dissents are low-severity, adopt; if medium-severity, weigh. |
| 0.4-0.7 | Real disagreement. Decision is genuinely contested. | Bring the user in. Surface the disagreement dimensions. |
| <0.4 | Models couldn't converge. | Treat as decided NOT YET. Either gather more context or punt to the user. |

Note: `action` enum already encodes this threshold logic. If `action` is `escalate_to_human`, that's the signal — you don't need to compute the threshold yourself. The thresholds above are for when you want to interpret beyond the binary.

## When a single dissent is signal vs. noise

**Signal:**

- The dissenter raised a specific concern the consensus didn't address ("Three models said REST; Gemini noted that two of our biggest partners already use GraphQL clients").
- The dissent is on a dimension you didn't think about in your `options_considered` (the deliberation surfaced a new axis).
- The dissenter explicitly disagreed on a foundational assumption ("Three models assumed we have a maintenance window; one questioned whether we actually do").

**Noise:**

- The dissent is stylistic without meaningful impact ("Three models prefer naming X; one prefers Y").
- The dissenter ignored the constraints (they argued for an option that your constraints already ruled out).
- The dissent is on a hypothetical edge case that doesn't apply to your situation.

## How to surface to the user

When `action` is `escalate_to_human` OR when you want the user's input on a `proceed_with_caveats` decision, surface the disagreement like this:

> "The deliberation came back with `agreement_score = 0.72`. Three models recommended REST; Gemini argued for GraphQL on the basis that [specific dissent reasoning]. Their proposed decision: REST with versioned paths. Do you want me to proceed with REST, or revisit the GraphQL option?"

Don't:

- Dump the entire response on the user. Summarize.
- Hide the disagreement to avoid burdening the user. The disagreement is exactly what they want to see.
- Take the consensus as final when there's a real dissent on a load-bearing dimension.

## When you should re-run

If you read the disagreement dimensions and realize:

- One of your `options_considered` was wrong / incomplete → fix it and re-run.
- A constraint you stated was incorrect → fix it and re-run.
- The dissent reveals a new option worth adding → add it and re-run.

Re-running a deliberation with corrected inputs is normal. The cost is one credit; the value is a decision based on the actual trade-off space.
