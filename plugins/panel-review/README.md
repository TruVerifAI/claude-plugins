# TruVerifAI Claude Code Plugin

Multi-model second-opinion deliberation for high-stakes coding decisions. Routes your agent to TruVerifAI's MCP server at the moments where being right matters most.

## What this plugin does

When you install this plugin, your Claude Code agent gets five skills that auto-activate at decision moments — three that fire BEFORE a decision, one AFTER, and one when a review gate fires:

- **`audit-before-commit`** — Use before committing a code change that's hard to undo, touches a security/safety boundary (auth, crypto, input validation, payment, PII, persistence, infra-as-code), or replaces load-bearing logic. Four frontier models stress-test it for blind spots.
- **`deliberate-before-implementing`** — Use when about to commit to a design choice with multiple defensible answers (schema design, API shape, library/framework selection, infra-as-code pattern, caching strategy, concurrency model). Four models reason independently, then route conflicts back to each model for revision.
- **`synthesize-quick-check`** — Use for quick sanity checks (idiomatic patterns, bounded library choices, "is there a standard way to do X?" questions). Faster than the other two.
- **`record-outcome-after-acting`** (V1.1) — Fires AFTER acting on a response from any of the three above. Reports whether the deliberation was useful and whether it changed the agent's decision (free of credits). Powers the Impact card on the dashboard so you can see what % of MCP calls actually mattered.
- **`skip-gate-when-not-needed`** — Fires when a proactive review gate has blocked a commit/write and the agent judges the review genuinely unnecessary (false positive, already reviewed, generated/test/docs, true hotfix). Calls `record_gate_skip` to log a skip-with-reason and release the gate (free of credits). Biased toward running the review — skipping is the exception.

Each of the three primary skills calls the matching MCP tool with structured inputs (`proposed_action`, `relevant_code`, `architectural_context`, etc.) and returns a decision-grade response: a **verdict** (audit: approve / approve_with_caveats / request_changes / reject), **recommendation** (deliberate: clear / qualified / split / insufficient_basis), or **answer_status** (synthesize: settled / qualified / contested / unresolved); a severity-tagged **`findings[]`** list (critical / major / minor / preference); a derived **`action`** (proceed / proceed_with_caveats / request_changes / escalate_to_human) with an **`action_reason`** when a finding tightened it; plus an *auxiliary* agreement signal and dimensions of disagreement. The action is driven by the verdict + findings — the agreement signal is telemetry only, it does not drive the action. The follow-up skill calls `record_outcome` with the prior call's `request_id` plus the agent's self-reported outcome.

Two additional MCP tools (no skill — the agent calls them directly, both **free, no credits**): **`record_outcome`** (reports whether a prior call changed the agent's decision — powers the Impact card) and **`record_gate_skip`** (releases a proactive review gate by logging a skip-with-reason instead of running the review — see Review gates below).

## Install

Submit each of these slash commands on its own — Claude Code parses one slash command per submission, so pasting them all in a single block produces a malformed-URL error.

**1. Add the TruVerifAI marketplace:**

```
/plugin marketplace add https://github.com/TruVerifAI/claude-plugins.git
```

**2. Install the plugin:**

```
/plugin install panel-review@truverifai
```

**3. Reload Claude Code's plugin set:**

```
/reload-plugins
```

**4. Configure your API key.** Run `/plugin`, click **Installed** → **AI Panel Review**, paste your `tvai_…` key (generate one at https://truverif.ai/settings/api-keys), click **Save configuration**, then run `/reload-plugins` again.

**5. Enable auto-update (recommended).** While you're in the `/plugin` UI, click the **Marketplaces** tab, select **truverifai**, and toggle **Enable auto-update** on. This is a one-time setting — once enabled, future plugin updates (new skills, bug fixes, new tools) flow in automatically on the next Claude Code session start. Without this, you'd have to run `/plugin marketplace update truverifai && /plugin install panel-review@truverifai && /reload-plugins` manually every time a new version ships.

**6. Verify everything's wired up:** run `/panel-review:setup`. It pings the MCP server, confirms the API key is valid, and reports which skills are loaded.

## Uninstall

To remove the plugin, submit each slash command on its own:

```
/plugin uninstall panel-review@truverifai
```

```
/reload-plugins
```

Optional — also remove the marketplace registration:

```
/plugin marketplace remove truverifai
```

To pull the latest release without doing a full uninstall + reinstall:

```
/plugin update panel-review
```

## Review gates (proactive invocation)

Beyond the auto-activating skills, the plugin ships **PreToolUse review gates** that prompt the right call at the right moment:

- **Audit gate** — before a risky `git commit`, prompts `audit_coding` on the about-to-be-committed change.
- **Deliberate gate** — before a risky design **Write / Edit** (schema, migration, dependency, auth, IaC exposure, etc.), prompts `deliberate_coding`.

A local classifier scores the change across many domains — web (auth, billing, secrets), data migrations, infra-as-code, plus universal risk shapes and **risky deletions** (e.g. a removed permission or validation check) — and routes by confidence: high-confidence risks prompt a review; lower-confidence "borderline" changes get a fast `synthesize_coding` nudge (see `borderline_mode`). Either way the agent can release by running the suggested tool **or** calling the `record_gate_skip` MCP tool to log a skip-with-reason (free; the reason improves the classifier). When a gate blocks, its message prints the exact release key to copy into `record_gate_skip` — a `hunk_hashes` list (commit gate) or an `area` directory (write gate) — so a skip is copy-paste, not a reconstruction. The gate sends TruVerifAI only a repo fingerprint + hunk content hashes — never source, paths, or diffs — and **fails open** on any error (missing token, no network, our server down); it never deadlocks.

Options, set in `/plugin` → **Installed** → **AI Panel Review** (type the value, then `/reload-plugins`):

- **`enable_gates`** (`true` / `false`, default `true`) — turns the gates on or off.
- **`deliberate_mode`** (`tiered` / `block` / `advisory`, default `tiered`) — `tiered` blocks only high-confidence / irreversible design forks and is advisory on the rest; `block` blocks every risky design write; `advisory` never blocks (surfaces a suggestion only). The audit (pre-commit) gate is unaffected.
- **`borderline_mode`** (`advisory` / `synthesize_gate` / `off`, default `advisory`) — how borderline (low-confidence) changes are handled: `advisory` surfaces a fast `synthesize_coding` suggestion **to the agent** (non-blocking; shown once per area per session for the highest-signal "heavy" spikes); `synthesize_gate` soft-gates the highest-signal borderline changes (releasable by a quick `synthesize_coding` or a one-line skip); `off` ignores them. Never hard-blocks.

## Pricing

Tool invocations are billed against your TruVerifAI account. Pricing at https://truverif.ai/pricing. Approximate per-call cost: synthesize ~$0.04, deliberate ~$0.20, audit ~$0.20. Latencies: synthesize 15-30s, deliberate/audit 60-120s.

## Cross-platform install (non-Claude-Code users)

For Codex CLI / Gemini CLI / Cursor: see `install-cross-platform.sh` in the plugin directory. Cursor users invoke skills manually (`/skill-name`) — Cursor doesn't have native auto-discovery yet, so the plugin's value on Cursor is reduced to "well-curated reference material for invoking TruVerifAI MCP via your existing MCP client."

## Known limitations

### Run `/reload-plugins` after the plugin updates (or the gates run stale)

Claude Code does **not** hot-reload plugin hooks after an auto-update: a session that was already running when the plugin updated keeps the **previous** version's gate hooks loaded until you run `/reload-plugins` or restart. The gates then run the older classifier. As of v0.2.2 a blocked-gate message **stamps the version it ran** and, if it detects it's a superseded version, prints a `⚠️ running a SUPERSEDED version — /reload-plugins` warning — so staleness is visible rather than silent. **After any plugin update, run `/reload-plugins`** (Claude Code prunes the old cached version on its own once no session is using it; you don't need to delete anything).

### No in-progress display during 60-120s calls (Claude Code regression)

In current Claude Code builds (v2.1.116+, April 2026 onward), the UI shows only `"Calling panel-review..."` during a long-running MCP tool call and suppresses progress notifications until the call returns. Our server emits progress events correctly on the wire — Claude Code receives them but doesn't render them mid-call. This is tracked at [anthropics/claude-code#51713](https://github.com/anthropics/claude-code/issues/51713) and affects every MCP server, not just ours.

What you'll see:
- `synthesize_*` (15-30s) — brief "Calling panel-review..." then the response.
- `deliberate_*` / `audit_*` (60-120s) — a longer "Calling panel-review..." window with no visible progress, then the response.

Workarounds while waiting for the upstream fix:
- Trust the call is running — we have a 300s server-side deadline, so it can't hang silently forever.
- Watch the agent's last spoken plan to know what to expect ("calling deliberate_coding to weigh this schema decision...").
- For long-form work, prefer `synthesize` first to validate the question shape; escalate to `deliberate`/`audit` only when needed.

We've added the `anthropic/expandByDefault: true` `_meta` annotation to all tools — the moment Anthropic ships the #51713 fix, our tools will auto-expand and show streaming progress without any plugin update needed.

### Cursor: no native skill auto-discovery

Cursor (as of 2026-05) doesn't auto-activate skills. The skills install correctly under `~/.cursor/skills/` but you have to invoke them manually (`/audit-before-commit`). The references and examples files give Cursor the context it needs once invoked. Auto-discovery may land in a future Cursor release.


## Support

- Documentation: https://truverif.ai/docs/mcp
- Issues: https://github.com/truverifai/claude-plugins/issues
- Email: support@truverif.ai

## License

MIT — see LICENSE.
