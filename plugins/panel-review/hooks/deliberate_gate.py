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

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gate_lib as g
from risk_classifier import classify_diff, is_hard_floor


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

    # Write-gate-deadlock-fix-v2 (Option D): classify a REAL delta (not the all-adds
    # synth_write_diff) so the fire's per-hunk content hashes match what a natural agent
    # gate_diff produces — the root-cause fix for the floor write-gate deadlock.
    classification = classify_diff(
        g.build_change_diff(inp, path, content), trigger_threshold=g.effective_threshold(cfg))
    cwd = inp.get("cwd") or os.getcwd()

    # P6.3 (repo-scope suppression): a write whose target resolves OUTSIDE the working repo
    # or into a temp/scratch dir cannot be committed/merged — it can't SHIP, and the gate's
    # threat model is "review before it ships." So it never gates — EXCEPT a real secret
    # VALUE (auto_trigger -> the hardcoded_secret category), which is a leak regardless of
    # where it is written. Recall-safe by construction (an out-of-repo file has nothing to
    # review-before-merge); the secret carve-out preserves the one location-independent risk.
    # is_out_of_repo_scope fails toward REVIEW (uncertain -> not out-of-scope), so this only
    # suppresses when confident. Checked before gate-self because an out-of-repo path is
    # never a gate-self file (those live in the repo), and before the risky/advisory tiers.
    if (g.is_out_of_repo_scope(path, cwd)
            and "hardcoded_secret" not in (classification.get("risk_categories") or [])):
        g.emit_allow()

    # Gate self-mutation (§6.1, audit F-005): writing the gate's own config/hooks is
    # privilege escalation — ALWAYS require a review even if the content classifier finds
    # nothing. The gate-self branch below releases ONLY on a real PASS of THIS exact change
    # (its synthesized self-coverage hash), never recent_pass / skip / area (Option 4).
    gate_self = g.is_gate_self_mutation(path)
    if not classification["risky"] and not gate_self:
        g.emit_allow()

    repo = g.repo_fingerprint(cwd)
    session_id = inp.get("session_id")

    # Gate self-mutation (§6.1, audit F-005): writing the gate's own config/hooks is
    # privilege escalation. It releases ONLY on a real review (audit/deliberate PASS) of
    # THIS exact write — keyed on the synthesized self-coverage hash of the content being
    # written — never recent_pass, never a skip, never the coarse area-unlock (Option 4,
    # 2026-06-17). The authoritative gate-self control is the commit gate; this is the
    # symmetric pre-write layer. Still fails OPEN on infra error (no deadlock).
    if gate_self:
        write_diff = g.synth_write_diff(path, content)
        # Phase 9 (inc 5): a purely INERT gate-self write (comment/whitespace only) to a
        # NON-gate-core file releases without a review (same rule as the commit gate). gate-CORE
        # always reviews. (For a whole-file Write this rarely fires — the content has code — so
        # it's conservative; it mainly helps a comment-only Edit to a non-core gate-self file.)
        if g.diff_is_inert(write_diff) and not g.diff_touches_gate_core(write_diff):
            g.emit_allow("trivial gate-self edit (comment/whitespace only, non-core) — released")
        self_hash = g.gate_self_coverage_hash(write_diff)
        gs_resp = g.check_audit_coverage(cfg, repo, [self_hash])
        gs_action, gs_detail = g.audit_decision_gate_self(gs_resp)
        if gs_action == "deny":
            g.emit_deny(
                "TruVerifAI flagged a high-risk change for a quick review before it ships — "
                "this write edits the review gate's own settings (risk_signals.json / "
                "risk_classifier.py / gate_lib.py / hooks.json / .claude-plugin), the "
                "highest-stakes area, so the review can't be skipped.\n"
                "Run `deliberate_coding` (or `audit_coding`) with your question + "
                "options_considered, AND pass:\n"
                f'  gate_repo = "{repo}"\n'
                "  gate_diff = a unified diff ADDING the file's new contents "
                "(the change you're about to write)\n"
                f'  gate_session_id = "{session_id or ""}"\n'
                "TruVerifAI records the result and the write proceeds on retry. "
                "(Gate-self changes need a real review of THIS change — they can't be "
                "skipped, and an unrelated recent review won't release them.)"
            )
        g.emit_allow(gs_detail)  # covered / fail-open

    # Non-gate-self design fork: coarse area-unlock (recent_pass escape valve OK). Send the
    # fire-time classifier metadata so the minted gate-fire context is COMPLETE (Step 0), and
    # label it with the write gate's TIER. The two blocking tiers are deliberate (high-
    # confidence fork) and synthesize (low-confidence borderline). We only reach here for a
    # risky non-gate-self change, so max_confidence is "high" or "low" (None means non-risky,
    # which returned earlier); map ONLY those two and omit gate_type otherwise so the server
    # applies its own default rather than a guessed label (audit F-001/F-002, 2026-06-26).
    # Server contract: when gate_type is omitted, /receipts/deliberate-check defaults the
    # minted fire to 'deliberate' (mcp_user_routes.receipts_deliberate_check).
    area = os.path.dirname(path) or "repo-root"
    gate_type = {"high": "deliberate", "low": "synthesize"}.get(
        classification.get("max_confidence"))
    resp = g.check_deliberate_unlock(cfg, repo, area, session_id,
                                     classification=classification, gate_type=gate_type)

    # Write-gate-deadlock fix: a Write/Edit is FINISHED code, so its natural review is `audit`.
    # If the change is already reviewed — an `audit_coding` PASS or a `synthesize_coding`
    # SYNTH_CONFIRM covers every risky hunk (server `covered`, floor-aware) — release NOW, for
    # BOTH the deliberate and the borderline/synthesize tier, before any tier-specific logic.
    # This is the primary fix that removes the deliberate-only deadlock and restores the design
    # invariant "run the review -> release" at the write gate.
    if resp and resp.get("covered"):
        g.emit_allow("change reviewed — audit / SYNTH_CONFIRM covers every risky hunk")

    action, detail = g.deliberate_decision(classification, resp, cfg["deliberate_mode"])
    cats = ", ".join(sorted({h["category"] for h in classification["hunks"]}))

    # 1. High-confidence change -> block in tiered/block mode. This is FINISHED code, so the
    #    natural review is `audit_coding`; `synthesize_coding` (SYNTH_CONFIRM) also releases a
    #    low-risk floor; `deliberate_coding` is accepted for a still-open design. All three write
    #    a receipt the server now reads at the write gate (covered / unlocked).
    if action == "deny":
        gcid = (resp or {}).get("gate_context_id")
        gcid_line = ("  gate_context_id = %s\n" % json.dumps(gcid)) if gcid else ""
        # Write-gate-deadlock-fix-v2: FLOOR-aware release paths. A floor hunk is released ONLY by a
        # diff-level review (audit PASS or a synthesize SYNTH_CONFIRM) — a `deliberate` area-unlock
        # can't cover a floor hunk (server F-001/F-006), so the floor message does NOT offer it.
        # It forwards the fire's floor hunk hashes as `target_hunk_hashes` (Option B) so coverage
        # binds deterministically even if the write gate's diff shape differs from the agent's.
        floor_hashes = [h["content_hash"] for h in classification.get("hunks", [])
                        if h.get("content_hash") and is_hard_floor(h.get("category"))]
        if floor_hashes:
            hh_line = "  target_hunk_hashes = %s\n" % json.dumps(floor_hashes)
            g.emit_deny(
                f"TruVerifAI flagged a {cats} change (a floor class: auth / secrets / money / "
                "migration / removed-guard). Run a quick review to release the gate — either:\n"
                "  • `audit_coding` — a PASS releases it, or\n"
                "  • `synthesize_coding` — a passing SYNTH_CONFIRM releases it (a fast ~15-30s check).\n"
                "Pass to whichever you run:\n"
                f'  gate_repo = "{repo}"\n'
                "  gate_diff = the change you're about to write\n"
                f'  gate_session_id = "{session_id or ""}"\n'
                + gcid_line
                + hh_line +
                "Copy the `target_hunk_hashes` line above verbatim — it binds the review to this "
                "change so the write proceeds on retry.\n"
                + g.gate_signal_line(classification)
            )
        g.emit_deny(
            f"TruVerifAI flagged a {cats} change worth a review before it ships.\n"
            "This is finished code, so the natural review is `audit_coding` — run it with your "
            "proposed_action, AND pass:\n"
            f'  gate_repo = "{repo}"\n'
            "  gate_diff = the change you're about to write\n"
            f'  gate_session_id = "{session_id or ""}"\n'
            + gcid_line +
            "A PASS releases the gate. `deliberate_coding` is accepted if the design is still open "
            "(no concrete diff); `synthesize_coding` is a fast second opinion. You may also record a "
            "one-line skip with a reason (`record_gate_skip`). Passing gate_context_id binds "
            "coverage to the gate's own hunks, so a cosmetically-drifted diff still releases.\n"
            + g.skip_and_signal(classification, audit=False, area=area,
                                gate_context_id=gcid)
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
            # PREFERRED handle (Step 0): the server-issued gate-fire id, when present. The
            # area line stays for the backward-compat window (an old server returns no id).
            gcid = (resp or {}).get("gate_context_id")
            gcid_line = ("  gate_context_id = %s\n" % json.dumps(gcid)) if gcid else ""
            g.emit_deny(
                f"TruVerifAI flagged a borderline-consequential {cats} change — worth a "
                "fast second opinion before building on it.\n"
                "Run `synthesize_coding` (a ~15-30s second opinion; on a FLOOR-class change a "
                "passing SYNTH_CONFIRM releases the gate), OR `audit_coding` (a PASS releases any "
                "change), OR record a one-line skip with a reason (`record_gate_skip`), AND pass:\n"
                f'  gate_repo = "{repo}"\n'
                "  gate_diff = the change you're about to write\n"
                f'  gate_session_id = "{session_id or ""}"\n'
                + gcid_line
                # The synthesize soft-gate releases on an AREA skip (the write-gate key);
                # without this line a `record_gate_skip` here fails server validation
                # (no gate context) and the borderline skip is unusable (2026-06-19 fix).
                # json.dumps so a quote/backslash in the path can't malform the copy key.
                + f"  area = {json.dumps(area)}\n"
                + g.gate_signal_line(classification) + "\n"
                "Then retry. (Both tools are in your MCP tools; passing gate_context_id binds "
                "coverage to the gate's own hunks.)"
            )
        if b_action == "advise":
            # Option B (2026-06-19): make the nudge MODEL-visible so synthesize can
            # actually get called — but only for a Borderline-HEAVY spike, once per area
            # per session, and not if the area was already consulted. Borderline is the
            # high-volume band, so an unthrottled per-write nudge would train the model to
            # dismiss it (deliberate_coding mcp_f044c940, 0.88). Scoped to borderline_mode
            # == 'advisory' (the default): in synthesize_gate mode 'advise' means the
            # soft-gate DEGRADED (not sampled / budget spent / area consulted), where a
            # "worth calling synthesize" nudge would be misleading — that path keeps the
            # old stderr note. Lite / repeat / consulted changes also keep the stderr note.
            if (cfg["borderline_mode"] == "advisory"
                    and classification.get("borderline_tier") == "heavy"
                    and not area_consulted
                    and not g.area_advisory_seen(session_id, area)):
                # Order matters: mark + log BEFORE emit (emit_allow_advisory calls
                # sys.exit, so anything after it is unreachable). Marking first makes the
                # advisory genuinely once-per-area even though the emit exits.
                g.mark_area_advisory_seen(session_id, area)
                g.log_advisory_shown(session_id, area, classification.get("risk_categories"))
                g.emit_allow_advisory(
                    f"`synthesize_coding` can give a fast, independent multi-model read on "
                    f"this {cats} change — worth calling if you're unsure it's correct "
                    "before building on it. Optional; it won't block you."
                )  # exits; the emit_allow below is the fall-through for every other case
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
