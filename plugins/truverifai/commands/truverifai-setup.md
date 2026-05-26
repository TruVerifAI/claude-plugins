---
name: truverifai-setup
description: Verify your TruVerifAI plugin install (API key, connectivity, hook settings) and optionally toggle the forced-eval hook.
---

You are running the TruVerifAI plugin setup flow. Execute these steps in order and report results back to the user clearly.

## Step 1 — Verify the API key is configured

Check whether `${user_config.api_token}` is set. If it's empty, tell the user to run `/plugin enable truverifai` and supply their `tvai_…` key when prompted (or to edit it via `/plugin config truverifai`). Stop here if no key.

## Step 2 — Test connectivity via ping

Call `mcp__truverifai__ping` with no arguments. This is a free, instant health-check tool that returns connectivity info without billing.

If the call succeeds: report "✓ Connected to TruVerifAI MCP. API key valid."
If the call returns a 401: report "✗ API key rejected — generate a fresh key at https://truverif.ai/settings/api-keys."
If the call times out: report "✗ Could not reach mcp.truverif.ai. Check your network connection."

## Step 3 — Report which skills are installed

Confirm the three skills are present: `truverifai-audit-before-commit`, `truverifai-deliberate-before-implementing`, `truverifai-synthesize-quick-check`. List them to the user with one-line summaries:

- `audit` — Before committing high-stakes changes. ~60-120s.
- `deliberate` — For design choices with multiple defensible answers. ~60-120s.
- `synthesize` — Quick sanity checks. ~15-30s.

## Step 4 — Forced-eval hook status

Check the value of `${user_config.enable_forced_eval}`.

If `false` (default): tell the user the hook is off and explain when they might want to turn it on:
> "The forced-eval hook adds about 2 seconds of latency per prompt but improves how reliably your agent reaches for TruVerifAI on relevant prompts. Most users don't need it — directive skill descriptions are usually sufficient. Turn it on via `/plugin config truverifai` if you've observed your agent skipping TruVerifAI invocations despite the skills being installed."

If `true`: confirm the hook is on; remind the user they can toggle it off the same way.

## Step 5 — Final summary

Report a one-paragraph summary:
> "TruVerifAI plugin is installed and connected. Three skills are active; the forced-eval hook is [on/off]. Your agent will reach for TruVerifAI automatically when it encounters decision moments matching the skill triggers. Run `/truverifai-setup` again any time to re-verify."

Then end the command. Do not start a conversation thread beyond the setup report unless the user asks a follow-up.
