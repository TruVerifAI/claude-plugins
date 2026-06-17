"""Shared library for the TruVerifAI proactive-invocation PreToolUse gates.

Pure stdlib (urllib, subprocess, hashlib) so it runs anywhere python3 does, with
no pip installs — matching the plugin's "drop-in" promise.

Design (docs/MCP/adoption solve/proactive-invocation-v2-hybrid.md):
- The gate classifies the change LOCALLY (vendored risk_classifier) and sends the
  backend only a repo *fingerprint* + hunk content *hashes* — never source.
- It NEVER hard-fails the agent on our own infra: missing python/token, network
  errors, or our server being down all FAIL-OPEN (allow). The escape valve
  (`recent_pass`) ensures a hash/area *misalignment* also can't deadlock.
- The decision functions here are pure and unit-tested; the hook drivers
  (audit_gate.py / deliberate_gate.py) just do I/O + translate the decision into
  a PreToolUse output.
"""

import hashlib
import json
import os
import random
import re
import shlex
import subprocess
import sys
import tempfile
import urllib.request

from risk_classifier import (  # vendored, same dir
    classify_diff,
    hunk_content_hash,
    clamp_threshold,
    # Gate-self detection + the synthesized self-coverage hash live in the vendored
    # classifier so the client gate and the SERVER receipt writer agree byte-for-byte.
    is_gate_self_mutation,
    diff_touches_gate_self,
    gate_self_coverage_hash,
    GATE_SELF_HASH_PREFIX,
)


DEFAULT_BASE_URL = "https://api.truverif.ai"


# ---------------------------------------------------------------------------
# Config (from plugin userConfig env vars, with safe fallbacks)
# ---------------------------------------------------------------------------

def config():
    return {
        "token": os.environ.get("CLAUDE_PLUGIN_OPTION_API_TOKEN", ""),
        "enabled": os.environ.get("CLAUDE_PLUGIN_OPTION_ENABLE_GATES", "true") == "true",
        "base_url": os.environ.get("CLAUDE_PLUGIN_OPTION_API_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
        # Per-confidence demotion (v2-hybrid §11.1): 'tiered' (block high-confidence,
        # advisory low — the default), 'block' (block all risky), or 'advisory'
        # (never block deliberate).
        "deliberate_mode": os.environ.get("CLAUDE_PLUGIN_OPTION_DELIBERATE_MODE", "tiered"),
        # Borderline (low-confidence) tier routing to synthesize (design §6.5):
        # 'synthesize_gate' (soft-gate Borderline-Heavy -> synthesize_coding),
        # 'advisory' (surface a suggestion only — the default until the F-001
        # output-quality pre-validation passes), or 'off' (ignore borderline).
        "borderline_mode": os.environ.get("CLAUDE_PLUGIN_OPTION_BORDERLINE_MODE", "advisory"),
        # Floor-bounded trigger-threshold override (F-011, §4.3): a user may RAISE the
        # threshold to cut borderline noise in a noisy repo. clamp_threshold() pins it to
        # [borderline_low+1, ceiling] so the must-fire signals (auth/secrets/migration/
        # removed-guard) always fire — the gate can't be silently disabled this way.
        # Empty -> config default.
        "trigger_threshold": os.environ.get("CLAUDE_PLUGIN_OPTION_GATE_THRESHOLD", ""),
        # §6.5 borderline throttles (only active when borderline_mode='synthesize_gate'):
        # fractional sampling of Heavy events + a per-session soft-gate budget cap. Keep
        # the trigger rate flat on a high-volume band (design §6.5 "three throttles").
        "borderline_sampling_rate": _parse_rate(
            os.environ.get("CLAUDE_PLUGIN_OPTION_BORDERLINE_SAMPLING_RATE", ""), 0.5),
        "borderline_session_budget": _parse_int(
            os.environ.get("CLAUDE_PLUGIN_OPTION_BORDERLINE_SESSION_BUDGET", ""), 3),
    }


def _parse_rate(val, default):
    try:
        r = float(val)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, r))


def _parse_int(val, default):
    try:
        return max(0, int(val))
    except (TypeError, ValueError):
        return default


def effective_threshold(cfg):
    """The clamped (floor-bounded) trigger threshold to hand classify_diff, or None
    for the config default (F-011)."""
    return clamp_threshold(cfg.get("trigger_threshold", ""))


# Structured skip reason codes (design §5.2). The agent releases a gate by acting
# OR by recording a skip with one of these + free-form text (the free-form is the
# training signal for the §3.4 classifier-improvement model).
SKIP_REASON_CODES = (
    "false_positive_not_risky",
    "trivial_change",
    "already_reviewed_this_session",
    "reviewed_outside_truverifai",
    "generated_or_vendored_code",
    "test_or_docs_only",
    "time_critical_hotfix",
    "disagree_with_classification",
    "tool_unavailable",
    "other",
)


# ---------------------------------------------------------------------------
# Git / repo helpers
# ---------------------------------------------------------------------------

def _git(args, cwd):
    try:
        out = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=5,
        )
        return out.stdout if out.returncode == 0 else ""
    except Exception:
        return ""


def repo_fingerprint(cwd):
    """A stable, non-identifying repo id shared across hook + receipt. Prefer the
    origin remote URL; fall back to the repo top-level path. Hashed so no URL or
    path leaves the machine."""
    basis = _git(["remote", "get-url", "origin"], cwd).strip()
    if not basis:
        basis = _git(["rev-parse", "--show-toplevel"], cwd).strip() or (cwd or ".")
    return "repo_" + hashlib.sha256(basis.encode("utf-8", "replace")).hexdigest()[:24]


def staged_diff(cwd, command=""):
    """Return the diff the imminent commit will record.

    `git diff --staged` is correct ONLY when files are already staged by a prior
    SEPARATE `git add`. But this is a PreToolUse hook — it fires BEFORE the Bash
    command runs, so `git add X && git commit`, `git commit -a`, and
    `git commit <path>` all leave nothing staged at hook time. The old code then
    saw an empty diff and waved the commit through — the exact gap that let risky
    commits slip past (the whole reason the audit gate "never triggered").

    When nothing is staged, fall back to the full working-tree diff vs HEAD so the
    about-to-be-committed change is still classified. Over-inclusion (flagging a
    tracked change a path-scoped commit won't include) is the SAFE direction for a
    risk gate; under-inclusion (the old behavior) is not.

    Brand-new UNTRACKED files don't appear in `git diff HEAD`, so we ALSO synthesize
    add-diffs for the untracked files THIS commit will stage (design §6.1 loophole
    closure) — but ONLY those. `command` is the Bash command being gated; the
    untracked sweep is scoped to what a `git add` in that same command stages
    (`git add X && git commit` -> just X; `git add .`/`-A` -> all). A bare
    `git commit` / `git commit -a` stages no untracked files, so we sweep NONE —
    otherwise pre-existing untracked working-tree cruft (eval fixtures, screenshots)
    gates an unrelated scoped commit (the over-inclusion bug).

    A `git commit -a` / `git commit <pathspec>` records WORKING-TREE content that is
    NOT in the index (it stages inline, after the hook fires). If something else was
    already staged, `git diff --staged` would be non-empty yet MISS those worktree
    changes -> under-coverage. So when the commit targets the worktree
    (`commit_targets_worktree`), classify `git diff HEAD` (HEAD..worktree, a superset
    of both the index and the inline-staged content) rather than the index alone.
    """
    if commit_targets_worktree(command):
        base = _git(["diff", "HEAD"], cwd)
    else:
        staged = _git(["diff", "--staged"], cwd)
        base = staged if staged.strip() else _git(["diff", "HEAD"], cwd)
    return base + _untracked_diff(cwd, command)


# Max bytes we'll read from an untracked file to synthesize a diff. Large/binary
# files are skipped — the gate is for source-shaped changes, and we never want a
# blocking hook to choke on a multi-MB artifact.
_UNTRACKED_MAX_BYTES = 200_000

# Sentinel: a `git add .` / `-A` / `--all` stages every untracked file.
_ADD_ALL = "ALL"


# ---------------------------------------------------------------------------
# Git command parsing — robust to GLOBAL options before the subcommand.
# `git -C <path> commit`, `git --no-pager commit`, `git -c k=v commit`,
# `sudo git commit`, ... all invoke commit, but a naive `git\s+commit` regex
# misses them. If the gate's command filter / add-scope / worktree check were
# fooled by a global option, the commit would BYPASS THE GATE ENTIRELY (audit
# F-001, 2026-06-17). All three share this parser so none of them is fooled.
# ---------------------------------------------------------------------------

# git GLOBAL options (BEFORE the subcommand) that consume the NEXT token as a value
# (space-separated form). The `=`-joined form (`--git-dir=.git`, `-C=foo`) is a single
# token that starts with `-`, so it's handled by the generic flag branch (i += 1) — do
# NOT special-case it here, or the embedded value would wrongly skip the following token.
_GIT_GLOBAL_VALUE_OPTS = frozenset({
    "-c", "-C", "--git-dir", "--work-tree", "--namespace", "--super-prefix",
    "--config-env", "--exec-path",
})

# `git commit` options that CONSUME the next token as their value, so that token is not
# a pathspec. (`=`-joined forms like `--message=x` and short-bundled `-mx` are single
# tokens that start with `-`, so they're handled as flags without special-casing.)
_COMMIT_VALUE_OPTS = frozenset({
    "-m", "--message", "-F", "--file", "-C", "--reuse-message", "-c", "--reedit-message",
    "--author", "--date", "-t", "--template", "--fixup", "--squash", "--trailer",
})

# Identity sentinel (compared with `is`, NOT ==): a segment that mentions git + a target
# subcommand but can't be shlex-parsed, so callers take their safe/over-inclusive branch.
_GIT_PARSE_ERROR = object()


def _is_git_token(tok):
    """True if `tok` is the git executable — `git`, an absolute path like `/usr/bin/git`,
    or a Windows `...\\git.exe`. Structural (basename) so we don't lean on the parse-error
    sentinel for a fully-qualified git path (audit F-001)."""
    base = tok.replace("\\", "/").rsplit("/", 1)[-1]
    return base in ("git", "git.exe")


def _segment_git_subcommand_args(seg, subcommands):
    """For ONE shell segment, return (subcommand, args_after_it) if it invokes
    `git <sub>` for some sub in `subcommands` — skipping leading wrapper tokens
    (sudo / env) and git GLOBAL options (incl. value-taking `-C <path>` / `-c k=v`).
    Return (None, None) otherwise. Raises ValueError if the segment can't be parsed."""
    toks = shlex.split(seg.strip(), posix=True)  # may raise ValueError
    gi = next((idx for idx, t in enumerate(toks) if _is_git_token(t)), None)
    if gi is None:
        return (None, None)
    i = gi + 1
    while i < len(toks):
        t = toks[i]
        if t in subcommands:
            return (t, toks[i + 1:])
        if t in _GIT_GLOBAL_VALUE_OPTS:
            i += 2  # global option + its value token
            continue
        if t.startswith("-"):
            i += 1  # other global flag (--no-pager, --paginate, --bare, ...)
            continue
        return (None, None)  # a different git subcommand (git log / status / ...)
    return (None, None)


def _iter_git_subcommands(command, subcommands):
    """Yield (subcommand, args_after) for each shell segment of `command` that invokes
    `git <sub>` for sub in `subcommands`. A segment that mentions git + a target
    subcommand but is unparseable yields (_GIT_PARSE_ERROR, None) so callers fail safe."""
    # NOTE: this split is not quote-aware (a `;`/`&&` inside a quoted commit message splits
    # the segment), but that only makes the segment unparseable -> the sentinel below fires
    # the gate (safe over-inclusion), same as the prior regex approach.
    for seg in re.split(r"&&|\|\||;|\n", command or ""):
        try:
            sub, args = _segment_git_subcommand_args(seg, subcommands)
        except ValueError:
            # unparseable segment: fire safe iff it plausibly invokes `git <sub>`. Word-
            # boundary `git` (not a bare substring, so `/home/digit/...` doesn't match).
            if re.search(r"\bgit\b", seg) and any(s in seg for s in subcommands):
                yield (_GIT_PARSE_ERROR, None)
            continue
        if sub is not None:
            yield (sub, args)


def command_invokes_git(command, subcommands):
    """True if `command` invokes `git <sub>` for any sub in `subcommands` — robust to git
    GLOBAL options (so `git -C repo commit` is NOT mistaken for a non-commit). Used by the
    audit gate's command filter; a parse error counts as a match (the gate then fires and
    classifies the real diff — the safe direction)."""
    for _ in _iter_git_subcommands(command, subcommands):
        return True
    return False


def parse_git_add_targets(command):
    """What untracked paths will a `git add` in `command` stage?

    None when there is no `git add` (bare `git commit` / `-a` stage nothing untracked).
    _ADD_ALL for `git add .` / `-A` / `--all`. Else the explicit path tokens. Robust to
    git global options. Conservative: an unparseable `git add` -> _ADD_ALL (recall-safe).
    """
    saw_add = False
    targets = []
    for sub, args in _iter_git_subcommands(command, ("add",)):
        if sub is _GIT_PARSE_ERROR:
            return _ADD_ALL  # unparseable -> sweep all (recall-safe)
        saw_add = True
        for t in args:
            if t in (".", "-A", "--all", ":/", "*"):
                return _ADD_ALL
            if t.startswith("-"):
                continue  # other flags: -u (tracked only), -p, -f, -v, ...
            targets.append(t)
    return targets if saw_add else None


def commit_targets_worktree(command):
    """True if a `git commit` in `command` records WORKING-TREE content not in the index —
    `git commit -a/--all` (incl. short bundles like `-am`) or `git commit <pathspec>`. For
    those the staged diff under-covers (see staged_diff). A bare `git commit` /
    `git commit -m ...` records only the index. Robust to git global options. Bias-to-True
    (unparseable / ambiguous -> True; over-inclusion is the SAFE direction for a risk gate).
    """
    for sub, args in _iter_git_subcommands(command, ("commit",)):
        if sub is _GIT_PARSE_ERROR:
            return True
        i = 0
        while i < len(args):
            t = args[i]
            if t == "--":
                return i + 1 < len(args)  # paths after `--`
            if t in ("-a", "--all"):
                return True
            if re.fullmatch(r"-[A-Za-z]*a[A-Za-z]*", t):  # short bundle with 'a' (-am, -av)
                return True
            if t in _COMMIT_VALUE_OPTS:
                i += 2  # skip the option AND its value token
                continue
            if t.startswith("-"):
                i += 1  # other no-value flag (-v, --amend, --no-verify, -q, -S, ...)
                continue
            return True  # a bare (non-flag) token = a pathspec -> records worktree content
    return False  # bare `git commit` (index-only) or no commit segment


def _add_covers(spec, rel):
    """True if an untracked `rel` path is staged by the parsed add `spec`."""
    if spec == _ADD_ALL:
        return True
    rel_n = rel.replace("\\", "/")
    for p in spec or []:
        p_n = p.replace("\\", "/").rstrip("/")
        if rel_n == p_n or rel_n.startswith(p_n + "/"):
            return True
    return False


def _untracked_diff(cwd, command=""):
    """Synthesize add-diffs for the untracked files THIS commit stages (scoped to
    the command's `git add`; see staged_diff). Brand-new risky files added by the
    commit are still classified; unrelated working-tree cruft is not."""
    spec = parse_git_add_targets(command)
    if spec is None:
        return ""  # no `git add` in this command -> no untracked files staged
    porcelain = _git(["status", "--porcelain", "--untracked-files=all"], cwd)
    if not porcelain.strip():
        return ""
    out = []
    for line in porcelain.splitlines():
        if not line.startswith("?? "):
            continue
        rel = line[3:].strip().strip('"')
        if not rel or rel.endswith("/"):
            continue
        if not _add_covers(spec, rel):
            continue
        try:
            full = os.path.join(cwd or ".", rel)
            if os.path.getsize(full) > _UNTRACKED_MAX_BYTES:
                continue
            with open(full, "r", encoding="utf-8", errors="strict") as fh:
                content = fh.read()
        except Exception:
            continue  # binary / unreadable / vanished — skip (fail open)
        out.append(synth_write_diff(rel, content))
    return "".join(out)


# Gate self-mutation detection (`is_gate_self_mutation` / `diff_touches_gate_self`)
# and the synthesized self-coverage hash (`gate_self_coverage_hash`) now live in the
# vendored `risk_classifier` module (imported above), so the SERVER receipt writer
# computes the SAME hash for the SAME gate-self diff. Writes targeting the gate's own
# config/hooks can disable it from inside (raise the threshold, empty the signal sets,
# unhook it) — always-risky regardless of content (design §6.1, audit F-005).


def synth_write_diff(path, added_text):
    """Synthesize a unified diff for a Write/Edit so the classifier (which speaks
    unified-diff) can score the content being written."""
    if not path:
        path = "unknown"
    lines = (added_text or "").splitlines()
    body = "\n".join("+" + ln for ln in lines)
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- /dev/null\n+++ b/{path}\n"
        f"@@ -0,0 +1,{len(lines)} @@\n{body}\n"
    )


# ---------------------------------------------------------------------------
# Backend coverage calls (fail-open on any error)
# ---------------------------------------------------------------------------

def _post(cfg, path, body):
    """POST JSON to the backend. Returns the parsed dict, or None on any error
    (the caller fails open)."""
    try:
        req = urllib.request.Request(
            cfg["base_url"] + path,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + cfg["token"],
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def check_audit_coverage(cfg, repo, hunk_hashes):
    return _post(cfg, "/api/mcp/receipts/check", {"repo": repo, "hunks": hunk_hashes})


def check_deliberate_unlock(cfg, repo, area, session_id):
    return _post(cfg, "/api/mcp/receipts/deliberate-check",
                 {"repo": repo, "area": area, "session_id": session_id})


# ---------------------------------------------------------------------------
# Pure decision logic (unit-tested in tests/test_gate_logic.py)
# ---------------------------------------------------------------------------

def audit_decision(classification, check_response, force_risky=False):
    """Return (action, detail). action ∈ {'allow', 'allow_warn', 'deny'}.

    - not risky → allow.
    - network/None response → allow (FAIL-OPEN; never block on our infra).
    - covered → allow.
    - recent_pass (escape valve) → allow_warn (a recent audit passed; hashes
      didn't align, but we don't deadlock).
    - else → deny (route the agent to audit_coding).

    `force_risky` (gate self-mutation, §6.1, audit F-005): treat the change as
    risky even if the classifier found nothing, so a commit touching the gate's
    own config/hooks ALWAYS requires a review — but is RELEASABLE (covered /
    recent_pass / fail-open), not the old unconditional deny (which made the gate's
    own files un-maintainable through the gate).
    """
    if not classification.get("risky") and not force_risky:
        return ("allow", "no risky hunks")
    if check_response is None:
        return ("allow", "coverage check unavailable; failing open")
    # `covered` is only meaningful when there are hunks to cover. A gate-self
    # change may classify to zero risky hunks, and "all of [] covered" is vacuously
    # true — don't let that wave it through; require recent_pass (a real review).
    if classification.get("hunks") and check_response.get("covered"):
        return ("allow", "covered by a prior audit")
    if check_response.get("recent_pass"):
        return ("allow_warn", "a recent audit passed but coverage could not be "
                              "confirmed (hash misalignment) — allowing")
    return ("deny", "uncovered")


def audit_decision_gate_self(check_response):
    """Decision for a GATE-SELF change (a write/commit touching the gate's own
    config/hooks). Return (action, detail). action ∈ {'allow', 'allow_warn', 'deny'}.

    Gate-self changes are the highest-stakes — weakening these files disables the
    gate from inside (privilege escalation). Unlike `audit_decision`, this path
    releases ONLY on `covered`: a real audit/deliberate PASS of THIS exact change
    (its `gate_self_coverage_hash`, written into the receipt by the server). It
    deliberately does NOT honor `recent_pass` or a logged SKIP — a repo-wide recent
    audit of unrelated code, or a one-line skip, must not release a gate-self change
    (Option 4, 2026-06-17 deliberation; closes the gate-self bypass).

    Still FAILS OPEN on infrastructure error (None response) — our own server being
    unreachable must never permanently trap the agent (no-deadlock constraint). The
    real "out" is `audit_coding`/`deliberate_coding` on the change itself → the
    server writes its coverage hash → the retry sees `covered` → released.
    """
    if check_response is None:
        return ("allow_warn", "coverage check unavailable (infra error); failing open — "
                              "review this gate-self change manually")
    if check_response.get("covered"):
        return ("allow", "gate-self change covered by a real audit PASS of this change")
    # Version-skew safety (audit F-001): an OLD server (pre-Option-4) neither reports
    # `gate_self_coverage` support nor writes the gself coverage hash, so `covered` can
    # never become true against it. Hard-denying would DEADLOCK a gate-self change under
    # healthy infra during a server-before-client rollout. Fail OPEN instead (the scoped
    # gate-self protection just isn't active until the server ships) — never trap the agent.
    # Key on the capability flag's ABSENCE, not its falsiness (F-NEW-001): a healthy server
    # always sends True, so a present-but-False value must NOT silently downgrade to
    # allow_warn — only a missing key (an old server) does.
    if "gate_self_coverage" not in check_response:
        return ("allow_warn", "server has not deployed scoped gate-self coverage yet; "
                              "failing open — review this gate-self change manually")
    return ("deny", "uncovered")


def deliberate_decision(classification, check_response, mode, force_risky=False):
    """Return (action, detail). action ∈ {'allow', 'allow_warn', 'advise', 'deny'}.

    Per-confidence tiering (mode='tiered'): high-confidence forks block, low ones
    are advisory. mode='block' blocks all risky; mode='advisory' never blocks.

    `force_risky` (gate self-mutation): the change touches the gate's own
    config/hooks — ALWAYS block until reviewed, regardless of mode/confidence
    (privilege-escalation risk), but RELEASABLE via unlock / recent_pass /
    fail-open (not the old unconditional deny).
    """
    if not classification.get("risky") and not force_risky:
        return ("allow", "no risky design change")
    if check_response is None:
        return ("allow", "unlock check unavailable; failing open")
    if check_response.get("unlocked"):
        return ("allow", "area already deliberated")
    if check_response.get("recent_pass"):
        return ("allow_warn", "a recent deliberation passed; area unverified — allowing")

    conf = classification.get("max_confidence")
    if force_risky:
        blocking = True  # gate-self blocks in every mode until reviewed
    elif mode == "advisory":
        blocking = False
    elif mode == "block":
        blocking = True
    else:  # 'tiered' (default): only high-confidence forks block
        blocking = (conf == "high")
    return ("deny", "uncovered") if blocking else ("advise", "uncovered (low confidence)")


def borderline_decision(classification, mode, sampled=True, area_consulted=False):
    """Decide the BORDERLINE (low-confidence) tier action for the synthesize gate
    (design §6.5). action ∈ {'allow', 'advise', 'deny'}.

    - 'off'             -> never act on borderline.
    - 'advisory'        -> surface a suggestion (advise) for any borderline change.
    - 'synthesize_gate' -> soft-gate Borderline-HEAVY (deny -> route to
                           synthesize_coding OR a logged skip); advise on
                           Borderline-LITE.

    Throttles (design §6.5 — borderline is the high-volume band, so a Heavy spike only
    *soft-gates* when all of these pass; otherwise it degrades to advisory):
    - `area_consulted`  -> a consultation/PASS receipt already exists for this area this
                           session (from check_deliberate_unlock) -> advisory.
    - `sampled`         -> fractional sampling let this event through (else advisory; also
                           the A/B signal for whether the gate adds value).
    The per-session BUDGET cap is the third throttle; it's stateful, so the hook applies
    it (borderline_budget_consume) AFTER a 'deny' verdict here.

    High-confidence changes are handled by the audit/deliberate gate, so this defers
    (allow) on them. Heavy vs Lite is the classifier's spike sub-tier, never primitive
    density (design §4.2/§6.5). Activating 'synthesize_gate' is gated on the F-001
    output-quality pre-validation (design §6.5); default config is 'advisory'.
    """
    if not classification.get("risky"):
        return ("allow", "no borderline risk")
    if classification.get("max_confidence") == "high":
        return ("allow", "handled by audit/deliberate gate")
    tier = classification.get("borderline_tier")
    if mode == "off" or tier is None:
        return ("allow", "borderline tier off")
    if mode == "synthesize_gate" and tier == "heavy":
        if area_consulted:
            return ("advise", "borderline-heavy (area already consulted this session)")
        if not sampled:
            return ("advise", "borderline-heavy (not sampled)")
        return ("deny", "borderline-heavy: synthesize or skip")
    return ("advise", "borderline (%s)" % tier)


def borderline_sampled(rate):
    """Fractional-sampling throttle (design §6.5). True ~`rate` of the time."""
    if rate >= 1.0:
        return True
    if rate <= 0.0:
        return False
    return random.random() < rate


def _borderline_state_dir():
    """A best-effort writable dir for per-session borderline budget counters. Never
    raises — falls back to the system temp dir; the caller fails open if even that
    can't be written."""
    base = os.path.join(os.path.expanduser("~"), ".truverifai", "gate_state")
    try:
        os.makedirs(base, exist_ok=True)
        return base
    except Exception:
        return tempfile.gettempdir()


def borderline_budget_consume(session_id, cap):
    """Per-session synthesize soft-gate budget cap (design §6.5, third throttle).

    Returns True and increments the session's counter if budget remains (< cap);
    returns False once the session has hit the cap (all further borderline degrades to
    advisory). cap <= 0 disables the cap (always True). Fails OPEN (returns True) if the
    counter file can't be read/written — a throttle must never *create* a wall.

    SOFT cap by design (audit F-001/F-002): this counts soft-*gates* (deny verdicts), not
    cheap advisory nudges — advisories are intentionally uncapped. The read-incr-write is
    not locked, so two truly-concurrent same-session hooks could share a slot; PreToolUse
    hooks fire sequentially in practice, and the cap is a backstop (design §6.5), not a
    hard guarantee, so an occasional off-by-one is acceptable and never blocks.
    """
    if not cap or cap <= 0:
        return True
    sid = re.sub(r"[^A-Za-z0-9_-]", "_", str(session_id or "nosession"))[:64]
    path = os.path.join(_borderline_state_dir(), "borderline_budget_%s.json" % sid)
    try:
        count = 0
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                count = int(json.load(fh).get("count", 0))
        if count >= cap:
            return False
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"count": count + 1}, fh)
        return True
    except Exception:
        return True  # fail open — never let the budget file brick the gate


# ---------------------------------------------------------------------------
# Hook input / output
# ---------------------------------------------------------------------------

def gate_signal_line(classification):
    """The compact classifier-signal line for a deny message — the labels the agent
    forwards to record_gate_skip so the skip-log carries what the classifier saw
    (design §5.3). No source content; just version/score/categories."""
    cats = ",".join(classification.get("risk_categories") or [])
    return ('  gate_signal = classifier_version="%s" score=%s risk_categories="%s"'
            % (classification.get("classifier_version") or "",
               classification.get("score") if classification.get("score") is not None else 0,
               cats))


def skip_and_signal(classification, audit):
    """The 'or log a skip' second branch + the gate_signal line for a deny message
    (design §5.1 second branch + §5.3). `audit` selects the gate context the agent
    passes (hunk_hashes for the commit gate, area for the write gate)."""
    ctx = "hunk_hashes (derive from gate_diff)" if audit else "area"
    return (
        "Or, if this genuinely does NOT need review, call `record_gate_skip` (free) "
        f"with a reason_code, gate_repo, and {ctx}; if you skip, forward this too:\n"
        + gate_signal_line(classification)
    )


def read_hook_input():
    try:
        return json.loads(sys.stdin.read() or "{}")
    except Exception:
        return {}


# User-facing one-liner shown alongside the deny via the top-level
# `systemMessage` field (rendered to the user, separate from the model-facing
# `permissionDecisionReason`). Framed positively so a gate reads as TruVerifAI
# doing its job, not erroring. NOTE: the "Error:" label on the blocked tool
# itself is Claude Code's own rendering of a PreToolUse deny and can't be
# changed from a hook; this softens the surrounding message, not that prefix.
_DENY_SYSTEM_MESSAGE = (
    "TruVerifAI flagged a high-risk change for a quick review — run the "
    "suggested check (or log a one-line skip) and it proceeds."
)


def emit_deny(reason, system_message=_DENY_SYSTEM_MESSAGE):
    """Emit a PreToolUse deny so Claude Code blocks the tool and shows the model
    the reason. The model still holds full context and can act on it. A short,
    positive `systemMessage` accompanies the block for the user; the detailed
    `reason` goes to the model."""
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    if system_message:
        out["systemMessage"] = system_message
    print(json.dumps(out))
    sys.exit(0)


def emit_allow(note=None):
    """Allow (defer). For advisory / allow-with-warning, surface a note on stderr
    so it reaches the transcript without blocking."""
    if note:
        sys.stderr.write("TruVerifAI: " + note + "\n")
    sys.exit(0)
