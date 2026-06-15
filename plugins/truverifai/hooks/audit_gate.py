#!/usr/bin/env python3
"""PreToolUse gate — TruVerifAI audit-before-commit (proactive-invocation Layer 1).

Fires before a Bash `git commit` / `git merge`. Classifies the staged diff
LOCALLY; if it has risky hunks not covered by a prior PASS audit, BLOCKS with a
message routing the agent to call `audit_coding` (which records coverage). The
agent keeps full context and acts on it, then retries.

Fails OPEN on anything (not configured, no git, network down, our server down) —
the gate never traps the agent. The `recent_pass` escape valve prevents a
hash-misalignment deadlock.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gate_lib as g
from risk_classifier import classify_diff


def main():
    cfg = g.config()
    if not cfg["enabled"] or not cfg["token"]:
        g.emit_allow()  # not configured → fail open

    inp = g.read_hook_input()
    if inp.get("tool_name") != "Bash":
        g.emit_allow()

    command = (inp.get("tool_input") or {}).get("command", "") or ""
    if not re.search(r"(^|\s)git\s+(commit|merge)\b", command):
        g.emit_allow()  # not a commit/merge

    cwd = inp.get("cwd") or os.getcwd()
    diff = g.staged_diff(cwd)
    if not diff.strip():
        g.emit_allow()  # nothing staged

    # Gate self-mutation (§6.1, audit F-005): a commit that modifies the gate's own
    # config/hooks can disable it from inside — always require a review, regardless of
    # what the content classifier says.
    if g.diff_touches_gate_self(diff):
        g.emit_deny(
            "TruVerifAI gate: this commit modifies the gate's own config/hooks "
            "(risk_signals.json / risk_classifier.py / gate_lib.py / hooks.json / "
            ".claude-plugin) — that can disable the gate from inside.\n"
            "Call `audit_coding` with your proposed_action + relevant_code, AND pass:\n"
            f'  gate_repo = "{g.repo_fingerprint(cwd)}"\n'
            "  gate_diff = the staged diff (run: git diff --staged)\n"
            "then retry the commit."
        )

    classification = classify_diff(diff)
    if not classification["risky"]:
        g.emit_allow()  # trivial change

    repo = g.repo_fingerprint(cwd)
    hashes = [h["content_hash"] for h in classification["hunks"]]
    resp = g.check_audit_coverage(cfg, repo, hashes)
    action, detail = g.audit_decision(classification, resp)

    if action == "deny":
        cats = ", ".join(sorted({h["category"] for h in classification["hunks"]}))
        g.emit_deny(
            f"TruVerifAI gate: this commit touches high-stakes code ({cats}) that "
            "should be audited first.\n"
            "Call `audit_coding` with your proposed_action + relevant_code, AND pass:\n"
            f'  gate_repo = "{repo}"\n'
            "  gate_diff = the staged diff (run: git diff --staged)\n"
            "so TruVerifAI records coverage, then retry the commit. "
            "(`audit_coding` is in your MCP tools.)"
        )

    g.emit_allow(detail if action == "allow_warn" else None)


if __name__ == "__main__":
    main()
