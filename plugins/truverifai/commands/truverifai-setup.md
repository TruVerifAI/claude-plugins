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

Confirm the four skills are present: `truverifai-audit-before-commit`, `truverifai-deliberate-before-implementing`, `truverifai-synthesize-quick-check`, `truverifai-record-outcome-after-acting`. List them to the user with one-line summaries:

- `audit` — Before committing high-stakes changes. ~60-120s.
- `deliberate` — For design choices with multiple defensible answers. ~60-120s.
- `synthesize` — Quick sanity checks. ~15-30s.
- `record-outcome` (V1.1) — AFTER acting on any of the three above; reports whether the deliberation mattered. Free of credits.

## Step 4 — Adherence telemetry status

Check the value of `${user_config.enable_adherence_telemetry}`.

If `true` (the default for V1): tell the user explicitly that telemetry is on, what it does and doesn't report, and how to opt out. Don't be vague — this is a privacy-relevant default that the install flow did NOT explicitly prompt for, so the user should know:

> "Adherence telemetry is ON. This means: each time your agent runs `git commit` from inside Claude Code, the plugin reports the TIMING of that commit to TruVerifAI. The number you'll see on the adherence card at https://truverif.ai/settings/mcp is 'agent committed N times this week; invoked TruVerifAI M times' — the gap is what tells you whether your agent is actually reaching for the tool. NEVER reported: commit messages, file paths, diffs, branch names, repository identifiers, working directory, raw commands, or commit SHAs. Full disclosure: https://truverif.ai/data-handling. To opt out, run `/plugin`, click Installed → TruVerifAI, toggle 'Enable adherence telemetry' off, click Save configuration, then run `/reload-plugins`."

If `false`: tell the user telemetry is off:

> "Adherence telemetry is OFF. The adherence card on /settings/mcp won't populate for this Claude Code install. If you want to enable it, run `/plugin`, click Installed → TruVerifAI, toggle 'Enable adherence telemetry' on, Save, then `/reload-plugins`."

## Step 5 — Final summary

Report a one-paragraph summary:
> "TruVerifAI plugin is installed and connected. Four skills are active (three primary plus the V1.1 record-outcome follow-up); adherence telemetry is [on/off]. Your agent will reach for TruVerifAI automatically when it encounters decision moments matching the skill triggers, and will report outcomes back to your dashboard after acting on responses. Run `/truverifai-setup` again any time to re-verify."

Then end the command. Do not start a conversation thread beyond the setup report unless the user asks a follow-up.
