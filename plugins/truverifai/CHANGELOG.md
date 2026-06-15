# Changelog

All notable changes to the TruVerifAI plugin. Versions match
`.claude-plugin/marketplace.json` and `plugins/truverifai/.claude-plugin/plugin.json`.

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
