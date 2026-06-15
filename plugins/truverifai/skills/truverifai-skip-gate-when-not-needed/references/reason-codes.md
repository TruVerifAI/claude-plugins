# `record_gate_skip` reason codes

Pick the closest single fit. `reason_text` is required for `other` and
`disagree_with_classification` (and welcome on any code). All skips are logged.

| reason_code | Use when | reason_text |
|---|---|---|
| `false_positive_not_risky` | The gate flagged it, but the change genuinely isn't risky (the classifier over-fired). | optional |
| `trivial_change` | A cosmetic / no-op / rename-only change with no risk surface. | optional |
| `already_reviewed_this_session` | You already ran `audit_coding`/`deliberate_coding` on this exact change this session. | optional |
| `reviewed_outside_truverifai` | A human or another tool already reviewed it. | optional |
| `generated_or_vendored_code` | Generated / vendored / lockfile content, not hand-written risk. | optional |
| `test_or_docs_only` | The change is confined to tests or documentation. | optional |
| `time_critical_hotfix` | A genuine production hotfix where you accept the unreviewed risk. | recommended |
| `disagree_with_classification` | The classifier mis-categorized the change and you disagree with the flag. | **required** |
| `tool_unavailable` | The review tool errored / is down and you can't run it. | optional |
| `other` | None of the above. | **required** |

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
