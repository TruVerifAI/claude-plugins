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
- **`record-outcome-after-acting`** — Fires after the agent acts on any coding or financial review response. Reports whether the review was useful and whether it changed the agent's decision (free of credits). Powers the Impact card on the dashboard so you can see what % of MCP calls actually mattered.
- **`skip-gate-when-not-needed`** — Fires when a proactive review gate has blocked a commit/write and the agent either judges the review genuinely unnecessary (false positive, generated/test/docs, a true hotfix) or is proceeding on ONE review it already ran (apply-and-log, or defer a batch to commit). Calls `record_gate_skip` to log a reason and release the gate (free of credits). Biased toward running the review — skipping is the exception.

Each of the six primary skills (three per profile) calls the matching MCP tool with structured inputs and returns a decision-grade response: a **verdict** (audit — coding: approve / approve_with_caveats / request_changes / reject; financial: sound / sound_with_caveats / reconsider / reject), **recommendation** (deliberate: clear / qualified / split / insufficient_basis), or **answer_status** (synthesize: settled / qualified / contested / unresolved); a severity-tagged **`findings[]`** list (critical / major / minor / preference); a derived **`action`** (coding: proceed / proceed_with_caveats / request_changes / escalate_to_human; financial: proceed / review_assumptions / gather_more_data / escalate_to_human) with an **`action_reason`** when a finding tightened it; plus an *auxiliary* agreement signal and dimensions of disagreement. The verdict and findings drive the `action`; the agreement signal is telemetry only and never drives it. The follow-up skill calls `record_outcome` with the prior call's `call_id` (from the response body's `post_action.call_id`) plus the agent's self-reported outcome.

Three tools are **free (no credits)** and the agent can call them directly: **`record_outcome`** (reports whether a prior call changed the agent's decision — powers the Impact card), **`record_gate_skip`** (releases a proactive review gate by logging a reason instead of running the review — see Review gates below), and **`confirm_floor`** (clears a suspected FALSE *floor* gate with one cheap budget model — a low-risk verdict releases it). `record_outcome` and `record_gate_skip` each also back a skill; `confirm_floor` has none. `confirm_floor` invokes a model, so its calls count against the daily cap; `record_outcome` and `record_gate_skip` don't. (All three are burst-rate-limited.)

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

**4. Configure your API key.** Run `/plugin`, go to **Installed** → **AI Panel Review** → **Configure options**, paste your `tvai_…` key (generate one at https://truverif.ai/settings/api-keys), click **Save configuration**, then run `/reload-plugins` again.

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

- **Commit gate** — before a risky `git commit` or `git merge`, prompts `audit_coding` on the about-to-be-committed change.
- **Write gate** — before a risky **Write / Edit** (schema, migration, dependency, auth, IaC exposure, etc.). A Write/Edit is *finished code*, so its natural review is **`audit_coding`** (a PASS releases it); use **`deliberate_coding`** only when the design is still open. On a **floor-class** write, match the tool to the situation: a **genuine** floor change → `audit_coding` (a PASS releases it, and it covers non-floor hunks too); you believe the gate **mis-fired** → a free **`confirm_floor`** or a **`synthesize_coding`** SYNTH_CONFIRM, each of which releases the **floor hunks only**, and only if the model agrees the change isn't risky. Both gates release the same way — a review releases either.
- **Post-commit backstop** *(non-blocking)* — a file **created and committed in one shell command** (e.g. `printf … > f.py && git add f.py && git commit`) never touches the Write tool and doesn't exist on disk when the commit gate runs, so it slips past both gates. A PostToolUse hook catches it *after the fact*: it classifies the **real committed diff** and, if a **floor** change shipped **unreviewed**, surfaces a **non-blocking advisory** (nudging you to review/amend — it can't block a commit that already happened) and logs a row on the admin dashboard so the owner can see the miss (that row carries only the repo fingerprint + floor category labels + hunk count + a pushed flag — never a diff, path, command text, or commit SHA). It fires on both success and a non-zero-exit command. This is a visibility backstop, not a gate — it never blocks and never nags twice for the same commit.

A local classifier scores the change across many domains — web (auth, billing, secrets), data migrations, infra-as-code, systems & mobile security (memory-safety, TLS, CI/CD), plus universal risk shapes and **risky deletions** (e.g. a removed permission or validation check) — and routes by confidence: high-confidence risks prompt a review; lower-confidence "borderline" changes get a fast `synthesize_coding` nudge (see `borderline_mode`).

To release a blocked gate, run the suggested tool **or** call `record_gate_skip` to log a skip-with-reason (free; the reason improves the classifier). The block message prints the exact release key to copy: a server-issued `gate_context_id` (`gc_…`), which the server verifies, consumes single-use, and binds to the hunks **it** recorded. That id is **required** — a skip can only release a gate the server can verify actually fired, so the agent never supplies hunk hashes itself. (If the gate can't mint one — rare — there's no skip; `audit_coding` still releases the change.) Copy the key, never reconstruct it.

The gate sends TruVerifAI only a repo fingerprint + hunk content hashes — never source, paths, or diffs — and **fails open** on any error (missing token, no network, our server down); it never deadlocks.

> **`git commit --no-verify` does NOT bypass these gates.** They are Claude Code **PreToolUse** hooks, not git `pre-commit` hooks, so `--no-verify` (which only skips git's own hooks) never reaches them. Release a gate the real way — run the suggested review or `record_gate_skip` — not with `--no-verify`.

**A mixed change has two buckets, and each needs its own release.** Most real changes fire **both** floor and ordinary risky hunks, and they clear **separately**. A **floor tool** (`confirm_floor`, `synthesize_coding`, `accept_risk_no_review`) covers **FLOOR hunks only** — on a mixed change it will report success and the gate will **still block**, on the ordinary hunks it never touched. **Non-floor** hunks clear on an `audit_coding` PASS or a one-line judgment `record_gate_skip`. An **`audit_coding` PASS covers both** in a single call, which is usually the simplest move. The gate prints a **`Still uncovered: N floor, M non-floor`** line — use *that bucket's* tool. Once every floor hunk is covered, the judgment skip that was denied **becomes admissible** and clears the non-floor remainder. **Never disable the gates**: every block has a reachable exit, and if a release tool succeeded but the count didn't move, you cleared the wrong bucket.

**Floor classes can't be waved away with a one-line skip.** For the highest-stakes changes — **auth, secrets, money, migrations, a removed guard, and other high-severity domains** (memory-safety, infra-as-code exposure, TLS/CI security) — a judgment `record_gate_skip` (false positive, trivial, etc.) is **denied** while any floor hunk is still **unreviewed**, and a recent *unrelated* review doesn't release them either — the recent-pass shortcut is disabled whenever a floor hunk is uncovered. To release a floor change:

- **Match the tool to the situation.** A **genuine** floor change you want reviewed → `audit_coding` (a PASS clears it — the recommended review for a real auth/secrets/money/migration/guard change). You believe the gate **mis-fired** (a false positive) → `confirm_floor` (**free**, one budget model) or `synthesize_coding` (a ~15–30s panel) — each mints a **SYNTH_CONFIRM** and releases the gate **only if it agrees the change is token-shape noise / low-risk**; if it finds the change material, run `audit_coding`. `deliberate_coding` is for still-open designs; it does **not** release a floor change.
- **Forward the `gate_context_id` the gate printed.** Coverage then binds to the gate's own recorded hunks, so a genuinely-reviewed change clears even if the diff drifted by a character (a smart-quote, an em-dash) — no more "I reviewed it but it's still blocked." On any **write**-gate block the gate also prints a `target_hunk_hashes` line — pass it too (whole, verbatim), binding coverage to exactly those hunks even when the diff shape differs.
- **Sustained outage.** Under a *sustained* review-tool outage the gate asks a **human** to approve (the agent can't skip a floor change past it, or approve its own prompt). This human gate is **best-effort in automation**: interactively a real human decides, but in a non-interactive context (`bypassPermissions` / `dontAsk`, or a headless `-p` run) Claude Code auto-proceeds the prompt with no human present. TruVerifAI logs every prompt with the raw `permission_mode` and the admin dashboard labels it honestly (`human_prompted` vs `auto_proceed_noninteractive` vs `unknown`) rather than claiming a human always decided.
- **Applied a review's findings and got re-blocked on the floor?** (gate-usability Wave 3) Applying the audit's recommendations changes the bytes, so the commit gate re-fires — and compliance is never penalized: `record_gate_skip(recommendations_applied, gate_context_id)` now releases the **floor hunks too**, in the same single free call the non-floor path has always had. Guardrails: a real review of this repo must be on recent record (lineage-verified — a prior skip/defer token never qualifies), the release binds only that fire's own hunks, it expires in **minutes**, and the receipt is logged distinctly as **"findings applied (revision not re-reviewed)"** — your dashboard can always tell it from an audited PASS or an accept-risk override.
- **Merging an already-reviewed branch?** (Wave 3) A merge commit re-presents branch content whose per-commit receipts don't hash-match the merge diff. On a **merge** fire the gate offers `record_gate_skip(branch_already_reviewed, gate_context_id, reason_text=<which PRs/commits reviewed it>)` — merge fires only (server-enforced), non-floor hunks only; conflict-resolution or otherwise NEW floor content still needs a real PASS.
- **Cosmetic drift no longer re-blocks.** (Wave 2b) Coverage now also matches on a **normalized** tier (em-dash/smart-quote folding, never inside string literals) when the strict hashes miss — an ASCII-vs-unicode punctuation re-edit of covered code releases instead of re-firing. Every block response also carries machine-readable `release_options` with the `gate_context_id` pre-filled.
- **Suspension.** If a reason code's skips keep preceding real findings, a maintainer can **suspend** that code per repo (off by default) — a suspended skip is denied.
- **Last resort — only after the real paths above genuinely don't fit** (the gate mis-fired, you're deadlocked, or you're consciously shipping un-reviewed and accepting responsibility), `record_gate_skip(accept_risk_no_review, gate_context_id, reason_text=<pre-mortem>)` ships the floor change *un-reviewed* and releases **both** gates — as a logged, accountable **override**, not a review. Not a shortcut on a genuine change. It requires a substantive pre-mortem, is bound to the one gate fire, expires in minutes, lands a distinct row on the admin dashboard for the human to review after the fact, and never releases a gate-self change.

**One review call per change (the single-call model).** The agent never needs to call TruVerifAI more than once for a given change:

- **PASS → proceed.** Ideally write exactly what you reviewed; if you modify the content after a PASS (even a comment) the gate re-fires on the changed bytes, released by `record_gate_skip(recommendations_applied, gate_context_id)` — no second review.
- **Findings → apply + log.** Apply them and call the same `recommendations_applied` (server-verified against the review that ran).
- **A batch → defer.** For successive risky edits (e.g. a multi-file migration), `record_gate_skip(review_deferred_to_commit, gate_context_id)` defers all review to the **commit gate** and silences the write gate for the session (~1h) — the commit gate then re-classifies the whole staged diff and still demands a real PASS for every floor hunk, so nothing ships unreviewed. Deferral is for batches; a one-off change should just be reviewed and proceed.

The dashboards count these two outcomes separately from skips — a review ran, or you postponed it; neither is a waived review.

A **purely inert** edit (comment/whitespace only) to one of the gate's *own* files releases automatically without a review — *unless* it touches the gate's core (the classifier, the decision logic, the hooks, or the plugin config), which always require a real review even when the edit looks trivial.

**The gate aims to fire only when it should (precision, recall-safe).** It **ignores writes outside your repo** and to scratch/temp dirs (they can't ship — except a real secret value, which always fires). **Docs and prose don't fire** on a keyword unless they contain a real secret value. And an auth *mention* — a `role`/`session`/`permission` identifier in ordinary code — is at most an advisory nudge, while an auth *action* (a permission decorator, an auth/credential check, a real secret) still blocks. These cut the false-positive walls without lowering recall on genuine risk.

Options, set in `/plugin` → **Installed** → **AI Panel Review** → **Configure options** (type the value, then `/reload-plugins`):

- **`enable_gates`** (`true` / `false`, default `true`) — turns the gates on or off.
- **`gate_tightness`** (`focused` / `thorough`, default `focused`) — how often **both gates** block (the commit gate *and* the write gate now share this one setting). `focused` blocks only the highest-stakes changes — the floor classes (auth, secrets, billing, migrations, a removed safety check, and other high-severity domains — blocked at **any** confidence) and high-confidence security signals — and downgrades lower-confidence "code-review" changes (API routes, concurrency, network calls, large refactors, error handling) to a non-blocking advisory; `thorough` blocks any risky change that isn't covered. The floor always blocks at both levels.
- **`borderline_mode`** (`advisory` / `synthesize_gate` / `off`, default `advisory`) — how borderline (low-confidence) changes are handled: `advisory` surfaces a fast `synthesize_coding` suggestion **to the agent** (non-blocking; shown once per area per session for the highest-signal "heavy" spikes); `synthesize_gate` soft-gates the highest-signal borderline changes (releasable by a quick `synthesize_coding` or a one-line skip); `off` ignores them. Never hard-blocks.

Advanced (rarely changed):

- **`gate_threshold`** (a whole number entered as text; blank = the built-in per-category thresholds) — a manual override for the classifier's fire threshold. Floor classes always fire regardless.
- **`borderline_sampling_rate`** (`0.0`–`1.0`, default `0.5`) — fraction of the highest-signal borderline spikes that soft-gate when `borderline_mode='synthesize_gate'`; the rest degrade to advisory.
- **`borderline_session_budget`** (integer, default `3`) — max borderline soft-gates per session before the rest degrade to advisory (only applies under `synthesize_gate`).

## Pricing

Tool invocations are billed against your TruVerifAI account. Pricing at https://truverif.ai/pricing. Approximate per-call cost: synthesize ~$0.04, deliberate ~$0.20, audit ~$0.20. Latencies: synthesize ~15-30s, deliberate/audit ~2-5 min.

## Cross-platform install (non-Claude-Code users)

For Codex CLI / Gemini CLI / Cursor: see `install-cross-platform.sh` in the plugin directory. Cursor users invoke skills manually (`/skill-name`) — Cursor doesn't have native auto-discovery yet, so the plugin's value on Cursor is reduced to "well-curated reference material for invoking TruVerifAI MCP via your existing MCP client."

## Known limitations

### Run `/reload-plugins` after the plugin updates (or the gates run stale)

Claude Code does **not** hot-reload plugin hooks after an auto-update: a session that was already running when the plugin updated keeps the **previous** version's gate hooks loaded until you run `/reload-plugins` or restart. The gates then run the older classifier. A blocked-gate message **stamps the version it ran** and, if it detects it's a superseded version, prints a `⚠️ running a SUPERSEDED version — /reload-plugins` warning — so staleness is visible rather than silent. **After any plugin update, run `/reload-plugins`** (Claude Code prunes the old cached version on its own once no session is using it; you don't need to delete anything).

### No in-progress display during multi-minute calls (Claude Code regression)

In current Claude Code builds (v2.1.116+, April 2026 onward), the UI shows only `"Calling panel-review..."` during a long-running MCP tool call and suppresses progress notifications until the call returns. Our server emits progress events correctly on the wire — Claude Code receives them but doesn't render them mid-call. This is tracked at [anthropics/claude-code#51713](https://github.com/anthropics/claude-code/issues/51713) and affects every MCP server, not just ours.

What you'll see:
- `synthesize_*` (15-30s) — brief "Calling panel-review..." then the response.
- `deliberate_*` / `audit_*` (~2-5 min) — a longer "Calling panel-review..." window with no visible progress, then the response.

Workarounds while waiting for the upstream fix:
- Trust the call is running — we have a 600s server-side deadline, so it can't hang silently forever.
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
