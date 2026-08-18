---
name: gates
description: Show or change the TruVerifAI review-gate state — status by default; pass "off" or "on" to switch every gate delivery on this machine (the git pre-commit hook and every agent, not just Claude Code).
---

You are operating the TruVerifAI gate switch for the user. This command exists
because the plugin's settings panel can only reach Claude Code's own hooks: the
git pre-commit hook and the gates in Codex / Cursor / Copilot / VS Code /
Gemini / Antigravity never see a plugin setting. The `npx @truverifai/init
gates` CLI writes the one config level every delivery reads
(`~/.truverifai/config.json`), so it is the single switch that means what it
says. This command runs that CLI, so the user does not have to leave the
session.

**Interpret the argument:**

- No argument, or `status` → Step 1 only.
- `off` → Step 2.
- `on` → Step 3.
- Anything else → say the valid forms are `/panel-review:gates`,
  `/panel-review:gates off`, `/panel-review:gates on`, and stop.

## Step 1 — Status (default; read-only, always safe)

Run:

```bash
npx @truverifai/init gates status
```

Report its output to the user faithfully — it names the effective state AND
which configuration level decided it. Two things to relay verbatim when
present, because each one is a trap the status output exists to expose:

- a `TVAI_ENABLE_GATES` env-var line — an exported env var silently outranks
  everything, including this command;
- a "these DISAGREE" line — a leftover per-host setting is splitting the state.

## Step 2 — Turn the gates off (`off`)

This is the USER's switch, not yours. If you arrived here because a gate
blocked you, stop: do not run this to unblock yourself, and do not suggest it
as a way past a block — every block has a review path, and the block message
names it. Run this step only when the human asked for the gates to be off.

```bash
npx @truverifai/init gates off
```

Relay the output. Confirm to the user that this reaches EVERY delivery — the
git pre-commit hook included — and that the MCP review tools stay connected;
only the proactive gating stops.

## Step 3 — Turn the gates on (`on`)

```bash
npx @truverifai/init gates on
```

Relay the output. If the output warns that an env var outranks the file, make
sure the user sees that line — the command did what it could, but their shell
profile is still the deciding level.

## If the command itself is blocked

Claude Code's permission classifier may refuse `npx @truverifai/init gates …`
("Blocked by classifier"). That is the host, not TruVerifAI. Tell the user to
add the allow rule and retry in a new session:

```
/permissions → allow →  Bash(npx @truverifai/init:*)
```
