# TruVerifAI Claude Code Plugin

Multi-model second-opinion deliberation for high-stakes coding and finance decisions. Routes your agent to TruVerifAI's MCP server at the moments where being right matters most.

## What this plugin does

When you install this plugin, your Claude Code agent gets eight skills that auto-activate at decision moments, across two profiles — **coding** and **financial**. Per profile, three fire around a decision (audit / deliberate / synthesize); two more are shared (one AFTER any decision, one when a review gate fires):

- **`audit-before-commit`** — Use before committing a code change that's hard to undo, touches a security/safety boundary (auth, crypto, input validation, payment, PII, persistence, infra-as-code), or replaces load-bearing logic. Four frontier models stress-test it for blind spots.
- **`deliberate-before-implementing`** — Use when about to commit to a design choice with multiple defensible answers (schema design, API shape, library/framework selection, infra-as-code pattern, caching strategy, concurrency model). Four models reason independently, then route conflicts back to each model for revision.
- **`synthesize-quick-check`** — Use for quick sanity checks (idiomatic patterns, bounded library choices, "is there a standard way to do X?" questions). Faster than the other two.
- **`synthesize-financial`** — Fast multi-model take on any finance question (thesis, valuation, forecast, credit, accounting), or to **generate candidate finance options** — trade/investment ideas, capital-allocation alternatives, valuation approaches, budget scenarios, credit structures (each returned with its disconfirming case + a falsifiable test). Information, not advice.
- **`deliberate-financial`** — Evaluate or compare any finance decision with more than one defensible answer — which trade/investment, position sizing, a valuation, capital allocation (M&A / capex / buyback), a forecast/budget assumption, a credit decision, an accounting treatment. Weighs the affirmative case AND the downside to the same bar (for markets decisions, edge after costs).
- **`audit-financial`** — Stress-test a drafted finance decision, or review a finance model/document — a strategy & backtest (survivorship / lookahead / leakage), a valuation (DCF / LBO / credit), a forecast/budget, a risk report, an accounting memo, a capital-allocation proposal, a lending approval. Information/critique, not advice.
- **`record-outcome-after-acting`** (V1.1) — Fires AFTER acting on a response from any of the three above. Reports whether the deliberation was useful and whether it changed the agent's decision (free of credits). Powers the Impact card on the dashboard so you can see what % of MCP calls actually mattered.
- **`skip-gate-when-not-needed`** — Fires when a proactive review gate has blocked a commit/write and the agent judges the review genuinely unnecessary (false positive, already reviewed, generated/test/docs, true hotfix). Calls `record_gate_skip` to log a skip-with-reason and release the gate (free of credits). Biased toward running the review — skipping is the exception.

Each of the six primary skills (three per profile) calls the matching MCP tool with structured inputs and returns a decision-grade response: a **verdict** (audit — coding: approve / approve_with_caveats / request_changes / reject; financial: sound / sound_with_caveats / reconsider / reject), **recommendation** (deliberate: clear / qualified / split / insufficient_basis), or **answer_status** (synthesize: settled / qualified / contested / unresolved); a severity-tagged **`findings[]`** list (critical / major / minor / preference); a derived **`action`** (coding: proceed / proceed_with_caveats / request_changes / escalate_to_human; financial: proceed / review_assumptions / gather_more_data / escalate_to_human) with an **`action_reason`** when a finding tightened it; plus an *auxiliary* agreement signal and dimensions of disagreement. The action is driven by the verdict + findings — the agreement signal is telemetry only, it does not drive the action. The follow-up skill calls `record_outcome` with the prior call's `request_id` plus the agent's self-reported outcome.

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

A local classifier scores the change across many domains — web (auth, billing, secrets), data migrations, infra-as-code, plus universal risk shapes and **risky deletions** (e.g. a removed permission or validation check) — and routes by confidence: high-confidence risks prompt a review; lower-confidence "borderline" changes get a fast `synthesize_coding` nudge (see `borderline_mode`). Either way the agent can release by running the suggested tool **or** calling the `record_gate_skip` MCP tool to log a skip-with-reason (free; the reason improves the classifier). When a gate blocks, its message prints the exact release key to copy into `record_gate_skip` — preferably a server-issued `gate_context_id` (`gc_…`), which the server verifies (the gate really fired) and consumes single-use, using its own recorded hunks/area; older gates that print no id fall back to a `hunk_hashes` list (commit gate) or an `area` directory (write gate). Either way the skip is copy-paste, not a reconstruction. The gate sends TruVerifAI only a repo fingerprint + hunk content hashes — never source, paths, or diffs — and **fails open** on any error (missing token, no network, our server down); it never deadlocks.

**Floor classes can't be waved away with a one-line skip.** For the highest-stakes changes — **auth, secrets, money, migrations, and removed guards** — a judgment `record_gate_skip` (false positive, trivial, etc.) is **denied**. Release a floor change by running `audit_coding` (a PASS clears it), or, for a genuine false positive, `synthesize_coding` with `gate_repo` + `gate_diff` — if the panel agrees it's low-risk the server mints a cheap **SYNTH_CONFIRM** (~15–30s) that releases the gate. If the review tool is genuinely down during a *sustained* outage, the commit gate asks a **human** to approve (the agent can't skip a floor change past it, and can't approve its own prompt). A reason code whose skips keep preceding real findings can also be **suspended** for a repo (off by default; maintainer-enabled on real data) — a suspended skip is denied and you run the review.

**The gate aims to fire only when it should (precision, recall-safe).** It **ignores writes outside your repo** and to scratch/temp dirs (they can't ship — except a real secret value, which always fires). **Docs and prose don't fire** on a keyword unless they contain a real secret value. And an auth *mention* — a `role`/`session`/`permission` identifier in ordinary code — is at most an advisory nudge, while an auth *action* (a permission decorator, an auth/credential check, a real secret) still blocks. These cut the false-positive walls without lowering recall on genuine risk.

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

### Long-running calls may return a continuation token

`deliberate_*` / `audit_*` run several minutes — longer than the tool-call timeout most MCP clients enforce (≈60s on Cursor / Cline / Zed; 300s on Claude Code v2.1.187+). To stay under any client's limit, a long call may return a holding response **before it finishes**, instead of the verdict:

```json
{ "status": "in_progress", "continuation_token": "mcp_…", "stage": "running",
  "next_step": "Not finished. Call the SAME tool again with only continuation_token …" }
```

The agent then calls the **same tool** again with **only** that `continuation_token` (no other arguments), repeating until the final verdict returns. The orchestration keeps running on the server between calls — each call just waits up to the client's budget — and credits are charged once, on completion. The token is scoped to your API key and the specific tool; an unknown / expired / not-yours token returns `{ "status": "expired" }`, meaning re-run from scratch. Most agents handle this re-invocation automatically from the `next_step` instruction — you don't need to do anything.

### Cursor: no native skill auto-discovery

Cursor (as of 2026-05) doesn't auto-activate skills. The skills install correctly under `~/.cursor/skills/` but you have to invoke them manually (`/audit-before-commit`). The references and examples files give Cursor the context it needs once invoked. Auto-discovery may land in a future Cursor release.


## Support

- Documentation: https://truverif.ai/docs/mcp
- Issues: https://github.com/truverifai/claude-plugins/issues
- Email: support@truverif.ai

## License

MIT — see LICENSE.
