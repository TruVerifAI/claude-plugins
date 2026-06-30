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
    # Robust to git global options (`git -C repo commit`, `git --no-pager commit`,
    # `git -c k=v commit`) — a naive `git\s+commit` regex would miss those and let the
    # commit bypass the gate entirely (audit F-001, 2026-06-17).
    if not g.command_invokes_git(command, ("commit", "merge")):
        g.emit_allow()  # not a commit/merge

    cwd = inp.get("cwd") or os.getcwd()
    session_id = inp.get("session_id")
    diff = g.staged_diff(cwd, command)
    if not diff.strip():
        g.emit_allow()  # nothing staged

    classification = classify_diff(diff, trigger_threshold=g.effective_threshold(cfg))
    gate_self = g.diff_touches_gate_self(diff)
    if not classification["risky"] and not gate_self:
        g.emit_allow()  # trivial, non-gate-self change

    repo = g.repo_fingerprint(cwd)

    # Gate self-mutation (§6.1, audit F-005): a commit that modifies the gate's own
    # config/hooks can disable it from inside — privilege escalation. It releases ONLY
    # on a real audit PASS of THIS exact change (no recent_pass, no skip; Option 4,
    # 2026-06-17). ALL gate-self changes bind to the synthesized self-coverage hash —
    # empty-hunk AND risky-hunk (re-audit F-001): the `gself:` namespace is what the
    # SKIP / recent_pass exclusions key off, so a risky gate-self change must NOT fall back
    # to bare-hex hunk hashes (those would be SKIP-releasable). audit_decision_gate_self
    # ignores recent_pass; the server writes the matching gself hash on a PASS.
    if gate_self:
        # Phase 9 (inc 5): a purely INERT gate-self edit (comment / whitespace only — its code
        # skeleton is empty) to a NON-gate-core file doesn't change enforcement behavior, so
        # release it without forcing a full review. gate-CORE files (the classifier, the decision
        # logic, the hook entrypoints + config, the plugin manifest, the real git hooks) ALWAYS
        # require a review, even for an inert edit (a comment there can be load-bearing). A
        # string-value / code change is NOT inert (diff_is_inert keeps string delimiters).
        if g.diff_is_inert(diff) and not g.diff_touches_gate_core(diff):
            g.emit_allow("trivial gate-self edit (comment/whitespace only, non-core) — released")
        resp = g.check_audit_coverage(cfg, repo, [g.gate_self_coverage_hash(diff)])
        action, detail = g.audit_decision_gate_self(resp)
        if action == "deny":
            g.emit_deny(
                "TruVerifAI flagged a high-risk change for a quick review before it ships — "
                "this commit edits the review gate's own settings (risk_signals.json / "
                "risk_classifier.py / gate_lib.py / hooks.json / .claude-plugin), the "
                "highest-stakes area, so the review can't be skipped.\n"
                "Run `audit_coding` with your proposed_action + relevant_code, AND pass:\n"
                f'  gate_repo = "{repo}"\n'
                "  gate_diff = the staged diff (run: git diff --staged)\n"
                "TruVerifAI records the result and the commit proceeds on retry. "
                "(Gate-self changes need a real audit of THIS change — they can't be "
                "skipped, and an unrelated recent audit won't release them.)"
            )
        g.emit_allow(detail if action == "allow_warn" else None)

    # Non-gate-self risky change: covered / recent_pass escape valve / fail-open. Send the
    # fire-time classifier metadata (+ session_id) so the server can mint a COMPLETE
    # gate-fire context (Step 0, design §2.2) and return its gate_context_id — the
    # preferred skip handle surfaced by skip_and_signal below.
    hashes = [h["content_hash"] for h in classification["hunks"]]
    resp = g.check_audit_coverage(cfg, repo, hashes,
                                  classification=classification, session_id=session_id)
    action, detail = g.audit_decision(classification, resp, force_risky=False)
    if action == "deny":
        cats = ", ".join(sorted({h["category"] for h in classification["hunks"]})) or "high-stakes code"
        # §4.E human override (Phase 4 Increment 1): a floor-class hunk uncovered AND the
        # review tool in a SUSTAINED outage (both server-asserted on `resp`) → no agent
        # self-release; route to a FAST, agent-inaccessible HUMAN via permissionDecision
        # "ask". maybe_human_override EXITS the process on the ask; otherwise it RETURNS and
        # the normal deny below runs. Fails open by construction (None `resp` → our
        # gate-server down → returns → normal deny) and robust (any internal failure → returns
        # → normal deny, never crashes / never auto-allows). Debounced per repo+hunkset.
        g.maybe_human_override(cfg, classification, resp, session_id, repo)
        gcid = (resp or {}).get("gate_context_id")
        # Phase 9: pass the gate_context_id to audit_coding so coverage binds to the gate's OWN
        # recorded hunks — a cosmetically-drifted gate_diff (a smart-quote, an em-dash an LLM
        # courier mangled) then still releases the change instead of silently missing coverage.
        gcid_line = f'  gate_context_id = "{gcid}"  (binds coverage to THIS change)\n' if gcid else ""
        g.emit_deny(
            f"TruVerifAI flagged a potential high-risk change for a quick review before "
            f"it ships — this commit touches {cats}.\n"
            "Run `audit_coding` with your proposed_action + relevant_code, AND pass:\n"
            f'  gate_repo = "{repo}"\n'
            "  gate_diff = the staged diff (run: git diff --staged)\n"
            + gcid_line +
            "TruVerifAI records the result and the commit proceeds on retry. "
            "(`audit_coding` is in your MCP tools.)\n"
            # §4.I diff-delta: re-committing after addressing earlier audit findings only
            # needs the CHANGED code re-audited — a prior audit PASS still covers the hunks
            # you didn't touch, and the two compose. Keeps the mandatory re-review cheap.
            "If this is a re-commit after fixing earlier audit findings, you can scope "
            "`audit_coding` to the changed hunks and any newly affected surrounding code — "
            "your prior PASS still covers the hunks you didn't touch.\n"
            + g.skip_and_signal(classification, audit=True,
                                gate_context_id=(resp or {}).get("gate_context_id"))
        )

    g.emit_allow(detail if action == "allow_warn" else None)


if __name__ == "__main__":
    main()
