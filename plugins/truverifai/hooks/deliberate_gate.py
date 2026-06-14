#!/usr/bin/env python3
"""PreToolUse gate — TruVerifAI deliberate-before-implementing (Layer 1).

Fires before a Write / Edit / MultiEdit. Classifies the content being written;
if it encodes a risky design fork (schema / migration / dependency / auth) in an
area not yet deliberated, it gates (TIERED by default: high-confidence forks
BLOCK and route to `deliberate_coding`; low-confidence ones are ADVISORY). The
mode is configurable (`tiered` | `block` | `advisory`) — the §11.1 demotion flag.

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

    classification = classify_diff(g.synth_write_diff(path, content))
    if not classification["risky"]:
        g.emit_allow()

    cwd = inp.get("cwd") or os.getcwd()
    repo = g.repo_fingerprint(cwd)
    area = os.path.dirname(path) or "repo-root"
    session_id = inp.get("session_id")
    resp = g.check_deliberate_unlock(cfg, repo, area, session_id)
    action, detail = g.deliberate_decision(classification, resp, cfg["deliberate_mode"])

    cats = ", ".join(sorted({h["category"] for h in classification["hunks"]}))
    if action == "deny":
        g.emit_deny(
            f"TruVerifAI gate: this change encodes a design decision ({cats}) worth a "
            "second opinion before you build on it.\n"
            "Call `deliberate_coding` with your question + options_considered, AND pass:\n"
            f'  gate_repo = "{repo}"\n'
            "  gate_diff = the change you're about to write\n"
            f'  gate_session_id = "{session_id or ""}"\n'
            "Then retry the write. (`deliberate_coding` is in your MCP tools.)"
        )
    if action == "advise":
        g.emit_allow(
            f"consider `deliberate_coding` for this {cats} change (advisory — not blocking)."
        )

    g.emit_allow(detail if action == "allow_warn" else None)


if __name__ == "__main__":
    main()
