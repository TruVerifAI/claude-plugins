# Changelog

All notable changes to the TruVerifAI plugin. Versions match
`.claude-plugin/marketplace.json` and `plugins/panel-review/.claude-plugin/plugin.json`.

## 0.3.2

**Long-running calls survive client tool-call timeouts (continuation).**
`deliberate_*` and `audit_*` run several minutes — longer than the tool-call timeout
most MCP clients enforce (~60s on many clients; 300s on Claude Code v2.1.187+). A long
call may now return a holding response — `{ "status": "in_progress",
"continuation_token": "…" }` — before it finishes; the agent re-invokes the same tool
with only that token until the verdict returns. The orchestration keeps running on the
server between calls and credits are charged once, on completion. Most agents handle
this automatically from the `next_step` instruction in the response. (The continuation
logic is server-side; this plugin release is the descriptive copy in the README and the
audit / deliberate skills.)

## 0.3.1

**Fewer false-positive gate blocks — same risk detection.** The local risk
classifier (the engine behind the proactive coding gates) was re-tuned to stop
walling changes that only *look* risky, with no loss of recall on real risks:

- **Prose & UI no longer trip the gate.** A risk keyword (`auth`, `session`,
  `billing`, …) inside a comment, a string literal, marketing copy, or JSX text is
  recognized as *not code* — so docs, marketing pages, and presentational
  components stop hard-blocking. The same keyword used as real code still fires.
- **Tighter SQL detection.** The bulk-DELETE/UPDATE check now requires real SQL
  shape (`UPDATE … SET`, `DELETE FROM`), so presentational React/TS no longer
  matches.
- **Smarter secret detection.** Placeholder and env-interpolation values
  (`"${DB_PASSWORD}"`, `"your-api-key-here"`) no longer hit the always-on secret
  block; genuine hardcoded secrets — even weak ones — still fire.
- **Proactive-review credit.** If your agent runs `deliberate_coding` on an area
  *before* the deliberate gate fires (optionally passing `relevant_paths`), a later
  deliberate gate on that same area this session is downgraded to an advisory nudge
  instead of blocking — a review you already ran isn't demanded twice. Only the
  directory is recorded, never file contents. The pre-commit `audit` gate is
  unchanged.

No configuration changes; existing settings carry over.

## 0.3.0

**Financial profile — a second profile for high-stakes finance decisions.**

- **New: three financial skills** — `synthesize-financial`, `deliberate-financial`,
  and `audit-financial` — the finance counterparts to the coding trio. They serve
  the full loop (generate / decide / verify) across **any** finance decision:
  trading & investment, valuation (DCF / LBO / comparables), capital allocation
  (M&A / capex / buyback), FP&A / forecasting, credit / lending, and
  accounting / disclosure. They route to the matching `*_financial` MCP tools and
  return a verdict / recommendation / answer_status, severity-tagged findings, and
  a server-derived action. **Information / critique, not advice.**
- **The plugin now ships eight skills across two profiles** (coding + financial).
  The proactive PreToolUse review gates remain **coding-only**; finance is invoked
  through its skills.
- Broadened the coding/finance copy throughout (README, catalog, descriptions).

## 0.2.2

**Gate-skip usability + a more visible second-opinion nudge.**

- **Skipping a gate is now copy-paste.** When a review gate blocks a commit or a
  write, its message prints the exact value to pass to `record_gate_skip` — a
  `hunk_hashes` list (commit gate) or an `area` directory (write gate). No more
  reconstructing the key by hand.
- **Fixed:** a borderline "consider `synthesize_coding`" nudge could route you to
  `record_gate_skip` without the context the server needs, so the skip was rejected.
  It now carries the right key.
- **Stale-version safety.** After the plugin auto-updates, a still-running session
  can keep the *old* gate hooks until you reload. A blocked-gate message now stamps
  the version it ran, and warns you to run `/reload-plugins` if it detects it's a
  superseded version. (Run `/reload-plugins` after any plugin update.)
- **More visible borderline nudge.** For low-confidence-but-consequential changes,
  the `synthesize_coding` suggestion is now surfaced to the agent (once per area per
  session, for the highest-signal changes) instead of only the user transcript — so
  a fast second opinion actually gets considered. Still non-blocking; nothing
  auto-approves.

## 0.2.1

**Review-gate correctness fixes** — closes cases where the proactive gates could
release a risky change *without* a real review.

- **Gate-self changes** (edits to the gate's own config/hooks) now require a real
  audit of *that exact change* to proceed. They can no longer slip through on an
  unrelated recent review or a logged skip.
- **Escape valve tightened:** a logged skip of one change no longer briefly
  downgrades every *other* risky commit/write to advisory.
- **Broader commit coverage:** `git commit -a` and `git commit <pathspec>`, and
  commits run with git global options (`git -C <path> commit`, `git --no-pager
  commit`, `git -c k=v commit`, …), are now correctly reviewed — some of these
  previously bypassed the gate entirely.
- Works with the updated TruVerifAI backend; the gate fails *open* (never blocks)
  if it reaches an older backend, so there's no disruption during rollout.

No changes to tools, skills, configuration options, or your API key.

## 0.2.0

**Plugin renamed to `panel-review` ("AI Panel Review").** The installable plugin
is now `panel-review` — install with `/plugin install panel-review@truverifai`.
Only the *plugin* changed; the MCP server, the `truverifai` marketplace, your API
key, and the `mcp__truverifai__*` tools are all unchanged.

- Skills dropped the `truverifai-` prefix: `audit-before-commit`,
  `deliberate-before-implementing`, `synthesize-quick-check`,
  `record-outcome-after-acting`, `skip-gate-when-not-needed`.
- Setup command is now `/panel-review:setup`.
- Reviewed and tightened all five skill texts (severity/action-floor
  consistency, clearer triggers, removed misleading latency numbers).

**Upgrading from `truverifai`:** the plugin id changed, so install the new one and
remove the old: `/plugin uninstall truverifai@truverifai`, then
`/plugin install panel-review@truverifai`, then `/reload-plugins`.

## 0.1.17

**Friendlier review-gate messages.** When a gate pauses a commit or write
for review, the message now leads with the value ("TruVerifAI flagged a
high-risk change for a quick review …") instead of reading like a plugin
error. The actionable steps (which tool to run, or how to log a skip) are
unchanged, and a short positive note now accompanies the block. (Claude Code
still renders a blocked tool with its own "Error"/red styling — that's the
client's, not the plugin's — but the message text itself is now constructive.)

## 0.1.16

**Adherence telemetry config removed.** The commit-based "adherence card" was
retired (superseded by the gate-based review/skip metrics and the outcome Impact
card), so the `enable_adherence_telemetry` plugin option is removed — it only added
confusion with no user-visible payoff. The `commit-detected` PostToolUse hook now
defaults to **off**: it no-ops unless that timing-telemetry env var is explicitly
set. Only timing was ever reported (never commit content), and nothing else changes
about how the gates or skills work.

## 0.1.15

**Two review-gate fixes (hooks only).**
- **Scoped untracked-file checking.** The audit commit-gate used to classify *every*
  untracked file in your working tree, so a bare `git commit` (or `git commit -a`)
  could be blocked by unrelated files it wasn't even committing. It now only looks at
  the untracked files the commit's own `git add` actually stages — bare commit → none,
  `git add path` → that path, `git add .` → all.
- **Gate-config changes are reviewable, not a dead end.** A commit/write touching the
  gate's own config or hooks used to be blocked unconditionally with no way to proceed.
  It now still always requires a review (privilege-escalation safety), but releases
  normally once you run the suggested audit/deliberate — it cannot be released by a
  skip.

## 0.1.14

**Two-channel risk classifier for the review gates.** The PreToolUse gates'
local risk classifier is rebuilt: it now recognizes risk across many domains —
web (auth, billing, secrets, migrations, API), infrastructure-as-code, embedded,
ML/data, mobile, systems — and scores risky **deletions** (e.g. a removed
permission or validation check), not just additions. Far fewer false positives on
docs/config/test files; far better recall on non-web code. Privacy and fail-open
posture unchanged (only a repo fingerprint + hunk hashes leave the machine).

**New `record_gate_skip` MCP tool.** An agent can release a gate without running
the review by logging a one-line skip-with-reason (structured `reason_code` +
optional `reason_text`). A gate releases on a passing review **or** a logged skip.
Free — no credits; the reason is logged to improve the classifier.

**New `borderline_mode` config** (`advisory` default | `synthesize_gate` | `off`).
Low-confidence "borderline" changes route to a fast `synthesize_coding` second
opinion instead of the heavier deliberate block. Never hard-blocks.

**Gate hardening.** Untracked-file coverage at commit time; gate self-mutation
detection (a write to the gate's own config/hooks is always flagged).

**Wider risk coverage + tunable gates.** Added embedded/firmware signals
(register writes, ISR/HAL/RTOS, `.ld`/`.dts`), bulk `DELETE`/`UPDATE`-without-WHERE,
removed-conditional and large-change significance. New **advanced** config knobs:
`gate_threshold` (raise to fire less in a noisy repo — *floor-bounded*, so
auth/secrets/migrations/removed-checks and hardcoded secrets always fire and the
gate can't be silently disabled this way), plus `borderline_sampling_rate` and
`borderline_session_budget` to throttle the `synthesize_gate` soft-gate on
high-volume codebases. These throttles only *relax* the soft-gate (sampled,
session-capped, and fail-open to advisory) — they never add hard blocks. The skip
log now records the classifier signal (no source) so skips can improve the
classifier over time.

## 0.1.13

Finding B — `action` derived from the per-primitive verdict / recommendation /
answer_status + severity-tagged `findings[]`, not the (auxiliary) agreement
score. Skills + README reframed to the v3 response shape. Audit-gate staged-diff
fallback so `git add X && git commit` / `git commit -a` are covered.

## 0.1.12

Audit commit-gate fix: read the working-tree diff vs HEAD when nothing is staged,
so inline-staging commits no longer slip through with an empty diff.

## 0.1.10

Reverted a `userConfig` `enum` field that failed plugin load (Claude Code
userConfig has no `enum`); `deliberate_mode` stays a typed string.
