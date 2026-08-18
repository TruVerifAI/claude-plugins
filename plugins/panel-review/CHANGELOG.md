# Changelog

## 0.19.38 (round-3 findings batch)

Every finding from the four-platform 0.19.37 test round, fixed:

- **One paid review now covers both gates, from any session.** The write
  gate keys review receipts to the TARGET file's repo instead of the
  session's working directory — a session rooted outside the repo no longer
  double-charges a second audit for the same change.
- **The git pre-commit hook runs the shared launcher** (`node run_gate.js`)
  — interpreter record + self-heal + honest give-ups, replacing the hook's
  own python search (which silently allowed on python2 boxes and exhausted
  searches). A real deny blocks (exit 21 through the stack); any ERROR still
  fails open — but loudly, printing why into git's own output.
- **Dead gate code is loud now**: with gate code missing or crashing, Claude
  Code gets a model-visible "this action was NOT gated (fail-open)"
  advisory; other hosts keep a clear stderr line.
- **Advisories carry the version stamp** (fail-open + tightness), the
  doubled "TruVerifAI: TruVerifAI" prefix is gone on every host, and the
  tightness advisory points at the real user-run switch.
- **macOS: init sets the plugin api_token automatically** (guarded Keychain
  write, verified after write; falls back to a manual path that names the
  true cause) — and doctor reads the Keychain, so the tools row is finally
  honest (present / missing / cannot-verify).
- **init enables marketplace auto-update** (respecting an explicit off) and
  **updates an existing Claude plugin install** (`claude plugin update`) —
  re-running `npx @truverifai/init@latest` now refreshes every layer.
- Empty MCP config files (Antigravity's zero-byte stub) initialize instead
  of being refused; a genuinely corrupt file refuses loudly (✗).
- The commit-block recovery instruction is untracked-aware
  (`git add -N . && git diff HEAD`).
- `doctor`/`init` exit 0 when the gates are healthy (tools rows can be ✗
  without failing scripts); `--strict` restores any-✗ = 1.
- Cursor install copy matches verified delivery (the IDE write gate denies
  first).


## 0.19.37 (cross-OS round 2)

The reliability release for the failures found by the first external installs
(Windows Store-alias crash X13, the macOS trust-store outage, the Mac
review-tools disconnect).

- **The launcher never searches for Python in its own process.** `init`
  resolves the interpreter once (sacrificial child probes; the MS Store
  placeholder is rejected by its 9009 exit), proves it can run real gate code,
  and records ONE absolute path in `~/.truverifai/python-path.json`. Hooks
  read the record; a stale record heals out-of-process (fingerprint + time +
  failure-cap back-off, heal-and-continue) — the crash path that killed every
  gate on one external user's machine is structurally unreachable.
- **Fail-open messages now say WHY.** `gate_lib` keeps the last transport
  error (secret-redacted, URL reduced to host) and appends it to every
  fail-open advisory and the self-check — the macOS
  `CERTIFICATE_VERIFY_FAILED` mystery becomes a one-line read.
- **Vendored Mozilla CA bundle as a TLS fallback** — engages only on
  certificate-verification failure, so a machine with a broken Python trust
  store still reaches the gate endpoint.
- **`init` runs the gate self-check at install** and fails loudly instead of
  printing success over a dead install.
- **Mac review-tools connect honestly**: the Keychain is probed
  (found/absent/unavailable) instead of inferring "Claude Code has not run"
  from a missing `.credentials.json`; failures are a `✗` with a true cause and
  a working instruction.
- **Antigravity gets its own review-tools entry**
  (`~/.gemini/config/mcp_config.json`, `serverUrl`) and its own doctor row —
  no more gates-without-exits on that platform.
- The plugin panel now holds only `api_token`; all gate behaviour moved to
  `npx @truverifai/init gates ...` / the `/panel-review:gates` command (X10).
- Gate code installs are now staged, verified, and swapped in two renames — an
  interrupted install can no longer leave the machine silently ungated; `init`
  recovers leftover swap state on startup.
- The post-commit backstop notice now carries the `(TruVerifAI gate vX)` stamp,
  and the update nudge renders on ordinary clean commits (24h-capped, verdict
  cached across processes), not only when a gate blocks you.
- **`run_gate.sh` removed** (it has been dead weight since 0.19.32, when the
  launcher moved to `node run_gate.js`). If your hook configs predate 0.19.32
  and still reference the `.sh`, those hooks were ALREADY broken — re-run
  `npx @truverifai/init@latest` to rewrite every config.
- `doctor`: reports the recorded absolute interpreter path (a bare `python3`
  is now a failure), labels the node-client connectivity rows, and adds a
  `[gate endpoint]` row measured over the exact route the gates use.
- Hardening from the round's adversarial review: the launcher fails open (not
  exit 1) when its resolver module is missing; a gate script that crashes at
  runtime can no longer defeat the repair back-off; apostrophe-safe
  interpreter probes; installer cleanup can never throw from a catch block.

## 0.19.36

- **Packaging fix, no behaviour change.** `hooks/run_gate.cmd` had been
  published LF-only. The rule that keeps it CRLF lived in the monorepo's root
  `.gitattributes`, which is never copied into this repo — so git stored the
  file LF and every published copy since has been LF. `cmd.exe` cannot parse an
  LF-only batch file; it executes fragments of it. The rule now ships inside the
  bundle, so the published copy is CRLF again.
- Nothing else in this release differs from 0.19.32. `run_gate.cmd` is not
  invoked by anything today — hook commands run `node run_gate.js` — so this
  corrects a latent packaging defect rather than a live failure.

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
