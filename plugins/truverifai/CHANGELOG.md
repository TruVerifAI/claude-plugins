# Changelog

All notable changes to the TruVerifAI plugin. Versions match
`.claude-plugin/marketplace.json` and `plugins/truverifai/.claude-plugin/plugin.json`.

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
