# `record_gate_skip` reason codes

Pick the closest single fit. `reason_text` is required for `other` and
`disagree_with_classification` — **and for the judgment codes (`false_positive_not_risky`,
`trivial_change`, `reviewed_outside_truverifai`, `time_critical_hotfix`) at the
`deliberate` and `audit` gates** (the synthesize gate is exempt). It's welcome on any code.
All skips are logged.

| reason_code | Use when | reason_text |
|---|---|---|
| `false_positive_not_risky` | The gate flagged it, but the change genuinely isn't risky (the classifier over-fired). | required at deliberate/audit |
| `trivial_change` | A cosmetic / no-op / rename-only change with no risk surface. | required at deliberate/audit |
| `reviewed_outside_truverifai` | A human or another tool already reviewed it. | required at deliberate/audit |
| `generated_or_vendored_code` | Generated / vendored / lockfile content, not hand-written risk. | optional |
| `test_or_docs_only` | The change is confined to tests or documentation. | optional |
| `time_critical_hotfix` | A genuine production hotfix where you accept the unreviewed risk. | required at deliberate/audit |
| `disagree_with_classification` | The classifier mis-categorized the change and you disagree with the flag. | **required** |
| `tool_unavailable` | The review tool errored / is down and you can't run it. | optional |
| `other` | None of the above. | **required** |

## Floor classes — a judgment skip is **denied**; run a real check

For a change touching a **floor class — auth / secrets / money / migration / removed-guard**,
the judgment and external-trust codes (`false_positive_not_risky`, `trivial_change`,
`disagree_with_classification`, `reviewed_outside_truverifai`, `time_critical_hotfix`,
`tool_unavailable`, `other`) are **denied** — those classes "need a real check, not a judgment
call." Only the **path-verified** codes (`test_or_docs_only`, `generated_or_vendored_code`) can
release a floor change, and only when the server confirms the path class from fire-time evidence.

To release a floor change you have three real options (the gate's deny message spells them out).
**This is identical at the commit gate and the write gate** — a `Write`/`Edit` is finished code, so
`audit_coding` is its natural review, and a `SYNTH_CONFIRM` releases either gate. Always also pass
the `gate_context_id` the gate printed (binds coverage to the gate's own hunks):

1. **Already decided (the usual case) →** run `audit_coding` with your `proposed_action` +
   `gate_repo`/`gate_diff`/`gate_context_id`; a PASS releases it.
2. **Genuine low-risk false positive →** run `synthesize_coding` with `gate_repo` + `gate_diff` +
   `gate_context_id` (the diff you're committing or writing). If the panel agrees it's low-risk it
   mints a **SYNTH_CONFIRM** that releases the gate — cheap (~15–30s), no full audit.
3. **Review tool down + sustained outage →** the gate prompts a **human** to approve
   (`permissionDecision: "ask"`). You cannot skip a floor change past it, and you cannot approve
   your own prompt.

## A reason code can be **suspended** (Phase 5 calibration)

If a reason code's skips keep preceding real findings, the maintainers' calibration loop can
**suspend** that code for that repo. A suspended code's skip is denied
(`gate_skip_reason_code_suspended`) and you run the real review instead — re-run `audit_coding`
with `gate_repo` + `gate_diff`. `tool_unavailable` is never suspendable (it's the outage valve).
This is **off by default** and only enabled by a maintainer on real usage data, so you'll rarely
see it; when you do, it's not an error to report — just run the review.

## `time_critical_hotfix` records a deferred-review obligation

A `time_critical_hotfix` skip is honored immediately, but it logs an **open obligation** to
review the change later. A subsequent `record_gate_skip` in the same repo may surface a
non-blocking `advisory` reminding you the hotfix still needs a real review; it resolves once a
later `audit_coding` covers the same hunks. The skip isn't blocked — this is a reminder, not a gate.

### `prior_pass_receipt_match` is **not** a skip (don't use it to skip)

`prior_pass_receipt_match` replaces the old `already_reviewed_this_session`, but it is **not
a way to skip**: if you genuinely already passed an `audit_coding` of this *exact* code, the
gate releases **automatically** — a matching PASS receipt covers the hunks, so no skip is
needed. If the gate still fired, the code **changed** since that review, so re-run the
review (you can scope `audit_coding` to just the changed/uncovered hunks — the prior PASS
still covers the rest). Recording a skip with this reason is **denied at every gate**.
(`already_reviewed_this_session` is a **deprecated** alias — still accepted for now,
normalized to `prior_pass_receipt_match`, and likewise denied — but don't use it.)

## Honesty matters

`false_positive_not_risky` and `disagree_with_classification` are the codes the
maintainers watch most — a high rate signals the classifier needs tuning, and the
free-form text is the training signal. `time_critical_hotfix` and
`disagree_with_classification` are the codes most open to lazy use; reserve them for
when they're true. When unsure whether a skip is justified, run the review instead.

## Privacy

Same rule as `record_outcome`: `reason_text` must not contain secrets, proprietary
file paths, function/class names, or copied source. Describe the change in general
terms ("removed an unused import in a test helper"), not specifics.
