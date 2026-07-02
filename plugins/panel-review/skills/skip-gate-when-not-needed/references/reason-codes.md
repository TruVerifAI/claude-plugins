# `record_gate_skip` reason codes

Pick the closest single fit. `reason_text` is required for `other` and
`disagree_with_classification` — **and for the judgment codes (`false_positive_not_risky`,
`trivial_change`, `reviewed_outside_truverifai`, `time_critical_hotfix`) at the
write and commit gates** (the fast borderline/synthesize tier is exempt). It's welcome on any code.
All skips are logged.

| reason_code | Use when | reason_text |
|---|---|---|
| `false_positive_not_risky` | The gate flagged it, but the change genuinely isn't risky (the classifier over-fired). | required at write/commit |
| `trivial_change` | A cosmetic / no-op / rename-only change with no risk surface. | required at write/commit |
| `reviewed_outside_truverifai` | A human or another tool already reviewed it. | required at write/commit |
| `generated_or_vendored_code` | Generated / vendored / lockfile content, not hand-written risk. | optional |
| `test_or_docs_only` | The change is confined to tests or documentation. | optional |
| `time_critical_hotfix` | A genuine production hotfix where you accept the unreviewed risk. | required at write/commit |
| `disagree_with_classification` | The classifier mis-categorized the change and you disagree with the flag. | **required** |
| `tool_unavailable` | The review tool errored / is down and you can't run it. | optional |
| `other` | None of the above. | **required** |
| `recommendations_applied` | You ran ONE review, applied its findings (or a PASS-then-modify re-fired the gate) and want to proceed. Server-verified against a real review. | optional |
| `review_deferred_to_commit` | Defer a batch of successive risky writes to the commit gate; releases this write + silences the write gate for the session (~1h). | optional |

## Floor classes — a judgment skip is **denied**; run a real check

For a change touching a **floor class — auth / secrets / money / migration / removed-guard**,
the judgment and external-trust codes (`false_positive_not_risky`, `trivial_change`,
`disagree_with_classification`, `reviewed_outside_truverifai`, `time_critical_hotfix`,
`tool_unavailable`, `other`) are **denied** — those classes "need a real check, not a judgment
call." Only the **path-verified** codes (`test_or_docs_only`, `generated_or_vendored_code`) can
release a floor change on that basis, and only when the server confirms the path class from
fire-time evidence.

The two **single-call** codes are **gate-dependent** on floor: `recommendations_applied` and
`review_deferred_to_commit` release a floor change at the **write gate** (you reviewed / are
deferring the batch) but are **denied at the commit gate**, where a shipping floor hunk needs a
real PASS. So a floor change can be applied/deferred while you work, and the commit gate audits it
on the real staged bytes before it ships — defer *up to* commit, never past it.

To release a floor change you have three real options (the gate's deny message spells them out).
**This is identical at the commit gate and the write gate** — a `Write`/`Edit` is finished code, so
`audit_coding` is its natural review, and a `SYNTH_CONFIRM` releases either gate. (`deliberate_coding`
is only for a still-open design.) Always also pass
the `gate_context_id` the gate printed (binds coverage to the gate's own hunks); and on a **write gate**
floor block, also pass the `target_hunk_hashes = [...]` line the gate printed — copy it verbatim so
coverage binds *deterministically* to exactly those floor hunks:

1. **Already decided (the usual case) →** run `audit_coding` with your `proposed_action` +
   `gate_repo`/`gate_diff`/`gate_context_id` (+ `target_hunk_hashes` on a write-gate floor block);
   a PASS releases it.
2. **Genuine low-risk false positive →** run `synthesize_coding` with `gate_repo` + `gate_diff` +
   `gate_context_id` (+ `target_hunk_hashes` on a write-gate floor block; the diff you're committing
   or writing). If the panel agrees it's low-risk it mints a **SYNTH_CONFIRM** that releases the gate
   — cheap (~15–30s), no full audit.
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

## The single-call codes — `recommendations_applied` / `review_deferred_to_commit`

Make at most **one** panel-review call per change; these two proceed on that one review:

- **`recommendations_applied`** is server-**verified** — it's accepted only if a real review
  receipt (`audit` / `deliberate` / `synthesize`, any verdict) exists for this repo recently.
  It's not a free skip; it attests you ran the review and addressed it. Use it after applying a
  review's findings, or when a **PASS-then-modify** re-fired the gate (you changed the reviewed
  bytes — even a comment — so the gate re-classifies; no second review is needed). A floor hunk is
  still re-audited at commit.
- **`review_deferred_to_commit`** needs no prior review — it's an explicit "review later." It
  releases this write and silences the write gate for the session/area (~1h), and logs an **open
  obligation** (a later `record_gate_skip` may surface a non-blocking advisory). Use it **only when
  you expect a batch of successive risky/floor writes** to review together at commit; for a one-off
  change, just review and proceed. The commit gate re-classifies the whole staged diff and requires
  a real PASS for every floor hunk — deferral never ships unreviewed floor code.

Both take the `gate_context_id` the gate printed; never re-supply the diff or recompute a hash.

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
