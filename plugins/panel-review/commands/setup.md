---
name: setup
description: Verify your TruVerifAI plugin install — API key, MCP connectivity, the review gates, and which skills are loaded.
---

You are running the TruVerifAI plugin setup flow. Execute these steps in order and report results back to the user clearly.

## Step 1 — Verify the API key is configured

Check whether `${user_config.api_token}` is set. If it's empty, tell the user to run `/plugin enable panel-review` and supply their `tvai_…` key when prompted (or to edit it via `/plugin config panel-review`). Stop here if no key.

## Step 2 — Test connectivity via ping

Call the `ping` tool with no arguments (it may appear as `mcp__plugin_panel-review_truverifai__ping`, or `mcp__truverifai__ping`, depending on the client). It's a free, instant health check that returns connectivity info without billing.

If the call succeeds: report "✓ Connected to TruVerifAI MCP. API key valid."
If the call returns a 401: report "✗ API key rejected — generate a fresh key at https://truverif.ai/settings/api-keys."
If the call times out: report "✗ Could not reach mcp.truverif.ai. Check your network connection."

## Step 2b — Gate-endpoint self-check (the hooks' half)

`ping` verifies only the MCP tools. The review gates POST to a different endpoint (the
backend's `/api/mcp/*` routes), and a failure there is fail-open by design — invisible
except for a per-event advisory. Prove that half works end-to-end:

Run (Bash), from the plugin's hooks directory (`${CLAUDE_PLUGIN_ROOT}/hooks` when that
variable is set; otherwise locate the installed plugin's `hooks/` folder):

```
TVAI_TOKEN=${user_config.api_token} python gate_selfcheck.py
```

It prints the gate `base_url` it resolved, makes one free authorized round-trip to the
coverage endpoint, and prints PASS or a named FAIL.

If PASS: report "✓ Gate endpoint reachable and authorized — the review gates are enforcing."
If FAIL: report the printed reason verbatim and warn: "✗ The review gates are FAILING
OPEN — they will not block anything until this is fixed."

## Step 3 — Report which skills are installed

Confirm the eight skills are present and list them with one-line summaries:

**Coding**
- `audit-before-commit` — Before committing a high-stakes change. ~2-5 min.
- `deliberate-before-implementing` — For a design choice with more than one defensible answer. ~2-5 min.
- `synthesize-quick-check` — Quick sanity checks. ~15-30s.

**Financial**
- `audit-financial` — Stress-test a drafted finance decision or model. ~2-5 min.
- `deliberate-financial` — Choose among finance options. ~2-5 min.
- `synthesize-financial` — Fast take, or generate candidate options. ~15-30s.

**Shared**
- `record-outcome-after-acting` — AFTER acting on any review; reports whether it changed the decision. Free.
- `skip-gate-when-not-needed` — Releases a blocked review gate by logging a reason instead of running a review. Free.

## Step 4 — Final summary

Report a one-paragraph summary:
> "TruVerifAI plugin is installed and connected. Eight skills are active (three coding + three financial primaries, plus record-outcome and skip-gate). The review gates are installed too: they prompt a review before a risky commit or Write/Edit. Your agent will reach for TruVerifAI automatically at decision moments matching the skill triggers, and will report outcomes back to your dashboard. Run `/panel-review:setup` again any time to re-verify."

Then end the command. Do not start a conversation thread beyond the setup report unless the user asks a follow-up.
