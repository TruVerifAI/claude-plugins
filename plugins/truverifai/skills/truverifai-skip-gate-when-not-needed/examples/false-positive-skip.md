# Example — skipping a gate false positive

## The situation

You add a docstring to a test helper. The deliberate gate blocks the Write:

```
TruVerifAI gate: this <api_route> change is borderline-consequential — worth a
fast second opinion before building on it.
Call `synthesize_coding` ... OR record a one-line skip with a reason, AND pass:
  gate_repo = "repo_268c1440e37b3de823d2ace6"
  gate_session_id = "cf7f53..."
```

The flagged file is `tests/helpers/fixtures.py` and the change is a docstring. This
is a genuine false positive — no risk surface.

## The right move

```
mcp__truverifai__record_gate_skip(
  gate_repo   = "repo_268c1440e37b3de823d2ace6",
  reason_code = "test_or_docs_only",
  area        = "tests/helpers",
  session_id  = "cf7f53...",
)
```

Then retry the Write — the gate sees the logged skip and releases.

## A counter-example (do NOT skip)

The gate blocks a Write to `auth/session.py` that changes how a session token is
validated. You feel confident it's correct. **Do not skip.** Confidence is not a
reason — run `deliberate_coding` (or `audit_coding` at commit) instead. This is
exactly the kind of change the gate exists for; a wrong skip here is the expensive
failure. If after the review you still disagree with the flag, *then* a skip with
`reason_code="disagree_with_classification"` + an explanation is the honest record.
