# Example — skipping a gate false positive

## The situation

You add a docstring to a test helper. The write gate flags it:

```
TruVerifAI flagged a test/docs change — worth a quick check before it ships.
Run `audit_coding` ... OR record a one-line skip with a reason, AND pass:
  gate_repo       = "repo_268c1440e37b3de823d2ace6"
  gate_context_id = "gc_5f3a9c1b2d4e6f80"
  gate_session_id = "cf7f53..."
```

The flagged file is `tests/helpers/fixtures.py` and the change is a docstring. This
is a genuine false positive — no risk surface, and it's confined to a test file.

## The right move

```
mcp__truverifai__record_gate_skip(
  gate_repo       = "repo_268c1440e37b3de823d2ace6",
  reason_code     = "test_or_docs_only",
  gate_context_id = "gc_5f3a9c1b2d4e6f80",
)
```

Then retry the Write — the gate sees the logged skip and releases. Pass the
`gate_context_id` the gate printed (copy it verbatim); the server verifies the gate
fired and uses its own recorded hunks/area, so you don't also send `area`/`hunk_hashes`.
(Only an older gate that printed no `gate_context_id` needs the legacy key — `area`
for the write gate, `hunk_hashes` for the commit gate.)

## A counter-example (do NOT skip)

The gate blocks a Write to `auth/session.py` that changes how a session token is
validated. You feel confident it's correct. **Do not skip.** Confidence is not a
reason — a `Write`/`Edit` is finished code, so run `audit_coding` (its natural
review; a PASS releases). This is exactly the kind of change the gate exists for.
Auth is a **floor class**, so a judgment skip (`false_positive_not_risky`,
`disagree_with_classification`, …) is denied here anyway — if the panel agrees it's
genuinely low-risk, a `synthesize_coding` SYNTH_CONFIRM is the cheap release; if it
surfaces real risk, you're glad you checked.
