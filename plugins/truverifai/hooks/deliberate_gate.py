#!/usr/bin/env python3
"""PreToolUse gate — TruVerifAI deliberate-before-implementing (Layer 1).

Fires before a Write / Edit / MultiEdit and routes by confidence:
- HIGH-confidence design fork (schema / migration / dependency / auth / IaC) -> the
  deliberate gate (TIERED default: block + route to `deliberate_coding`; mode
  `tiered` | `block` | `advisory`, the §11.1 demotion flag).
- LOW-confidence borderline change -> the synthesize tier (§6.5), governed by
  `borderline_mode` (`advisory` default | `synthesize_gate` | `off`): a Heavy spike may
  soft-gate to `synthesize_coding` (or a one-line skip); else an advisory nudge.

Fails OPEN on anything; the `recent_pass` escape valve prevents area-misalignment
deadlock. A Write already contains finished code, so this is pre-PERSISTENCE
(not pre-decision) — see v2-hybrid §2.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gate_lib as g
from risk_classifier import classify_diff


def _content_and_path(inp):
    ti = inp.get("tool_input") or {}
    tool = inp.get("tool_name")
    path = ti.get("file_path") or ti.get("path") or ""
    if tool == "Write":
        return path, ti.get("content", "") or ""
    if tool == "Edit":
        return path, ti.get("new_string", "") or ""
    if tool == "MultiEdit":
        edits = ti.get("edits") or []
        return path, "\n".join((e.get("new_string", "") or "") for e in edits)
    return path, ""


def main():
    cfg = g.config()
    if not cfg["enabled"] or not cfg["token"]:
        g.emit_allow()

    inp = g.read_hook_input()
    if inp.get("tool_name") not in ("Write", "Edit", "MultiEdit"):
        g.emit_allow()

    path, content = _content_and_path(inp)
    if not content.strip():
        g.emit_allow()

    classification = classify_diff(
        g.synth_write_diff(path, content), trigger_threshold=g.effective_threshold(cfg))
    # Gate self-mutation (§6.1, audit F-005): writing the gate's own config/hooks is
    # privilege escalation — ALWAYS require a review (force_risky) even if the content
    # classifier finds nothing, but route it through the SAME release path (unlock /
    # recent_pass / fail-open) so the gate's own files stay maintainable via a review —
    # not the old unconditional deny.
    gate_self = g.is_gate_self_mutation(path)
    if not classification["risky"] and not gate_self:
        g.emit_allow()

    cwd = inp.get("cwd") or os.getcwd()
    repo = g.repo_fingerprint(cwd)
    area = os.path.dirname(path) or "repo-root"
    session_id = inp.get("session_id")
    resp = g.check_deliberate_unlock(cfg, repo, area, session_id)

    # Gate-self: always block until reviewed (every mode), releasable via unlock /
    # recent_pass / fail-open. No skip branch — a real deliberation is required.
    if gate_self:
        gs_action, gs_detail = g.deliberate_decision(
            classification, resp, cfg["deliberate_mode"], force_risky=True)
        if gs_action == "deny":
            g.emit_deny(
                "TruVerifAI gate: this write modifies the gate's own config/hooks "
                "(risk_signals.json / risk_classifier.py / gate_lib.py / hooks.json / "
                ".claude-plugin) — privilege-escalation risk, so it always needs a review.\n"
                "Call `deliberate_coding` with your question + options_considered, AND pass:\n"
                f'  gate_repo = "{repo}"\n'
                "  gate_diff = the change you're about to write\n"
                f'  gate_session_id = "{session_id or ""}"\n'
                "Then retry the write. (Gate-self changes cannot be skipped — a real review is required.)"
            )
        g.emit_allow(gs_detail)  # unlocked / recent_pass / fail-open

    action, detail = g.deliberate_decision(classification, resp, cfg["deliberate_mode"])
    cats = ", ".join(sorted({h["category"] for h in classification["hunks"]}))

    # 1. High-confidence design fork -> the deliberate gate (block in tiered/block mode).
    if action == "deny":
        g.emit_deny(
            f"TruVerifAI gate: this change encodes a design decision ({cats}) worth a "
            "second opinion before you build on it.\n"
            "Call `deliberate_coding` with your question + options_considered, AND pass:\n"
            f'  gate_repo = "{repo}"\n'
            "  gate_diff = the change you're about to write\n"
            f'  gate_session_id = "{session_id or ""}"\n'
            "Then retry the write. (`deliberate_coding` is in your MCP tools.)\n"
            + g.skip_and_signal(classification, audit=False)
        )
    if action == "allow_warn":
        g.emit_allow(detail)  # recent_pass escape valve

    # 2. Low-confidence (borderline) change -> the synthesize tier (§6.5), governed by
    #    borderline_mode. Heavy spikes may soft-gate (synthesize OR a one-line skip);
    #    everything else is an advisory nudge. Never the heavy deliberate block.
    if classification["max_confidence"] == "low":
        # §6.5 throttles: an area already consulted/passed this session, or an event the
        # fractional sampler dropped, degrades a Heavy spike to advisory. The per-session
        # budget cap is the third throttle, applied below only if we're about to deny.
        area_consulted = bool(resp and (resp.get("unlocked") or resp.get("recent_pass")))
        sampled = g.borderline_sampled(cfg["borderline_sampling_rate"])
        b_action, _ = g.borderline_decision(
            classification, cfg["borderline_mode"],
            sampled=sampled, area_consulted=area_consulted)
        if b_action == "deny" and not g.borderline_budget_consume(
                session_id, cfg["borderline_session_budget"]):
            b_action = "advise"  # session synthesize soft-gate budget exhausted
        if b_action == "deny":
            g.emit_deny(
                f"TruVerifAI gate: this {cats} change is borderline-consequential — worth a "
                "fast second opinion before building on it.\n"
                "Call `synthesize_coding` with your question + relevant_code (a ~15-30s check), "
                "OR record a one-line skip with a reason (`record_gate_skip`), AND pass:\n"
                f'  gate_repo = "{repo}"\n'
                f'  gate_session_id = "{session_id or ""}"\n'
                + g.gate_signal_line(classification) + "\n"
                "Then retry. (`synthesize_coding` is in your MCP tools.)"
            )
        if b_action == "advise":
            g.emit_allow(
                f"consider `synthesize_coding` for this {cats} change "
                "(fast second opinion; advisory — not blocking)."
            )
        g.emit_allow()

    # 3. High-confidence but non-blocking (deliberate_mode=advisory) -> deliberate nudge.
    if action == "advise":
        g.emit_allow(
            f"consider `deliberate_coding` for this {cats} change (advisory — not blocking)."
        )

    g.emit_allow()


if __name__ == "__main__":
    main()
