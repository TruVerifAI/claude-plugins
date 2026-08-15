# Changelog — AI Panel Review (Claude Code plugin)

## 0.19.32

- **The gates now run through Node, not a bare shell script — this fixes the
  gates being silently dead on macOS and Linux.** `hooks.json` invoked
  `${CLAUDE_PLUGIN_ROOT}/hooks/run_gate.sh` with no interpreter, but that file
  ships non-executable (git on Windows cannot record an exec bit), so on any
  POSIX machine the shell answered `Permission denied` — which Claude Code
  treats as a non-blocking error. Every gate allowed everything, with no error
  shown. Windows was unaffected, which is why it went unnoticed. Commands are
  now `node "${CLAUDE_PLUGIN_ROOT}/hooks/run_gate.js" claude_code <gate>.py`,
  the same form Anthropic's own plugins use.
- **`enable_gates` is Claude-Code-scoped, and now says so.** It is delivered as
  an environment variable to the hooks Claude Code spawns, so it cannot reach
  the git pre-commit hook or the Cursor / Codex / Copilot / VS Code / Gemini /
  Antigravity hooks. If you installed those via `npx @truverifai/init`, one
  switch covers all of them: `npx @truverifai/init gates off` (`on`, `status`).
- **`/panel-review:setup` no longer tells the agent to run `python`**, which
  does not exist on macOS 12.3+ or on Debian/Ubuntu without `python-is-python3`.
- **Requirements are now stated:** Python 3 and Node 18+ must be on `PATH`.
- The inert `commit-detected.sh` hook was unhooked (its config option was
  removed some releases ago, so it exited immediately on every invocation).
- **Behavior change for anyone scripting `tvai doctor`:** an intentionally
  disabled gate is now a `!` warning rather than a `✗` failure, so `doctor` no
  longer exits 1 for a supported user choice. Genuine faults still exit 1. If
  you gate CI on `tvai doctor`, check the row text, not only the exit code.

## 0.19.31

- **Server identity is now declared properly instead of inferred.** The plugin
  declared no icon of its own, so a client that wanted one had to scrape the
  `homepage` page for its icon links — and that page, `truverif.ai/mcp`, now
  308-redirects to the Panel Review landing page and served a 15-byte stub with
  no icon links at all. `homepage` now points at the canonical
  `truverif.ai/panel-review`, and the MCP server additionally declares its
  icons and website URL directly in the initialize handshake
  (`serverInfo.icons` / `websiteUrl`, per the MCP spec), so clients are handed
  the URLs rather than left to infer them.
- **Whether that is visible anywhere is client-side and mostly not implemented
  yet.** Most MCP clients do not render icons for third-party servers: Cursor
  staff have confirmed their UI does not render custom MCP server icons, and
  Claude's own surfaces show letter placeholders for custom connectors. This
  release makes the metadata correct and available so it renders wherever
  support lands; it does not by itself put a mark on your screen. No behaviour
  change to the gates or the tools.


## 0.19.30

- **Gate-self WRITE-gate deadlock fully fixed.** 0.19.28 relativized the
  self-coverage hash path but the deny message's diff spec dropped the `@@`
  hunk header, so an agent that followed it verbatim submitted a diff the
  classifier parses to zero content — an audit PASS could never release the
  write. The deny now prescribes the required `@@ -0,0 +1,N @@` line, so the
  reviewed diff hashes identically to the change the gate recorded and the
  write releases on a real PASS. Fail-safe unchanged (any mismatch re-reviews,
  never over-releases). See docs/MCP/Architecture/gate-self-write-deadlock-postmortem.md.
- **Server hardening (defense in depth).** The receipt writer now refuses to
  mint releasing coverage for a degenerate gate-self diff — one that presents
  content headers yet carries no reviewable lines — so a malformed submission
  fails toward a real review instead of a misleading "released". A legitimate
  rename/mode-only gate-self change (no content headers) still releases on a
  PASS as before.


## 0.19.29

- **Fixed a false-positive "gate integrity" tamper warning on Windows (no actual tampering occurred).** `run_gate.js` was hashed raw (not line-ending-normalized) in the tamper-evidence manifest, so a clean install whose `run_gate.js` landed with CRLF line endings falsely reported `modified:run_gate.js` on every invocation. It is now normalized like every other gate file, so a clean install verifies clean. Informational only (the gate always enforced and failed open). **Upgrading resolves it automatically** — the new manifest ships with the update and the self-check re-runs on the next gate invocation; no reinstall step needed.


## 0.19.28

- **Gate-self WRITE-gate deadlock fixed.** The write gate hashed the absolute
  tool-input path into the gate-self self-coverage hash, while the server
  mints its receipt hash from the reviewer's repo-relative diff — so a
  gate-self write could never be released by a real `audit_coding` PASS and
  deadlocked. It now relativizes the path against the git root before hashing
  (`gate_lib.repo_relative_path`), so client and server hashes match. The deny
  message also states the exact all-adds, repo-relative diff shape to submit.
  Total/never-raises and fail-safe: any relativization failure reproduces the
  old mismatch (re-review), never an over-release. The commit gate was
  unaffected. See docs/MCP/Architecture/gate-self-write-deadlock-postmortem.md.
- **Tamper advisory clears user-wide on a verified clean check.** A clean
  reinstall now clears the "gate tampered" advisory promptly instead of
  lingering up to 48h; the post-commit backstop carries the integrity flag.

## 0.19.27

- **Gate-code tamper-evidence self-check.** The plugin now ships a
  `gate_manifest.json` (sha256 of every gate file) and self-verifies on each
  gate invocation. If an installed gate file was modified since install
  (accidental corruption, or an edit outside the review path), the gate warns
  loudly and FAILS OPEN — it never blocks your work, and it reports the state
  to the server so the maintainer can see it. Silent no-op on a clean install;
  older installs (no manifest) are unaffected. No change to the gate contract
  or the classifier.

## 0.19.24

- **The commit gate now follows the commit to the right repo.** Hosts can
  run a shell command somewhere other than the session root — a per-call
  working-directory argument (Codex `workdir`, Gemini `dir_path`, Cursor
  `cwd`, Antigravity `Cwd`), a `cd X && git commit` chain, a
  `cmd /c "cd X && ..."` subshell wrapper (Copilot CLI / VS Code), or
  `git -C`. The gates previously inspected only the session root, so
  commits into nested repos could pass unreviewed (found live on Codex,
  2026-08-05). The gate now emulates the shell's own resolution, validated
  at every step, and falls back to exactly the old behavior on anything
  ambiguous — fail open, never a new block. Receipts bind to the repo
  actually inspected. `tvai doctor` gains a nested-repo drift alarm, and a
  `TVAI_PAYLOAD_LOG` env flag records raw hook payloads for diagnosis.
- **Known behavior:** a subshell command whose quoting is malformed (nested
  unescaped quotes that cmd.exe itself rejects) conservatively keeps the
  old resolution — such commands fail in the shell anyway, so nothing ships
  unreviewed. Not a regression if you see `cwd_source: payload` on them.
- **Deferred:** the `cwd_source` tag is recorded in the local
  `TVAI_PAYLOAD_LOG` only; server-side telemetry needs a paired backend
  change and ships separately. When filing a resolution bug, include the
  payload-log lines.
- **Known limitation:** the VS Code agent's default "new branch" sessions
  run in a git WORKTREE, which only contains TRACKED files — if the
  `.github/hooks/` gate configs are untracked, that session has NO gates.
  Commit the hook config files to your repo to keep worktree sessions
  gated.

## 0.19.23

- **Auto-mode classifier allowlist.** Claude Code 2.1.221 added an
  intent-shaped auto-mode permission classifier that can deny the free
  gate-release calls (`record_gate_skip` pre-review reasons, defers) —
  they pattern-match "skip a safety review". The one-command setup
  (`npx @truverifai/init` 0.19.23+) now writes the fix: a server-scoped
  `permissions.allow` rule (`mcp__plugin_panel-review_truverifai`) in
  `~/.claude/settings.json`, never created/overwritten, additive-only,
  effective in new sessions. `doctor` warns when the rule is missing.
  Manual path: `/permissions` -> allow that rule. No gate-code changes.

## 0.19.22

- **The gates now self-announce updates.** Coverage responses carry an
  additive `gate_update` flag when a newer release exists (the server
  checks the npm registry, cached ~1h, strictly validated); stale clients
  append a one-line, host-aware, agent-actionable nudge to deny messages
  and backstop advisories — at most once per 24h per machine, never
  blocking, fail-silent on every error. `doctor` gains an update row.
  Operator note: the TruVerifAI backend performs a best-effort version
  check against registry.npmjs.org at most ~once per hour per process on a
  background thread (3s timeout, silent on failure) — the gate request
  path never blocks on it. Design: OPTION-B-GATE-UPDATE-NUDGE.md
  (deliberated, unanimous; audit-hardened).

## 0.19.21

- **P1 fix: commits made through Claude Code's native PowerShell tool
  bypassed the commit gate AND the post-commit backstop.** Claude Code on
  Windows ships a PowerShell tool (v2.1.84; the PRIMARY shell since
  ~v2.1.139) but every shell hook matcher said only `Bash`, and the gate
  additionally keyed on `tool_name == "Bash"` — so a PowerShell-routed
  `git commit` matched no hook and would have been allowed even if it had.
  Both layers fixed: matchers widened to `Bash|PowerShell` (commit gate,
  HEAD stash, backstop, commit-detected) and the host adapter renames the
  PowerShell tool to Bash (same `{command}` input shape). The write gate
  was never affected (tool-based, not shell-based). Codex's installer
  matchers widened as insurance. Found by owner-run thorough prod testing,
  2026-08-03.

## 0.19.20

- **Fix (Windows): backslash paths in `git add` bypassed the commit gate's
  untracked-file sweep** — `git add migrations\999.sql; git commit` landed
  ungated (the tokenizer swallowed the backslash). Found live during the
  Copilot certification; fixed with Windows-scoped path normalization and
  regression-pinned. Affected every Windows host.
- The short deny banner now carries the `gate_context_id`, so hosts that
  surface only the one-line banner to the agent stay actionable without
  re-triggering the gate.
- Vendored rules gain a compact "How to operate the tools" section for
  hosts without a skills framework.
- Copilot-family host adapters: shell tools named by shell (powershell/
  pwsh/cmd), JSON-string toolArgs parsing, `file_text` write alias,
  VS Code `runTerminalCommand`. Antigravity: toolCall payload
  normalization, schema-exact deny, dashboard-only backstop emit.

## 0.19.15

- **Fix: the post-commit backstop was silently dead — resurrected.** An
  entry-point bug (`gate_lib` imported only inside `main()`) crashed the
  backstop and its pre-side HEAD stash on every invocation since the
  cross-platform refactor; fail-open masked it. The fused
  `create-a-file && git commit` advisory works again, with a subprocess
  regression suite so the class can't ship again.
- Hook stdin decoded with `utf-8-sig` (BOM-prefixing hosts no longer cause
  a silent fail-open).
- Cursor host adapter: top-level `command` payloads, URI-style
  `workspace_roots` mapping, native `ask`, `postToolUse` backstop channel.
- `run_gate.js` node launcher vendored for shell-agnostic hook commands.

## 0.18.0 — superseded; see 0.19.15/0.19.20

Cross-platform gate core (phase 0). Gate **decisions, wire format, and defaults
are preserved** relative to 0.17.0 under a default environment — with **three
intentional, documented behavior deltas** operators should read:

1. **New config sources (additive).** Every option now resolves through a chain:
   `TVAI_<OPTION>` environment variables (highest priority; the API key's
   canonical name is `TVAI_API_KEY`) → the platform-native mechanism (Claude
   Code `userConfig` env vars, unchanged) → `~/.truverifai/config.json` (written
   by `tvai login`). **If you set none of the new sources, values are identical
   to 0.17.0.** If a `TVAI_*` variable is set in your environment, it now WINS
   over the plugin's configured option — intended for CI/Docker/MDM overrides.
2. **Empty-string `enable_gates` now falls through to the default (enabled).**
   Before: `CLAUDE_PLUGIN_OPTION_ENABLE_GATES=""` (empty, as opposed to unset)
   disabled the gates via a strict `== "true"` comparison. Now an empty value at
   any level is treated as UNSET and falls through — ending with the default,
   **enabled**. If you relied on an empty env var to disable the gates, set the
   option explicitly to `false` instead. (Rationale: a blank override silently
   blanking a security control is the defect class recorded 2026-07-23; unset
   and blank now behave the same.)
3. **The hook launcher always exits 0.** `run_gate.sh` (and the new
   `run_gate.cmd`) no longer propagate the Python interpreter's exit code: the
   gates deny via stdout JSON, never via exit codes, so any non-zero exit is an
   error — and on hosts that fail CLOSED on non-zero exits (GitHub Copilot CLI)
   propagating a traceback would block your edit on our bug. On Claude Code the
   net behavior is unchanged (a crashed gate failed open before and still does);
   only the process exit code differs (0 instead of 1).

Also in 0.18.0:
- The gate code is now generated from a shared cross-platform core
  (`plugin-core/` in the source repo); the hooks tree gains a `host/` adapter
  package. On Claude Code the adapter is the identity mapping.
- Explicitly setting `TVAI_PLATFORM` to an unknown/broken value now disables the
  gates LOUDLY (a `TVAI_GATE_MISCONFIGURED` stderr marker on every hook, and no
  enforcement) instead of silently running Claude Code semantics. Unset remains
  the silent Claude Code default.
- Gate-self tamper protection extended to the new layout (host adapters,
  generator, platforms.yaml, launchers, all platforms' manifest dirs) and now
  covered by an explicit enumeration test.

## 0.17.0

See the marketplace release notes (gate usability waves 1–3, gate_release
visibility, rev-3 applied-floor release, severity calibration).
