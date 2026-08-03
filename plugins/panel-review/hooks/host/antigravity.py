"""Google Antigravity host adapter.

Wire contract (antigravity.google/docs/hooks):
- PreToolUse / PostToolUse / PreInvocation / PostInvocation / Stop.
- deny: {"decision": "allow" | "deny" | "ask" | "force_ask", "reason": ...}.
  `ask` IS enforced here (respects cached permissions), so emit_ask keeps it.
- config lives in hooks.json under .agents/ (workspace) or ~/.gemini/config/;
  plugins are drop-in bundles (no CLI install, no marketplace yet).
- no native secrets mechanism: the key comes from TVAI_API_KEY env or
  ~/.truverifai/config.json (the tvai-login path) — plan §3.3.
- tool naming follows the Gemini family (shared lineage); normalization
  mirrors gemini.py with the same fail-open-on-unknown posture.
"""

import json
import sys

from host.base import Host
from host.gemini import GeminiHost


class AntigravityHost(GeminiHost):
    name = "antigravity"

    capabilities = dict(GeminiHost.capabilities, **{
        # Docs sweep 2026-08-02 (antigravity.google/docs/hooks): hooks load
        # ONLY from .agents/hooks.json (workspace) or ~/.gemini/config/
        # hooks.json (user) — plugin-contributed hooks and ${pluginPath} are
        # UNDOCUMENTED, so the drop-in-bundle delivery was stripped; tvai
        # init writes the workspace config.
        "install": "hooks_config_file",
        "supports_ask": True,              # ask/force_ask are documented decisions
        "supports_advisory_context": False,  # PostToolUse output is {} ONLY
        "secrets": "none",                 # config-file / env only
        "stderr_reaches_model": "unknown",
    })

    manifest_paths = ("plugin.json",) + Host.manifest_paths

    def normalize_input(self, raw):
        # Antigravity wraps the tool under toolCall {name, args} (docs
        # verified 2026-08-02) — NOT tool_name/tool_input — and has no
        # top-level cwd: command tools carry it in args (Cwd), else fall
        # back to the first workspacePaths entry.
        out = dict(raw or {})
        tc = out.get("toolCall")
        if isinstance(tc, dict) and not out.get("tool_name"):
            out["tool_name"] = str(tc.get("name") or "")
            args = tc.get("args")
            out["tool_input"] = args if isinstance(args, dict) else {}
        ti = out.get("tool_input") or {}
        if not isinstance(ti, dict):
            ti = {}
        if not out.get("cwd"):
            wp = out.get("workspacePaths")
            cand = ti.get("Cwd") or ti.get("cwd") or \
                (wp[0] if isinstance(wp, list) and wp else None)
            if cand and isinstance(cand, str):
                out["cwd"] = cand
        # The docs' shell-tool example is `run_command` (the gemini-lineage
        # `run_shell_command` is handled by the parent) — cover both, with
        # arg-name aliases since args casing isn't exhaustively documented.
        if str(out.get("tool_name") or "") == "run_command":
            out["tool_name"] = "Bash"
            if "command" not in ti:
                cmd = ti.get("Command") or ti.get("CommandLine") or \
                    ti.get("cmd") or ti.get("commandLine")
                if isinstance(cmd, str):
                    ti = dict(ti)
                    ti["command"] = cmd
            out["tool_input"] = ti
            return out
        return super(AntigravityHost, self).normalize_input(out)

    def emit_deny(self, reason, system_message=None):
        # Schema-exact (docs 2026-08-02): {"decision", "reason"} — the
        # parent's systemMessage rider is a GEMINI-documented field, not an
        # antigravity one; never emit supersets to a host of unknown
        # strictness (playbook rule 5).
        print(json.dumps({"decision": "deny", "reason": reason}))
        sys.exit(0)

    def emit_ask(self, reason, system_message=None):
        print(json.dumps({"decision": "ask", "reason": reason}))
        sys.exit(0)

    def emit_post_advisory(self, message, event_name="PostToolUse"):
        # PostToolUse output is documented as {} ONLY — no context injection
        # (that lives at Pre/PostInvocation). The backstop's model-visible
        # advisory is NOT deliverable here; its dashboard row (posted before
        # this emit) is the value. Emit the documented empty object, and make
        # the constraint load-bearing (audit F-005): the dropped message is
        # surfaced on stderr under TVAI_DEBUG so a future advisory-wiring
        # change can't silently assume delivery.
        try:
            import os as _os
            if message and _os.environ.get("TVAI_DEBUG"):
                sys.stderr.write(
                    "TruVerifAI debug: advisory NOT deliverable on "
                    "antigravity PostToolUse (dashboard-only); dropped: "
                    + message[:120] + "\n")
            print("{}")
            sys.stdout.flush()
        except Exception:
            pass
