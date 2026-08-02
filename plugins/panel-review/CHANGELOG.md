# Changelog — AI Panel Review (Claude Code plugin)

## 0.19.15

**Fix: the post-commit backstop was silently dead — resurrected.** An
entry-point bug (`g.host_run(main)` with `gate_lib` imported only inside
`main()`) made the backstop and its pre-side HEAD stash crash with a
NameError on every invocation since the cross-platform refactor; the
fail-open design masked it completely. The fused `create-a-file && git
commit` bypass advisory works again. A new regression suite executes every
gate script as a real subprocess so this class of bug cannot ship again.

Also in this release (shared gate core, aligned with CLI 0.19.15):
- Hook stdin is decoded with `utf-8-sig` — hosts that BOM-prefix the
  payload (observed on Cursor/Windows) no longer cause a silent fail-open.
- Cursor host adapter: top-level `command` payloads normalized, URI-style
  `workspace_roots` (`/C:/...`) mapped to real paths, strings-only cwd
  hardening, native `ask` support, and a `post_commit_backstop` advisory
  channel via `postToolUse` (`additional_context`).
- `run_gate.js` node launcher vendored for shell-agnostic hook commands.

## 0.18.0 (unreleased) — superseded by 0.19.15

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
