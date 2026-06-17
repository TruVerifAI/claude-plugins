---
name: setup
description: Verify your TruVerifAI plugin install (API key, connectivity, hook settings) and optionally toggle the forced-eval hook.
---

You are running the TruVerifAI plugin setup flow. Execute these steps in order and report results back to the user clearly.

## Step 1 — Verify the API key is configured

Check whether `${user_config.api_token}` is set. If it's empty, tell the user to run `/plugin enable panel-review` and supply their `tvai_…` key when prompted (or to edit it via `/plugin config panel-review`). Stop here if no key.

## Step 2 — Test connectivity via ping

Call `mcp__truverifai__ping` with no arguments. This is a free, instant health-check tool that returns connectivity info without billing.

If the call succeeds: report "✓ Connected to TruVerifAI MCP. API key valid."
If the call returns a 401: report "✗ API key rejected — generate a fresh key at https://truverif.ai/settings/api-keys."
If the call times out: report "✗ Could not reach mcp.truverif.ai. Check your network connection."

## Step 3 — Report which skills are installed

Confirm the four skills are present: `audit-before-commit`, `deliberate-before-implementing`, `synthesize-quick-check`, `record-outcome-after-acting`. List them to the user with one-line summaries:

- `audit` — Before committing high-stakes changes. ~60-120s.
- `deliberate` — For design choices with multiple defensible answers. ~60-120s.
- `synthesize` — Quick sanity checks. ~15-30s.
- `record-outcome` (V1.1) — AFTER acting on any of the three above; reports whether the deliberation mattered. Free of credits.

## Step 4 — Final summary

Report a one-paragraph summary:
> "TruVerifAI plugin is installed and connected. Four skills are active (three primary plus the V1.1 record-outcome follow-up). Your agent will reach for TruVerifAI automatically when it encounters decision moments matching the skill triggers, and will report outcomes back to your dashboard after acting on responses. Run `/panel-review:setup` again any time to re-verify."

Then end the command. Do not start a conversation thread beyond the setup report unless the user asks a follow-up.
