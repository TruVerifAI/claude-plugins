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
import re
import subprocess
import sys
import urllib.request

from risk_classifier import classify_diff, hunk_content_hash  # vendored, same dir


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
    }


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


def staged_diff(cwd):
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

    Brand-new UNTRACKED files don't appear in `git diff HEAD`, so we also synthesize
    add-diffs for them via `git status --porcelain` (design §6.1 loophole closure) —
    a wholly-new risky file (e.g. a fresh `auth.py`) is now classified at commit time.
    """
    staged = _git(["diff", "--staged"], cwd)
    base = staged if staged.strip() else _git(["diff", "HEAD"], cwd)
    return base + _untracked_diff(cwd)


# Max bytes we'll read from an untracked file to synthesize a diff. Large/binary
# files are skipped — the gate is for source-shaped changes, and we never want a
# blocking hook to choke on a multi-MB artifact.
_UNTRACKED_MAX_BYTES = 200_000


def _untracked_diff(cwd):
    """Synthesize add-diffs for untracked files so brand-new risky files are seen."""
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


# Writes that target the gate's OWN config / hooks / plugin dir can disable the gate
# from inside (raise the threshold, empty the signal sets, unhook it). Treat them as
# always-risky regardless of content (design §6.1, audit F-005 — gate self-mutation).
_GATE_SELF_PATHS = re.compile(
    r"(^|/)(risk_signals\.json|risk_classifier\.py|gate_lib\.py|hooks\.json"
    r"|\.claude-plugin/|\.git/hooks/)",
    re.IGNORECASE,
)


def is_gate_self_mutation(path):
    """True if `path` would modify the gate's own config/hooks (a bypass vector)."""
    if not path:
        return False
    return bool(_GATE_SELF_PATHS.search(path.replace("\\", "/")))


def diff_touches_gate_self(diff_text):
    """True if any file in the diff modifies the gate's own config/hooks."""
    for line in (diff_text or "").splitlines():
        if line.startswith("+++ b/"):
            if is_gate_self_mutation(line[6:].strip()):
                return True
        elif line.startswith("diff --git "):
            parts = line.split(" b/", 1)
            if len(parts) > 1 and is_gate_self_mutation(parts[1].strip()):
                return True
    return False


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

def audit_decision(classification, check_response):
    """Return (action, detail). action ∈ {'allow', 'allow_warn', 'deny'}.

    - not risky → allow.
    - network/None response → allow (FAIL-OPEN; never block on our infra).
    - covered → allow.
    - recent_pass (escape valve) → allow_warn (a recent audit passed; hashes
      didn't align, but we don't deadlock).
    - else → deny (route the agent to audit_coding).
    """
    if not classification.get("risky"):
        return ("allow", "no risky hunks")
    if check_response is None:
        return ("allow", "coverage check unavailable; failing open")
    if check_response.get("covered"):
        return ("allow", "covered by a prior audit")
    if check_response.get("recent_pass"):
        return ("allow_warn", "a recent audit passed but coverage could not be "
                              "confirmed (hash misalignment) — allowing")
    return ("deny", "uncovered")


def deliberate_decision(classification, check_response, mode):
    """Return (action, detail). action ∈ {'allow', 'allow_warn', 'advise', 'deny'}.

    Per-confidence tiering (mode='tiered'): high-confidence forks block, low ones
    are advisory. mode='block' blocks all risky; mode='advisory' never blocks.
    """
    if not classification.get("risky"):
        return ("allow", "no risky design change")
    if check_response is None:
        return ("allow", "unlock check unavailable; failing open")
    if check_response.get("unlocked"):
        return ("allow", "area already deliberated")
    if check_response.get("recent_pass"):
        return ("allow_warn", "a recent deliberation passed; area unverified — allowing")

    conf = classification.get("max_confidence")
    if mode == "advisory":
        blocking = False
    elif mode == "block":
        blocking = True
    else:  # 'tiered' (default): only high-confidence forks block
        blocking = (conf == "high")
    return ("deny", "uncovered") if blocking else ("advise", "uncovered (low confidence)")


def borderline_decision(classification, mode):
    """Decide the BORDERLINE (low-confidence) tier action for the synthesize gate
    (design §6.5). action ∈ {'allow', 'advise', 'deny'}.

    - 'off'             -> never act on borderline.
    - 'advisory'        -> surface a suggestion (advise) for any borderline change.
    - 'synthesize_gate' -> soft-gate Borderline-HEAVY (deny -> route to
                           synthesize_coding OR a logged skip); advise on
                           Borderline-LITE.

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
        return ("deny", "borderline-heavy: synthesize or skip")
    return ("advise", "borderline (%s)" % tier)


# ---------------------------------------------------------------------------
# Hook input / output
# ---------------------------------------------------------------------------

def read_hook_input():
    try:
        return json.loads(sys.stdin.read() or "{}")
    except Exception:
        return {}


def emit_deny(reason):
    """Emit a PreToolUse deny so Claude Code blocks the tool and shows the model
    the reason. The model still holds full context and can act on it."""
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def emit_allow(note=None):
    """Allow (defer). For advisory / allow-with-warning, surface a note on stderr
    so it reaches the transcript without blocking."""
    if note:
        sys.stderr.write("TruVerifAI: " + note + "\n")
    sys.exit(0)
