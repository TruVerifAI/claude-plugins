# Changelog

All notable changes to the TruVerifAI plugin. Versions match
`.claude-plugin/marketplace.json` and `plugins/panel-review/.claude-plugin/plugin.json`.

## 0.14.0

**The gate no longer blocks code a review already passed.** Three defects, all reaching that same
failure - which is what makes an agent conclude it is deadlocked and ask you to switch the gates
off. No change to the tools, config options, or response shape.

- **The floor deadlock.** Coverage is tracked per hunk, but admission was decided per *fire*: once a
  change contained any floor hunk, the fire was stamped floor-class and stayed that way, so a
  one-line skip was denied *even after the floor had been reviewed* - leaving the ordinary hunks
  with no reachable exit. Admission now keys on **live floor exposure**: clear the floor, and the
  skip that was denied becomes admissible and releases the non-floor remainder.
- **MultiEdit hunk hashes.** A write gate has to synthesize its diff (the bytes aren't on disk yet).
  It was concatenating each edit's diff whole, so the next edit's `+++ b/<path>` header landed
  *inside* the previous hunk - where a `+`-prefixed line is, correctly, read as added content. Every
  hunk but the last hashed wrong, so an `audit_coding` PASS earned at the write gate covered hashes
  the commit gate would never compute, and the commit gate re-blocked the reviewed code.
- **Windows `area` matching.** An area is matched as a string; the server stores `/`-form while the
  write gate sent a raw `os.path.dirname` (`\`-separated on Windows). They could never match, so the
  proactive-review downgrade and the deliberate area-unlock were **silently dead on Windows**.

**Clearer copy where it counts.** The skill text claimed `accept_risk_no_review` "always releases a
floor block" - it does not (never for gate-self) - and the claim sat in the *"never disable the
gates"* paragraph, which is exactly what an agent reads when it feels stuck. The gates now state the
two-bucket model plainly: a floor tool (`confirm_floor` / `synthesize_coding`) releases FLOOR hunks
**only**, so on a mixed change the gate keeps blocking on the ordinary hunks it never touched - read
the `Still uncovered: N floor, M non-floor` line and clear *that* bucket. An `audit_coding` PASS
covers both in one call.

**`record_gate_skip` now requires `gate_context_id`** (breaking; the legacy path is gone). A skip may
only release a gate the server can verify actually fired - a client-supplied hunk list proves nothing
about the hunks it chose to omit. If we fail to issue a gate context, the gate now **fails open**:
that is our bug, not yours, and it must never block you.

## 0.13.0

**Risk-classifier coverage expansion (classifier 2.5.0 -> 2.12.0).** Broadens what the local gate
classifier recognizes, well beyond the Python/JS SaaS shapes it started with, at unchanged precision
(100% recall / 0% false positives across the calibration corpus). No change to the tools, gates,
config options, or response shape - only *what* the classifier detects. Still privacy-preserving:
only a repo fingerprint + hunk content hashes ever leave the machine.

- **New floor classes** (un-skippable blocks): memory-safety sinks (C `strcpy`/`gets`/`strcat`),
  TLS-pinning removal / cert-validation bypass, secret-material paths (`.env`, `.pem`, `secrets/`),
  destructive schema migrations (DROP/TRUNCATE + ORM deletes + removed `downgrade`), CI secret-echo,
  CI pwn-request (`pull_request_target` + untrusted checkout), unsafe ML deserialization
  (`joblib.load`), and PII-redaction removal.
- **Polyglot breadth** - memory-safety, mobile (WebView / App-Transport-Security), embedded, and
  IaC-exposure signals across C/C++/Go/Ruby/PHP/Kotlin/Swift/C#, each with per-language
  false-positive guards (e.g. Ruby `gets`, a role string-literal, a `.free()` method call).
- **Two engine mechanisms** - M1 same-file co-occurrence (catches a guard removed here and re-added
  elsewhere without false-flooring a refactor) and M2 path-gating (a noisy signal scores only on the
  file types where it's real; floors are never path-gated).

## 0.12.0

**Post-commit backstop.** Catches a floor change (auth / secrets / money / migration /
removed-guard) that is **created and committed in one shell command** — which slips past both
pre-commit gates (the write gate only sees Write/Edit tools; the commit gate can't classify a file
that isn't on disk yet).

- **Post-commit backstop hook (new, non-blocking)** — after a commit, classifies the real committed
  diff and, on an uncovered floor hunk that shipped without a review, surfaces a non-blocking
  advisory and logs a dashboard row. It never blocks (it runs after the tool) and never nags twice
  for the same commit. Registered on both `PostToolUse` and `PostToolUseFailure`, so it also catches
  a fused commit whose command exits non-zero (e.g. a rejected `git push`).
- **Isolated pre-commit stash hook (new)** — records the pre-command HEAD so the backstop covers
  every commit a single command made, with fail-safe guards that degrade to the tip commit when it
  can't prove ownership. It emits no decision and always exits 0 — it cannot affect the gates.
- **Dashboards** — an "Unreviewed floor commits" view appears both on your own MCP Usage tab (your
  rows) and the admin surface (fleet-wide). Privacy: repo fingerprint + floor category labels + hunk
  count + a pushed flag only — never diffs, paths, command text, or commit SHAs.

No change to the existing commit/write gates.

## 0.11.0

**Keep the gate installed.** This release accepts a few false positives in exchange for making a
false *floor* block cheap and honest to clear — so there's no reason to disable the gate. A real
auth / secret / money / migration / removed-guard change still never ships un-reviewed.

- **`confirm_floor` (new, FREE)** — clear a *suspected false* floor block with one cheap budget-model
  call. Fail-closed: only an explicit low-risk verdict releases (mints a `synth_floor_confirm`
  receipt); material / uncertain / gate-self / unbound coverage all release nothing. No credits.
- **`accept_risk_no_review` (new skip reason)** — the last-resort, accountable floor override: ships
  the change un-reviewed, requires a substantive pre-mortem, expires in minutes, and lands a distinct
  override row for the human. Generic judgment skips stay denied on the floor.
- **Situation-first floor-release guidance** — the deny messages and skills now say which path to
  use when: `audit_coding` for a genuine floor change (recommended), `confirm_floor` /
  `synthesize_coding` for a suspected false positive, `accept_risk_no_review` only as a last resort.
- **Honest override logging** — when a sustained review-tool outage prompts a human, the raw
  permission mode is recorded so a non-interactive auto-proceed is labeled truthfully, not as a
  human decision.
- **Fewer false floors** — an auth change under `tests/` is advisory (a real secret there still
  floors); `dynamic_code` only fires on a non-const `getattr`/`setattr`.
- **Write gate matches the commit gate** — both now block the same per-hunk floor set and share one
  `gate_tightness` setting. The `deliberate_mode` write-gate option is **retired**
  (`deliberate_mode=block` maps to `thorough`, otherwise `focused`).

Additive and backward-compatible. Requires the matching server deploy.

## 0.10.0

**Single-call review model.** You never have to call TruVerifAI more than once per change, and you
can defer a batch of edits to the commit gate.

- **`recommendations_applied`** — after ONE review, apply its findings (or release a
  PASS-then-modify re-fire) and proceed. Server-verified against a real review receipt, not a free
  skip; a floor hunk is still re-audited at commit.
- **`review_deferred_to_commit`** — defer all review to the commit gate; releases the write gate
  for the rest of the session (~1h) and re-reviews the batch at commit. For successive risky edits
  (e.g. a multi-file migration); a one-off change should just be reviewed.
- **Floor guarantee preserved** — both release a floor change at the write gate but are denied at
  the commit gate, which re-audits every floor hunk on the real staged bytes before it ships.
- Deny messages, skills, and README updated to the single-call flow; the two outcomes show as their
  own rows (separate from skips) on the dashboards. Raised three internal caps so large-but-legit
  inputs classify instead of being silently skipped.

Additive and backward-compatible (an older plugin keeps working). Requires the matching server
deploy for the two new reasons.

## 0.9.1

**Fix a non-ASCII write-gate deadlock (Windows / non-UTF-8 locales).** A floor-class
Write/Edit whose diff contained a non-ASCII character (an em-dash, a section sign, an
accented identifier) could still deadlock: the hook read its input with the platform
locale (cp1252 on Windows, ASCII under a C/POSIX locale) instead of UTF-8, so the
character was mangled before the change was hashed and a correctly-encoded review diff
never matched the gate's own hunks. The hook now decodes its stdin payload AND git
output as UTF-8 on every OS and locale, so the natural-diff (D) release path works for
non-ASCII floor changes too.

- Client-only; no server change. ASCII changes behave exactly as before.
- The commit gate had the same latent decode flaw (it escaped the deadlock only via the
  structural coverage tier); it is now correct at the source too.

## 0.9.0

**Fix the floor write-gate deadlock (for real this time).** A floor-class Write/Edit
(auth, secrets, money, migrations, removed guards) now reliably releases after you run
the review. The write gate classifies the *real* change (a delta), so a natural
`gate_diff` you pass to `audit_coding` matches the gate's own hunks and releases it —
just like the commit gate. And the floor block now prints a `target_hunk_hashes` line:
pass it (verbatim) to `audit_coding` / `synthesize_coding` and coverage binds
deterministically even if your diff's shape differs from the gate's.

- **Floor writes release via `audit_coding` (a PASS) or `synthesize_coding` (a
  SYNTH_CONFIRM).** `deliberate_coding` is for non-floor writes and still-open designs.
- The block message is now prescriptive — it tells you exactly what to run and what to
  pass, and prints `gate_context_id` + `target_hunk_hashes`.
- The floor per-hunk rule is unchanged: a coarse area-unlock or an unrelated recent
  review still can't wave a floor change through — only a review of *that* change does.

## 0.8.0

**The write gate releases on a review.** A risky Write/Edit is finished code, so its
natural review is `audit_coding` (a PASS releases it) or a `synthesize_coding`
SYNTH_CONFIRM — the write gate now reads those receipts, matching the commit gate, so
"I reviewed it but it's still blocked" no longer happens.

## 0.7.0

**Focus the gate on major decisions, not code review.** A new `gate_tightness` setting
(default `focused`) makes the pre-commit gate block only on the highest-stakes changes: the
floor classes (auth, secrets, billing, migrations, a removed safety check) and high-confidence
security signals (crypto, unsafe exec, deserialization, dependency changes, IaC exposure, SQL).
Lower-confidence "code-review" changes — API routes, concurrency, network calls, large
refactors, error handling — become a **non-blocking advisory** instead of a hard block. Set
`gate_tightness=thorough` to keep the previous behavior (block any risky change).

- **The floor always blocks** at both levels — you can't disable it this way.
- **Advisories are visible, never silent.** The agent still sees a note for a downgraded
  change, and it is recorded as neither a block nor a skip.
- On update, existing installs get the lighter `focused` behavior by default; switch to
  `thorough` if you want every risky change to keep blocking.

## 0.6.0

**The drift-tolerant coverage from 0.5.0, now actually reliable.** 0.5.0 promised that a
real review would clear a cosmetically-drifted change — but the binding still missed when
the diff that reached the server was *mangled* (a multibyte char like an em-dash arriving as
mojibake), and on a miss it silently bound to the wrong change, so a review you *did* run
left the change blocked. 0.6.0 makes the coverage hold through that mangling and never binds
to the wrong thing.

- **Coverage survives real multibyte mangling.** Beyond exact and cosmetic-normalized
  matching, a review now also binds by the change's **structure** (which hunks moved, where)
  when the bytes themselves were garbled in transit — so a floor change with an em-dash in a
  comment releases on a genuine review instead of deadlocking. If nothing matches, the review
  records **no coverage at all** (a loud miss) rather than silently binding to the agent's
  re-hashed diff — the failure mode that could mask an unreviewed change.
- **Accurate human-override prompt.** The rare one-click human prompt (an uncovered floor
  change with a recent unrelated pass) now names the real reason — *coverage drift* — instead
  of mislabeling it a tool outage, and logs `floor_uncovered_recent_pass`. It stays a single
  approve/deny click; the agent still can't self-approve it.
- **The fix is visible to the agent.** `ping` (and the server `/health`) now advertise a
  `capabilities` block (`structural_coverage`, classifier/normalization versions), so an agent
  or operator can confirm in one call that the reliable-coverage build is live.

## 0.5.0

**Reliable review coverage + a stricter floor release.** A genuine review now clears a
change dependably even when the diff drifts cosmetically, and the high-stakes "floor" can
no longer be released by an unrelated recent pass.

- **Drift-tolerant coverage.** A real review used to miss its mark when the diff that
  reached the server drifted by a byte (a smart-quote, an em-dash, a reflow) — so a change
  you *did* review stayed blocked. Pass the **`gate_context_id`** the gate prints to
  `audit_coding` / `deliberate_coding` / `synthesize_coding`, and the review binds to the
  gate's own recorded change, so a cosmetically-drifted diff still releases. The audit /
  deliberate / synthesize / skip-gate skills document the new param.
- **The floor is no longer released by a recent unrelated pass.** A 15-minute "recent
  pass" shortcut still releases ordinary changes, but **no longer** a **floor** change
  (auth, secrets, money, migrations, a removed guard) — each floor change is reviewed on
  its own. A human-override backstop catches the rare post-review edge case so nothing
  hard-deadlocks.
- **Trivial plugin-file edits release without a review.** A purely cosmetic
  (comment/whitespace) edit to a non-core gate file no longer triggers a review; the
  enforcement-defining gate files always review.

## 0.4.0

**Higher-stakes review gates + a more precise classifier.** The proactive coding gates
now enforce a hard floor and fire more precisely, and the skills/docs describe both.

- **Floor classes can't be skipped with a judgment call.** For changes touching **auth,
  secrets, money, migrations, or a removed guard**, a one-line `record_gate_skip` (false
  positive, trivial, etc.) is **denied**. Release a floor change by running `audit_coding`,
  or — for a genuine false positive — `synthesize_coding` with `gate_repo` + `gate_diff`,
  which mints a cheap **SYNTH_CONFIRM** (~15–30s) when the panel agrees it's low-risk. Under
  a *sustained* review-tool outage the commit gate asks a **human** to approve (the agent
  can't skip past it). The `audit` / `deliberate` / `synthesize` skills document the
  `gate_repo` / `gate_diff` / `gate_session_id` release params.
- **A reason code can be suspended.** If a skip reason's skips keep preceding real findings,
  it can be suspended for a repo (off by default, maintainer-enabled) — a suspended skip is
  denied and you run the review.
- **Classifier precision (recall-safe).** Fewer false-positive walls with no loss of recall:
  an auth **mention** (a `role` / `session` / `permission` identifier in ordinary code) is now
  at most an advisory nudge, while an auth **action** (a permission decorator, an auth/
  credential check, a real secret value) still blocks. The gate ignores writes **outside your
  repo** or in scratch/temp dirs (they can't ship — except a real secret value, which always
  fires), and **docs/prose** no longer fire on a keyword unless they contain a real secret
  value (which now correctly fires even in a `.md`).

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
